"""SBIN Intraday Analysis Dashboard — Streamlit + yfinance"""
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
from datetime import datetime, timedelta
import time
import pytz

import data_fetcher as df_api
from analysis import to_df, add_indicators, generate_signals, correlation_analysis, pivot_points
from mtf_analysis import mtf_trend, overall_bias

st.set_page_config(
    page_title="SBIN Analyzer",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

IST = pytz.timezone("Asia/Kolkata")
REFRESH_EVERY = 60  # seconds

st.markdown("""
<style>
  .block-container { padding-top: 0.8rem; padding-bottom: 0.5rem; }
  .signal-card {
    padding: 14px; border-radius: 10px; text-align: center;
    border: 2px solid; margin-bottom: 8px;
  }
  .mtf-row {
    display: flex; justify-content: space-between; align-items: center;
    padding: 7px 10px; border-radius: 6px; margin-bottom: 4px;
    background: #161b22; border: 1px solid #30363d;
  }
  .mtf-label { color: #8b949e; font-size: 13px; font-weight: 600; min-width: 60px; }
  .mtf-arrow { font-size: 20px; font-weight: 900; min-width: 36px; text-align: center; }
  .mtf-trend { font-size: 12px; font-weight: 700; letter-spacing: 0.4px; min-width: 100px; }
  .mtf-chg   { font-size: 13px; font-weight: 600; font-variant-numeric: tabular-nums; text-align: right; }
  .metric-row {
    display: flex; justify-content: space-between; align-items: center;
    padding: 5px 0; border-bottom: 1px solid #1c2128; font-size: 13px;
  }
  .bias-box {
    padding: 10px 14px; border-radius: 8px; text-align: center;
    border: 2px solid; margin-bottom: 8px;
    font-size: 18px; font-weight: 800; letter-spacing: 0.5px;
  }
  .countdown-bar {
    height: 4px; border-radius: 2px; background: #1c2128;
    margin-top: 4px; overflow: hidden;
  }
  .countdown-fill {
    height: 100%; border-radius: 2px;
    background: linear-gradient(90deg, #58a6ff, #3fb950);
    transition: width 1s linear;
  }
  h1,h2,h3 { margin-bottom: 0 !important; }
  .stMetric label { font-size: 11px !important; }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════
#  SESSION STATE — track refresh timing
# ══════════════════════════════════════════════════════
if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = datetime.now()
if "refresh_count" not in st.session_state:
    st.session_state.refresh_count = 0

now_wall = datetime.now()
elapsed  = (now_wall - st.session_state.last_refresh).total_seconds()

# Auto-trigger rerun when REFRESH_EVERY seconds have passed
if elapsed >= REFRESH_EVERY:
    st.cache_data.clear()
    st.session_state.last_refresh = datetime.now()
    st.session_state.refresh_count += 1
    st.rerun()


# ══════════════════════════════════════════════════════
#  CACHED DATA FETCHERS
# ══════════════════════════════════════════════════════
@st.cache_data(ttl=REFRESH_EVERY)
def fetch_live(_tick):
    return df_api.get_ltp("SBIN"), df_api.get_ltp("NIFTY")

@st.cache_data(ttl=REFRESH_EVERY)
def fetch_candles(symbol, interval, days, _tick):
    return df_api.get_candles(symbol, interval, days=days)

@st.cache_data(ttl=300)
def fetch_correlation(_tick):
    s = df_api.get_daily_candles("SBIN",  days=90)
    n = df_api.get_daily_candles("NIFTY", days=90)
    return correlation_analysis(s, n)

# _tick changes every refresh cycle — forces cache miss on new cycle
tick = st.session_state.refresh_count


# ══════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════
def fmt(v, dec=2):
    if v is None: return "—"
    try: return f"{float(v):.{dec}f}"
    except: return "—"

def rsi_color(v):
    if v is None: return "#8b949e"
    if v > 70: return "#f85149"
    if v < 30: return "#3fb950"
    return "#d29922"

now_ist = datetime.now(IST)


# ══════════════════════════════════════════════════════
#  FETCH ALL DATA
# ══════════════════════════════════════════════════════
sbin_ltp, nifty_ltp = fetch_live(tick)

# 1-min data for MTF (last 3 days covers enough history)
candles_1m   = fetch_candles("SBIN", "1m",  days=3,   _tick=tick)
corr_data    = fetch_correlation(tick)

# MTF analysis (always from 1-min candles)
mtf = mtf_trend(candles_1m)
bias = overall_bias(mtf)

# Countdown to next refresh
secs_left    = max(0, int(REFRESH_EVERY - elapsed))
pct_done     = min(100, int(elapsed / REFRESH_EVERY * 100))


# ══════════════════════════════════════════════════════
#  HEADER
# ══════════════════════════════════════════════════════
data_ok = bool(sbin_ltp and sbin_ltp.get("ltp"))
h1, h2, h3, h4 = st.columns([2.2, 1.4, 1.4, 1])

with h1:
    dot = "🟢" if data_ok else "🔴"
    st.markdown("## 📈 SBIN Intraday Analyzer")
    st.caption(f"{dot} Yahoo Finance (NSE) • {now_ist.strftime('%d %b %Y  %H:%M:%S IST')}  •  Refresh #{st.session_state.refresh_count}")

with h2:
    if data_ok:
        chg = sbin_ltp["ltp"] - sbin_ltp["close"]
        pct = chg / sbin_ltp["close"] * 100 if sbin_ltp["close"] else 0
        st.metric("SBIN", f"₹{sbin_ltp['ltp']:.2f}", f"{chg:+.2f} ({pct:+.2f}%)")
    else:
        st.metric("SBIN", "—", "Loading…")

with h3:
    if nifty_ltp and nifty_ltp.get("ltp"):
        chg = nifty_ltp["ltp"] - nifty_ltp["close"]
        pct = chg / nifty_ltp["close"] * 100 if nifty_ltp["close"] else 0
        st.metric("NIFTY 50", f"₹{nifty_ltp['ltp']:.2f}", f"{chg:+.2f} ({pct:+.2f}%)")
    else:
        st.metric("NIFTY 50", "—", "Loading…")

with h4:
    st.markdown(f"**Next refresh:** {secs_left}s")
    st.markdown(
        f'<div class="countdown-bar"><div class="countdown-fill" style="width:{pct_done}%"></div></div>',
        unsafe_allow_html=True,
    )
    if st.button("↻ Now", use_container_width=True):
        st.cache_data.clear()
        st.session_state.last_refresh = datetime.now()
        st.session_state.refresh_count += 1
        st.rerun()

st.divider()


# ══════════════════════════════════════════════════════
#  TOP SECTION: MTF TREND  +  OVERALL BIAS
# ══════════════════════════════════════════════════════
st.markdown("### Multi-Timeframe Trend Analysis")
mtf_col, bias_col = st.columns([3, 1])

with mtf_col:
    if mtf:
        # Table header
        hdr = st.columns([1.2, 0.8, 1.8, 1.2, 1.2, 1.2])
        hdr[0].markdown("**Timeframe**")
        hdr[1].markdown("**Direction**")
        hdr[2].markdown("**Trend**")
        hdr[3].markdown("**Change %**")
        hdr[4].markdown("**High**")
        hdr[5].markdown("**Low**")

        for r in mtf:
            sign = "+" if r["chg_pct"] >= 0 else ""
            st.markdown(
                f'<div class="mtf-row">'
                f'<span class="mtf-label">{r["label"]}</span>'
                f'<span class="mtf-arrow" style="color:{r["color"]}">{r["arrow"]}</span>'
                f'<span class="mtf-trend" style="color:{r["color"]}">{r["trend"]}</span>'
                f'<span class="mtf-chg"  style="color:{r["color"]}">{sign}{r["chg_pct"]:.3f}%</span>'
                f'<span class="mtf-chg"  style="color:#8b949e">H: ₹{r["high"]}</span>'
                f'<span class="mtf-chg"  style="color:#8b949e">L: ₹{r["low"]}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
    else:
        st.info("Loading 1-min data for MTF analysis…")

with bias_col:
    # Overall bias box
    if bias["bias"] != "UNKNOWN":
        st.markdown(
            f'<div class="bias-box" style="border-color:{bias["color"]};color:{bias["color"]}">'
            f'Overall Bias<br>{bias["bias"]}'
            f'<div style="font-size:13px;color:#8b949e;font-weight:400;margin-top:6px">'
            f'🟢 {bias["bull"]} TF  🔴 {bias["bear"]} TF  🟡 {bias["neutral"]} TF'
            f'</div></div>',
            unsafe_allow_html=True,
        )
    # NIFTY direction check (same time window)
    nifty_1m = fetch_candles("NIFTY", "1m", days=1, _tick=tick)
    nifty_mtf = mtf_trend(nifty_1m)
    nifty_bias = overall_bias(nifty_mtf)
    if nifty_bias["bias"] != "UNKNOWN":
        st.markdown(
            f'<div class="bias-box" style="border-color:{nifty_bias["color"]};color:{nifty_bias["color"]}">'
            f'NIFTY Bias<br>{nifty_bias["bias"]}'
            f'<div style="font-size:13px;color:#8b949e;font-weight:400;margin-top:6px">'
            f'🟢 {nifty_bias["bull"]} TF  🔴 {nifty_bias["bear"]} TF'
            f'</div></div>',
            unsafe_allow_html=True,
        )
        # Alignment note
        both_bull = bias["bull"] >= 3 and nifty_bias["bull"] >= 3
        both_bear = bias["bear"] >= 3 and nifty_bias["bear"] >= 3
        if both_bull:
            st.success("✅ SBIN + NIFTY both bullish — strong long setup")
        elif both_bear:
            st.error("🔻 SBIN + NIFTY both bearish — strong short setup")
        elif bias["bull"] >= 3 and nifty_bias["bear"] >= 3:
            st.warning("⚡ SBIN bullish but NIFTY bearish — SBIN outperforming")
        elif bias["bear"] >= 3 and nifty_bias["bull"] >= 3:
            st.warning("⚡ SBIN bearish but NIFTY bullish — SBIN underperforming")

st.divider()


# ══════════════════════════════════════════════════════
#  CHART SECTION + RIGHT PANEL
# ══════════════════════════════════════════════════════
TF_OPTIONS = {"1 Min": "1m", "5 Min": "5m", "15 Min": "15m", "1 Hour": "1h", "Daily": "1d"}
TF_DAYS    = {"1m": 3, "5m": 10, "15m": 20, "1h": 30, "1d": 365}

tf_label = st.radio("Chart Timeframe", list(TF_OPTIONS.keys()), index=1, horizontal=True)
tf   = TF_OPTIONS[tf_label]
days = TF_DAYS[tf]

# Fetch chart data
sbin_raw  = fetch_candles("SBIN",  tf, days, _tick=tick)
nifty_raw = fetch_candles("NIFTY", tf, days, _tick=tick)

sbin_df  = add_indicators(to_df(sbin_raw))  if sbin_raw  else pd.DataFrame()
nifty_df = to_df(nifty_raw)                 if nifty_raw else pd.DataFrame()
signals  = generate_signals(sbin_df)         if not sbin_df.empty else {}
pivots   = pivot_points(sbin_df)             if tf == "1d" and not sbin_df.empty else {}

left, right = st.columns([3, 1.2])

# ── LEFT: Charts ────────────────────────────────────
with left:

    if not sbin_df.empty:
        fig = make_subplots(
            rows=3, cols=1, shared_xaxes=True,
            row_heights=[0.60, 0.20, 0.20],
            vertical_spacing=0.02,
        )
        fig.add_trace(go.Candlestick(
            x=sbin_df["time"], open=sbin_df["open"], high=sbin_df["high"],
            low=sbin_df["low"], close=sbin_df["close"], name="SBIN",
            increasing_line_color="#3fb950", decreasing_line_color="#f85149",
        ), row=1, col=1)
        for col_, color, name in [("ema9","#f0c060","EMA9"),("ema21","#58a6ff","EMA21"),("ema50","#bc8cff","EMA50")]:
            if col_ in sbin_df.columns:
                fig.add_trace(go.Scatter(x=sbin_df["time"], y=sbin_df[col_],
                    line=dict(color=color, width=1), name=name), row=1, col=1)
        if "vwap" in sbin_df.columns:
            fig.add_trace(go.Scatter(x=sbin_df["time"], y=sbin_df["vwap"],
                line=dict(color="#ff7b00", width=2, dash="dot"), name="VWAP"), row=1, col=1)
        if "bb_upper" in sbin_df.columns:
            fig.add_trace(go.Scatter(x=sbin_df["time"], y=sbin_df["bb_upper"],
                line=dict(color="#484f58", width=1), name="BB+", showlegend=False), row=1, col=1)
            fig.add_trace(go.Scatter(x=sbin_df["time"], y=sbin_df["bb_lower"],
                line=dict(color="#484f58", width=1), name="BB-",
                fill="tonexty", fillcolor="rgba(72,79,88,0.1)", showlegend=False), row=1, col=1)
        if "rsi" in sbin_df.columns:
            fig.add_trace(go.Scatter(x=sbin_df["time"], y=sbin_df["rsi"],
                line=dict(color="#bc8cff", width=1.5), name="RSI"), row=2, col=1)
            fig.add_hline(y=70, line_dash="dash", line_color="#f85149", line_width=0.8, row=2, col=1)
            fig.add_hline(y=30, line_dash="dash", line_color="#3fb950", line_width=0.8, row=2, col=1)
        if "macd" in sbin_df.columns:
            colors_ = ["#3fb950" if v >= 0 else "#f85149" for v in sbin_df["macd_hist"].fillna(0)]
            fig.add_trace(go.Bar(x=sbin_df["time"], y=sbin_df["macd_hist"],
                marker_color=colors_, name="MACD Hist", showlegend=False), row=3, col=1)
            fig.add_trace(go.Scatter(x=sbin_df["time"], y=sbin_df["macd"],
                line=dict(color="#58a6ff", width=1), name="MACD"), row=3, col=1)
            fig.add_trace(go.Scatter(x=sbin_df["time"], y=sbin_df["macd_signal"],
                line=dict(color="#f0c060", width=1), name="Signal"), row=3, col=1)
        fig.update_layout(
            height=500, template="plotly_dark",
            paper_bgcolor="#161b22", plot_bgcolor="#0d1117",
            margin=dict(l=0, r=0, t=30, b=0),
            legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0),
            xaxis_rangeslider_visible=False,
            title=dict(text=f"SBIN — {tf_label}  (Updated {now_ist.strftime('%H:%M:%S')})", font=dict(size=13)),
        )
        fig.update_yaxes(gridcolor="#1c2128")
        fig.update_xaxes(gridcolor="#1c2128")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("SBIN chart loading… (market may be closed on weekends)")

    if not nifty_df.empty:
        nfig = go.Figure(go.Candlestick(
            x=nifty_df["time"], open=nifty_df["open"], high=nifty_df["high"],
            low=nifty_df["low"], close=nifty_df["close"], name="NIFTY",
            increasing_line_color="#3fb950", decreasing_line_color="#f85149",
        ))
        nfig.update_layout(
            height=200, template="plotly_dark",
            paper_bgcolor="#161b22", plot_bgcolor="#0d1117",
            margin=dict(l=0, r=0, t=30, b=0),
            xaxis_rangeslider_visible=False,
            title=dict(text=f"NIFTY 50 — {tf_label}", font=dict(size=12)),
        )
        nfig.update_yaxes(gridcolor="#1c2128")
        nfig.update_xaxes(gridcolor="#1c2128")
        st.plotly_chart(nfig, use_container_width=True)

    # Correlation heatmap
    if corr_data and corr_data.get("daily_data"):
        st.markdown("#### SBIN vs NIFTY — Daily Direction (last 30 days)")
        daily   = corr_data["daily_data"]
        df_heat = pd.DataFrame(daily)
        colors_ = ["rgba(63,185,80,0.55)" if r else "rgba(248,81,73,0.55)" for r in df_heat["same_dir"]]
        tips    = [f"{row['date']}<br>SBIN:{row['sbin_ret']:+.2f}%  NIFTY:{row['nifty_ret']:+.2f}%"
                   for _, row in df_heat.iterrows()]
        hfig = go.Figure(go.Bar(x=df_heat["date"], y=[1]*len(df_heat),
            marker_color=colors_, hovertext=tips, hoverinfo="text"))
        hfig.update_layout(height=100, template="plotly_dark",
            paper_bgcolor="#161b22", plot_bgcolor="#0d1117",
            margin=dict(l=0,r=0,t=6,b=28),
            yaxis=dict(showticklabels=False, showgrid=False),
            xaxis=dict(tickfont=dict(size=9)))
        st.plotly_chart(hfig, use_container_width=True)
        st.caption("🟢 Same direction  🔴 Opposite direction — hover for details")


# ── RIGHT: Analysis Panel ──────────────────────────
with right:

    # Signal box
    if signals:
        sig_color = signals.get("color", "#d29922")
        st.markdown(
            f'<div class="signal-card" style="border-color:{sig_color};color:{sig_color}">'
            f'<div style="font-size:20px;font-weight:800">{signals.get("signal","—")}</div>'
            f'<div style="font-size:24px;font-weight:700;margin:4px 0">₹{signals.get("current_price",0):.2f}</div>'
            f'<div style="font-size:11px;color:#8b949e">{tf_label} Timeframe</div>'
            f'</div>', unsafe_allow_html=True)

    st.markdown("**Risk Levels (ATR-based)**")
    c1, c2 = st.columns(2)
    c1.metric("Stop Loss", f"₹{signals.get('stop_loss',0):.2f}" if signals else "—")
    c2.metric("ATR",       f"{signals.get('atr',0):.2f}"         if signals else "—")
    c1.metric("Target 1",  f"₹{signals.get('target1',0):.2f}"   if signals else "—")
    c2.metric("Target 2",  f"₹{signals.get('target2',0):.2f}"   if signals else "—")

    st.divider()
    st.markdown("**Indicators**")
    if signals and not sbin_df.empty:
        last = sbin_df.iloc[-1]
        cp   = signals.get("current_price", 0)
        for name, val, bull in [
            ("EMA 9",    last.get("ema9"),    cp > (last.get("ema9")  or cp)),
            ("EMA 21",   last.get("ema21"),   cp > (last.get("ema21") or cp)),
            ("EMA 50",   last.get("ema50"),   cp > (last.get("ema50") or cp)),
            ("RSI (14)", signals.get("rsi"),  None),
            ("MACD",     signals.get("macd"), (signals.get("macd") or 0) > (signals.get("macd_signal") or 0)),
            ("VWAP",     signals.get("vwap"), cp > (signals.get("vwap") or 0) if signals.get("vwap") else None),
            ("BB Upper", last.get("bb_upper"), False),
            ("BB Lower", last.get("bb_lower"), True),
        ]:
            if val is None: continue
            if name == "RSI (14)": color = rsi_color(val)
            elif bull is None: color = "#8b949e"
            else: color = "#3fb950" if bull else "#f85149"
            st.markdown(
                f'<div class="metric-row"><span style="color:#8b949e">{name}</span>'
                f'<span style="color:{color};font-weight:600">{fmt(val)}</span></div>',
                unsafe_allow_html=True)

    st.divider()
    st.markdown("**Why This Signal?**")
    for r in signals.get("reasons", []):
        st.markdown(f"• {r}")

    st.divider()
    st.markdown("**SBIN × NIFTY Correlation**")
    if corr_data:
        corr_r = corr_data.get("correlation", 0)
        st.progress(abs(corr_r), text=f"Pearson r = {corr_r:.3f}")
        for label, val in [
            ("Beta",           f"{corr_data.get('beta',0):.3f}"),
            ("Same Dir (90d)", f"{corr_data.get('same_dir_days')}d/{corr_data.get('total_days')}d ({corr_data.get('same_dir_pct')}%)"),
            ("Last 30d",       f"{corr_data.get('last30_same')}/30 ({corr_data.get('last30_pct')}%)"),
            ("RS (10d avg)",   f"{corr_data.get('relative_strength_10d',0):+.3f}%"),
        ]:
            st.markdown(
                f'<div class="metric-row"><span style="color:#8b949e">{label}</span>'
                f'<span style="font-weight:600">{val}</span></div>', unsafe_allow_html=True)
        if corr_r > 0.7: st.success("SBIN strongly follows NIFTY")
        elif corr_r > 0.4: st.warning("Moderate correlation")
        else: st.error("Weak correlation — moving independently")

    if pivots:
        st.divider()
        st.markdown("**Pivot Points (Daily)**")
        for level, val in [("R3",pivots.get("R3")),("R2",pivots.get("R2")),("R1",pivots.get("R1")),
                           ("Pivot",pivots.get("P")),("S1",pivots.get("S1")),("S2",pivots.get("S2")),("S3",pivots.get("S3"))]:
            if val is None: continue
            color = "#3fb950" if level.startswith("R") else ("#d29922" if level=="Pivot" else "#f85149")
            st.markdown(
                f'<div class="metric-row"><span style="color:{color};font-weight:700">{level}</span>'
                f'<span style="font-weight:600">₹{val}</span></div>', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════
# BACKGROUND RERUN — triggers after REFRESH_EVERY secs
# ══════════════════════════════════════════════════════
# Small sleep then rerun — keeps page live without meta-refresh flicker
time.sleep(1)
st.rerun()
