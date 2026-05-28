/* ── SBIN Intraday Analyzer — Frontend ── */

const BASE = "";
let currentTF  = "5m";
let sbinChart  = null;
let niftyChart = null;
let candleSeries  = null;
let ema9Series    = null;
let ema21Series   = null;
let ema50Series   = null;
let vwapSeries    = null;
let bbUpperSeries = null;
let bbLowerSeries = null;
let niftyCandleSeries = null;
let liveTimer = null;

/* ══════════ CHART INIT ══════════ */
function initCharts() {
  const chartOpts = {
    layout: { background: { color: "#161b22" }, textColor: "#c9d1d9" },
    grid:   { vertLines: { color: "#1c2128" }, horzLines: { color: "#1c2128" } },
    crosshair: { mode: 1 },
    rightPriceScale: { borderColor: "#30363d" },
    timeScale: { borderColor: "#30363d", timeVisible: true, secondsVisible: false },
  };

  // SBIN chart
  sbinChart = LightweightCharts.createChart(document.getElementById("chart-sbin"), { ...chartOpts, height: 360 });
  candleSeries = sbinChart.addCandlestickSeries({
    upColor: "#3fb950", downColor: "#f85149",
    borderUpColor: "#3fb950", borderDownColor: "#f85149",
    wickUpColor: "#3fb950", wickDownColor: "#f85149",
  });

  ema9Series  = sbinChart.addLineSeries({ color: "#f0c060", lineWidth: 1, title: "EMA9"  });
  ema21Series = sbinChart.addLineSeries({ color: "#58a6ff", lineWidth: 1, title: "EMA21" });
  ema50Series = sbinChart.addLineSeries({ color: "#bc8cff", lineWidth: 1, title: "EMA50" });
  vwapSeries  = sbinChart.addLineSeries({ color: "#ff7b00", lineWidth: 2, title: "VWAP", lineStyle: 2 });
  bbUpperSeries = sbinChart.addLineSeries({ color: "#484f58", lineWidth: 1, title: "BB+" });
  bbLowerSeries = sbinChart.addLineSeries({ color: "#484f58", lineWidth: 1, title: "BB-" });

  // NIFTY chart
  niftyChart = LightweightCharts.createChart(document.getElementById("chart-nifty"), { ...chartOpts, height: 180 });
  niftyCandleSeries = niftyChart.addCandlestickSeries({
    upColor: "#3fb950", downColor: "#f85149",
    borderUpColor: "#3fb950", borderDownColor: "#f85149",
    wickUpColor: "#3fb950", wickDownColor: "#f85149",
  });
}

/* ══════════ TIMEFRAME SELECTOR ══════════ */
function setTF(tf) {
  currentTF = tf;
  document.querySelectorAll(".tf-btn").forEach(b => {
    b.classList.toggle("active", b.textContent.trim().toLowerCase() === tf);
  });
  document.getElementById("signal-tf").textContent = tf.toUpperCase() + " Timeframe";
  loadCharts();
}

/* ══════════ LOAD CANDLES + INDICATORS ══════════ */
async function loadCharts() {
  showLoading("sbin", true);
  showLoading("nifty", true);

  const days = tfToDays(currentTF);

  const [sbinData, niftyData] = await Promise.all([
    fetchJSON(`/api/candles/SBIN/${currentTF}?days=${days}`),
    fetchJSON(`/api/candles/NIFTY/${currentTF}?days=${days}`),
  ]);

  if (sbinData && sbinData.candles) {
    renderSbinChart(sbinData);
    updateSignalPanel(sbinData.signals);
    updateIndicatorPanel(sbinData.signals);
    if (currentTF === "1d" && sbinData.pivots) {
      renderPivots(sbinData.pivots);
    } else {
      document.getElementById("pivot-card").style.display = "none";
    }
  }

  if (niftyData && niftyData.candles) {
    renderNiftyChart(niftyData.candles);
  }

  showLoading("sbin", false);
  showLoading("nifty", false);
}

function tfToDays(tf) {
  return { "1m": 2, "5m": 3, "15m": 5, "1h": 20, "1d": 365 }[tf] || 5;
}

/* ══════════ RENDER SBIN CHART ══════════ */
function renderSbinChart(data) {
  const candles = data.candles;
  if (!candles || candles.length === 0) return;

  const toTs = t => Math.floor(new Date(t).getTime() / 1000);

  candleSeries.setData(candles.map(c => ({
    time: toTs(c.time), open: c.open, high: c.high, low: c.low, close: c.close
  })));

  setLine(ema9Series,    candles, "ema9");
  setLine(ema21Series,   candles, "ema21");
  setLine(ema50Series,   candles, "ema50");
  setLine(vwapSeries,    candles, "vwap");
  setLine(bbUpperSeries, candles, "bb_upper");
  setLine(bbLowerSeries, candles, "bb_lower");

  sbinChart.timeScale().fitContent();
}

