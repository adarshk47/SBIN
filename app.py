import logging
import json
from datetime import datetime
import pytz
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS
from config import FLASK_SECRET_KEY, IST_TZ
from angel_api import AngelOneAPI
from analysis import to_df, add_indicators, generate_signals, correlation_analysis, pivot_points

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = FLASK_SECRET_KEY
CORS(app)

angel = AngelOneAPI()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/live")
def live_prices():
    sbin  = angel.get_ltp("SBIN")
    nifty = angel.get_ltp("NIFTY")
    ist   = pytz.timezone(IST_TZ)
    return jsonify({
        "SBIN":  sbin,
        "NIFTY": nifty,
        "time":  datetime.now(ist).strftime("%H:%M:%S"),
        "date":  datetime.now(ist).strftime("%d %b %Y"),
    })


@app.route("/api/candles/<symbol>/<interval>")
def candles(symbol: str, interval: str):
    symbol = symbol.upper()
    days   = int(request.args.get("days", 5))
    raw    = angel.get_candles(symbol, interval, days=days)
    if not raw:
        return jsonify({"error": "No data", "candles": [], "indicators": {}})

    df = to_df(raw)
    df = add_indicators(df)

    # Convert to JSON-serializable list
    records = []
    for _, row in df.iterrows():
        r = {k: (None if hasattr(v, "__float__") and str(v) == "nan" else
                 (v.isoformat() if hasattr(v, "isoformat") else
                  (float(v) if hasattr(v, "__float__") else v)))
             for k, v in row.items()}
        records.append(r)

    signals = generate_signals(df)
    pivots  = {}
    if interval == "1d":
        pivots = pivot_points(df)

    return jsonify({
        "symbol":    symbol,
        "interval":  interval,
        "candles":   records,
        "signals":   signals,
        "pivots":    pivots,
        "count":     len(records),
    })


@app.route("/api/analysis/<symbol>/<interval>")
def analysis(symbol: str, interval: str):
    symbol = symbol.upper()
    raw    = angel.get_candles(symbol, interval, days=5)
    df     = to_df(raw)
    df     = add_indicators(df)
    sigs   = generate_signals(df)

    if not df.empty:
        last = df.iloc[-1]
        sigs["current_price"] = float(last["close"])
        sigs["ema9"]  = float(last.get("ema9", 0) or 0)
        sigs["ema21"] = float(last.get("ema21", 0) or 0)
        sigs["ema50"] = float(last.get("ema50", 0) or 0)
        sigs["bb_upper"] = float(last.get("bb_upper", 0) or 0)
        sigs["bb_lower"] = float(last.get("bb_lower", 0) or 0)
        sigs["vwap"]  = float(last["vwap"]) if "vwap" in df.columns and not str(last.get("vwap")) == "nan" else None

    return jsonify(sigs)


@app.route("/api/correlation")
def correlation():
    days  = int(request.args.get("days", 90))
    sbin  = angel.get_daily_candles("SBIN",  days=days)
    nifty = angel.get_daily_candles("NIFTY", days=days)
    result = correlation_analysis(sbin, nifty)
    return jsonify(result)


@app.route("/api/daily_compare")
def daily_compare():
    sbin  = angel.get_daily_candles("SBIN",  days=60)
    nifty = angel.get_daily_candles("NIFTY", days=60)
    result = correlation_analysis(sbin, nifty)
    return jsonify(result.get("daily_data", []))


if __name__ == "__main__":
    logger.info("Authenticating with Angel One...")
    if not angel.authenticate():
        logger.error("Angel One auth failed — check credentials in .env")
    app.run(host="0.0.0.0", port=5000, debug=False)
