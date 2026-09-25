import discord
from config import config
from services.ai_analyzer import ai_analyzer
from services.notifier import notifier
from utils.logger import setup_logger

logger = setup_logger("DiscordListener")

class DiscordSignalBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True  # Memerlukan izin Message Content Intent di Discord Portal
        super().__init__(intents=intents)
        self.target_channel_ids = config.get_discord_channel_ids()

    async def on_ready(self):
        logger.info(f"🤖 Discord Bot terhubung sebagai: {self.user} (ID: {self.user.id})")
        if self.target_channel_ids:
            logger.info(f"🎯 Memantau {len(self.target_channel_ids)} Channel Discord: {self.target_channel_ids}")
        else:
            logger.warning("⚠️ Tidak ada DISCORD_CHANNEL_IDS yang dispesifikasikan di .env! Bot akan memantau semua channel yang memiliki akses.")

    async def on_message(self, message: discord.Message):
        # 1. Hindari pesan dari bot itu sendiri
        if message.author.id == self.user.id:
            return

        # 2. Filter channel jika target_channel_ids diatur
        if self.target_channel_ids and message.channel.id not in self.target_channel_ids:
            return

        # 3. Kumpulkan konten pesan (teks dan embed jika ada)
        content_parts = []
        if message.content:
            content_parts.append(message.content)

        # Jika ada embed (misalnya alert dari webhook bot atau tradingview bot di discord)
        if message.embeds:
            for emb in message.embeds:
                if emb.title:
                    content_parts.append(f"Title: {emb.title}")
                if emb.description:
                    content_parts.append(f"Desc: {emb.description}")
                for field in emb.fields:
                    content_parts.append(f"{field.name}: {field.value}")

        full_raw_text = "\n".join(content_parts).strip()
        if not full_raw_text:
            return

        logger.info(f"📨 Menerima pesan dari [#{message.channel.name}] ({message.author.name}): {full_raw_text[:60]}...")

        # 4. Kirim ke AI Analyzer
        signal = await ai_analyzer.analyze_message(full_raw_text)

        # 5. Jika sinyal valid, broadcast notifikasi
        if signal and signal.is_valid_signal:
            channel_label = f"Discord #{message.channel.name}"
            await notifier.broadcast_signal(signal, source=channel_label)

async def start_discord_bot():
    """Fungsi wrapper untuk menjalankan Discord Bot."""
    if not config.DISCORD_BOT_TOKEN:
        logger.warning("DISCORD_BOT_TOKEN tidak ditemukan di .env. Discord listener dinonaktifkan.")
        return

    bot = DiscordSignalBot()
    try:
        await bot.start(config.DISCORD_BOT_TOKEN)
    except discord.LoginFailure:
        logger.error("Gagal login Discord: Token bot salah atau expired!")
    except Exception as e:
        logger.error(f"Error pada Discord Bot: {e}", exc_info=True)
