import pyotp
import time
import logging
from datetime import datetime, timedelta
import pytz
from SmartApi import SmartConnect
from config import (
    ANGEL_API_KEY, ANGEL_CLIENT_ID, ANGEL_PASSWORD,
    ANGEL_TOTP_SECRET, SYMBOLS, INTERVAL_MAP, IST_TZ
)

logger = logging.getLogger(__name__)
IST = pytz.timezone(IST_TZ)


class AngelOneAPI:
    def __init__(self):
        self.obj = SmartConnect(api_key=ANGEL_API_KEY)
        self._auth_data = None
        self._auth_time = None
        self._session_valid_for = 3600  # re-auth every hour

    def _totp(self):
        return pyotp.TOTP(ANGEL_TOTP_SECRET).now()

    def authenticate(self):
        try:
            data = self.obj.generateSession(
                ANGEL_CLIENT_ID, ANGEL_PASSWORD, self._totp()
            )
            if data and data.get("status"):
                self._auth_data = data["data"]
                self._auth_time = time.time()
                logger.info("Angel One auth success")
                return True
            logger.error("Auth failed: %s", data)
            return False
        except Exception as e:
            logger.error("Auth exception: %s", e)
            return False

    def _ensure_auth(self):
        if (not self._auth_time or
                time.time() - self._auth_time > self._session_valid_for):
            self.authenticate()

    def get_ltp(self, symbol: str) -> dict:
        self._ensure_auth()
        info = SYMBOLS[symbol]
        try:
            resp = self.obj.ltpData(info["exchange"], symbol + "-EQ" if symbol != "NIFTY" else "Nifty 50", info["token"])
            if resp and resp.get("status"):
                d = resp["data"]
                return {
                    "symbol": symbol,
                    "ltp": d.get("ltp", 0),
                    "open": d.get("open", 0),
                    "high": d.get("high", 0),
                    "low": d.get("low", 0),
                    "close": d.get("close", 0),
                }
        except Exception as e:
            logger.error("LTP error for %s: %s", symbol, e)
        return {}

    def get_candles(self, symbol: str, interval: str, days: int = 5) -> list:
        """
        Returns list of OHLCV dicts sorted ascending.
        interval: '1m','5m','15m','1h','1d'
        """
        self._ensure_auth()
        info = SYMBOLS[symbol]
        angel_interval = INTERVAL_MAP.get(interval, "FIVE_MINUTE")

        now = datetime.now(IST)
        # For intraday intervals limit lookback to avoid huge data
        if interval in ("1m", "5m"):
            from_dt = now - timedelta(days=min(days, 3))
        elif interval == "15m":
            from_dt = now - timedelta(days=min(days, 10))
        elif interval == "1h":
            from_dt = now - timedelta(days=min(days, 30))
        else:
            from_dt = now - timedelta(days=min(days, 365))

        fmt = "%Y-%m-%d %H:%M"
        params = {
            "exchange": info["exchange"],
            "symboltoken": info["token"],
            "interval": angel_interval,
            "fromdate": from_dt.strftime(fmt),
            "todate": now.strftime(fmt),
        }

        try:
            resp = self.obj.getCandleData(params)
            if resp and resp.get("status") and resp.get("data"):
                candles = []
                for row in resp["data"]:
                    # row: [timestamp, open, high, low, close, volume]
                    candles.append({
                        "time": row[0],
                        "open": float(row[1]),
                        "high": float(row[2]),
                        "low":  float(row[3]),
                        "close": float(row[4]),
                        "volume": float(row[5]) if len(row) > 5 else 0,
                    })
                return candles
        except Exception as e:
            logger.error("Candle error for %s/%s: %s", symbol, interval, e)
        return []

    def get_daily_candles(self, symbol: str, days: int = 90) -> list:
        return self.get_candles(symbol, "1d", days=days)