function setLine(series, candles, key) {
  const data = candles
    .filter(c => c[key] != null && !isNaN(c[key]))
    .map(c => ({ time: Math.floor(new Date(c.time).getTime() / 1000), value: c[key] }));
  series.setData(data);
}

/* ══════════ RENDER NIFTY CHART ══════════ */
function renderNiftyChart(candles) {
  if (!candles || candles.length === 0) return;
  const toTs = t => Math.floor(new Date(t).getTime() / 1000);
  niftyCandleSeries.setData(candles.map(c => ({
    time: toTs(c.time), open: c.open, high: c.high, low: c.low, close: c.close
  })));
  niftyChart.timeScale().fitContent();
}

/* ══════════ SIGNAL PANEL ══════════ */
function updateSignalPanel(sig) {
  if (!sig) return;
  const box = document.getElementById("signal-box");
  const color = sig.color || "#ffeb3b";

  box.style.borderColor = color;
  box.style.color = color;
  document.getElementById("signal-label").textContent = sig.signal || "—";
  document.getElementById("signal-price").textContent = sig.current_price ? "₹" + sig.current_price.toFixed(2) : "—";

  setText("sl-val",  sig.stop_loss ? "₹" + sig.stop_loss  : "—");
  setText("t1-val",  sig.target1   ? "₹" + sig.target1    : "—");
  setText("t2-val",  sig.target2   ? "₹" + sig.target2    : "—");
  setText("atr-val", sig.atr       ? sig.atr.toFixed(2)    : "—");

  // Reasons
  const ul = document.getElementById("reasons-list");
  ul.innerHTML = (sig.reasons || []).map(r => `<li>${r}</li>`).join("") || "<li>No reasons</li>";
}

function updateIndicatorPanel(sig) {
  if (!sig) return;
  const cp = sig.current_price || 0;
  const colored = (val, ref) => {
    if (!val || !ref) return fmt(val);
    const cls = cp > val ? "up" : "down";
    return `<span class="${cls}">${fmt(val)}</span>`;
  };

  setHTML("ema9-val",  colored(sig.ema9, cp));
  setHTML("ema21-val", colored(sig.ema21, cp));
  setHTML("ema50-val", colored(sig.ema50, cp));

  const rsi = sig.rsi;
  const rsiCls = rsi > 70 ? "down" : rsi < 30 ? "up" : "neu";
  setHTML("rsi-val", `<span class="${rsiCls}">${fmt(rsi)}</span>`);

  const macdColor = sig.macd > sig.macd_signal ? "up" : "down";
  setHTML("macd-val", `<span class="${macdColor}">${fmt(sig.macd)} / ${fmt(sig.macd_signal)}</span>`);

  if (sig.vwap) {
    const vwapCls = cp > sig.vwap ? "up" : "down";
    setHTML("vwap-val", `<span class="${vwapCls}">${fmt(sig.vwap)}</span>`);
  }
  setHTML("bbu-val", `<span class="down">${fmt(sig.bb_upper)}</span>`);
  setHTML("bbl-val", `<span class="up">${fmt(sig.bb_lower)}</span>`);
}

/* ══════════ PIVOT TABLE ══════════ */
function renderPivots(p) {
  if (!p || !p.P) return;
  const card = document.getElementById("pivot-card");
  const table = document.getElementById("pivot-table");
  card.style.display = "block";
  const rows = [
    ["R3", p.R3, "pivot-R"], ["R2", p.R2, "pivot-R"], ["R1", p.R1, "pivot-R"],
    ["Pivot", p.P, "pivot-P"],
    ["S1", p.S1, "pivot-S"], ["S2", p.S2, "pivot-S"], ["S3", p.S3, "pivot-S"],
  ];
  table.innerHTML = rows.map(([l, v, cls]) =>
    `<tr><td class="${cls}">${l}</td><td class="${cls}">₹${v}</td></tr>`
  ).join("");
}

/* ══════════ LIVE PRICES ══════════ */
async function fetchLive() {
  const data = await fetchJSON("/api/live");
  if (!data) return;

  updatePriceTile("sbin",  data.SBIN);
  updatePriceTile("nifty", data.NIFTY);
  setText("clock", data.date + "  " + data.time);
}

