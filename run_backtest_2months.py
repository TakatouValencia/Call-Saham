import sys
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

def run_stock_smc_backtest(ticker: str, period: str = '60d', interval: str = '1h', swing_len: int = 5, min_score: int = 4, rr_ratio: float = 2.0):
    """
    Menjalankan backtest Institutional SMC pada saham selama 60 hari (2 bulan terakhir).
    Mencatat setiap call sinyal, Entry, Stop Loss, Take Profit, dan hasilnya.
    """
    try:
        df = yf.download(ticker, period=period, interval=interval, progress=False)
    except Exception as e:
        print(f"Error download {ticker}: {e}")
        return None

    if df is None or df.empty:
        return None

    # Flatten MultiIndex columns jika ada
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.dropna().copy()
    n = len(df)
    if n < 50:
        return None

    opens = df['Open'].values
    highs = df['High'].values
    lows = df['Low'].values
    closes = df['Close'].values
    timestamps = df.index

    # 1. Hitung ATR (14)
    tr = np.zeros(n)
    tr[0] = highs[0] - lows[0]
    for i in range(1, n):
        tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
    atr = pd.Series(tr).rolling(14).mean().values

    # 2. EMAs (50 & 200)
    ema50 = pd.Series(closes).ewm(span=50, adjust=False).mean().values
    ema200 = pd.Series(closes).ewm(span=200, adjust=False).mean().values

    # 3. RSI (14)
    delta = pd.Series(closes).diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / (loss + 1e-9)
    rsi = (100 - (100 / (1 + rs))).values

    # Struktur & Order Blocks
    last_sh_price, prev_sh_price = np.nan, np.nan
    last_sl_price, prev_sl_price = np.nan, np.nan
    market_bullish, market_bearish = False, False
    bull_bos_pending, bear_bos_pending = True, True
    bull_setup_active, bear_setup_active = False, False
    last_bull_bos_bar, last_bear_bos_bar = -1, -1

    active_bull_obs = []
    active_bear_obs = []
    active_bull_fvgs = []
    active_bear_fvgs = []

    trades = []
    last_signal_bar = -999

    for i in range(swing_len * 2 + 1, n):
        # Pivot detection
        p_idx = i - swing_len
        is_ph, is_pl = True, True
        for k in range(p_idx - swing_len, p_idx + swing_len + 1):
            if k != p_idx:
                if highs[k] >= highs[p_idx]: is_ph = False
                if lows[k] <= lows[p_idx]: is_pl = False

        if is_ph:
            prev_sh_price = last_sh_price
            last_sh_price = highs[p_idx]
            bull_bos_pending = True
        if is_pl:
            prev_sl_price = last_sl_price
            last_sl_price = lows[p_idx]
            bear_bos_pending = True

        if not np.isnan(last_sh_price) and not np.isnan(prev_sh_price) and not np.isnan(last_sl_price) and not np.isnan(prev_sl_price):
            if last_sh_price > prev_sh_price and last_sl_price > prev_sl_price:
                market_bullish, market_bearish = True, False
            elif last_sh_price < prev_sh_price and last_sl_price < prev_sl_price:
                market_bullish, market_bearish = False, True

        # BOS
        bull_bos_event = False
        bear_bos_event = False
        if not np.isnan(last_sh_price) and bull_bos_pending:
            if closes[i] > last_sh_price and closes[i-1] <= last_sh_price:
                bull_bos_event = True
                bull_bos_pending = False
                bull_setup_active = True
                bear_setup_active = False
                last_bull_bos_bar = i
                market_bullish, market_bearish = True, False

        if not np.isnan(last_sl_price) and bear_bos_pending:
            if closes[i] < last_sl_price and closes[i-1] >= last_sl_price:
                bear_bos_event = True
                bear_bos_pending = False
                bear_setup_active = True
                bull_setup_active = False
                last_bear_bos_bar = i
                market_bearish, market_bullish = True, False

        # Order Blocks
        if bull_bos_event:
            for b in range(1, min(25, i)):
                if closes[i-b] < opens[i-b]:
                    ob_top, ob_bot = opens[i-b], lows[i-b]
                    if ob_top > ob_bot:
                        active_bull_obs.append({'top': ob_top, 'bottom': ob_bot, 'mitigated': False, 'created_bar': i-b})
                        if len(active_bull_obs) > 4: active_bull_obs.pop(0)
                    break
        if bear_bos_event:
            for b in range(1, min(25, i)):
                if closes[i-b] > opens[i-b]:
                    ob_top, ob_bot = highs[i-b], opens[i-b]
                    if ob_top > ob_bot:
                        active_bear_obs.append({'top': ob_top, 'bottom': ob_bot, 'mitigated': False, 'created_bar': i-b})
                        if len(active_bear_obs) > 4: active_bear_obs.pop(0)
                    break

        active_bull_obs = [ob for ob in active_bull_obs if closes[i] >= ob['bottom']]
        active_bear_obs = [ob for ob in active_bear_obs if closes[i] <= ob['top']]

        # FVG Detection
        c1_body = abs(closes[i-1] - opens[i-1])
        c1_atr = atr[i-1] if not np.isnan(atr[i-1]) else 1.0
        disp = c1_body >= (c1_atr * 0.7)

        if disp and closes[i-1] > opens[i-1] and lows[i] > highs[i-2]:
            active_bull_fvgs.append({'top': lows[i], 'bottom': highs[i-2], 'mitigated': False, 'created_bar': i})
            if len(active_bull_fvgs) > 4: active_bull_fvgs.pop(0)

        if disp and closes[i-1] < opens[i-1] and highs[i] < lows[i-2]:
            active_bear_fvgs.append({'top': lows[i-2], 'bottom': highs[i], 'mitigated': False, 'created_bar': i})
            if len(active_bear_fvgs) > 4: active_bear_fvgs.pop(0)

        active_bull_fvgs = [fvg for fvg in active_bull_fvgs if closes[i] >= fvg['bottom']]
        active_bear_fvgs = [fvg for fvg in active_bear_fvgs if closes[i] <= fvg['top']]

        # Zone Check
        in_bull_zone = any(not ob['mitigated'] and (lows[i] <= ob['top'] and highs[i] >= ob['bottom']) for ob in active_bull_obs) or \
                       any(not fvg['mitigated'] and i > fvg['created_bar'] and (lows[i] <= fvg['top'] and highs[i] >= fvg['bottom']) for fvg in active_bull_fvgs)
        in_bear_zone = any(not ob['mitigated'] and (highs[i] >= ob['bottom'] and lows[i] <= ob['top']) for ob in active_bear_obs) or \
                       any(not fvg['mitigated'] and i > fvg['created_bar'] and (highs[i] >= fvg['bottom'] and lows[i] <= fvg['top']) for fvg in active_bear_fvgs)

        # Candlestick confirmation
        c_range = highs[i] - lows[i]
        c_body = abs(closes[i] - opens[i])
        l_wick = min(opens[i], closes[i]) - lows[i]
        u_wick = highs[i] - max(opens[i], closes[i])
        is_green = closes[i] > opens[i]
        is_red = closes[i] < opens[i]

        bull_confirmed = (c_range > 0 and (l_wick / c_range >= 0.30) and is_green) or \
                         (is_green and closes[i-1] < opens[i-1] and closes[i] >= opens[i-1]) or \
                         (is_green and c_range > 0 and (c_body / c_range >= 0.50))

        bear_confirmed = (c_range > 0 and (u_wick / c_range >= 0.30) and is_red) or \
                         (is_red and closes[i-1] > opens[i-1] and closes[i] <= opens[i-1]) or \
                         (is_red and c_range > 0 and (c_body / c_range >= 0.50))

        # Scoring
        score_buy = (1 if market_bullish else 0) + \
                    (1 if (last_bull_bos_bar > 0 and i - last_bull_bos_bar <= 40) else 0) + \
                    (1 if in_bull_zone else 0) + \
                    (1 if bull_confirmed else 0) + \
                    (1 if (closes[i] > ema50[i] and rsi[i] >= 45) else 0)

        score_sell = (1 if market_bearish else 0) + \
                     (1 if (last_bear_bos_bar > 0 and i - last_bear_bos_bar <= 40) else 0) + \
                     (1 if in_bear_zone else 0) + \
                     (1 if bear_confirmed else 0) + \
                     (1 if (closes[i] < ema50[i] and rsi[i] <= 55) else 0)

        # Signal trigger (cooldown 4 bar)
        buy_sig = bull_setup_active and in_bull_zone and bull_confirmed and (score_buy >= min_score) and (i - last_signal_bar >= 4)
        sell_sig = bear_setup_active and in_bear_zone and bear_confirmed and (score_sell >= min_score) and (i - last_signal_bar >= 4)

        if buy_sig:
            last_signal_bar = i
            bull_setup_active = False
            entry_price = float(closes[i])
            cur_atr = float(atr[i]) if not np.isnan(atr[i]) else (entry_price * 0.02)
            sl_price = float(last_sl_price - cur_atr * 0.2) if not np.isnan(last_sl_price) else (entry_price - cur_atr * 1.5)
            if sl_price >= entry_price:
                sl_price = entry_price - cur_atr * 1.5
            risk = entry_price - sl_price
            tp_price = entry_price + risk * rr_ratio

            call_time = str(timestamps[i])[:16]
            trades.append({
                'ticker': ticker,
                'type': 'BUY',
                'entry_bar': i,
                'call_time': call_time,
                'entry_price': round(entry_price, 2),
                'sl': round(sl_price, 2),
                'tp': round(tp_price, 2),
                'score': score_buy,
                'rr': f"1:{rr_ratio:.1f}",
                'outcome': None,
                'exit_bar': None,
                'exit_price': None,
                'pnl_pct': 0.0,
                'r_return': 0.0
            })

        elif sell_sig:
            last_signal_bar = i
            bear_setup_active = False
            entry_price = float(closes[i])
            cur_atr = float(atr[i]) if not np.isnan(atr[i]) else (entry_price * 0.02)
            sl_price = float(last_sh_price + cur_atr * 0.2) if not np.isnan(last_sh_price) else (entry_price + cur_atr * 1.5)
            if sl_price <= entry_price:
                sl_price = entry_price + cur_atr * 1.5
            risk = sl_price - entry_price
            tp_price = entry_price - risk * rr_ratio

            call_time = str(timestamps[i])[:16]
            trades.append({
                'ticker': ticker,
                'type': 'SELL',
                'entry_bar': i,
                'call_time': call_time,
                'entry_price': round(entry_price, 2),
                'sl': round(sl_price, 2),
                'tp': round(tp_price, 2),
                'score': score_sell,
                'rr': f"1:{rr_ratio:.1f}",
                'outcome': None,
                'exit_bar': None,
                'exit_price': None,
                'pnl_pct': 0.0,
                'r_return': 0.0
            })

    # Evaluasi hasil trade
    for t in trades:
        e_bar = t['entry_bar']
        is_buy = t['type'] == 'BUY'
        tp = t['tp']
        sl = t['sl']
        entry = t['entry_price']

        for b in range(e_bar + 1, n):
            h = highs[b]
            l = lows[b]

            if is_buy:
                if h >= tp:
                    t['outcome'] = 'WIN (TP HIT)'
                    t['exit_bar'] = b
                    t['exit_price'] = tp
                    t['pnl_pct'] = round(((tp - entry) / entry) * 100, 2)
                    t['r_return'] = rr_ratio
                    break
                elif l <= sl:
                    t['outcome'] = 'LOSS (SL HIT)'
                    t['exit_bar'] = b
                    t['exit_price'] = sl
                    t['pnl_pct'] = round(((sl - entry) / entry) * 100, 2)
                    t['r_return'] = -1.0
                    break
            else:
                if l <= tp:
                    t['outcome'] = 'WIN (TP HIT)'
                    t['exit_bar'] = b
                    t['exit_price'] = tp
                    t['pnl_pct'] = round(((entry - tp) / entry) * 100, 2)
                    t['r_return'] = rr_ratio
                    break
                elif h >= sl:
                    t['outcome'] = 'LOSS (SL HIT)'
                    t['exit_bar'] = b
                    t['exit_price'] = sl
                    t['pnl_pct'] = round(((entry - sl) / entry) * 100, 2)
                    t['r_return'] = -1.0
                    break

        if t['outcome'] is None:
            # Trade masih floating / open
            cur_price = closes[-1]
            t['outcome'] = 'OPEN (FLOATING)'
            t['exit_price'] = cur_price
            if is_buy:
                t['pnl_pct'] = round(((cur_price - entry) / entry) * 100, 2)
            else:
                t['pnl_pct'] = round(((entry - cur_price) / entry) * 100, 2)

    return trades

