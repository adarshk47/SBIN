"""Data fetcher using yfinance — no auth, no IP restrictions."""
import logging
from datetime import datetime, timedelta
import pandas as pd
import yfinance as yf
import pytz

logger = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")

SYMBOLS = {
    "SBIN":  {"ticker": "SBIN.NS",  "name": "State Bank of India"},
    "NIFTY": {"ticker": "^NSEI",    "name": "Nifty 50"},
}

# yfinance interval → (yf_period_for_live, max_history_days)
INTERVAL_MAP = {
    "1m":  ("1m",  "5d",    7),
    "5m":  ("5m",  "5d",    60),
    "15m": ("15m", "5d",    60),
    "1h":  ("60m", "30d",   730),
    "1d":  ("1d",  "max",   1825),
}


def get_ltp(symbol: str) -> dict:
    ticker = SYMBOLS[symbol]["ticker"]
    try:
        t    = yf.Ticker(ticker)
        info = t.fast_info
        ltp  = float(info.last_price or 0)
        prev = float(info.previous_close or 0)
        return {
            "symbol": symbol,
            "ltp":    round(ltp, 2),
            "open":   round(float(info.open or 0), 2),
            "high":   round(float(info.day_high or 0), 2),
            "low":    round(float(info.day_low or 0), 2),
            "close":  round(prev, 2),
        }
    except Exception as e:
        logger.error("LTP error %s: %s", symbol, e)
    return {}


def get_candles(symbol: str, interval: str, days: int = 5) -> list:
    ticker = SYMBOLS[symbol]["ticker"]
    yf_interval, _, max_days = INTERVAL_MAP.get(interval, ("5m", "5d", 60))
    days = min(days, max_days)

    period = f"{max(days, 5)}d" if interval != "1d" else "2y"
    try:
        df = yf.download(
            ticker,
            period=period,
            interval=yf_interval,
            progress=False,
            auto_adjust=True,
        )
        if df.empty:
            logger.warning("No data %s/%s", symbol, interval)
            return []

        # Flatten multi-index columns if present
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df = df.reset_index()
        time_col = "Datetime" if "Datetime" in df.columns else "Date"
        df = df.rename(columns={time_col: "time", "Open": "open", "High": "high",
                                 "Low": "low", "Close": "close", "Volume": "volume"})
        df["time"] = pd.to_datetime(df["time"])
        if df["time"].dt.tz is None:
            df["time"] = df["time"].dt.tz_localize("UTC").dt.tz_convert(IST)
        else:
            df["time"] = df["time"].dt.tz_convert(IST)

        df = df.sort_values("time").dropna(subset=["close"])

        candles = []
        for _, row in df.iterrows():
            candles.append({
                "time":   row["time"].isoformat(),
                "open":   round(float(row["open"]),   2),
                "high":   round(float(row["high"]),   2),
                "low":    round(float(row["low"]),    2),
                "close":  round(float(row["close"]),  2),
                "volume": round(float(row.get("volume", 0) or 0), 0),
            })
        return candles
    except Exception as e:
        logger.error("Candle error %s/%s: %s", symbol, interval, e)
    return []


def get_daily_candles(symbol: str, days: int = 90) -> list:
    return get_candles(symbol, "1d", days=days)