function updatePriceTile(id, d) {
  if (!d || !d.ltp) return;
  const ltpEl = document.getElementById(`${id}-ltp`);
  const chgEl = document.getElementById(`${id}-chg`);
  const ltp = d.ltp;
  const chg = ltp - d.close;
  const pct = d.close ? (chg / d.close * 100) : 0;
  const cls = chg >= 0 ? "up" : "down";
  const sign = chg >= 0 ? "+" : "";

  ltpEl.textContent = "₹" + ltp.toFixed(2);
  ltpEl.className   = `ltp ${cls}`;
  chgEl.textContent = `${sign}${chg.toFixed(2)} (${sign}${pct.toFixed(2)}%)`;
  chgEl.className   = `chg ${cls}`;
}

/* ══════════ CORRELATION ══════════ */
async function loadCorrelation() {
  const data = await fetchJSON("/api/correlation?days=90");
  if (!data || !data.correlation) return;

  setText("corr-val",  data.correlation.toFixed(3));
  setText("beta-val",  data.beta.toFixed(3));
  setText("same-pct",  data.same_dir_pct + "%");
  setText("l30-same",  `${data.last30_same}/30 (${data.last30_pct}%)`);
  setText("l60-same",  `${data.last60_same}/60 (${data.last60_pct}%)`);

  const rs = data.relative_strength_10d;
  const rsEl = document.getElementById("rs-val");
  rsEl.textContent = (rs >= 0 ? "+" : "") + rs.toFixed(2) + "%";
  rsEl.className = `val ${rs >= 0 ? "up" : "down"}`;

  // Sidebar correlation
  setText("corr-r",    data.correlation.toFixed(3));
  setText("corr-beta", data.beta.toFixed(3));
  setText("corr-same", `${data.same_dir_days}/${data.total_days} days (${data.same_dir_pct}%)`);

  const barPct = Math.round(Math.abs(data.correlation) * 100);
  const barEl  = document.getElementById("corr-bar");
  barEl.style.width = barPct + "%";
  barEl.style.background = data.correlation >= 0 ? "var(--green)" : "var(--red)";

  const noteEl = document.getElementById("corr-note");
  if (data.correlation > 0.7) {
    noteEl.textContent = "✅ SBIN strongly follows NIFTY — use NIFTY as leading indicator";
  } else if (data.correlation > 0.4) {
    noteEl.textContent = "⚡ Moderate correlation — NIFTY gives directional bias";
  } else {
    noteEl.textContent = "⚠️ Weak correlation — SBIN moving independently";
  }

  // Heatmap
  renderHeatmap(data.daily_data || []);
}

function renderHeatmap(days) {
  const wrap = document.getElementById("heatmap");
  wrap.innerHTML = "";
  days.forEach(d => {
    const div = document.createElement("div");
    div.className = `heatmap-day ${d.same_dir ? "same" : "diff"}`;
    const dateStr = d.date.slice(5);  // MM-DD
    const tip = `${d.date} | SBIN:${d.sbin_ret>0?"+":""}${d.sbin_ret}% | NIFTY:${d.nifty_ret>0?"+":""}${d.nifty_ret}%`;
    div.setAttribute("data-tip", tip);
    div.textContent = dateStr.slice(3);  // day only
    wrap.appendChild(div);
  });
}

/* ══════════ HELPERS ══════════ */
function fmt(v) {
  if (v == null || isNaN(v)) return "—";
  return Number(v).toFixed(2);
}
function setText(id, v)  { const el = document.getElementById(id); if (el) el.textContent = v; }
function setHTML(id, v)  { const el = document.getElementById(id); if (el) el.innerHTML = v; }

function showLoading(id, show) {
  const el = document.getElementById(`loading-${id}`);
  if (el) el.style.display = show ? "flex" : "none";
}

async function fetchJSON(url) {
  try {
    const r = await fetch(BASE + url);
    if (!r.ok) { console.warn("HTTP", r.status, url); return null; }
    return await r.json();
  } catch (e) {
    console.error("Fetch error", url, e);
    return null;
  }
}

/* ══════════ REFRESH ALL ══════════ */
function refreshAll() {
  fetchLive();
  loadCharts();
  loadCorrelation();
}

/* ══════════ AUTO-REFRESH ══════════ */
function startAutoRefresh() {
  // Live prices every 15s
  fetchLive();
  liveTimer = setInterval(fetchLive, 15000);
  // Charts every 60s
  setInterval(loadCharts, 60000);
}

/* ══════════ INIT ══════════ */
window.addEventListener("DOMContentLoaded", () => {
  initCharts();
  loadCharts();
  loadCorrelation();
  startAutoRefresh();
});

window.addEventListener("resize", () => {
  if (sbinChart)  sbinChart.applyOptions({ width: document.getElementById("chart-sbin").clientWidth });
  if (niftyChart) niftyChart.applyOptions({ width: document.getElementById("chart-nifty").clientWidth });
});
