"""OI (Open Interest) fetcher via yfinance options chain."""
import logging
from datetime import datetime
import pytz
import yfinance as yf
import pandas as pd

logger = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")


def fetch_oi_snapshot(symbol: str = "SBIN") -> dict | None:
    """
    Fetch current options OI for nearest expiry.
    Returns PCR, total call OI, total put OI, and ATM strike details.
    """
    ticker_sym = "SBIN.NS" if symbol == "SBIN" else "^NSEI"
    try:
        t = yf.Ticker(ticker_sym)
        exp_dates = t.options
        if not exp_dates:
            return None

        # Use nearest expiry
        chain = t.option_chain(exp_dates[0])
        calls = chain.calls[["strike", "openInterest", "volume", "lastPrice"]].copy()
        puts  = chain.puts [["strike", "openInterest", "volume", "lastPrice"]].copy()

        calls = calls.dropna(subset=["openInterest"])
        puts  = puts.dropna(subset=["openInterest"])

        total_call_oi  = int(calls["openInterest"].sum())
        total_put_oi   = int(puts["openInterest"].sum())
        total_call_vol = int(calls["volume"].fillna(0).sum())
        total_put_vol  = int(puts["volume"].fillna(0).sum())

        pcr_oi  = round(total_put_oi  / total_call_oi,  3) if total_call_oi  else 0
        pcr_vol = round(total_put_vol / total_call_vol, 3) if total_call_vol else 0

        # ATM strike (closest to LTP)
        ltp = float(t.fast_info.last_price or 0)
        atm = None
        if ltp and not calls.empty:
            idx  = (calls["strike"] - ltp).abs().idxmin()
            atm_strike = float(calls.loc[idx, "strike"])
            atm_call_oi = int(calls.loc[idx, "openInterest"])
            atm_put_row = puts.iloc[(puts["strike"] - atm_strike).abs().argsort()[:1]]
            atm_put_oi  = int(atm_put_row["openInterest"].values[0]) if not atm_put_row.empty else 0
            atm = {
                "strike":   atm_strike,
                "call_oi":  atm_call_oi,
                "put_oi":   atm_put_oi,
            }

        # Top OI strikes (max pain indicators)
        top_call = calls.nlargest(3, "openInterest")[["strike","openInterest"]].to_dict("records")
        top_put  = puts.nlargest(3, "openInterest")[["strike","openInterest"]].to_dict("records")

        return {
            "time":           datetime.now(IST).strftime("%H:%M:%S"),
            "expiry":         exp_dates[0],
            "ltp":            round(ltp, 2),
            "total_call_oi":  total_call_oi,
            "total_put_oi":   total_put_oi,
            "total_call_vol": total_call_vol,
            "total_put_vol":  total_put_vol,
            "pcr_oi":         pcr_oi,
            "pcr_vol":        pcr_vol,
            "atm":            atm,
            "top_call_strikes": top_call,
            "top_put_strikes":  top_put,
        }
    except Exception as e:
        logger.error("OI fetch error %s: %s", symbol, e)
        return None


def pcr_sentiment(pcr: float) -> tuple[str, str]:
    """Return (label, color) for a PCR value."""
    if pcr == 0:
        return "—", "#8b949e"
    if pcr > 1.3:
        return "BEARISH", "#f85149"
    if pcr > 1.1:
        return "MILD BEARISH", "#ff7b00"
    if pcr < 0.7:
        return "BULLISH", "#3fb950"
    if pcr < 0.9:
        return "MILD BULLISH", "#69f0ae"
    return "NEUTRAL", "#d29922"


def oi_change(history: list) -> dict:
    """Compute OI delta between last two snapshots."""
    if len(history) < 2:
        return {}
    prev = history[-2]
    curr = history[-1]
    return {
        "call_oi_chg": curr["total_call_oi"] - prev["total_call_oi"],
        "put_oi_chg":  curr["total_put_oi"]  - prev["total_put_oi"],
        "pcr_chg":     round(curr["pcr_oi"]  - prev["pcr_oi"], 3),
    }
