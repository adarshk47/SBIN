"""SBIN Intraday Analysis Dashboard — Streamlit"""
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
from datetime import datetime
import pytz
from angel_api import AngelOneAPI
from analysis import to_df, add_indicators, generate_signals, correlation_analysis, pivot_points

# ── Page config ─────────────────────────────────────────
st.set_page_config(
    page_title="SBIN Analyzer",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

IST = pytz.timezone("Asia/Kolkata")

# ── Auto refresh via HTML meta tag (no extra package needed) ──
st.markdown('<meta http-equiv="refresh" content="60">', unsafe_allow_html=True)

# ── Custom CSS ───────────────────────────────────────────
st.markdown("""
<style>
  .block-container { padding-top: 0.8rem; padding-bottom: 0; }
  .signal-card {
    padding: 16px; border-radius: 10px; text-align: center;
    border: 2px solid; margin-bottom: 10px;
  }
  .metric-row {
    display: flex; justify-content: space-between;
    padding: 5px 0; border-bottom: 1px solid #30363d; font-size: 14px;
  }
  .up   { color: #3fb950; font-weight: 700; }
  .down { color: #f85149; font-weight: 700; }
  .neu  { color: #d29922; font-weight: 700; }
  h1, h2, h3 { margin-bottom: 0 !important; }
  .stMetric label { font-size: 12px !important; }
</style>
""", unsafe_allow_html=True)


# ── Cached API singleton ─────────────────────────────────
@st.cache_resource
def get_api():
    api = AngelOneAPI()
    api.authenticate()
    return api


@st.cache_data(ttl=30)
def fetch_live():
    return get_api().get_ltp("SBIN"), get_api().get_ltp("NIFTY")


@st.cache_data(ttl=60)
def fetch_candles(symbol, interval, days):
    return get_api().get_candles(symbol, interval, days=days)


@st.cache_data(ttl=300)
def fetch_correlation(days=90):
    s = get_api().get_daily_candles("SBIN",  days=days)
    n = get_api().get_daily_candles("NIFTY", days=days)
    return correlation_analysis(s, n)


# ── Helpers ──────────────────────────────────────────────
def pct_color(v):
    if v is None: return "#8b949e"
    return "#3fb950" if v >= 0 else "#f85149"

def fmt(v, dec=2):
    if v is None: return "—"
    return f"{v:.{dec}f}"

def rsi_color(v):
    if v is None: return "#8b949e"
    if v > 70: return "#f85149"
    if v < 30: return "#3fb950"
    return "#d29922"


# ════════════════════════════════════════════════════════
#  MAIN LAYOUT
# ════════════════════════════════════════════════════════

# ── Header ──────────────────────────────────────────────
now_ist = datetime.now(IST)
sbin_ltp, nifty_ltp = fetch_live()

h1, h2, h3, h4 = st.columns([2, 1.5, 1.5, 1])
with h1:
    st.markdown("## 📈 SBIN Intraday Analyzer")
    st.caption(f"Angel One • NSE • {now_ist.strftime('%d %b %Y  %H:%M:%S IST')}")

with h2:
    if sbin_ltp:
        chg = sbin_ltp['ltp'] - sbin_ltp['close']
        pct = chg / sbin_ltp['close'] * 100 if sbin_ltp['close'] else 0
        delta_str = f"{chg:+.2f} ({pct:+.2f}%)"
        st.metric("SBIN", f"₹{sbin_ltp['ltp']:.2f}", delta_str)
    else:
        st.metric("SBIN", "—")

with h3:
    if nifty_ltp:
        chg = nifty_ltp['ltp'] - nifty_ltp['close']
        pct = chg / nifty_ltp['close'] * 100 if nifty_ltp['close'] else 0
        delta_str = f"{chg:+.2f} ({pct:+.2f}%)"
        st.metric("NIFTY 50", f"₹{nifty_ltp['ltp']:.2f}", delta_str)
    else:
        st.metric("NIFTY 50", "—")

with h4:
    if st.button("↻ Refresh Now", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

st.divider()

# ── Timeframe selector ───────────────────────────────────
TF_OPTIONS = {"1 Min": "1m", "5 Min": "5m", "15 Min": "15m", "1 Hour": "1h", "Daily": "1d"}
TF_DAYS    = {"1m": 2, "5m": 3, "15m": 5, "1h": 20, "1d": 365}

tf_label = st.radio("Timeframe", list(TF_OPTIONS.keys()), index=1, horizontal=True)
tf = TF_OPTIONS[tf_label]
days = TF_DAYS[tf]

# ── Fetch & process data ─────────────────────────────────
with st.spinner("Loading chart data..."):
    sbin_raw   = fetch_candles("SBIN",  tf, days)
    nifty_raw  = fetch_candles("NIFTY", tf, days)
    corr_data  = fetch_correlation(90)

sbin_df  = add_indicators(to_df(sbin_raw))  if sbin_raw  else pd.DataFrame()
nifty_df = to_df(nifty_raw)                 if nifty_raw else pd.DataFrame()

signals = generate_signals(sbin_df) if not sbin_df.empty else {}
pivots  = pivot_points(sbin_df)     if tf == "1d" and not sbin_df.empty else {}


# ════════════════════════════════════════════════════════
#  CHARTS  +  RIGHT PANEL
# ════════════════════════════════════════════════════════
left, right = st.columns([3, 1.2])

# ── LEFT: Charts ────────────────────────────────────────
with left:

    # SBIN candlestick chart
    if not sbin_df.empty:
        fig = make_subplots(
            rows=3, cols=1,
            shared_xaxes=True,
            row_heights=[0.60, 0.20, 0.20],
            vertical_spacing=0.02,
        )

        # Candlesticks
        fig.add_trace(go.Candlestick(
            x=sbin_df["time"], open=sbin_df["open"], high=sbin_df["high"],
            low=sbin_df["low"], close=sbin_df["close"],
            name="SBIN", increasing_line_color="#3fb950", decreasing_line_color="#f85149",
        ), row=1, col=1)

        # EMAs
        for col, color, name in [("ema9","#f0c060","EMA9"), ("ema21","#58a6ff","EMA21"), ("ema50","#bc8cff","EMA50")]:
            if col in sbin_df.columns:
                fig.add_trace(go.Scatter(x=sbin_df["time"], y=sbin_df[col],
                    line=dict(color=color, width=1), name=name), row=1, col=1)

        # VWAP
        if "vwap" in sbin_df.columns:
            fig.add_trace(go.Scatter(x=sbin_df["time"], y=sbin_df["vwap"],
                line=dict(color="#ff7b00", width=2, dash="dot"), name="VWAP"), row=1, col=1)

        # Bollinger Bands
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

        # MACD
        if "macd" in sbin_df.columns:
            colors = ["#3fb950" if v >= 0 else "#f85149" for v in sbin_df["macd_hist"].fillna(0)]
            fig.add_trace(go.Bar(x=sbin_df["time"], y=sbin_df["macd_hist"],
                marker_color=colors, name="MACD Hist", showlegend=False), row=3, col=1)
            fig.add_trace(go.Scatter(x=sbin_df["time"], y=sbin_df["macd"],
                line=dict(color="#58a6ff", width=1), name="MACD"), row=3, col=1)
            fig.add_trace(go.Scatter(x=sbin_df["time"], y=sbin_df["macd_signal"],
                line=dict(color="#f0c060", width=1), name="Signal"), row=3, col=1)

        fig.update_layout(
            height=520, template="plotly_dark",
            paper_bgcolor="#161b22", plot_bgcolor="#0d1117",
            margin=dict(l=0, r=0, t=30, b=0),
            legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0),
            xaxis_rangeslider_visible=False,
            title=dict(text=f"SBIN — {tf_label}", font=dict(size=14)),
        )
        fig.update_yaxes(gridcolor="#1c2128", showgrid=True)
        fig.update_xaxes(gridcolor="#1c2128", showgrid=True)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("SBIN chart data unavailable — market may be closed.")

    # NIFTY reference chart
    if not nifty_df.empty:
        nfig = go.Figure(go.Candlestick(
            x=nifty_df["time"], open=nifty_df["open"], high=nifty_df["high"],
            low=nifty_df["low"], close=nifty_df["close"],
            increasing_line_color="#3fb950", decreasing_line_color="#f85149",
            name="NIFTY",
        ))
        nfig.update_layout(
            height=220, template="plotly_dark",
            paper_bgcolor="#161b22", plot_bgcolor="#0d1117",
            margin=dict(l=0, r=0, t=30, b=0),
            xaxis_rangeslider_visible=False,
            title=dict(text=f"NIFTY 50 — {tf_label} (Reference)", font=dict(size=13)),
        )
        nfig.update_yaxes(gridcolor="#1c2128")
        nfig.update_xaxes(gridcolor="#1c2128")
        st.plotly_chart(nfig, use_container_width=True)

    # Correlation Heatmap
    if corr_data and corr_data.get("daily_data"):
        st.markdown("### SBIN vs NIFTY — Daily Direction (last 30 days)")
        daily = corr_data["daily_data"]
        df_heat = pd.DataFrame(daily)

        hfig = go.Figure()
        for _, row in df_heat.iterrows():
            color = "rgba(63,185,80,0.5)" if row["same_dir"] else "rgba(248,81,73,0.5)"
            tip   = f"{row['date']}<br>SBIN: {row['sbin_ret']:+.2f}%<br>NIFTY: {row['nifty_ret']:+.2f}%"
            hfig.add_trace(go.Bar(
                x=[row["date"]], y=[1],
                marker_color=color, hovertext=tip, hoverinfo="text",
                showlegend=False,
            ))

        hfig.update_layout(
            height=110, template="plotly_dark",
            paper_bgcolor="#161b22", plot_bgcolor="#0d1117",
            margin=dict(l=0, r=0, t=10, b=30),
            barmode="stack",
            yaxis=dict(showticklabels=False, showgrid=False),
            xaxis=dict(tickfont=dict(size=9)),
        )
        st.plotly_chart(hfig, use_container_width=True)
        st.caption("🟢 Same direction  🔴 Opposite direction  — hover for details")


# ── RIGHT: Analysis Panel ────────────────────────────────
with right:

    # Signal Box
    if signals:
        sig_color = signals.get("color", "#d29922")
        st.markdown(f"""
        <div class="signal-card" style="border-color:{sig_color};color:{sig_color}">
          <div style="font-size:22px;font-weight:800;letter-spacing:1px">{signals.get('signal','—')}</div>
          <div style="font-size:26px;font-weight:700;margin:4px 0">
            ₹{signals.get('current_price', 0):.2f}
          </div>
          <div style="font-size:12px;color:#8b949e">{tf_label} Timeframe</div>
        </div>
        """, unsafe_allow_html=True)

    # Risk Levels
    with st.container():
        st.markdown("**Risk Levels (ATR-based)**")
        c1, c2 = st.columns(2)
        c1.metric("Stop Loss",  f"₹{signals.get('stop_loss',0):.2f}" if signals else "—")
        c2.metric("ATR",        f"{signals.get('atr',0):.2f}"         if signals else "—")
        c1.metric("Target 1",   f"₹{signals.get('target1',0):.2f}"   if signals else "—")
        c2.metric("Target 2",   f"₹{signals.get('target2',0):.2f}"   if signals else "—")

    st.divider()

    # Technical Indicators
    st.markdown("**Indicators**")
    if signals and not sbin_df.empty:
        last = sbin_df.iloc[-1]
        cp   = signals.get("current_price", 0)
        rows = [
            ("EMA 9",    last.get("ema9"),    cp > last.get("ema9",  cp), True),
            ("EMA 21",   last.get("ema21"),   cp > last.get("ema21", cp), True),
            ("EMA 50",   last.get("ema50"),   cp > last.get("ema50", cp), True),
            ("RSI (14)", signals.get("rsi"),  None, False),
            ("MACD",     signals.get("macd"), signals.get("macd",0) > signals.get("macd_signal",0), True),
            ("VWAP",     signals.get("vwap"), cp > (signals.get("vwap") or 0) if signals.get("vwap") else None, True),
            ("BB Upper", last.get("bb_upper"), False, True),
            ("BB Lower", last.get("bb_lower"), True, True),
        ]
        for name, val, bull, use_bull in rows:
            if val is None: continue
            if name == "RSI (14)":
                color = rsi_color(val)
            elif use_bull:
                color = "#3fb950" if bull else "#f85149"
            else:
                color = "#8b949e"
            st.markdown(
                f'<div class="metric-row"><span style="color:#8b949e">{name}</span>'
                f'<span style="color:{color};font-weight:600">{fmt(val)}</span></div>',
                unsafe_allow_html=True,
            )

    st.divider()

    # Signal Reasons
    st.markdown("**Why This Signal?**")
    for reason in signals.get("reasons", []):
        st.markdown(f"• {reason}")

    st.divider()

    # Correlation Stats
    st.markdown("**SBIN × NIFTY Correlation**")
    if corr_data:
        corr_r = corr_data.get("correlation", 0)
        st.progress(abs(corr_r), text=f"Pearson r = {corr_r:.3f}")

        rows_c = [
            ("Beta",             f"{corr_data.get('beta', 0):.3f}"),
            ("Same Dir (90d)",   f"{corr_data.get('same_dir_days')}d / {corr_data.get('total_days')}d ({corr_data.get('same_dir_pct')}%)"),
            ("Last 30d",         f"{corr_data.get('last30_same')}/30 ({corr_data.get('last30_pct')}%)"),
            ("Last 60d",         f"{corr_data.get('last60_same')}/60 ({corr_data.get('last60_pct')}%)"),
            ("RS (10d avg)",     f"{corr_data.get('relative_strength_10d', 0):+.3f}%"),
        ]
        for label, val in rows_c:
            st.markdown(
                f'<div class="metric-row"><span style="color:#8b949e">{label}</span>'
                f'<span style="font-weight:600">{val}</span></div>',
                unsafe_allow_html=True,
            )

        note_r = corr_data.get("correlation", 0)
        if note_r > 0.7:
            st.success("SBIN strongly follows NIFTY — use NIFTY as leading indicator")
        elif note_r > 0.4:
            st.warning("Moderate correlation — NIFTY gives directional bias")
        else:
            st.error("Weak correlation — SBIN moving independently")

    # Pivot Points (Daily only)
    if pivots:
        st.divider()
        st.markdown("**Pivot Points (Daily)**")
        for level, val in [("R3", pivots.get("R3")), ("R2", pivots.get("R2")), ("R1", pivots.get("R1")),
                            ("Pivot", pivots.get("P")), ("S1", pivots.get("S1")), ("S2", pivots.get("S2")),
                            ("S3", pivots.get("S3"))]:
            if val is None: continue
            color = "#3fb950" if level.startswith("R") else ("#d29922" if level == "Pivot" else "#f85149")
            st.markdown(
                f'<div class="metric-row"><span style="color:{color};font-weight:700">{level}</span>'
                f'<span style="font-weight:600">₹{val}</span></div>',
                unsafe_allow_html=True,
            )
