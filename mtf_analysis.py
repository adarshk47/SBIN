"""Multi-timeframe trend analysis from 1-minute base candles."""
import pandas as pd
import numpy as np
from analysis import ema


WINDOWS = {
    "5 Min":  5,
    "10 Min": 10,
    "15 Min": 15,
    "1 Hour": 60,
    "2 Hour": 120,
}


def _slope(series: pd.Series) -> float:
    """Linear regression slope over last N values (normalised %)."""
    n = len(series)
    if n < 2:
        return 0.0
    x = np.arange(n, dtype=float)
    y = series.values.astype(float)
    m = np.polyfit(x, y, 1)[0]
    return float(m / y[0] * 100) if y[0] != 0 else 0.0


def mtf_trend(candles_1m: list) -> list:
    """
    Returns list of dicts, one per window, describing trend.
    candles_1m must be sorted ascending (oldest first).
    """
    if not candles_1m or len(candles_1m) < 5:
        return []

    df = pd.DataFrame(candles_1m)
    df["time"]  = pd.to_datetime(df["time"])
    df["close"] = df["close"].astype(float)
    df["high"]  = df["high"].astype(float)
    df["low"]   = df["low"].astype(float)
    df["volume"]= df.get("volume", pd.Series(0, index=df.index)).astype(float)

    # EMA on full series for slope context
    df["ema9"]  = ema(df["close"], 9)
    df["ema21"] = ema(df["close"], 21)

    current_price = float(df["close"].iloc[-1])
    results = []

    for label, n in WINDOWS.items():
        if len(df) < n:
            window = df
        else:
            window = df.iloc[-n:]

        open_price  = float(window["close"].iloc[0])
        close_price = float(window["close"].iloc[-1])
        high_price  = float(window["high"].max())
        low_price   = float(window["low"].min())

        chg     = close_price - open_price
        chg_pct = (chg / open_price * 100) if open_price else 0

        # Trend strength via linear slope on closes
        slope = _slope(window["close"])

        # EMA alignment at end of window
        ema9_last  = float(df["ema9"].iloc[-1])
        ema21_last = float(df["ema21"].iloc[-1])
        price_above_ema9  = current_price > ema9_last
        price_above_ema21 = current_price > ema21_last

        # Volume trend
        vol_avg = float(window["volume"].mean())

        # Score: +1 price up, +1 slope up, +1 above EMA9, +1 above EMA21
        score = (
            (1 if chg > 0 else -1) +
            (1 if slope > 0 else -1) +
            (1 if price_above_ema9 else -1) +
            (1 if price_above_ema21 else -1)
        )

        if score >= 3:
            trend, arrow, color = "STRONG UP", "↑↑", "#00e676"
        elif score >= 1:
            trend, arrow, color = "UP", "↑",  "#3fb950"
        elif score <= -3:
            trend, arrow, color = "STRONG DOWN", "↓↓", "#ff1744"
        elif score <= -1:
            trend, arrow, color = "DOWN", "↓", "#f85149"
        else:
            trend, arrow, color = "SIDEWAYS", "→", "#d29922"

        results.append({
            "label":      label,
            "n":          n,
            "trend":      trend,
            "arrow":      arrow,
            "color":      color,
            "score":      score,
            "chg_pct":    round(chg_pct, 3),
            "chg":        round(chg, 2),
            "high":       round(high_price, 2),
            "low":        round(low_price, 2),
            "slope":      round(slope, 4),
            "vol_avg":    round(vol_avg, 0),
            "open_price": round(open_price, 2),
        })

    return results


def overall_bias(mtf: list) -> dict:
    """Aggregate all timeframes into a single market bias."""
    if not mtf:
        return {"bias": "UNKNOWN", "color": "#8b949e", "bull": 0, "bear": 0, "neutral": 0}

    bull = sum(1 for r in mtf if "UP"   in r["trend"])
    bear = sum(1 for r in mtf if "DOWN" in r["trend"])
    neut = sum(1 for r in mtf if r["trend"] == "SIDEWAYS")

    if bull >= 4:
        bias, color = "BULLISH", "#00e676"
    elif bull == 3:
        bias, color = "MILD BULLISH", "#3fb950"
    elif bear >= 4:
        bias, color = "BEARISH", "#ff1744"
    elif bear == 3:
        bias, color = "MILD BEARISH", "#f85149"
    else:
        bias, color = "MIXED / SIDEWAYS", "#d29922"

    return {"bias": bias, "color": color, "bull": bull, "bear": bear, "neutral": neut}
