import uvicorn
from fastapi import FastAPI, HTTPException, Header, Request
from pydantic import BaseModel
from typing import Optional
from config import config
from services.ai_analyzer import ai_analyzer
from services.notifier import notifier
from utils.logger import setup_logger

logger = setup_logger("WebhookServer")

app = FastAPI(title="Call EANovaire Webhook Listener", version="1.0.0")

class WebhookSignalPayload(BaseModel):
    text: str
    source: Optional[str] = "Website / Webhook Alert"

@app.get("/")
@app.get("/health")
async def health_check():
    return {"status": "ok", "app": "Call EANovaire", "ai_provider": config.AI_PROVIDER}

@app.post("/webhook/signal")
async def receive_signal(
    payload: WebhookSignalPayload,
    x_secret_token: Optional[str] = Header(None, alias="X-Secret-Token")
):
    """
    Endpoint untuk menerima sinyal/alert dari website, scraper, atau TradingView webhook.
    """
    # Validasi secret token jika dikonfigurasi
    if config.WEBHOOK_SECRET and x_secret_token != config.WEBHOOK_SECRET:
        logger.warning("Upaya akses webhook ditolak: Secret Token tidak cocok.")
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid Secret Token")

    raw_text = payload.text.strip()
    if not raw_text:
        raise HTTPException(status_code=400, detail="Text tidak boleh kosong")

    logger.info(f"🌐 Menerima alert dari Webhook [{payload.source}]: {raw_text[:60]}...")

    # Analisis pesan dengan AI
    signal = await ai_analyzer.analyze_message(raw_text)

    if signal and signal.is_valid_signal:
        # Broadcast ke Telegram & Discord
        success = await notifier.broadcast_signal(signal, source=payload.source or "Website Webhook")
        return {
            "status": "success",
            "message": "Sinyal valid diproses dan dikirim ke channel notifikasi",
            "signal": signal.model_dump(),
            "notification_sent": success
        }
    else:
        return {
            "status": "ignored",
            "message": "Pesan bukan sinyal saham valid atau tidak memenuhi filter kriteria."
        }

async def start_webhook_server():
    """Fungsi pembantu untuk menjalankan Uvicorn server secara asinkron."""
    if not config.WEBHOOK_ENABLE:
        logger.info("Webhook server dinonaktifkan di .env.")
        return

    logger.info(f"🚀 Memulai Webhook Server pada http://{config.WEBHOOK_HOST}:{config.WEBHOOK_PORT}")
    server_config = uvicorn.Config(
        app=app,
        host=config.WEBHOOK_HOST,
        port=config.WEBHOOK_PORT,
        log_level="warning"
    )
    server = uvicorn.Server(server_config)
    await server.serve()
