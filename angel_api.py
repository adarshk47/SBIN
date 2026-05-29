"""Angel One SmartAPI — pure requests implementation (no smartapi-python package)"""
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
    "Content-Type":    "application/json",
    "Accept":          "application/json",
    "X-UserType":      "USER",
    "X-SourceID":      "WEB",
    "X-ClientLocalIP": "127.0.0.1",
    "X-ClientPublicIP":"127.0.0.1",
    "X-MACAddress":    "00:00:00:00:00:00",
    "X-PrivateKey":    ANGEL_API_KEY,
}


class AngelOneAPI:
    def __init__(self):
        self._jwt   = None
        self._auth_time = None
        self._session_valid_for = 3500  # ~1 hour

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
                json=payload, headers=HEADERS_BASE, timeout=10
            )
            data = r.json()
            if data.get("status") and data.get("data", {}).get("jwtToken"):
                self._jwt = data["data"]["jwtToken"]
                self._auth_time = time.time()
                logger.info("Angel One auth success")
                return True
            logger.error("Auth failed: %s", data.get("message"))
        except Exception as e:
            logger.error("Auth error: %s", e)
        return False

    def _ensure_auth(self):
        if not self._jwt or (time.time() - (self._auth_time or 0) > self._session_valid_for):
            self.authenticate()

    def _auth_headers(self) -> dict:
        return {**HEADERS_BASE, "Authorization": f"Bearer {self._jwt}"}

    # ── LTP ─────────────────────────────────────────────
    def get_ltp(self, symbol: str) -> dict:
        self._ensure_auth()
        info = SYMBOLS[symbol]
        trading_sym = "Nifty 50" if symbol == "NIFTY" else f"{symbol}-EQ"
        payload = {
            "exchange":      info["exchange"],
            "tradingsymbol": trading_sym,
            "symboltoken":   info["token"],
        }
        try:
            r = requests.post(
                f"{BASE_URL}/rest/secure/angelbroking/market/v1/getLtp",
                json=payload, headers=self._auth_headers(), timeout=10
            )
            data = r.json()
            if data.get("status") and data.get("data"):
                d = data["data"]
                return {
                    "symbol": symbol,
                    "ltp":    float(d.get("ltp",   0)),
                    "open":   float(d.get("open",  0)),
                    "high":   float(d.get("high",  0)),
                    "low":    float(d.get("low",   0)),
                    "close":  float(d.get("close", 0)),
                }
        except Exception as e:
            logger.error("LTP error %s: %s", symbol, e)
        return {}

    # ── Candles ─────────────────────────────────────────
    def get_candles(self, symbol: str, interval: str, days: int = 5) -> list:
        self._ensure_auth()
        info = SYMBOLS[symbol]
        angel_interval = INTERVAL_MAP.get(interval, "FIVE_MINUTE")

        now = datetime.now(IST)
        if interval in ("1m", "5m"):
            from_dt = now - timedelta(days=min(days, 3))
        elif interval == "15m":
            from_dt = now - timedelta(days=min(days, 10))
        elif interval == "1h":
            from_dt = now - timedelta(days=min(days, 30))
        else:
            from_dt = now - timedelta(days=min(days, 365))

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
                json=payload, headers=self._auth_headers(), timeout=15
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
            logger.warning("Candle fetch failed %s/%s: %s", symbol, interval, data.get("message"))
        except Exception as e:
            logger.error("Candle error %s/%s: %s", symbol, interval, e)
        return []

    def get_daily_candles(self, symbol: str, days: int = 90) -> list:
        return self.get_candles(symbol, "1d", days=days)
