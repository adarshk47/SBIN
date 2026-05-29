import os
from dotenv import load_dotenv

load_dotenv()

def _get(key: str, fallback: str = "") -> str:
    """Read from Streamlit secrets first, then env vars, then fallback."""
    try:
        import streamlit as st
        val = st.secrets.get(key)
        if val:
            return str(val)
    except Exception:
        pass
    return os.environ.get(key, fallback)

ANGEL_API_KEY     = _get("ANGEL_API_KEY",     "LkKs5NJG")
ANGEL_SECRET_KEY  = _get("ANGEL_SECRET_KEY",  "600734be-7bf2-4bfe-a00c-a5972673d16d")
ANGEL_CLIENT_ID   = _get("ANGEL_CLIENT_ID",   "A114064")
ANGEL_PASSWORD    = _get("ANGEL_PASSWORD",     "Mahadev1@#")
ANGEL_MPIN        = _get("ANGEL_MPIN",         "1008")
ANGEL_TOTP_SECRET = _get("ANGEL_TOTP_SECRET",  "6IK5P2KWF3YULRMR6VSUVZZVLI")
FLASK_SECRET_KEY  = _get("FLASK_SECRET_KEY",   "sbin-secret-2024")

# Angel One NSE token IDs
SYMBOLS = {
    "SBIN":  {"token": "3045",  "exchange": "NSE", "name": "State Bank of India"},
    "NIFTY": {"token": "26000", "exchange": "NSE", "name": "Nifty 50"},
}

INTERVAL_MAP = {
    "1m":  "ONE_MINUTE",
    "5m":  "FIVE_MINUTE",
    "15m": "FIFTEEN_MINUTE",
    "1h":  "ONE_HOUR",
    "1d":  "ONE_DAY",
}

IST_TZ       = "Asia/Kolkata"
MARKET_OPEN  = "09:15"
MARKET_CLOSE = "15:30"
