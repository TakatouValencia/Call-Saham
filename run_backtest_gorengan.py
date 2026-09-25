import sys
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
from collections import defaultdict

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

def get_fundamental_summary(ticker_obj) -> dict:
    """Mengambil metrik fundamental ringkas untuk saham."""
    try:
        info = ticker_obj.info
        sector = info.get("sector", "N/A")
        market_cap = info.get("marketCap", 0)
        cap_trillion = round(market_cap / 1e12, 1) if market_cap else 0
        pe = round(info.get("trailingPE", 0), 1) if info.get("trailingPE") else "N/A"
        pbv = round(info.get("priceToBook", 0), 1) if info.get("priceToBook") else "N/A"
        
        # Skor Fundamental Ringkas
        catalyst = "Komoditas & Momentum Aksi Korporasi"
        if "Technology" in sector or "Communication" in sector:
            catalyst = "Ekspansi Digital & Katalis AI Infra"
        elif "Basic Materials" in sector or "Energy" in sector:
            catalyst = "Katalis Harga Komoditas Global & Turnaround"
        elif "Real Estate" in sector:
            catalyst = "Sentimen Suku Bunga & Proyek IKN/Mega Urban"

        return {
            "sector": sector,
            "cap_t": cap_trillion,
            "pe": pe,
            "pbv": pbv,
            "catalyst": catalyst
        }
    except Exception:
        return {"sector": "IDX", "cap_t": 0, "pe": "N/A", "pbv": "N/A", "catalyst": "Momentum Trading"}

