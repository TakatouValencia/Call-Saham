import asyncio
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
from config import config
from models.signal import StockSignal
from services.ai_analyzer import ai_analyzer
from services.notifier import notifier
from utils.logger import setup_logger

logger = setup_logger("MarketScanner")

WIB = timezone(timedelta(hours=7))

# Watchlist Saham Aktif IHSG (Bluechip & Second-Liner/Gorengan Akumulasi)
DEFAULT_WATCHLIST = [
    "BBRI.JK", "BBCA.JK", "BMRI.JK", "BBNI.JK",
    "BRMS.JK", "BUMI.JK", "DEWA.JK", "PTRO.JK",
    "WIFI.JK", "PSAB.JK", "ENRG.JK", "ANTM.JK",
    "ASII.JK", "DOID.JK", "KIJA.JK"
]

class MarketScannerService:
    def __init__(self):
        self.watchlist = DEFAULT_WATCHLIST
        # Cache deduplikasi untuk mencegah spam sinyal berulang dalam rentang 18 jam
        self.last_called: Dict[str, datetime] = {}
        self.cooldown_hours = 18

    def is_idx_market_open(self) -> tuple[bool, str]:
        """
        Mengecek apakah saat ini bursa saham IDX sedang buka (WIB / UTC+7).
        Jadwal Perdagangan IDX:
        - Senin - Kamis: Sesi 1 (09:00 - 12:00 WIB), Sesi 2 (13:30 - 16:00 WIB)
        - Jumat: Sesi 1 (09:00 - 11:30 WIB), Sesi 2 (14:00 - 16:00 WIB)
        - Sabtu & Minggu: Libur / Tutup
        """
        now_wib = datetime.now(WIB)
        weekday = now_wib.weekday() # 0 = Senin, 4 = Jumat, 5 = Sabtu, 6 = Minggu
        cur_time = now_wib.time()

        if weekday >= 5:
            # Hitung mundur ke hari Senin 09:00 WIB
            days_ahead = 7 - weekday
            next_open = (now_wib + timedelta(days=days_ahead)).replace(hour=9, minute=0, second=0)
            return False, f"Market Tutup (Weekend). Buka kembali Senin, {next_open.strftime('%d %b %Y 09:00')} WIB"

        # Hari Kerja (Senin - Kamis)
        if weekday < 4:
            s1_open = (cur_time >= datetime.strptime("09:00", "%H:%M").time()) and (cur_time <= datetime.strptime("12:00", "%H:%M").time())
            s2_open = (cur_time >= datetime.strptime("13:30", "%H:%M").time()) and (cur_time <= datetime.strptime("16:00", "%H:%M").time())
            if s1_open: return True, "Sesi 1 Perdagangan Aktif"
            if s2_open: return True, "Sesi 2 Perdagangan Aktif"
            return False, "Market Tutup / Istirahat Sesi"

        # Khusus Jumat
        s1_fri = (cur_time >= datetime.strptime("09:00", "%H:%M").time()) and (cur_time <= datetime.strptime("11:30", "%H:%M").time())
        s2_fri = (cur_time >= datetime.strptime("14:00", "%H:%M").time()) and (cur_time <= datetime.strptime("16:00", "%H:%M").time())
        if s1_fri: return True, "Sesi 1 Jumat Aktif"
        if s2_fri: return True, "Sesi 2 Jumat Aktif"
        if cur_time < datetime.strptime("09:00", "%H:%M").time():
            return False, "Market Belum Buka. Buka pukul 09:00 WIB"
        if cur_time > datetime.strptime("16:00", "%H:%M").time():
            return False, "Market Tutup (Sesi Jumat Selesai). Buka kembali Senin pukul 09:00 WIB"
        return False, "Market Istirahat Sholat Jumat (11:30 - 14:00 WIB)"

    def is_in_cooldown(self, ticker: str) -> bool:
        """Mencegah spam sinyal pada saham yang sama dalam 18 jam terakhir."""
        if ticker not in self.last_called:
            return False
        elapsed = datetime.now(WIB) - self.last_called[ticker]
        return elapsed < timedelta(hours=self.cooldown_hours)

    def scan_ticker_technical(self, ticker: str) -> Optional[dict]:
        """
        Menganalisis indikator Volume Anomali, Akumulasi Bandar, dan Breakout pada data terbaru.
        """
        try:
            t = yf.Ticker(ticker)
            # Ambil data 5 hari dengan interval 15m untuk respons cepat saat market buka
            df = t.history(period="5d", interval="15m")
            if df is None or df.empty or len(df) < 20:
                return None

            closes = df['Close'].values
            opens = df['Open'].values
            volumes = df['Volume'].values
            highs = df['High'].values
            lows = df['Low'].values

            # Volume metrics
            vol_s = pd.Series(volumes)
            vol_ma20 = vol_s.rolling(20).mean().values
            cur_vol = volumes[-1]
            cur_ma = vol_ma20[-1] if not np.isnan(vol_ma20[-1]) and vol_ma20[-1] > 0 else 1
            rvol = cur_vol / cur_ma

            # Price trend
            closes_s = pd.Series(closes)
            ema20 = closes_s.ewm(span=20, adjust=False).mean().values[-1]
            cur_close = float(closes[-1])
            cur_open = float(opens[-1])

            # Cek Akumulasi / Breakout
            # 1. Volume spike >= 2.0x rata-rata
            # 2. Bullish candle (Close > Open)
            # 3. Berada di atas EMA20
            is_bullish = cur_close > cur_open
            is_vol_spike = rvol >= 1.8 and cur_vol >= 100_000
            is_above_ema = cur_close >= ema20

            if is_bullish and is_vol_spike and is_above_ema:
                clean_ticker = ticker.replace(".JK", "")
                
                # Rule Target Profit: Pastikan selalu 20%
                tp_target = round(cur_close * 1.20, 1)
                
                # Stop Loss terukur: swing low 5 candle terakhir atau max -5%
                recent_low = float(np.min(lows[-5:]))
                sl_price = round(max(recent_low, cur_close * 0.95), 1)
                if sl_price >= cur_close:
                    sl_price = round(cur_close * 0.95, 1)

                risk = cur_close - sl_price
                rrr_val = round((tp_target - cur_close) / (risk + 1e-9), 1)

                return {
                    "ticker": clean_ticker,
                    "entry": cur_close,
                    "sl": sl_price,
                    "tp": tp_target,
                    "rvol": round(rvol, 1),
                    "rrr": f"1:{rrr_val}"
                }
        except Exception as e:
            logger.debug(f"Scan error {ticker}: {e}")
            return None
        return None

    async def run_scan_cycle(self):
        """Menjalankan satu siklus pemindaian pada seluruh watchlist."""
        logger.info(f"🔍 Memulai pemindaian otomatis ({len(self.watchlist)} saham)...")
        candidates = []

        # Jalankan pengambilan data secara non-blocking
        loop = asyncio.get_running_loop()
        for ticker in self.watchlist:
            clean_t = ticker.replace(".JK", "")
            if self.is_in_cooldown(clean_t):
                continue

            setup = await loop.run_in_executor(None, self.scan_ticker_technical, ticker)
            if setup:
                candidates.append(setup)

        logger.info(f"📊 Pemindaian selesai: Terdeteksi {len(candidates)} saham dengan akumulasi volume.")

        for c in candidates:
            ticker = c["ticker"]
            raw_text = (
                f"🚨 SIGNAL CALL OTOMATIS: ${ticker}\n"
                f"Action: BUY ON ACCUMULATION\n"
                f"Entry Area: {c['entry']}\n"
                f"Target Profit: {c['tp']} (+20.0% Swing Target)\n"
                f"Stop Loss: {c['sl']}\n"
                f"Risk to Reward: {c['rrr']}\n"
                f"Setup: Terdeteksi volume anomali {c['rvol']}x rata-rata dengan tekanan akumulasi bandar di atas EMA20. "
                f"Target swing 20% tanpa batas waktu."
            )

            # Analisis via AI untuk format terstruktur
            signal = await ai_analyzer.analyze_message(raw_text)
            if signal and signal.is_valid_signal:
                # Tandai cache cooldown
                self.last_called[ticker] = datetime.now(WIB)
                # Broadcast sinyal
                await notifier.broadcast_signal(signal, source="Autonomous Market Scanner")
                await asyncio.sleep(2) # Hindari rate limit Discord

