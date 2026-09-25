import os
from typing import List, Set
from dotenv import load_dotenv

# Muat file .env jika ada
load_dotenv()

class Config:
    # --- AI Settings ---
    AI_PROVIDER: str = os.getenv("AI_PROVIDER", "gemini").lower().strip()
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "").strip()
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "").strip()
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()

    # --- Telegram Settings ---
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    # --- Discord Notifier (Webhook Output) ---
    DISCORD_WEBHOOK_URL: str = os.getenv("DISCORD_WEBHOOK_URL", "").strip()

    # --- Discord Listener (Input) ---
    DISCORD_BOT_TOKEN: str = os.getenv("DISCORD_BOT_TOKEN", "").strip()
    _raw_channel_ids: str = os.getenv("DISCORD_CHANNEL_IDS", "").strip()

    # --- Webhook Settings ---
    WEBHOOK_ENABLE: bool = os.getenv("WEBHOOK_ENABLE", "true").lower() in ("true", "1", "yes")
    # Otomatis deteksi port Railway ($PORT) atau default ke WEBHOOK_PORT
    WEBHOOK_PORT: int = int(os.getenv("PORT") or os.getenv("WEBHOOK_PORT", "8000"))
    WEBHOOK_SECRET: str = os.getenv("WEBHOOK_SECRET", "").strip()

    # --- Autonomous Market Scanner Settings ---
    # Memindai pasar secara otomatis di jam bursa tanpa perlu input manual
    AUTO_SCANNER_ENABLE: bool = os.getenv("AUTO_SCANNER_ENABLE", "true").lower() in ("true", "1", "yes")
    SCANNER_INTERVAL_MINUTES: int = int(os.getenv("SCANNER_INTERVAL_MINUTES", "30"))

    @classmethod
    def get_discord_channel_ids(cls) -> Set[int]:
        """Parse comma-separated channel IDs into a set of integers."""
        if not cls._raw_channel_ids:
            return set()
        ids = set()
        for item in cls._raw_channel_ids.split(","):
            clean_item = item.strip()
            if clean_item.isdigit():
                ids.add(int(clean_item))
        return ids

    @classmethod
    def validate(cls) -> List[str]:
        """Memeriksa apakah konfigurasi dasar sudah lengkap."""
        missing = []
        if cls.AI_PROVIDER == "gemini" and not cls.GEMINI_API_KEY:
            missing.append("GEMINI_API_KEY belum diisi di .env")
        elif cls.AI_PROVIDER == "openai" and not cls.OPENAI_API_KEY:
            missing.append("OPENAI_API_KEY belum diisi di .env")

        has_telegram = bool(cls.TELEGRAM_BOT_TOKEN and cls.TELEGRAM_CHAT_ID)
        has_discord_webhook = bool(cls.DISCORD_WEBHOOK_URL)

        if not has_telegram and not has_discord_webhook:
            missing.append("Minimal satu tujuan notifikasi harus diisi di .env (TELEGRAM_BOT_TOKEN/CHAT_ID atau DISCORD_WEBHOOK_URL)")

        return missing

config = Config()
