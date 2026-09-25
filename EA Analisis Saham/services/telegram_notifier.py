import aiohttp
from datetime import datetime
from typing import Optional
from models.signal import StockSignal
from config import config
from utils.logger import setup_logger

logger = setup_logger("TelegramNotifier")

class TelegramNotifierService:
    def __init__(self):
        self.bot_token = config.TELEGRAM_BOT_TOKEN
        self.chat_id = config.TELEGRAM_CHAT_ID
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"

    def format_signal_message(self, signal: StockSignal, source: str = "Discord Alert") -> str:
        """
        Memformat StockSignal menjadi pesan Telegram dengan HTML styling yang rapi dan elegan.
        """
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Action Badge
        if signal.action == "BUY":
            action_badge = "🟢 <b>BUY / AKUMULASI</b>"
        elif signal.action == "SELL":
            action_badge = "🔴 <b>SELL / PROFIT TAKING</b>"
        else:
            action_badge = "🟡 <b>WAIT & SEE</b>"

        # Risk Badge
        if signal.is_high_risk:
            risk_badge = f"🚨 <b>RISIKO TINGGI</b>\n<i>⚠️ {signal.risk_notes}</i>"
        else:
            risk_badge = "✅ <b>RISIKO TERUKUR / NORMAL</b>"

        # Take Profit list formatting
        if signal.take_profit:
            tp_text = " | ".join([f"TP{i+1}: <code>{tp}</code>" for i, tp in enumerate(signal.take_profit)])
        else:
            tp_text = "<i>Menyesuaikan Trailing Stop</i>"

        sl_text = f"<code>{signal.stop_loss}</code>" if signal.stop_loss else "<i>❌ Tidak Ditentukan</i>"
        entry_text = f"<code>{signal.entry_price}</code>" if signal.entry_price else "<i>Market Order</i>"
        rrr_text = f"<code>{signal.risk_reward_ratio}</code>" if signal.risk_reward_ratio else "<i>N/A</i>"

        # Confidence Stars
        confidence_map = {
            "HIGH": "⭐⭐⭐ HIGH",
            "MEDIUM": "⭐⭐ MEDIUM",
            "LOW": "⭐ LOW"
        }
        confidence_text = confidence_map.get(signal.confidence.upper(), signal.confidence)

        message = (
            f"⚡ <b>[CALL EANOVAIRE] AI STOCK SIGNAL</b> ⚡\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 <b>Emiten/Ticker :</b> <code>#{signal.ticker}</code>\n"
            f"🎯 <b>Rekomendasi   :</b> {action_badge}\n"
            f"⏳ <b>Timeframe     :</b> {signal.timeframe}\n"
            f"⭐ <b>Keyakinan AI  :</b> {confidence_text}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💵 <b>Area Beli (Entry) :</b> {entry_text}\n"
            f"🎯 <b>Target Profit     :</b> {tp_text}\n"
            f"🛑 <b>Stop Loss (SL)    :</b> {sl_text}\n"
            f"⚖️ <b>Risk/Reward Ratio :</b> {rrr_text}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🛡️ <b>Status Risiko :</b>\n{risk_badge}\n\n"
            f"📝 <b>Analisa & Alasan :</b>\n"
            f"<i>{signal.summary or 'Setup breakout / momentum trading.'}</i>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📡 <i>Sumber: {source} | 🕒 {now_str} WIB</i>\n"
            f"⚠️ <i>Disclaimer: Analisa dihasilkan otomatis oleh AI. Selalu terapkan Money Management (DYOR).</i>"
        )
        return message

    async def send_signal(self, signal: StockSignal, source: str = "Discord") -> bool:
        """
        Mengirim notifikasi sinyal ke Telegram via async HTTP POST.
        """
        if not self.bot_token or not self.chat_id:
            logger.warning("Token Telegram atau Chat ID belum dikonfigurasi. Notifikasi dilewati.")
            return False

        text = self.format_signal_message(signal, source=source)
        endpoint = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(endpoint, json=payload, timeout=10) as resp:
                    if resp.status == 200:
                        logger.info(f"✅ Sinyal #{signal.ticker} berhasil dikirim ke Telegram Chat ID: {self.chat_id}")
                        return True
                    else:
                        resp_text = await resp.text()
                        logger.error(f"❌ Gagal mengirim ke Telegram (Status {resp.status}): {resp_text}")
                        return False
        except aiohttp.ClientError as ce:
            logger.error(f"Koneksi jaringan error saat kirim ke Telegram: {ce}")
            return False
        except Exception as e:
            logger.error(f"Error tak terduga saat kirim notifikasi Telegram: {e}")
            return False

    async def send_raw_text(self, text: str) -> bool:
        """Mengirim pesan teks bebas (misal: alert sistem atau status online)."""
        if not self.bot_token or not self.chat_id:
            return False

        endpoint = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML"
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(endpoint, json=payload, timeout=10) as resp:
                    return resp.status == 200
        except Exception as e:
            logger.error(f"Error send_raw_text: {e}")
            return False

telegram_notifier = TelegramNotifierService()
