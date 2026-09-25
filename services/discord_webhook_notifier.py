import aiohttp
from datetime import datetime
from typing import Optional
from models.signal import StockSignal
from config import config
from utils.logger import setup_logger

logger = setup_logger("DiscordWebhookNotifier")

class DiscordWebhookNotifierService:
    def __init__(self):
        self.webhook_url = config.DISCORD_WEBHOOK_URL

    def build_embed(self, signal: StockSignal, source: str = "Call EANovaire") -> dict:
        """
        Membangun Discord Rich Embed JSON yang menarik dan rapi.
        """
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Color coding: Green for BUY, Red for SELL, Orange for High Risk
        if signal.is_high_risk:
            embed_color = 0xFFAA00  # Orange / Warning
        elif signal.action == "BUY":
            embed_color = 0x00E676  # Vibrant Green
        elif signal.action == "SELL":
            embed_color = 0xFF1744  # Vibrant Red
        else:
            embed_color = 0x9E9E9E  # Grey

        # Action Badge
        action_map = {
            "BUY": "🟢 BUY / AKUMULASI",
            "SELL": "🔴 SELL / PROFIT TAKING",
            "WAIT": "🟡 WAIT & SEE"
        }
        action_str = action_map.get(signal.action, signal.action)

        # TP formatting
        tp_text = " | ".join([f"TP{i+1}: **{tp}**" for i, tp in enumerate(signal.take_profit)]) if signal.take_profit else "Trailing Stop"

        # Risk Status
        if signal.is_high_risk:
            risk_text = f"🚨 **RISIKO TINGGI**\n*{signal.risk_notes}*"
        else:
            risk_text = f"✅ **RISIKO TERUKUR / NORMAL**\n*{signal.risk_notes or 'SL & RRR valid'}*"

        fields = [
            {"name": "📌 Emiten", "value": f"**${signal.ticker}**", "inline": True},
            {"name": "🎯 Rekomendasi", "value": f"**{action_str}**", "inline": True},
            {"name": "⭐ Keyakinan", "value": f"**{signal.confidence}**", "inline": True},
            {"name": "💵 Entry (Area Beli)", "value": f"`{signal.entry_price or 'Market'}`", "inline": True},
            {"name": "🛑 Stop Loss (SL)", "value": f"`{signal.stop_loss or 'Tidak Ada'}`", "inline": True},
            {"name": "⚖️ Risk/Reward", "value": f"`{signal.risk_reward_ratio or 'N/A'}`", "inline": True},
            {"name": "🎯 Target Profit (TP)", "value": tp_text, "inline": False},
            {"name": "🛡️ Status Risiko", "value": risk_text, "inline": False},
            {"name": "📝 Analisis & Setup", "value": signal.summary or "Setup breakout / momentum trading.", "inline": False}
        ]

        embed = {
            "title": f"⚡ [CALL EANOVAIRE] AI STOCK SIGNAL: ${signal.ticker}",
            "color": embed_color,
            "fields": fields,
            "footer": {
                "text": f"📡 Sumber: {source} | {now_str} WIB | DYOR"
            }
        }
        return embed

    async def send_signal(self, signal: StockSignal, source: str = "Signal Engine") -> bool:
        """
        Mengirim embed sinyal ke Discord Webhook via HTTP POST async.
        """
        webhook_url = config.DISCORD_WEBHOOK_URL
        if not webhook_url:
            logger.debug("DISCORD_WEBHOOK_URL tidak dikonfigurasi. Lewati notifikasi Discord Webhook.")
            return False

        embed = self.build_embed(signal, source=source)
        payload = {
            "username": "EANovaire AI Signal",
            "avatar_url": "https://cdn-icons-png.flaticon.com/512/2920/2920349.png",
            "embeds": [embed]
        }

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "CallEANovaire/1.0"
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=payload, headers=headers, timeout=10) as resp:
                    if resp.status in (200, 204):
                        logger.info(f"✅ Sinyal #{signal.ticker} berhasil dikirim ke Discord Webhook!")
                        return True
                    else:
                        resp_text = await resp.text()
                        logger.error(f"❌ Gagal mengirim ke Discord Webhook (Status {resp.status}): {resp_text}")
                        return False
        except aiohttp.ClientError as ce:
            logger.error(f"Koneksi jaringan error saat kirim ke Discord Webhook: {ce}")
            return False
        except Exception as e:
            logger.error(f"Error tak terduga ke Discord Webhook: {e}")
            return False

    async def send_raw_text(self, text: str) -> bool:
        """Kirim pesan teks sederhana ke Discord Webhook."""
        webhook_url = config.DISCORD_WEBHOOK_URL
        if not webhook_url:
            return False

        payload = {"content": text}
        headers = {"Content-Type": "application/json", "User-Agent": "CallEANovaire/1.0"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=payload, headers=headers, timeout=10) as resp:
                    return resp.status in (200, 204)
        except Exception as e:
            logger.error(f"Error send_raw_text ke Discord Webhook: {e}")
            return False

discord_webhook_notifier = DiscordWebhookNotifierService()
