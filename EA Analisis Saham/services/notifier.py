import asyncio
from models.signal import StockSignal
from services.telegram_notifier import telegram_notifier
from services.discord_webhook_notifier import discord_webhook_notifier
from utils.logger import setup_logger

logger = setup_logger("SignalNotifier")

class UnifiedSignalNotifier:
    """
    Dispatcher terpadu untuk mendistribusikan sinyal ke:
    1. Telegram Bot / Channel
    2. Discord Webhook (Channel Notifikasi)
    """
    async def broadcast_signal(self, signal: StockSignal, source: str = "Call EANovaire") -> bool:
        tasks = []
        
        # 1. Kirim ke Telegram jika dikonfigurasi
        tasks.append(telegram_notifier.send_signal(signal, source=source))
        
        # 2. Kirim ke Discord Webhook jika dikonfigurasi
        tasks.append(discord_webhook_notifier.send_signal(signal, source=source))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Cek apakah setidaknya ada salah satu yang sukses
        success = any(res is True for res in results if not isinstance(res, Exception))
        return success

    async def broadcast_raw_text(self, text: str) -> bool:
        tasks = [
            telegram_notifier.send_raw_text(text),
            discord_webhook_notifier.send_raw_text(text)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return any(res is True for res in results if not isinstance(res, Exception))

notifier = UnifiedSignalNotifier()
