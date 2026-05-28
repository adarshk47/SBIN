import os
from dotenv import load_dotenv

load_dotenv()

ANGEL_API_KEY     = os.environ.get("ANGEL_API_KEY", "")
ANGEL_SECRET_KEY  = os.environ.get("ANGEL_SECRET_KEY", "")
ANGEL_CLIENT_ID   = os.environ.get("ANGEL_CLIENT_ID", "")
ANGEL_PASSWORD    = os.environ.get("ANGEL_PASSWORD", "")
ANGEL_MPIN        = os.environ.get("ANGEL_MPIN", "")
ANGEL_TOTP_SECRET = os.environ.get("ANGEL_TOTP_SECRET", "")
FLASK_SECRET_KEY  = os.environ.get("FLASK_SECRET_KEY", "dev-secret")

# Angel One token IDs (NSE)
SYMBOLS = {
    "SBIN":   {"token": "3045",  "exchange": "NSE", "name": "State Bank of India"},
    "NIFTY":  {"token": "26000", "exchange": "NSE", "name": "Nifty 50"},
}

INTERVAL_MAP = {
    "1m":  "ONE_MINUTE",
    "5m":  "FIVE_MINUTE",
    "15m": "FIFTEEN_MINUTE",
    "1h":  "ONE_HOUR",
    "1d":  "ONE_DAY",
}

IST_TZ = "Asia/Kolkata"
MARKET_OPEN  = "09:15"
MARKET_CLOSE = "15:30"
