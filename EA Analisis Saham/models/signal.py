from typing import List, Optional, Literal, Any
from pydantic import BaseModel, Field, model_validator

class StockSignal(BaseModel):
    """
    Model representasi sinyal trading saham yang diekstrak oleh AI.
    Mendukung format 'entry' maupun 'entry_price', serta aksi 'BUY', 'SELL', 'HOLD', 'WAIT'.
    """
    is_valid_signal: bool = Field(
        default=False,
        description="True jika pesan mengandung sinyal trading saham yang valid, False jika bukan."
    )
    ticker: str = Field(
        default="", 
        description="Kode saham / emiten dalam huruf kapital, contoh: BBCA, BBRI, ASII, AAPL, NVDA."
    )
    action: Literal["BUY", "SELL", "HOLD", "WAIT", "INVALID"] = Field(
        default="INVALID",
        description="Aksi trading yang disarankan."
    )
    entry: str = Field(
        default="",
        description="Area atau harga beli/entry, contoh: '9800 - 9900'."
    )
    entry_price: str = Field(
        default="",
        description="Alias untuk entry."
    )
    stop_loss: Optional[str] = Field(
        default=None,
        description="Harga batas pengaman/Stop Loss (SL)."
    )
    take_profit: List[str] = Field(
        default_factory=list,
        description="Daftar target keuntungan/Take Profit (TP1, TP2, dst)."
    )
    risk_reward_ratio: Optional[str] = Field(
        default=None,
        description="Rasio Risk to Reward (contoh: '1:2', '1:1.5')."
    )
    timeframe: Optional[str] = Field(
        default="Swing / Day Trading",
        description="Gaya trading atau timeframe."
    )
    confidence: Literal["HIGH", "MEDIUM", "LOW"] = Field(
        default="MEDIUM",
        description="Estimasi keyakinan sinyal."
    )
    summary: str = Field(
        default="",
        description="Ringkasan analisa teknikal / katalis / alasan entry."
    )
    is_high_risk: bool = Field(
        default=False,
        description="Apakah sinyal masuk kategori risiko tinggi (SL tidak ada / RRR < 1:1.5)."
    )
    risk_notes: Optional[str] = Field(
        default=None,
        description="Catatan tambahan mengenai risiko sinyal."
    )

    @model_validator(mode="before")
    @classmethod
    def sync_entry_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Sinkronisasi antara 'entry' dan 'entry_price'
            val_entry = data.get("entry") or data.get("entry_price") or ""
            data["entry"] = str(val_entry)
            data["entry_price"] = str(val_entry)
            
            # Normalisasi action
            action_val = str(data.get("action", "")).upper().strip()
            if action_val in ("BUY", "BELI"):
                data["action"] = "BUY"
            elif action_val in ("SELL", "JUAL"):
                data["action"] = "SELL"
            elif action_val in ("HOLD", "TAHAN"):
                data["action"] = "HOLD"
            elif action_val in ("WAIT", "WAIT & SEE"):
                data["action"] = "WAIT"
        return data
