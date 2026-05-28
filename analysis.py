import numpy as np
import pandas as pd
from typing import List, Dict, Any


def to_df(candles: List[Dict]) -> pd.DataFrame:
    df = pd.DataFrame(candles)
    if df.empty:
        return df
    df["time"] = pd.to_datetime(df["time"])
    df = df.sort_values("time").reset_index(drop=True)
    return df


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, adjust=False).mean()
    avg_loss = loss.ewm(com=period - 1, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def macd(series: pd.Series):
    fast = ema(series, 12)
    slow = ema(series, 26)
    line = fast - slow
    signal = ema(line, 9)
    hist = line - signal
    return line, signal, hist


def bollinger(series: pd.Series, period: int = 20, std: float = 2.0):
    mid = series.rolling(period).mean()
    sd = series.rolling(period).std()
    return mid + std * sd, mid, mid - std * sd


def vwap(df: pd.DataFrame) -> pd.Series:
    """Intraday VWAP - resets each day."""
    df = df.copy()
    df["date"] = df["time"].dt.date
    df["tp"] = (df["high"] + df["low"] + df["close"]) / 3
    df["tpv"] = df["tp"] * df["volume"]
    df["cum_tpv"] = df.groupby("date")["tpv"].cumsum()
    df["cum_vol"] = df.groupby("date")["volume"].cumsum()
    return df["cum_tpv"] / df["cum_vol"].replace(0, np.nan)


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    hl = df["high"] - df["low"]
    hc = (df["high"] - df["close"].shift()).abs()
    lc = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.ewm(com=period - 1, adjust=False).mean()


def pivot_points(df: pd.DataFrame) -> Dict[str, float]:
    """Classic pivot points from last completed day."""
    if df.empty or len(df) < 2:
        return {}
    last = df.iloc[-2] if len(df) > 1 else df.iloc[-1]
    H, L, C = last["high"], last["low"], last["close"]
    P = (H + L + C) / 3
    return {
        "P":  round(P, 2),
        "R1": round(2 * P - L, 2),
        "R2": round(P + (H - L), 2),
        "R3": round(H + 2 * (P - L), 2),
        "S1": round(2 * P - H, 2),
        "S2": round(P - (H - L), 2),
        "S3": round(L - 2 * (H - P), 2),
    }


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or len(df) < 30:
        return df
    c = df["close"]
    df["ema9"]  = ema(c, 9).round(2)
    df["ema21"] = ema(c, 21).round(2)
    df["ema50"] = ema(c, 50).round(2)
    df["rsi"]   = rsi(c, 14).round(2)
    ml, ms, mh  = macd(c)
    df["macd"]       = ml.round(2)
    df["macd_signal"]= ms.round(2)
    df["macd_hist"]  = mh.round(2)
    bb_u, bb_m, bb_l = bollinger(c)
    df["bb_upper"] = bb_u.round(2)
    df["bb_mid"]   = bb_m.round(2)
    df["bb_lower"] = bb_l.round(2)
    df["atr"]      = atr(df, 14).round(2)
    if "volume" in df.columns and df["volume"].sum() > 0:
        df["vwap"] = vwap(df).round(2)
    return df


def generate_signals(df: pd.DataFrame) -> Dict[str, Any]:
    """Generate buy/sell signals from last candle."""
    if df.empty or len(df) < 50:
        return {"signal": "WAIT", "strength": 0, "reasons": []}

    last = df.iloc[-1]
    prev = df.iloc[-2]
    score = 0
    reasons = []

    # EMA trend
    if last["ema9"] > last["ema21"] > last["ema50"]:
        score += 2
        reasons.append("EMA bullish stack (9>21>50)")
    elif last["ema9"] < last["ema21"] < last["ema50"]:
        score -= 2
        reasons.append("EMA bearish stack (9<21<50)")

    # Price vs EMA21
    if last["close"] > last["ema21"]:
        score += 1
        reasons.append("Price above EMA21")
    else:
        score -= 1
        reasons.append("Price below EMA21")

    # RSI
    if 40 < last["rsi"] < 60:
        reasons.append(f"RSI neutral ({last['rsi']:.0f})")
    elif last["rsi"] > 70:
        score -= 1
        reasons.append(f"RSI overbought ({last['rsi']:.0f})")
    elif last["rsi"] < 30:
        score += 1
        reasons.append(f"RSI oversold ({last['rsi']:.0f})")
    elif last["rsi"] > 55:
        score += 1
        reasons.append(f"RSI bullish ({last['rsi']:.0f})")
    elif last["rsi"] < 45:
        score -= 1
        reasons.append(f"RSI bearish ({last['rsi']:.0f})")

    # MACD crossover
    if prev["macd"] < prev["macd_signal"] and last["macd"] > last["macd_signal"]:
        score += 2
        reasons.append("MACD bullish crossover")
    elif prev["macd"] > prev["macd_signal"] and last["macd"] < last["macd_signal"]:
        score -= 2
        reasons.append("MACD bearish crossover")
    elif last["macd"] > last["macd_signal"]:
        score += 1
        reasons.append("MACD above signal")
    else:
        score -= 1
        reasons.append("MACD below signal")

    # Bollinger position
    if last["close"] > last["bb_upper"]:
        score -= 1
        reasons.append("Price above BB upper (overextended)")
    elif last["close"] < last["bb_lower"]:
        score += 1
        reasons.append("Price below BB lower (bounce zone)")

    # VWAP
    if "vwap" in df.columns and not pd.isna(last.get("vwap")):
        if last["close"] > last["vwap"]:
            score += 1
            reasons.append("Price above VWAP (bullish intraday)")
        else:
            score -= 1
            reasons.append("Price below VWAP (bearish intraday)")

    # Determine signal
    if score >= 4:
        signal, color = "STRONG BUY", "#00e676"
    elif score >= 2:
        signal, color = "BUY", "#69f0ae"
    elif score <= -4:
        signal, color = "STRONG SELL", "#ff1744"
    elif score <= -2:
        signal, color = "SELL", "#ff5252"
    else:
        signal, color = "NEUTRAL", "#ffeb3b"

    # Stop loss / target based on ATR
    atr_val = last.get("atr", 0)
    stop_loss = round(last["close"] - 1.5 * atr_val, 2) if score > 0 else round(last["close"] + 1.5 * atr_val, 2)
    target1   = round(last["close"] + 2.0 * atr_val, 2) if score > 0 else round(last["close"] - 2.0 * atr_val, 2)
    target2   = round(last["close"] + 3.0 * atr_val, 2) if score > 0 else round(last["close"] - 3.0 * atr_val, 2)

    return {
        "signal":     signal,
        "color":      color,
        "score":      score,
        "reasons":    reasons,
        "stop_loss":  stop_loss,
        "target1":    target1,
        "target2":    target2,
        "atr":        round(atr_val, 2),
        "rsi":        round(last.get("rsi", 0), 2),
        "macd":       round(last.get("macd", 0), 2),
        "macd_signal":round(last.get("macd_signal", 0), 2),
    }


def correlation_analysis(sbin_daily: list, nifty_daily: list) -> Dict[str, Any]:
    """Compare SBIN vs NIFTY daily returns and direction."""
    sdf = to_df(sbin_daily)
    ndf = to_df(nifty_daily)

    if sdf.empty or ndf.empty:
        return {}

    sdf["ret"] = sdf["close"].pct_change()
    ndf["ret"] = ndf["close"].pct_change()

    # Merge on date
    sdf["date"] = sdf["time"].dt.date
    ndf["date"] = ndf["time"].dt.date
    merged = pd.merge(
        sdf[["date", "ret", "close"]].rename(columns={"ret": "sbin_ret", "close": "sbin_close"}),
        ndf[["date", "ret", "close"]].rename(columns={"ret": "nifty_ret", "close": "nifty_close"}),
        on="date"
    ).dropna()

    if merged.empty or len(merged) < 5:
        return {}

    # Same direction days
    merged["same_dir"] = (
        (merged["sbin_ret"] > 0) & (merged["nifty_ret"] > 0) |
        (merged["sbin_ret"] < 0) & (merged["nifty_ret"] < 0)
    )
    total = len(merged)
    same  = int(merged["same_dir"].sum())
    corr  = float(merged["sbin_ret"].corr(merged["nifty_ret"]))

    # Beta
    cov  = float(merged["sbin_ret"].cov(merged["nifty_ret"]))
    var  = float(merged["nifty_ret"].var())
    beta = round(cov / var, 3) if var > 0 else 0

    # Last 30 / 60 days
    last30 = merged.tail(30)
    last60 = merged.tail(60)

    # Daily direction data for heatmap (last 30 days)
    daily_data = []
    for _, row in merged.tail(30).iterrows():
        daily_data.append({
            "date": str(row["date"]),
            "sbin_ret": round(float(row["sbin_ret"]) * 100, 2),
            "nifty_ret": round(float(row["nifty_ret"]) * 100, 2),
            "same_dir": bool(row["same_dir"]),
        })

    # Relative strength today
    recent = merged.tail(10)
    rs = float((recent["sbin_ret"].mean() - recent["nifty_ret"].mean()) * 100)

    return {
        "correlation": round(corr, 3),
        "beta": beta,
        "total_days": total,
        "same_dir_days": same,
        "same_dir_pct": round(same / total * 100, 1),
        "last30_same": int(last30["same_dir"].sum()),
        "last30_pct": round(last30["same_dir"].sum() / len(last30) * 100, 1),
        "last60_same": int(last60["same_dir"].sum()),
        "last60_pct": round(last60["same_dir"].sum() / len(last60) * 100, 1),
        "relative_strength_10d": round(rs, 3),
        "daily_data": daily_data,
    }