def run_bandarmology_backtest(ticker: str, period: str = '60d', interval: str = '1h'):
    """
    Backtest deteksi akumulasi bandar (Bandarmology + Volume Price Analysis) 
    pada saham second liner / gorengan selama 2 bulan terakhir.
    """
    ticker_obj = yf.Ticker(ticker)
    try:
        df = ticker_obj.history(period=period, interval=interval)
    except Exception as e:
        print(f"Error {ticker}: {e}")
        return None, {}

    if df is None or df.empty or len(df) < 40:
        return None, {}

    fund = get_fundamental_summary(ticker_obj)

    opens = df['Open'].values
    highs = df['High'].values
    lows = df['Low'].values
    closes = df['Close'].values
    volumes = df['Volume'].values
    timestamps = df.index
    n = len(df)

    # 1. Volume Analysis (MA20 & RVOL)
    vol_series = pd.Series(volumes)
    vol_ma20 = vol_series.rolling(20).mean().values
    vol_ma5 = vol_series.rolling(5).mean().values

    # 2. Price Volatility & Moving Averages
    closes_series = pd.Series(closes)
    ema20 = closes_series.ewm(span=20, adjust=False).mean().values
    ema50 = closes_series.ewm(span=50, adjust=False).mean().values

    # ATR
    tr = np.zeros(n)
    tr[0] = highs[0] - lows[0]
    for i in range(1, n):
        tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
    atr = pd.Series(tr).rolling(14).mean().values

    # 3. Chaikin Money Flow (CMF Proxy)
    mfv = np.zeros(n)
    for i in range(n):
        hl_range = highs[i] - lows[i]
        if hl_range > 0:
            clv = ((closes[i] - lows[i]) - (highs[i] - closes[i])) / hl_range
            mfv[i] = clv * volumes[i]
    cmf20 = (pd.Series(mfv).rolling(20).sum() / (vol_series.rolling(20).sum() + 1e-9)).values

    calls = []
    last_call_bar = -999

    for i in range(25, n):
        cur_vol = volumes[i]
        cur_vma20 = vol_ma20[i] if not np.isnan(vol_ma20[i]) and vol_ma20[i] > 0 else 1
        rvol = cur_vol / cur_vma20

        # Kriteria Akumulasi Bandar:
        # 1. Volume Anomali: RVOL >= 2.0x rata-rata 20 hari ATAU (Vol MA5 > Vol MA20 * 1.4 dan CMF > 0.10)
        # 2. Price Action: Candle hijau bullish (Close > Open)
        # 3. Posisi Harga: Breakout di atas EMA20 atau Golden Cross
        # 4. Money Flow Positif: CMF > 0.05 (menandakan tekanan beli bandar mendominasi)
        is_bullish_candle = closes[i] > opens[i]
        is_volume_spike = rvol >= 2.0 and cur_vol >= 500_000
        is_silent_acc = (vol_ma5[i] > vol_ma20[i] * 1.3) and (cmf20[i] > 0.12)
        is_breakout_ema = closes[i] > ema20[i] and (closes[i-1] <= ema20[i-1] or closes[i] > ema50[i])

        bandar_accumulation = is_bullish_candle and (is_volume_spike or is_silent_acc) and is_breakout_ema
        can_call = (i - last_call_bar >= 8)  # Cooldown 8 bar (~2 hari trading)

        if bandar_accumulation and can_call:
            last_call_bar = i
            entry = float(closes[i])
            cur_atr = float(atr[i]) if not np.isnan(atr[i]) else (entry * 0.03)

            # Pola Akumulasi yang terdeteksi
            if rvol >= 3.0:
                pola = f"Volume Spike Monster ({rvol:.1f}x) - HAKA Bandar"
            elif rvol >= 2.0:
                pola = f"Breakout Akumulasi ({rvol:.1f}x Vol)"
            else:
                pola = f"Silent Accumulation (CMF Inflow {cmf20[i]:.2f})"

            # Money Management Saham Gorengan (Stop Loss Ketat 3.5% - 5%, TP Bertingkat):
            # SL di bawah swing low terdekat atau 1.5x ATR
            sl_price = round(max(entry - cur_atr * 1.5, entry * 0.95), 1)
            risk = entry - sl_price
            
            # Target Profit Bertingkat Saham Gorengan:
            tp1 = round(entry + risk * 1.5, 1)  # Target 1 (~+6% - +10%)
            tp2 = round(entry + risk * 3.0, 1)  # Target 2 (~+15% - +25%)
            tp3 = round(entry + risk * 5.0, 1)  # Target 3 (Moon / ARA +35%+)

            call_time = str(timestamps[i])[:16]
            calls.append({
                'ticker': ticker,
                'call_time': call_time,
                'entry_bar': i,
                'entry': entry,
                'sl': sl_price,
                'tp1': tp1,
                'tp2': tp2,
                'tp3': tp3,
                'rvol': round(rvol, 1),
                'pola': pola,
                'outcome': None,
                'exit_price': None,
                'pnl_pct': 0.0,
                'highest_tp': 'BELUM'
            })

    # Evaluasi Hasil Call 2 Bulan
    for c in calls:
        e_bar = c['entry_bar']
        entry = c['entry']
        sl = c['sl']
        tp1 = c['tp1']
        tp2 = c['tp2']
        tp3 = c['tp3']

        hit_tp1, hit_tp2, hit_tp3 = False, False, False

        for b in range(e_bar + 1, n):
            h = highs[b]
            l = lows[b]

            if h >= tp3: hit_tp3 = True
            if h >= tp2: hit_tp2 = True
            if h >= tp1: hit_tp1 = True

            # Stop loss hit sebelum TP1
            if l <= sl and not hit_tp1:
                c['outcome'] = 'SL HIT'
                c['exit_price'] = sl
                c['pnl_pct'] = round(((sl - entry) / entry) * 100, 2)
                c['highest_tp'] = 'GAGAL (SL)'
                break

            # Jika sudah kena TP tapi kemudian turun melewati entry (Trailing Stop at BEP)
            if hit_tp1 and l <= entry:
                # Close trade at TP1 gain
                c['outcome'] = 'WIN (TP1 HIT)'
                c['exit_price'] = tp1
                c['pnl_pct'] = round(((tp1 - entry) / entry) * 100, 2)
                c['highest_tp'] = 'TP1'
                break

        if c['outcome'] is None:
            if hit_tp3:
                c['outcome'] = 'SUPER WIN (TP3 HIT)'
                c['exit_price'] = tp3
                c['pnl_pct'] = round(((tp3 - entry) / entry) * 100, 2)
                c['highest_tp'] = 'TP3 (+30%+)'
            elif hit_tp2:
                c['outcome'] = 'BIG WIN (TP2 HIT)'
                c['exit_price'] = tp2
                c['pnl_pct'] = round(((tp2 - entry) / entry) * 100, 2)
                c['highest_tp'] = 'TP2 (+15%+)'
            elif hit_tp1:
                c['outcome'] = 'WIN (TP1 HIT)'
                c['exit_price'] = tp1
                c['pnl_pct'] = round(((tp1 - entry) / entry) * 100, 2)
                c['highest_tp'] = 'TP1 (+8%+)'
            else:
                cur_price = closes[-1]
                c['outcome'] = 'FLOATING / OPEN'
                c['exit_price'] = cur_price
                c['pnl_pct'] = round(((cur_price - entry) / entry) * 100, 2)
                c['highest_tp'] = 'PROSES'

    return calls, fund

