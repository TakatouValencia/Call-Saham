import asyncio
import sys
import argparse
from config import config
from utils.logger import setup_logger
from services.discord_listener import start_discord_bot
from services.webhook_server import start_webhook_server
from services.ai_analyzer import ai_analyzer
from services.notifier import notifier

logger = setup_logger("MainApp")

async def run_simulation_test():
    """
    Fungsi pengujian simulasi cepat untuk memverifikasi pipeline
    AI Analyzer -> Filter Rule -> Notifikasi (Telegram & Discord Webhook).
    """
    print("\n" + "="*50)
    print("🧪 MEMULAI SIMULASI PENGUJIAN SIGNAL CALL EANOVAIRE")
    print("="*50)

    sample_alert = (
        "🚨 IDX BREAKOUT ALERT 🚨\n"
        "Saham: BBCA (Bank Central Asia)\n"
        "Action: BUY ON BREAKOUT\n"
        "Entry Area: 9850 - 9925\n"
        "Target Profit 1: 10200\n"
        "Target Profit 2: 10500\n"
        "Stop Loss: 9650\n"
        "RRR: 1:2.2\n"
        "Alasan: Volume spike 2x rata-rata 20 hari, foreign flow inflow masif rebound dari support MA50."
    )

    print(f"\n[1] Mengirim teks simulasi:\n{sample_alert}\n")
    print("[2] Menghubungi AI Analyzer...")
    signal = await ai_analyzer.analyze_message(sample_alert)

    if signal:
        print("\n✅ AI Berhasil Mengekstrak Sinyal:")
        print(signal.model_dump_json(indent=2))
        print("\n[3] Mendistribusikan sinyal ke channel notifikasi...")
        sent = await notifier.broadcast_signal(signal, source="Simulasi Testing")
        if sent:
            print("🎉 SUKSES! Notifikasi terkirim ke Telegram / Discord Webhook.")
        else:
            print("⚠️ Gagal mengirim notifikasi. Periksa konfigurasi TELEGRAM atau DISCORD_WEBHOOK_URL di .env.")
    else:
        print("❌ AI gagal mengekstrak sinyal atau pesan ditolak oleh filter.")

async def main():
    parser = argparse.ArgumentParser(description="Call EANovaire - AI Stock Signal Automation")
    parser.add_argument("--test", action="store_true", help="Jalankan simulasi tes AI & Notifikasi")
    args = parser.parse_args()

    # Validasi konfigurasi
    missing_configs = config.validate()
    if missing_configs:
        logger.error("Konfigurasi belum lengkap:")
        for item in missing_configs:
            logger.error(f" - {item}")
        print("\nSilakan salin .env.example menjadi .env dan isi kredensial Anda.")
        sys.exit(1)

    if args.test:
        await run_simulation_test()
        return

    logger.info("=" * 60)
    logger.info("🚀 CALL EANOVAIRE - AI STOCK SIGNAL AUTOMATION AKTIF")
    logger.info(f"🧠 AI Provider        : {config.AI_PROVIDER.upper()}")
    logger.info(f"📱 Telegram Target    : {config.TELEGRAM_CHAT_ID or 'Nonaktif'}")
    logger.info(f"🎮 Discord Webhook    : {'Aktif' if config.DISCORD_WEBHOOK_URL else 'Nonaktif'}")
    logger.info(f"🌐 Webhook API Server : {'Aktif' if config.WEBHOOK_ENABLE else 'Nonaktif'}")
    logger.info("=" * 60)

    # Jalankan layanan secara paralel
    tasks = []

    # 1. Task Webhook Server
    if config.WEBHOOK_ENABLE:
        tasks.append(asyncio.create_task(start_webhook_server()))

    # 2. Task Discord Bot
    if config.DISCORD_BOT_TOKEN:
        tasks.append(asyncio.create_task(start_discord_bot()))
    else:
        logger.warning("DISCORD_BOT_TOKEN belum diisi. Discord listener tidak dijalankan.")

    if not tasks:
        logger.error("Tidak ada listener yang aktif! Aktifkan Discord atau Webhook di .env.")
        return

    try:
        await asyncio.gather(*tasks)
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Aplikasi dihentikan oleh pengguna (Ctrl+C).")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nProgram selesai.")
