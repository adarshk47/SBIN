"""SBIN Intraday Analysis Dashboard — Streamlit + yfinance"""
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
from datetime import datetime
import time
import pytz

import data_fetcher as df_api
from analysis import to_df, add_indicators, generate_signals, correlation_analysis, pivot_points
from mtf_analysis import mtf_trend, overall_bias, ema_crossovers
from oi_fetcher import fetch_oi_snapshot, oi_change, pcr_sentiment

st.set_page_config(
    page_title="SBIN Analyzer",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

IST = pytz.timezone("Asia/Kolkata")
REFRESH_EVERY = 60   # candles / LTP refresh (seconds)
OI_REFRESH    = 300  # OI refresh (every 5 min)

# ── CSS ─────────────────────────────────────────────────
st.markdown("""
<style>
  .block-container { padding-top: 0.7rem; padding-bottom: 0.5rem; }
  .signal-card { padding:14px; border-radius:10px; text-align:center;
    border:2px solid; margin-bottom:8px; }
  .mtf-row { display:flex; justify-content:space-between; align-items:center;
    padding:7px 10px; border-radius:6px; margin-bottom:4px;
    background:#161b22; border:1px solid #30363d; }
  .mtf-label { color:#8b949e; font-size:13px; font-weight:600; min-width:58px; }
  .mtf-arrow { font-size:20px; font-weight:900; min-width:32px; text-align:center; }
  .mtf-trend { font-size:12px; font-weight:700; letter-spacing:.3px; min-width:96px; }
  .mtf-chg   { font-size:13px; font-weight:600; font-variant-numeric:tabular-nums; text-align:right; min-width:70px; }
  .bias-box  { padding:10px 14px; border-radius:8px; text-align:center; border:2px solid;
    margin-bottom:8px; font-size:18px; font-weight:800; letter-spacing:.5px; }
  .metric-row { display:flex; justify-content:space-between; align-items:center;
    padding:5px 0; border-bottom:1px solid #1c2128; font-size:13px; }
  .cross-row  { display:flex; justify-content:space-between; align-items:center;
    padding:5px 8px; border-radius:5px; margin-bottom:3px; background:#161b22;
    border-left:3px solid; font-size:12px; }
  .oi-row    { display:flex; justify-content:space-between; align-items:center;
    padding:5px 0; border-bottom:1px solid #1c2128; font-size:13px; }
  .cnt-bar   { height:4px; border-radius:2px; background:#1c2128; margin-top:3px; overflow:hidden; }
  .cnt-fill  { height:100%; border-radius:2px; background:linear-gradient(90deg,#58a6ff,#3fb950); }
  h1,h2,h3  { margin-bottom:0 !important; }
  .stMetric label { font-size:11px !important; }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════
#  SESSION STATE — background data store
# ══════════════════════════════════════════════════════
def _init_state():
    defaults = {
        "last_refresh":    datetime.now(),
        "last_oi_fetch":   None,
        "refresh_count":   0,
        "oi_history":      [],      # list of OI snapshots
        "candles_1m":      [],      # latest 1-min SBIN candles
        "candles_1m_nifty":[],
        "corr_data":       {},
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()
now_wall = datetime.now()
elapsed  = (now_wall - st.session_state.last_refresh).total_seconds()

# ── Trigger refresh when REFRESH_EVERY seconds pass ──
if elapsed >= REFRESH_EVERY:
    st.cache_data.clear()
    st.session_state.last_refresh  = datetime.now()
    st.session_state.refresh_count += 1
    st.rerun()

tick = st.session_state.refresh_count
secs_left = max(0, int(REFRESH_EVERY - elapsed))
pct_done  = min(100, int(elapsed / REFRESH_EVERY * 100))


# ══════════════════════════════════════════════════════
#  CACHED FETCHERS
# ══════════════════════════════════════════════════════
@st.cache_data(ttl=REFRESH_EVERY)
def _fetch_live(t):
    return df_api.get_ltp("SBIN"), df_api.get_ltp("NIFTY")

@st.cache_data(ttl=REFRESH_EVERY)
def _fetch_candles(sym, iv, days, t):
    return df_api.get_candles(sym, iv, days=days)

@st.cache_data(ttl=600)
def _fetch_corr(t):
    s = df_api.get_daily_candles("SBIN",  days=90)
    n = df_api.get_daily_candles("NIFTY", days=90)
    return correlation_analysis(s, n)


# ══════════════════════════════════════════════════════
#  BACKGROUND DATA PIPELINE (runs each rerun cycle)
# ══════════════════════════════════════════════════════
# 1-min candles updated every tick
c1m = _fetch_candles("SBIN",  "1m", 3, tick)
c1m_nifty = _fetch_candles("NIFTY", "1m", 1, tick)
if c1m:
    st.session_state.candles_1m       = c1m
if c1m_nifty:
    st.session_state.candles_1m_nifty = c1m_nifty

# OI snapshot — every OI_REFRESH seconds
oi_elapsed = (now_wall - st.session_state.last_oi_fetch).total_seconds() \
             if st.session_state.last_oi_fetch else OI_REFRESH + 1
if oi_elapsed >= OI_REFRESH:
    snap = fetch_oi_snapshot("SBIN")
    if snap:
        st.session_state.oi_history.append(snap)
        if len(st.session_state.oi_history) > 50:   # keep last 50 readings
            st.session_state.oi_history = st.session_state.oi_history[-50:]
    st.session_state.last_oi_fetch = now_wall

# Correlation updated every 10 min (handled by cache ttl=600)
corr_data = _fetch_corr(tick // 10)

# ── Pull from session state ─────────────────────────
candles_1m   = st.session_state.candles_1m
candles_nifty= st.session_state.candles_1m_nifty
oi_history   = st.session_state.oi_history
mtf          = mtf_trend(candles_1m)
bias         = overall_bias(mtf)
nifty_mtf    = mtf_trend(candles_nifty)
nifty_bias   = overall_bias(nifty_mtf)
crossovers   = ema_crossovers(candles_1m)
oi_delta     = oi_change(oi_history)
latest_oi    = oi_history[-1] if oi_history else None
sbin_ltp, nifty_ltp = _fetch_live(tick)
now_ist      = datetime.now(IST)
data_ok      = bool(sbin_ltp and sbin_ltp.get("ltp"))


# ══════════════════════════════════════════════════════
#  HEADER
# ══════════════════════════════════════════════════════
h1, h2, h3, h4 = st.columns([2.2, 1.4, 1.4, 1])
with h1:
    dot = "🟢" if data_ok else "🔴"
    st.markdown("## 📈 SBIN Intraday Analyzer")
    st.caption(f"{dot} Yahoo Finance NSE • {now_ist.strftime('%d %b %Y  %H:%M:%S IST')} • Refresh #{tick}")
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
    st.markdown(f"**Next:** {secs_left}s")
    st.markdown(f'<div class="cnt-bar"><div class="cnt-fill" style="width:{pct_done}%"></div></div>',
                unsafe_allow_html=True)
    if st.button("↻ Now", use_container_width=True):
        st.cache_data.clear()
        st.session_state.last_refresh  = datetime.now()
        st.session_state.refresh_count += 1
        st.rerun()

st.divider()


# ══════════════════════════════════════════════════════
#  SECTION 1: MTF TREND TABLE
# ══════════════════════════════════════════════════════
st.markdown("### 📊 Multi-Timeframe Trend")
col_mtf, col_bias = st.columns([3, 1])

with col_mtf:
    if mtf:
        hdr = st.columns([1.1, 0.7, 1.6, 1.1, 1.1, 1.1])
        for h, t_ in zip(hdr, ["**Timeframe**","**Dir**","**Trend**","**Change%**","**High**","**Low**"]):
            h.markdown(t_)
        for r in mtf:
            sign = "+" if r["chg_pct"] >= 0 else ""
            st.markdown(
                f'<div class="mtf-row">'
                f'<span class="mtf-label">{r["label"]}</span>'
                f'<span class="mtf-arrow" style="color:{r["color"]}">{r["arrow"]}</span>'
                f'<span class="mtf-trend" style="color:{r["color"]}">{r["trend"]}</span>'
                f'<span class="mtf-chg"   style="color:{r["color"]}">{sign}{r["chg_pct"]:.3f}%</span>'
                f'<span class="mtf-chg"   style="color:#8b949e">₹{r["high"]}</span>'
                f'<span class="mtf-chg"   style="color:#8b949e">₹{r["low"]}</span>'
                f'</div>', unsafe_allow_html=True)
    else:
        st.info("Loading 1-min data…")

with col_bias:
    if bias["bias"] != "UNKNOWN":
        st.markdown(
            f'<div class="bias-box" style="border-color:{bias["color"]};color:{bias["color"]}">'
            f'SBIN Bias<br>{bias["bias"]}'
            f'<div style="font-size:12px;color:#8b949e;font-weight:400;margin-top:5px">'
            f'🟢{bias["bull"]} 🔴{bias["bear"]} 🟡{bias["neutral"]}</div></div>',
            unsafe_allow_html=True)
    if nifty_bias["bias"] != "UNKNOWN":
        st.markdown(
            f'<div class="bias-box" style="border-color:{nifty_bias["color"]};color:{nifty_bias["color"]}">'
            f'NIFTY Bias<br>{nifty_bias["bias"]}'
            f'<div style="font-size:12px;color:#8b949e;font-weight:400;margin-top:5px">'
            f'🟢{nifty_bias["bull"]} 🔴{nifty_bias["bear"]}</div></div>',
            unsafe_allow_html=True)
    # Alignment alert
    if bias["bull"] >= 3 and nifty_bias["bull"] >= 3:
        st.success("✅ Both BULLISH — Strong long setup")
    elif bias["bear"] >= 3 and nifty_bias["bear"] >= 3:
        st.error("🔻 Both BEARISH — Strong short setup")
    elif bias["bull"] >= 3 and nifty_bias["bear"] >= 3:
        st.warning("⚡ SBIN bullish, NIFTY bearish — SBIN outperforming")
    elif bias["bear"] >= 3 and nifty_bias["bull"] >= 3:
        st.warning("⚡ SBIN bearish, NIFTY bullish — SBIN underperforming")

st.divider()


# ══════════════════════════════════════════════════════
#  SECTION 2: EMA CROSSOVERS + OI PANEL (side by side)
# ══════════════════════════════════════════════════════
cross_col, oi_col = st.columns([1, 1])

with cross_col:
    st.markdown("### 🔀 EMA 9/21 Crossovers (1-min)")
    if crossovers:
        for ev in crossovers:
            border = ev["color"]
            st.markdown(
                f'<div class="cross-row" style="border-left-color:{border}">'
                f'<span style="color:{border};font-size:16px;font-weight:900">{ev["arrow"]}</span>'
                f'<span style="color:{border};font-weight:700">{ev["type"]}</span>'
                f'<span style="color:#8b949e">{ev["time"]}</span>'
                f'<span style="font-weight:600">₹{ev["price"]}</span>'
                f'<span style="color:#58a6ff;font-size:11px">E9:{ev["ema9"]}</span>'
                f'<span style="color:#bc8cff;font-size:11px">E21:{ev["ema21"]}</span>'
                f'</div>', unsafe_allow_html=True)
        # EMA crossover chart (1-min)
        if candles_1m:
            df_cross = add_indicators(to_df(candles_1m))
            if not df_cross.empty and "ema9" in df_cross.columns:
                fig_c = go.Figure()
                fig_c.add_trace(go.Scatter(x=df_cross["time"], y=df_cross["close"],
                    line=dict(color="#c9d1d9", width=1), name="Price"))
                fig_c.add_trace(go.Scatter(x=df_cross["time"], y=df_cross["ema9"],
                    line=dict(color="#f0c060", width=1.5), name="EMA9"))
                fig_c.add_trace(go.Scatter(x=df_cross["time"], y=df_cross["ema21"],
                    line=dict(color="#58a6ff", width=1.5), name="EMA21"))
                # Mark crossover points
                for ev in crossovers:
                    fig_c.add_annotation(x=f"2026-{ev['time']}" if len(ev["time"]) == 5 else ev["time"],
                        y=ev["price"], text=ev["arrow"], showarrow=False,
                        font=dict(size=16, color=ev["color"]))
                fig_c.update_layout(
                    height=200, template="plotly_dark",
                    paper_bgcolor="#161b22", plot_bgcolor="#0d1117",
                    margin=dict(l=0,r=0,t=10,b=0),
                    legend=dict(orientation="h", y=1.15, x=0, font=dict(size=10)),
                    xaxis_rangeslider_visible=False,
                )
                fig_c.update_yaxes(gridcolor="#1c2128")
                fig_c.update_xaxes(gridcolor="#1c2128")
                st.plotly_chart(fig_c, use_container_width=True)
    else:
        st.info("No EMA crossovers detected in 1-min data (need 25+ candles)")

with oi_col:
    st.markdown("### 📈 OI (Open Interest) Panel")
    oi_next = max(0, int(OI_REFRESH - oi_elapsed)) if st.session_state.last_oi_fetch else 0
    st.caption(f"Updates every 5 min • Next OI fetch in {oi_next}s • {len(oi_history)} readings stored")

    if latest_oi:
        # PCR gauge
        pcr   = latest_oi["pcr_oi"]
        label, col = pcr_sentiment(pcr)
        st.markdown(
            f'<div class="bias-box" style="border-color:{col};color:{col}">'
            f'PCR (OI) = {pcr}<br>{label}'
            f'<div style="font-size:11px;color:#8b949e;font-weight:400;margin-top:4px">'
            f'Expiry: {latest_oi["expiry"]} • as of {latest_oi["time"]}</div></div>',
            unsafe_allow_html=True)

        # OI numbers
        delta = oi_delta
        def chg_str(v):
            if not v: return ""
            return f" ({'+' if v>0 else ''}{v:,})"

        rows = [
            ("Total Call OI", f"{latest_oi['total_call_oi']:,}{chg_str(delta.get('call_oi_chg'))}",
             "#f85149" if delta.get("call_oi_chg", 0) > 0 else "#3fb950"),
            ("Total Put OI",  f"{latest_oi['total_put_oi']:,}{chg_str(delta.get('put_oi_chg'))}",
             "#3fb950" if delta.get("put_oi_chg", 0) > 0 else "#f85149"),
            ("PCR (Volume)",  str(latest_oi["pcr_vol"]),   "#8b949e"),
            ("PCR Change",    f"{delta.get('pcr_chg',0):+.3f}" if delta else "—",
             "#3fb950" if delta.get("pcr_chg",0) > 0 else "#f85149"),
        ]
        for lbl, val, col_ in rows:
            st.markdown(
                f'<div class="oi-row"><span style="color:#8b949e">{lbl}</span>'
                f'<span style="color:{col_};font-weight:600">{val}</span></div>',
                unsafe_allow_html=True)

        # ATM strike info
        if latest_oi.get("atm"):
            atm = latest_oi["atm"]
            st.markdown(f"**ATM Strike: ₹{atm['strike']}**")
            a1, a2 = st.columns(2)
            a1.metric("ATM Call OI", f"{atm['call_oi']:,}")
            a2.metric("ATM Put OI",  f"{atm['put_oi']:,}")

        # Top OI strikes (resistance / support via max pain)
        t1, t2 = st.columns(2)
        with t1:
            st.markdown("**Top Call OI (Resistance)**")
            for s in latest_oi.get("top_call_strikes", []):
                st.markdown(
                    f'<div class="metric-row"><span style="color:#f85149">₹{s["strike"]}</span>'
                    f'<span style="font-weight:600">{int(s["openInterest"]):,}</span></div>',
                    unsafe_allow_html=True)
        with t2:
            st.markdown("**Top Put OI (Support)**")
            for s in latest_oi.get("top_put_strikes", []):
                st.markdown(
                    f'<div class="metric-row"><span style="color:#3fb950">₹{s["strike"]}</span>'
                    f'<span style="font-weight:600">{int(s["openInterest"]):,}</span></div>',
                    unsafe_allow_html=True)

        # OI history chart (PCR over time)
        if len(oi_history) >= 2:
            df_oi = pd.DataFrame([{"time": h["time"], "pcr": h["pcr_oi"]} for h in oi_history])
            fig_oi = go.Figure()
            fig_oi.add_trace(go.Scatter(x=df_oi["time"], y=df_oi["pcr"],
                mode="lines+markers", line=dict(color="#bc8cff", width=2),
                marker=dict(size=6), name="PCR (OI)"))
            fig_oi.add_hline(y=1.0, line_dash="dash", line_color="#d29922", line_width=1,
                             annotation_text="Neutral (1.0)")
            fig_oi.update_layout(height=160, template="plotly_dark",
                paper_bgcolor="#161b22", plot_bgcolor="#0d1117",
                margin=dict(l=0,r=0,t=10,b=0),
                title=dict(text="PCR History (this session)", font=dict(size=11)),
                xaxis_rangeslider_visible=False)
            fig_oi.update_yaxes(gridcolor="#1c2128")
            fig_oi.update_xaxes(gridcolor="#1c2128", tickfont=dict(size=9))
            st.plotly_chart(fig_oi, use_container_width=True)
    else:
        with st.spinner("Fetching OI data…"):
            st.info("OI data loading on first fetch (5-min interval). Refresh once.")

st.divider()


# ══════════════════════════════════════════════════════
#  SECTION 3: CANDLESTICK CHARTS + ANALYSIS PANEL
# ══════════════════════════════════════════════════════
TF_OPTIONS = {"1 Min":"1m","5 Min":"5m","15 Min":"15m","1 Hour":"1h","Daily":"1d"}
TF_DAYS    = {"1m":3,"5m":10,"15m":20,"1h":30,"1d":365}

tf_label = st.radio("Chart Timeframe", list(TF_OPTIONS.keys()), index=1, horizontal=True)
tf   = TF_OPTIONS[tf_label]
days = TF_DAYS[tf]

sbin_raw  = _fetch_candles("SBIN",  tf, days, tick)
nifty_raw = _fetch_candles("NIFTY", tf, days, tick)

sbin_df  = add_indicators(to_df(sbin_raw))  if sbin_raw  else pd.DataFrame()
nifty_df = to_df(nifty_raw)                 if nifty_raw else pd.DataFrame()
signals  = generate_signals(sbin_df)         if not sbin_df.empty else {}
pivots   = pivot_points(sbin_df)             if tf == "1d" and not sbin_df.empty else {}

chart_col, right_col = st.columns([3, 1.2])

with chart_col:
    # SBIN chart with indicators + volume
    if not sbin_df.empty:
        has_vol = "volume" in sbin_df.columns and sbin_df["volume"].sum() > 0
        rows_n = 4 if has_vol else 3
        heights = [0.52, 0.18, 0.18, 0.12] if has_vol else [0.60, 0.20, 0.20]

        fig = make_subplots(
            rows=rows_n, cols=1, shared_xaxes=True,
            row_heights=heights, vertical_spacing=0.02,
            subplot_titles=["", "RSI (14)", "MACD", "Volume"] if has_vol else ["","RSI","MACD"],
        )
        # Candles
        fig.add_trace(go.Candlestick(
            x=sbin_df["time"], open=sbin_df["open"], high=sbin_df["high"],
            low=sbin_df["low"], close=sbin_df["close"], name="SBIN",
            increasing_line_color="#3fb950", decreasing_line_color="#f85149",
        ), row=1, col=1)
        # EMAs
        for c_, col_, nm in [("ema9","#f0c060","EMA9"),("ema21","#58a6ff","EMA21"),("ema50","#bc8cff","EMA50")]:
            if c_ in sbin_df.columns:
                fig.add_trace(go.Scatter(x=sbin_df["time"], y=sbin_df[c_],
                    line=dict(color=col_, width=1), name=nm), row=1, col=1)
        # VWAP
        if "vwap" in sbin_df.columns:
            fig.add_trace(go.Scatter(x=sbin_df["time"], y=sbin_df["vwap"],
                line=dict(color="#ff7b00", width=2, dash="dot"), name="VWAP"), row=1, col=1)
        # Bollinger
        if "bb_upper" in sbin_df.columns:
            fig.add_trace(go.Scatter(x=sbin_df["time"], y=sbin_df["bb_upper"],
                line=dict(color="#484f58", width=1), name="BB+", showlegend=False), row=1, col=1)
            fig.add_trace(go.Scatter(x=sbin_df["time"], y=sbin_df["bb_lower"],
                line=dict(color="#484f58", width=1), name="BB-",
                fill="tonexty", fillcolor="rgba(72,79,88,0.1)", showlegend=False), row=1, col=1)
        # RSI
        if "rsi" in sbin_df.columns:
            fig.add_trace(go.Scatter(x=sbin_df["time"], y=sbin_df["rsi"],
                line=dict(color="#bc8cff", width=1.5), name="RSI"), row=2, col=1)
            fig.add_hline(y=70, line_dash="dash", line_color="#f85149", line_width=0.8, row=2, col=1)
            fig.add_hline(y=30, line_dash="dash", line_color="#3fb950", line_width=0.8, row=2, col=1)
            fig.add_hline(y=50, line_dash="dot",  line_color="#484f58", line_width=0.5, row=2, col=1)
        # MACD
        if "macd" in sbin_df.columns:
            clrs = ["#3fb950" if v >= 0 else "#f85149" for v in sbin_df["macd_hist"].fillna(0)]
            fig.add_trace(go.Bar(x=sbin_df["time"], y=sbin_df["macd_hist"],
                marker_color=clrs, name="Hist", showlegend=False), row=3, col=1)
            fig.add_trace(go.Scatter(x=sbin_df["time"], y=sbin_df["macd"],
                line=dict(color="#58a6ff", width=1), name="MACD"), row=3, col=1)
            fig.add_trace(go.Scatter(x=sbin_df["time"], y=sbin_df["macd_signal"],
                line=dict(color="#f0c060", width=1), name="Sig"), row=3, col=1)
        # Volume
        if has_vol:
            vol_clr = ["#3fb950" if o <= c else "#f85149"
                       for o, c in zip(sbin_df["open"], sbin_df["close"])]
            fig.add_trace(go.Bar(x=sbin_df["time"], y=sbin_df["volume"],
                marker_color=vol_clr, name="Volume", showlegend=False), row=4, col=1)

        fig.update_layout(
            height=540, template="plotly_dark",
            paper_bgcolor="#161b22", plot_bgcolor="#0d1117",
            margin=dict(l=0,r=0,t=30,b=0),
            legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0, font=dict(size=10)),
            xaxis_rangeslider_visible=False,
            title=dict(text=f"SBIN — {tf_label} • Updated {now_ist.strftime('%H:%M:%S')}",
                       font=dict(size=13)),
        )
        fig.update_yaxes(gridcolor="#1c2128")
        fig.update_xaxes(gridcolor="#1c2128")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Chart loading… (market closed on weekends)")

    # NIFTY chart
    if not nifty_df.empty:
        nfig = go.Figure(go.Candlestick(
            x=nifty_df["time"], open=nifty_df["open"], high=nifty_df["high"],
            low=nifty_df["low"], close=nifty_df["close"], name="NIFTY",
            increasing_line_color="#3fb950", decreasing_line_color="#f85149",
        ))
        nfig.update_layout(
            height=200, template="plotly_dark",
            paper_bgcolor="#161b22", plot_bgcolor="#0d1117",
            margin=dict(l=0,r=0,t=30,b=0),
            xaxis_rangeslider_visible=False,
            title=dict(text=f"NIFTY 50 — {tf_label}", font=dict(size=12)),
        )
        nfig.update_yaxes(gridcolor="#1c2128")
        nfig.update_xaxes(gridcolor="#1c2128")
        st.plotly_chart(nfig, use_container_width=True)

    # Correlation heatmap
    if corr_data and corr_data.get("daily_data"):
        st.markdown("#### SBIN vs NIFTY — Daily Direction (last 30 days)")
        daily = corr_data["daily_data"]
        df_h  = pd.DataFrame(daily)
        clrs  = ["rgba(63,185,80,.55)" if r else "rgba(248,81,73,.55)" for r in df_h["same_dir"]]
        tips  = [f"{row['date']}<br>SBIN:{row['sbin_ret']:+.2f}%  NIFTY:{row['nifty_ret']:+.2f}%"
                 for _, row in df_h.iterrows()]
        hfig = go.Figure(go.Bar(x=df_h["date"], y=[1]*len(df_h),
            marker_color=clrs, hovertext=tips, hoverinfo="text"))
        hfig.update_layout(height=95, template="plotly_dark",
            paper_bgcolor="#161b22", plot_bgcolor="#0d1117",
            margin=dict(l=0,r=0,t=4,b=24),
            yaxis=dict(showticklabels=False, showgrid=False),
            xaxis=dict(tickfont=dict(size=9)))
        st.plotly_chart(hfig, use_container_width=True)
        st.caption("🟢 Same direction  🔴 Opposite — hover for details")


# ── RIGHT: Signal + Indicators ──────────────────────────
with right_col:
    if signals:
        sig_color = signals.get("color", "#d29922")
        st.markdown(
            f'<div class="signal-card" style="border-color:{sig_color};color:{sig_color}">'
            f'<div style="font-size:20px;font-weight:800">{signals.get("signal","—")}</div>'
            f'<div style="font-size:24px;font-weight:700;margin:4px 0">₹{signals.get("current_price",0):.2f}</div>'
            f'<div style="font-size:11px;color:#8b949e">{tf_label}</div></div>',
            unsafe_allow_html=True)

    st.markdown("**Risk (ATR-based)**")
    c1, c2 = st.columns(2)
    c1.metric("SL",  f"₹{signals.get('stop_loss',0):.2f}" if signals else "—")
    c2.metric("ATR", f"{signals.get('atr',0):.2f}"         if signals else "—")
    c1.metric("T1",  f"₹{signals.get('target1',0):.2f}"   if signals else "—")
    c2.metric("T2",  f"₹{signals.get('target2',0):.2f}"   if signals else "—")

    st.divider()
    st.markdown("**Indicators**")
    if signals and not sbin_df.empty:
        last = sbin_df.iloc[-1]
        cp   = signals.get("current_price", 0)
        def rsi_color(v):
            if v is None: return "#8b949e"
            return "#f85149" if v>70 else ("#3fb950" if v<30 else "#d29922")
        for nm, val, bull in [
            ("EMA 9",  last.get("ema9"),  cp>(last.get("ema9") or cp)),
            ("EMA 21", last.get("ema21"), cp>(last.get("ema21") or cp)),
            ("EMA 50", last.get("ema50"), cp>(last.get("ema50") or cp)),
            ("RSI",    signals.get("rsi"), None),
            ("MACD",   signals.get("macd"), (signals.get("macd") or 0)>(signals.get("macd_signal") or 0)),
            ("VWAP",   signals.get("vwap"), cp>(signals.get("vwap") or 0) if signals.get("vwap") else None),
            ("BB+",    last.get("bb_upper"), False),
            ("BB-",    last.get("bb_lower"), True),
        ]:
            if val is None: continue
            col_ = rsi_color(val) if nm=="RSI" else ("#8b949e" if bull is None else ("#3fb950" if bull else "#f85149"))
            v_str = f"{float(val):.2f}" if val else "—"
            st.markdown(
                f'<div class="metric-row"><span style="color:#8b949e">{nm}</span>'
                f'<span style="color:{col_};font-weight:600">{v_str}</span></div>',
                unsafe_allow_html=True)

    st.divider()
    st.markdown("**Why This Signal?**")
    for r in signals.get("reasons", []):
        st.markdown(f"• {r}")

    st.divider()
    st.markdown("**Correlation**")
    if corr_data:
        cr = corr_data.get("correlation", 0)
        st.progress(abs(cr), text=f"Pearson r = {cr:.3f}")
        for lbl, val in [
            ("Beta",      f"{corr_data.get('beta',0):.3f}"),
            ("Same (90d)",f"{corr_data.get('same_dir_pct')}%"),
            ("Last 30d",  f"{corr_data.get('last30_pct')}%"),
            ("RS 10d",    f"{corr_data.get('relative_strength_10d',0):+.3f}%"),
        ]:
            st.markdown(f'<div class="metric-row"><span style="color:#8b949e">{lbl}</span>'
                        f'<span style="font-weight:600">{val}</span></div>', unsafe_allow_html=True)
        if cr > 0.7: st.success("Follows NIFTY strongly")
        elif cr > 0.4: st.warning("Moderate correlation")
        else: st.error("Moving independently")

    if pivots:
        st.divider()
        st.markdown("**Pivot Points**")
        for lv, val in [("R3",pivots.get("R3")),("R2",pivots.get("R2")),("R1",pivots.get("R1")),
                        ("P",pivots.get("P")),("S1",pivots.get("S1")),("S2",pivots.get("S2")),("S3",pivots.get("S3"))]:
            if val is None: continue
            col_ = "#3fb950" if lv.startswith("R") else ("#d29922" if lv=="P" else "#f85149")
            st.markdown(f'<div class="metric-row"><span style="color:{col_};font-weight:700">{lv}</span>'
                        f'<span style="font-weight:600">₹{val}</span></div>', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════
#  BACKGROUND RERUN LOOP
# ══════════════════════════════════════════════════════
time.sleep(1)
st.rerun()