if __name__ == '__main__':
    # Daftar saham yang diuji (Saham Bluechip IHSG & Top US Stocks)
    stocks_idx = ['BBCA.JK', 'BBRI.JK', 'BMRI.JK', 'TLKM.JK', 'ASII.JK', 'ANTM.JK', 'BBNI.JK']
    stocks_us = ['NVDA', 'AAPL', 'TSLA']
    all_stocks = stocks_idx + stocks_us

    all_calls = []

    print("="*85)
    print("  MEMULAI BACKTEST SINYAL SAHAM 2 BULAN KEBELAKANG (JULI - SEPTEMBER 2026)")
    print("="*85)

    for ticker in all_stocks:
        print(f"[*] Menganalisis historis 2 bulan: {ticker}...")
        trades = run_stock_smc_backtest(ticker, period='60d', interval='1h', min_score=4, rr_ratio=2.0)
        if trades:
            all_calls.extend(trades)

    print("\n" + "="*95)
    print(f"{'TANGGAL CALL':<16} | {'SAHAM':<8} | {'AKSI':<5} | {'ENTRY':<10} | {'STOP LOSS':<10} | {'TAKE PROFIT':<12} | {'STATUS':<15} | {'PNL (%)':<8}")
    print("="*95)

    wins = 0
    losses = 0
    opens = 0

    for c in all_calls:
        clean_ticker = c['ticker'].replace('.JK', '')
        status = c['outcome']
        if 'WIN' in status:
            wins += 1
            status_str = "🟢 TP HIT"
        elif 'LOSS' in status:
            losses += 1
            status_str = "🔴 SL HIT"
        else:
            opens += 1
            status_str = "🟡 FLOATING"

        pnl_str = f"+{c['pnl_pct']}%" if c['pnl_pct'] > 0 else f"{c['pnl_pct']}%"
        print(f"{c['call_time']:<16} | {clean_ticker:<8} | {c['type']:<5} | {c['entry_price']:<10} | {c['sl']:<10} | {c['tp']:<12} | {status_str:<15} | {pnl_str:<8}")

    # Simpan hasil lengkap ke file Markdown
    md_content = []
    md_content.append("# 📊 LAPORAN BACKTEST SINYAL SAHAM 2 BULAN KEBELAKANG (JULI - SEPTEMBER 2026)")
    md_content.append(f"**Tanggal Pengujian:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    md_content.append(f"**Metode:** Institutional Smart Money Concepts (BOS, Order Block, FVG, Confluence Score & Risk/Reward 1:2.0)")
    md_content.append("\n---\n")
    md_content.append(f"### 📈 Ringkasan Performa Keseluruhan:")
    total_closed = wins + losses
    win_rate = (wins / total_closed * 100) if total_closed > 0 else 0
    md_content.append(f"- **Total Sinyal di-Call:** {len(all_calls)} Sinyal")
    md_content.append(f"- **Hit Take Profit (TP):** {wins} Trade ({win_rate:.1f}% Win Rate)")
    md_content.append(f"- **Hit Stop Loss (SL):** {losses} Trade")
    md_content.append(f"- **Posisi Masih Berjalan (Open):** {opens} Trade")
    md_content.append("\n---\n")

    # Kelompokkan per saham
    from collections import defaultdict
    grouped = defaultdict(list)
    for c in all_calls:
        clean_ticker = c['ticker'].replace('.JK', '')
        grouped[clean_ticker].append(c)

    for ticker, trades_list in grouped.items():
        t_wins = sum(1 for t in trades_list if 'WIN' in t['outcome'])
        t_losses = sum(1 for t in trades_list if 'LOSS' in t['outcome'])
        t_open = sum(1 for t in trades_list if 'OPEN' in t['outcome'])
        t_closed = t_wins + t_losses
        t_wr = (t_wins / t_closed * 100) if t_closed > 0 else 0

        md_content.append(f"## 📌 Saham: **${ticker}**")
        md_content.append(f"- Total Call: **{len(trades_list)}** | Win Rate: **{t_wr:.1f}%** (TP: {t_wins} | SL: {t_losses} | Open: {t_open})")
        md_content.append("\n| Tanggal Call | Aksi | Entry | Stop Loss (SL) | Take Profit (TP) | Target Gain | Status Hasil |")
        md_content.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |")

        for t in trades_list:
            status = t['outcome']
            if 'WIN' in status:
                st_label = f"🟢 **HIT TP (+{t['pnl_pct']}%)**"
            elif 'LOSS' in status:
                st_label = f"🔴 **HIT SL ({t['pnl_pct']}%)**"
            else:
                p_prefix = "+" if t['pnl_pct'] > 0 else ""
                st_label = f"🟡 **OPEN ({p_prefix}{t['pnl_pct']}%)**"

            # Hitung target gain saat TP
            if t['type'] == 'BUY':
                gain_tp = round(((t['tp'] - t['entry_price']) / t['entry_price']) * 100, 2)
            else:
                gain_tp = round(((t['entry_price'] - t['tp']) / t['entry_price']) * 100, 2)

            md_content.append(f"| {t['call_time']} | **{t['type']}** | `{t['entry_price']}` | `{t['sl']}` | `{t['tp']}` | +{gain_tp}% | {st_label} |")
        md_content.append("\n")

    report_path = "backtest_saham_2bulan.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_content))
    print(f"\n[OK] Laporan lengkap tersimpan di: {report_path}")

