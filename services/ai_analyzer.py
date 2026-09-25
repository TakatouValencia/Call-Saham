import json
import re
from typing import Optional
from models.signal import StockSignal
from config import config
from utils.logger import setup_logger

logger = setup_logger("AIAnalyzer")

SYSTEM_INSTRUCTION = """Anda adalah Financial Market AI Parser spesialis sinyal trading saham.
Tugas Anda adalah membaca pesan alert mentah dari grup Discord / Website dan mengekstrak sinyal trading menjadi format JSON terstruktur.

Aturan Pemrosesan:
1. "is_valid_signal": true jika pesan mengandung sinyal trading saham aktif yang jelas, false jika obrolan santai, spam, atau berita tanpa instruksi trading.
2. Identifikasi Ticker saham dengan tepat (format kode huruf kapital tanpa simbol, misal: BBRI, ASII, TSLA, BBCA).
3. Tentukan Aksi: "BUY", "SELL", "HOLD", atau "INVALID" jika pesan bukan sinyal trading.
4. Ekstrak Entry Price (bisa range atau single number, simpan di field "entry"), Take Profit (array take_profit, bisa TP1, TP2), dan Stop Loss (field "stop_loss", null jika tidak disebutkan).
5. Hitung atau cantumkan Risk to Reward Ratio jika data harga tersedia (contoh: "1:2", "1:1.5").
6. Tentukan timeframe trading (contoh: "Swing / Day Trading", "Scalping").
7. Berikan tingkat keyakinan sinyal ("HIGH", "MEDIUM", "LOW").
8. Berikan ringkasan alasan/setup teknikal di "summary" (contoh: "Breakout", "Rebound Support", "Volume Spike").
9. Abaikan pesan spam, obrolan santai, atau sinyal yang sudah expired/basi.

Format output HARUS selalu berupa JSON valid tanpa teks pengantar atau markdown apapun:
{
  "is_valid_signal": true,
  "ticker": "BBCA",
  "action": "BUY",
  "entry": "9800 - 9900",
  "take_profit": ["10200", "10500"],
  "stop_loss": "9650",
  "risk_reward_ratio": "1:2",
  "timeframe": "Swing / Day Trading",
  "confidence": "HIGH",
  "summary": "Rebound dari MA50 didukung akumulasi volume besar."
}
"""