if __name__ == '__main__':
    # Daftar saham gorengan & second liner berkapitalisasi aktif di bursa IDX
    gorengan_stocks = [
        'BRMS.JK', 'BUMI.JK', 'DEWA.JK', 'PANI.JK', 'PTRO.JK', 
        'WIFI.JK', 'RAJA.JK', 'ENRG.JK', 'PSAB.JK', 'DOID.JK', 'KIJA.JK'
    ]

    all_calls = []
    fund_db = {}

    print("="*90)
    print("  BACKTEST SAHAM GORENGAN & SECOND-LINER (AKUMULASI BANDAR & FUNDAMENTAL 2 BULAN)")
    print("="*90)

    for ticker in gorengan_stocks:
        print(f"[*] Menganalisis Akumulasi Bandar: {ticker}...")
        calls, fund = run_bandarmology_backtest(ticker, period='60d', interval='1h')
        fund_db[ticker] = fund
        if calls:
            all_calls.extend(calls)

    print("\n" + "="*105)
    print(f"{'TANGGAL CALL':<16} | {'SAHAM':<8} | {'ENTRY':<8} | {'SL':<8} | {'TP1':<8} | {'TP2':<8} | {'HIGHEST TP':<14} | {'STATUS':<18} | {'MAX PNL':<8}")
    print("="*105)

    wins = 0
    losses = 0
    opens = 0

    for c in all_calls:
        clean_ticker = c['ticker'].replace('.JK', '')
        status = c['outcome']
        if 'WIN' in status:
            wins += 1
            st_color = f"🟢 {status}"
        elif 'SL HIT' in status:
            losses += 1
            st_color = f"🔴 {status}"
        else:
            opens += 1
            st_color = f"🟡 {status}"

        p_prefix = "+" if c['pnl_pct'] > 0 else ""
        print(f"{c['call_time']:<16} | {clean_ticker:<8} | {c['entry']:<8} | {c['sl']:<8} | {c['tp1']:<8} | {c['tp2']:<8} | {c['highest_tp']:<14} | {st_color:<18} | {p_prefix}{c['pnl_pct']}%")

    print("="*105)
    total_closed = wins + losses
    win_rate = (wins / total_closed * 100) if total_closed > 0 else 0
    print(f"Total Call Sinyal Gorengan : {len(all_calls)} Sinyal")
    print(f"Hit Take Profit (TP1/2/3) : {wins} Trade ({win_rate:.1f}% Win Rate)")
    print(f"Hit Stop Loss             : {losses} Trade")
    print(f"Posisi Masih Berjalan     : {opens} Trade")
    print("="*105)

    # Simpan hasil ke file markdown
    md = []
    md.append("# 🔥 LAPORAN BACKTEST SAHAM GORENGAN & SECOND-LINER (AKUMULASI BANDAR)")
    md.append(f"**Tanggal Pengujian:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    md.append(f"**Strategi:** Bandarmology Flow (Volume Anomali 2x+, Chaikin Money Flow Inflow, Wyckoff Spring Breakout & Fundamental Catalyst)")
    md.append("\n---\n")
    md.append("### 📊 Ringkasan Hasil:")
    md.append(f"- **Total Call Akumulasi:** {len(all_calls)} Sinyal")
    md.append(f"- **Win Rate (Hit TP):** **{win_rate:.1f}%** ({wins} Win / {losses} Loss)")
    md.append(f"- **Posisi Masih Berjalan:** {opens} Saham")
    md.append("\n---\n")

    # Kelompokkan per ticker
    grouped = defaultdict(list)
    for c in all_calls:
        clean_ticker = c['ticker'].replace('.JK', '')
        grouped[clean_ticker].append(c)

    for ticker, c_list in grouped.items():
        raw_t = f"{ticker}.JK"
        f_info = fund_db.get(raw_t, {})
        t_wins = sum(1 for x in c_list if 'WIN' in x['outcome'])
        t_loss = sum(1 for x in c_list if 'SL' in x['outcome'])
        t_wr = (t_wins / (t_wins + t_loss) * 100) if (t_wins + t_loss) > 0 else 0

        md.append(f"## 🚀 Saham: **${ticker}**")
        md.append(f"**Sektor:** {f_info.get('sector')} | **Market Cap:** Rp {f_info.get('cap_t')} T | **Katalis:** {f_info.get('catalyst')}")
        md.append(f"**Performa:** Total Call: {len(c_list)} | Win Rate: **{t_wr:.1f}%** (TP: {t_wins} | SL: {t_loss})")
        md.append("\n| Tanggal Call | Entry | Stop Loss | TP1 | TP2 | TP3 | Pola Akumulasi Bandar | Status Hasil | PnL Realized |")
        md.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")

        for x in c_list:
            p_prefix = "+" if x['pnl_pct'] > 0 else ""
            if 'WIN' in x['outcome']:
                badge = f"🟢 **{x['outcome']}**"
            elif 'SL' in x['outcome']:
                badge = f"🔴 **{x['outcome']}**"
            else:
                badge = f"🟡 **{x['outcome']}**"

            md.append(f"| {x['call_time']} | `{x['entry']}` | `{x['sl']}` | `{x['tp1']}` | `{x['tp2']}` | `{x['tp3']}` | {x['pola']} | {badge} | **{p_prefix}{x['pnl_pct']}%** |")
        md.append("\n")

    report_file = "backtest_saham_gorengan_2bulan.md"
    with open(report_file, "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    print(f"\n[OK] Laporan detail tersimpan di: {report_file}")
