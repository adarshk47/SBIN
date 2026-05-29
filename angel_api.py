"""Angel One SmartAPI — pure requests, no external SDK needed"""
import pyotp
import time
import logging
import requests
from datetime import datetime, timedelta
import pytz
from config import (
    ANGEL_API_KEY, ANGEL_CLIENT_ID, ANGEL_PASSWORD,
    ANGEL_TOTP_SECRET, SYMBOLS, INTERVAL_MAP, IST_TZ
)

logger = logging.getLogger(__name__)
IST = pytz.timezone(IST_TZ)

BASE_URL = "https://apiconnect.angelone.in"

HEADERS_BASE = {
    "Content-Type":     "application/json",
    "Accept":           "application/json",
    "X-UserType":       "USER",
    "X-SourceID":       "WEB",
    "X-ClientLocalIP":  "127.0.0.1",
    "X-ClientPublicIP": "127.0.0.1",
    "X-MACAddress":     "00:00:00:00:00:00",
    "X-PrivateKey":     ANGEL_API_KEY,
}

# Angel One limits: max candles per request by interval
MAX_DAYS = {
    "1m": 30, "5m": 100, "15m": 100, "1h": 400, "1d": 2000,
}


class AngelOneAPI:
    def __init__(self):
        self._jwt        = None
        self._auth_time  = None
        self._auth_valid = 3500   # refresh before 1-hour expiry

    # ── Auth ────────────────────────────────────────────
    def _totp(self):
        return pyotp.TOTP(ANGEL_TOTP_SECRET).now()

    def authenticate(self) -> bool:
        payload = {
            "clientcode": ANGEL_CLIENT_ID,
            "password":   ANGEL_PASSWORD,
            "totp":       self._totp(),
        }
        try:
            r = requests.post(
                f"{BASE_URL}/rest/auth/angelbroking/user/v1/loginByPassword",
                json=payload, headers=HEADERS_BASE, timeout=15,
            )
            data = r.json()
            if data.get("status") and data.get("data", {}).get("jwtToken"):
                self._jwt       = data["data"]["jwtToken"]
                self._auth_time = time.time()
                logger.info("Angel One auth success")
                return True
            logger.error("Auth failed: %s", data.get("message"))
            return False
        except Exception as e:
            logger.error("Auth error: %s", e)
            return False

    def _ensure_auth(self):
        if not self._jwt or (time.time() - (self._auth_time or 0) > self._auth_valid):
            self.authenticate()

    def _headers(self) -> dict:
        return {**HEADERS_BASE, "Authorization": f"Bearer {self._jwt}"}

    def auth_status(self) -> dict:
        """Return auth state for UI display."""
        ok = bool(self._jwt and (time.time() - (self._auth_time or 0) < self._auth_valid))
        return {"connected": ok, "jwt_set": bool(self._jwt)}

    # ── LTP ─────────────────────────────────────────────
    def get_ltp(self, symbol: str) -> dict:
        self._ensure_auth()
        info = SYMBOLS[symbol]
        trading_sym = "Nifty 50" if symbol == "NIFTY" else f"{symbol}-EQ"
        try:
            r = requests.post(
                f"{BASE_URL}/rest/secure/angelbroking/market/v1/getLtp",
                json={"exchange": info["exchange"], "tradingsymbol": trading_sym,
                      "symboltoken": info["token"]},
                headers=self._headers(), timeout=10,
            )
            data = r.json()
            if data.get("status") and data.get("data"):
                d = data["data"]
                return {
                    "symbol": symbol,
                    "ltp":   float(d.get("ltp",   0)),
                    "open":  float(d.get("open",  0)),
                    "high":  float(d.get("high",  0)),
                    "low":   float(d.get("low",   0)),
                    "close": float(d.get("close", 0)),
                }
            logger.warning("LTP empty for %s: %s", symbol, data.get("message"))
        except Exception as e:
            logger.error("LTP error %s: %s", symbol, e)
        return {}

    # ── Candles ─────────────────────────────────────────
    def get_candles(self, symbol: str, interval: str, days: int = 5) -> list:
        self._ensure_auth()
        info = SYMBOLS[symbol]
        angel_interval = INTERVAL_MAP.get(interval, "FIVE_MINUTE")

        now     = datetime.now(IST)
        cap     = MAX_DAYS.get(interval, 100)
        days    = min(days, cap)

        # Always go back at least 7 calendar days to cover weekends/holidays
        # so we always get some data even if market was closed recently
        lookback = max(days, 7) if interval == "1d" else days
        from_dt  = now - timedelta(days=lookback)

        # For intraday: start from market open of from_dt date
        if interval != "1d":
            from_dt = from_dt.replace(hour=9, minute=15, second=0, microsecond=0)

        fmt = "%Y-%m-%d %H:%M"
        payload = {
            "exchange":    info["exchange"],
            "symboltoken": info["token"],
            "interval":    angel_interval,
            "fromdate":    from_dt.strftime(fmt),
            "todate":      now.strftime(fmt),
        }

        try:
            r = requests.post(
                f"{BASE_URL}/rest/secure/angelbroking/historical/v1/getCandleData",
                json=payload, headers=self._headers(), timeout=20,
            )
            data = r.json()
            if data.get("status") and data.get("data"):
                candles = []
                for row in data["data"]:
                    candles.append({
                        "time":   row[0],
                        "open":   float(row[1]),
                        "high":   float(row[2]),
                        "low":    float(row[3]),
                        "close":  float(row[4]),
                        "volume": float(row[5]) if len(row) > 5 else 0,
                    })
                return candles
            logger.warning("Candle failed %s/%s: %s", symbol, interval, data.get("message"))
        except Exception as e:
            logger.error("Candle error %s/%s: %s", symbol, interval, e)
        return []

    def get_daily_candles(self, symbol: str, days: int = 90) -> list:
        return self.get_candles(symbol, "1d", days=days)