async def start_autonomous_scanner():
    """Loop background mandiri yang memantau jam bursa tanpa henti."""
    if not config.AUTO_SCANNER_ENABLE:
        logger.info("Autonomous Market Scanner dinonaktifkan di konfigurasi.")
        return

    scanner = MarketScannerService()
    interval_sec = config.SCANNER_INTERVAL_MINUTES * 60

    logger.info("⚡ AUTONOMOUS MARKET SCANNER SIAP BEROPERASI")
    logger.info("📅 Bot akan otomatis aktif setiap Senin - Jumat pukul 09:00 - 16:00 WIB.")

    while True:
        try:
            is_open, status_msg = scanner.is_idx_market_open()

            if is_open:
                logger.info(f"🟢 Jam Bursa IDX Aktif ({status_msg}). Menjalankan scanner...")
                await scanner.run_scan_cycle()
                # Tunggu interval berikutnya (misal: 30 menit)
                await asyncio.sleep(interval_sec)
            else:
                logger.info(f"⏸️ Status Bursa: {status_msg}. Mode siaga (standby)...")
                # Jika market tutup/weekend, cek kembali setiap 15 menit
                await asyncio.sleep(900)

        except asyncio.CancelledError:
            logger.info("Market Scanner dihentikan.")
            break
        except Exception as e:
            logger.error(f"Error tak terduga pada Market Scanner: {e}", exc_info=True)
            # Jaga agar loop tidak mati, jeda 60 detik lalu coba lagi
            await asyncio.sleep(60)

market_scanner = MarketScannerService()