class AIAnalyzerService:
    def __init__(self):
        self.provider = config.AI_PROVIDER
        self.gemini_client = None
        self.openai_client = None

        if self.provider == "gemini":
            try:
                from google import genai
                self.gemini_client = genai.Client(api_key=config.GEMINI_API_KEY)
                logger.info(f"Gemini AI Client terinisialisasi (Model: {config.GEMINI_MODEL}).")
            except ImportError:
                import google.generativeai as legacy_genai
                legacy_genai.configure(api_key=config.GEMINI_API_KEY)
                self.gemini_client = legacy_genai.GenerativeModel(
                    model_name=config.GEMINI_MODEL,
                    system_instruction=SYSTEM_INSTRUCTION
                )
                logger.info(f"Legacy Gemini Client terinisialisasi (Model: {config.GEMINI_MODEL}).")
            except Exception as e:
                logger.error(f"Gagal inisialisasi Gemini: {e}")

        elif self.provider == "openai":
            try:
                from openai import AsyncOpenAI
                self.openai_client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)
                logger.info(f"OpenAI Client terinisialisasi (Model: {config.OPENAI_MODEL}).")
            except Exception as e:
                logger.error(f"Gagal inisialisasi OpenAI: {e}")

    def quick_prefilter(self, text: str) -> bool:
        """
        Penyaring awal (Regex & Keywords):
        Mencegah panggilan API LLM yang boros untuk pesan obrolan biasa (seperti 'pagi', 'halo', dsb).
        """
        if not text or len(text.strip()) < 5:
            return False

        keywords = [
            "buy", "sell", "beli", "jual", "entry", "sl", "tp", "target", "stoploss",
            "take profit", "stop loss", "swing", "scalp", "breakout", "accumulate",
            "speculative", "rebound", "haka", "antri"
        ]
        text_lower = text.lower()
        return any(kw in text_lower for kw in keywords)

    def evaluate_risk(self, signal: StockSignal) -> StockSignal:
        """
        Filter Rule Khusus:
        Tandai sebagai sinyal berisiko tinggi jika Stop Loss tidak ada / tidak jelas
        atau Risk to Reward Ratio (RRR) < 1:1.5.
        """
        high_risk_reasons = []

        # 1. Cek Stop Loss
        if not signal.stop_loss or signal.stop_loss.strip().lower() in ("none", "null", "-", "tidak ada"):
            signal.is_high_risk = True
            high_risk_reasons.append("Stop Loss tidak ditentukan/tidak jelas")

        # 2. Cek Risk to Reward Ratio
        if signal.risk_reward_ratio:
            try:
                # Cari pola angka 1:X
                match = re.search(r"1\s*:\s*([\d\.]+)", signal.risk_reward_ratio)
                if match:
                    reward_multiplier = float(match.group(1))
                    if reward_multiplier < 1.5:
                        signal.is_high_risk = True
                        high_risk_reasons.append(f"RRR rendah ({signal.risk_reward_ratio} < 1:1.5)")
            except Exception as err:
                logger.debug(f"Gagal parse RRR '{signal.risk_reward_ratio}': {err}")

        # 3. Cek Confidence
        if signal.confidence == "LOW":
            signal.is_high_risk = True
            high_risk_reasons.append("Keyakinan teknikal AI rendah (LOW)")

        if high_risk_reasons:
            signal.is_high_risk = True
            signal.risk_notes = " | ".join(high_risk_reasons)
        else:
            signal.is_high_risk = False
            signal.risk_notes = "Parameter risiko lengkap & terukur (RRR >= 1:1.5)"

        return signal

    async def analyze_message(self, raw_message: str) -> Optional[StockSignal]:
        """
        Mengirim pesan ke AI untuk diekstrak menjadi StockSignal terstruktur.
        """
        if not self.quick_prefilter(raw_message):
            logger.debug("Pesan diabaikan oleh pre-filter (bukan sinyal trading).")
            return None

        prompt = f"Ekstrak sinyal saham dari pesan berikut ke format JSON:\n\n{raw_message}"

        raw_json_str = ""
        try:
            if self.provider == "gemini":
                raw_json_str = await self._call_gemini(prompt)
            elif self.provider == "openai":
                raw_json_str = await self._call_openai(prompt)
            else:
                logger.error(f"Provider AI '{self.provider}' tidak dikenali.")
                return None

            # Bersihkan markdown formatting jika LLM membungkus dengan ```json ... ```
            cleaned_json = self._clean_json_output(raw_json_str)
            data = json.loads(cleaned_json)

            signal = StockSignal(**data)
            if not signal.is_valid_signal or signal.action == "INVALID":
                logger.info("AI menentukan bahwa pesan ini bukan sinyal saham valid.")
                return None

            # Terapkan evaluasi risiko
            signal = self.evaluate_risk(signal)
            logger.info(f"Sinyal valid terdeteksi: {signal.ticker} [{signal.action}] (High Risk: {signal.is_high_risk})")
            return signal

        except json.JSONDecodeError as jde:
            logger.error(f"Gagal decode JSON dari respons AI: {jde}\nOutput mentah: {raw_json_str}")
            return None
        except Exception as e:
            logger.error(f"Error saat memproses sinyal dengan AI: {e}", exc_info=True)
            return None

    def _clean_json_output(self, text: str) -> str:
        """Menghapus formatting markdown dari output LLM."""
        text = text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        return text

    async def _call_gemini(self, prompt: str) -> str:
        """Panggilan async ke Gemini API dengan dukungan fallback model otomatis."""
        import asyncio
        import warnings
        loop = asyncio.get_running_loop()

        # Daftar model yang dicoba secara berurutan
        candidate_models = [config.GEMINI_MODEL, "gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.8-flash"]
        # Hilangkan duplikat sambil mempertahankan urutan
        models_to_try = list(dict.fromkeys(candidate_models))

        def _sync_gemini_call():
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore")

                # Jika menggunakan library google-genai terbaru
                if hasattr(self.gemini_client, "models"):
                    from google.genai import types
                    cfg = types.GenerateContentConfig(
                        system_instruction=SYSTEM_INSTRUCTION,
                        response_mime_type="application/json",
                        temperature=0.1
                    )
                    last_err = None
                    for model_name in models_to_try:
                        try:
                            response = self.gemini_client.models.generate_content(
                                model=model_name,
                                contents=prompt,
                                config=cfg
                            )
                            return response.text
                        except Exception as e:
                            last_err = e
                            logger.warning(f"Percobaan model Gemini '{model_name}' gagal: {e}. Mencoba model alternatif...")
                    raise last_err
                # Jika menggunakan legacy google.generativeai
                else:
                    response = self.gemini_client.generate_content(prompt)
                    return response.text

        return await loop.run_in_executor(None, _sync_gemini_call)

    async def _call_openai(self, prompt: str) -> str:
        """Panggilan async ke OpenAI API."""
        response = await self.openai_client.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_INSTRUCTION},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            response_format={"type": "json_object"}
        )
        return response.choices[0].message.content

ai_analyzer = AIAnalyzerService()
