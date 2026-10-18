/* ============================================================================
   Liquidity & Sentiment — Market Regime Interpretation System (Front-End App)
   Reads window.DASH (built by build_dashboard.py) — zero hard-coded formulas.
   ============================================================================ */

(function () {
  "use strict";

  const D = window.DASH;
  if (!D) {
    document.body.innerHTML = "<p style='padding:24px;color:#be123c;'>Error: data.js not loaded. Run <code>python3 build_dashboard.py</code> first.</p>";
    return;
  }

  const CFG = Object.fromEntries(D.dictionary.map(d => [d.key, d]));

  // State
  const state = {
    rangePreset: "3Y",
    start: null,
    end: D.meta.latest_date,
    compMode: "contrib", // "contrib" | "levels"
    quadMode: "pct",     // "pct" | "z"
    tblSortCol: "date",
    tblSortDir: "desc",
    tblPage: 1,
    tblPageSize: 50,
    tblFollowRange: true,
    tblRegime: "",
    tblLiqOnly: false,
    tblVisibleCols: new Set(["date", "spx", "net_liq", "nl_chg13w", "vix", "aaii", "pc", "cnn", "nfci", "hy", "sent_comp", "stress", "regime"]),
  };

  const charts = {};

  // ==========================================================================
  // Formatting & Tone Helpers
  // ==========================================================================
  function fmtVal(v, key) {
    if (v === null || v === undefined || Number.isNaN(v)) return "—";
    if (key === "sent_comp") return `${Math.round(v)}`;
    const c = CFG[key];
    if (!c || !c.fmt) return Number(v).toLocaleString(undefined, { maximumFractionDigits: 2 });
    const dp = c.fmt.dp ?? 2;
    const pre = c.fmt.prefix ?? "";
    const suf = c.fmt.suffix ?? "";
    return `${pre}${Number(v).toLocaleString(undefined, { minimumFractionDigits: dp, maximumFractionDigits: dp })}${suf}`;
  }

  function fmtSigned(v, key) {
    if (v === null || v === undefined || Number.isNaN(v)) return "—";
    const sign = v > 0 ? "+" : v < 0 ? "−" : "";
    return sign + fmtVal(Math.abs(v), key);
  }

  function ordinal(n) {
    if (n === null || n === undefined || Number.isNaN(n)) return "—";
    const k = Math.round(n);
    const mod100 = k % 100;
    const suf = (mod100 >= 11 && mod100 <= 13) ? "th" : ({ 1: "st", 2: "nd", 3: "rd" }[k % 10] || "th");
    return `${k}${suf}`;
  }

  function labelTone(label) {
    const pos = new Set(["Risk-On", "Expanding", "Easing", "Greed", "Low", "Improving"]);
    const neg = new Set(["Risk-Off", "Contracting", "Tightening", "Fear", "High", "Deteriorating", "Weakening"]);
    const warn = new Set(["Mixed", "Transitional", "Medium"]);
    if (pos.has(label)) return "pos";
    if (neg.has(label)) return "neg";
    if (warn.has(label)) return "warn";
    return "neu";
  }

  function badgeHTML(text, tone) {
    return `<span class="badge ${tone || labelTone(text)}">${text}</span>`;
  }

  function addDays(dateStr, days) {
    const dt = new Date(dateStr + "T00:00:00Z");
    dt.setUTCDate(dt.getUTCDate() + days);
    return dt.toISOString().slice(0, 10);
  }

  function computePresetStart(preset, latest) {
    const y = latest.slice(0, 4);
    switch (preset) {
      case "1M": return addDays(latest, -31);
      case "3M": return addDays(latest, -92);
      case "6M": return addDays(latest, -183);
      case "YTD": return `${y}-01-01`;
      case "1Y": return addDays(latest, -365);
      case "3Y": return addDays(latest, -365 * 3);
      case "5Y": return addDays(latest, -365 * 5);
      case "10Y": return addDays(latest, -365 * 10);
      case "MAX": return D.meta.first_date;
      default: return addDays(latest, -365 * 3);
    }
  }

  function filterPairs(arr, start, end) {
    if (!arr) return [];
    return arr.filter(p => p[0] >= start && p[0] <= end);
  }

  // ==========================================================================
  // Header, Regime Banner, KPIs & Matrix
  // ==========================================================================
  function renderHeader() {
    document.getElementById("meta-line").textContent =
      `Latest observation: ${D.meta.latest_date} · Full CSV range: ${D.meta.first_date} to ${D.meta.latest_date} (${D.audit.rows.toLocaleString()} rows) · Liquidity/NFCI/HY available since 2023-10-17`;

    document.querySelectorAll("[data-avail]").forEach(el => {
      const k = el.getAttribute("data-avail");
      const st = D.stats[k];
      if (st) {
        el.textContent = `Available: ${st.first_date} → ${st.last_date} (${st.n_obs.toLocaleString()} obs)`;
      }
    });
    const cm = D.derived.comp_meta;
    document.getElementById("avail-comp").textContent =
      `Available: ${cm.coverage_from} → ${D.meta.latest_date} (all 3 inputs since ${cm.full_3_from})`;
    document.getElementById("avail-stress").textContent =
      `VIX since ${D.stats.vix.first_date} · HY OAS since ${D.stats.hy.first_date}`;
  }

  function renderRegimeBanner() {
    const rn = D.regime_now;
    const sec = document.getElementById("regime");
    const tone = labelTone(rn.overall);
    sec.className = `regime card tone-${tone}`;

    document.getElementById("regime-date").textContent = `· as of ${rn.date}`;
    const lblEl = document.getElementById("regime-label");
    lblEl.textContent = rn.overall.toUpperCase();

    const sub = document.getElementById("regime-sub");
    if (rn.overall === "Transitional") {
      const counts = Object.entries(rn.recent_base).map(([k, v]) => `${k}: ${v}d`).join(", ");
      sub.innerHTML = `Today's component votes point to <strong>${rn.base}</strong> (Liquidity Contracting + Financial Conditions Tightening), shifting away from the prior ${rn.recent_window}-trading-day dominant regime (<strong>${rn.prior_dominant}</strong>; recent breakdown: ${counts}).`;
    } else {
      sub.textContent = `Classification derived directly from the four pillar rules below.`;
    }

    document.getElementById("regime-confidence").innerHTML =
      `<strong>Confidence: ${rn.confidence}</strong> — ${rn.confidence_note}`;

    const order = [
      ["liquidity", "Liquidity", "↑ Expanding / → Neutral / ↓ Contracting"],
      ["sentiment", "Sentiment", "Greed / Neutral / Fear"],
      ["financial", "Financial Conditions", "Easing / Neutral / Tightening"],
      ["stress", "Market Stress", "Low / Medium / High"],
    ];
    const arrowFor = (key, label) => {
      if (key === "liquidity") return label === "Expanding" ? "↑" : label === "Contracting" ? "↓" : "→";
      if (key === "financial") return label === "Easing" ? "↓" : label === "Tightening" ? "↑" : "→";
      if (key === "sentiment") return rn.components.sentiment.trend === "Improving" ? "↑" : rn.components.sentiment.trend === "Weakening" ? "↓" : "→";
      if (key === "stress") return label === "High" ? "↑" : label === "Low" ? "↓" : "→";
      return "→";
    };

    document.getElementById("regime-components").innerHTML = order.map(([k, title]) => {
      const c = rn.components[k];
      const arr = arrowFor(k, c.label);
      return `<div class="rc-item">
        <div class="rc-top">
          <span class="rc-name">${title}</span>
          ${badgeHTML(`${arr} ${c.label}`, labelTone(c.label))}
        </div>
        <p class="rc-reason">${c.reason}</p>
      </div>`;
    }).join("");
  }

  function renderKPIs() {
    const nl = D.stats.net_liq;
    const vix = D.stats.vix;
    const nfci = D.stats.nfci;
    const hy = D.stats.hy;
    const comp = D.matrix.find(m => m.key === "sent_comp");

    const cards = [
      {
        title: "Net Liquidity",
        cat: "Liquidity",
        val: fmtVal(nl.last, "net_liq"),
        delta: `1Y: ${fmtSigned(nl.chg_1y, "net_liq")} (${nl.chg_1y_pct !== null ? (nl.chg_1y_pct >= 0 ? "+" : "") + nl.chg_1y_pct.toFixed(1) + "%" : "—"})`,
        trend: `${nl.trend_arrow} ${nl.trend_read}`,
        tone: nl.tone > 0 ? "pos" : nl.tone < 0 ? "neg" : "neu",
        pct: nl.pct,
        basis: `${ordinal(nl.pct)} pct · ${nl.pct_basis}`,
        flag: nl.flag,
      },
      {
        title: "Net Liquidity 3M Change",
        cat: "Liquidity Momentum",
        val: fmtSigned(nl.chg_trend, "net_liq"),
        delta: `3M %: ${nl.chg_trend_pct !== null ? (nl.chg_trend_pct >= 0 ? "+" : "") + nl.chg_trend_pct.toFixed(1) + "%" : "—"} (signal ${nl.trend_z >= 0 ? "+" : ""}${nl.trend_z}σ)`,
        trend: `${nl.trend_arrow} ${D.regime_now.components.liquidity.label}`,
        tone: labelTone(D.regime_now.components.liquidity.label),
        pct: nl.pct,
        basis: `TGA ${fmtSigned(D.derived.attr_3m.tga, "tga")} · WALCL ${fmtSigned(D.derived.attr_3m.fed_assets, "fed_assets")}`,
        flag: D.stats.tga.flag ? `TGA ${D.stats.tga.flag.toLowerCase()}` : null,
      },
      {
        title: "VIX Index",
        cat: "Sentiment / Volatility",
        val: fmtVal(vix.last, "vix"),
        delta: `30D: ${fmtSigned(vix.chg_trend, "vix")} (${vix.chg_trend_pct !== null ? (vix.chg_trend_pct >= 0 ? "+" : "") + vix.chg_trend_pct.toFixed(1) + "%" : "—"})`,
        trend: `${vix.trend_arrow} ${vix.trend_read}`,
        tone: vix.tone > 0 ? "pos" : vix.tone < 0 ? "neg" : "neu",
        pct: vix.pct,
        basis: `${ordinal(vix.pct)} pct · ${vix.pct_basis}`,
        flag: vix.flag,
      },
      {
        title: "Sentiment Composite",
        cat: "Sentiment (0=Fear, 100=Greed)",
        val: `${comp.last}`,
        delta: `30D: ${comp.chg_trend >= 0 ? "+" : "−"}${Math.abs(comp.chg_trend).toFixed(0)} pts · CNN F&G: ${D.stats.cnn.last.toFixed(0)}`,
        trend: `${comp.trend_arrow} ${D.regime_now.components.sentiment.label}`,
        tone: labelTone(D.regime_now.components.sentiment.label),
        pct: comp.pct,
        basis: `${ordinal(comp.pct)} pct since 1990 (VIX⁻¹ + AAII + P/C⁻¹)`,
        flag: comp.flag,
      },
      {
        title: "Chicago Fed NFCI",
        cat: "Financial Conditions",
        val: fmtVal(nfci.last, "nfci"),
        delta: `3M: ${fmtSigned(nfci.chg_trend, "nfci")} (< 0 = looser than 1971+ avg)`,
        trend: `${nfci.trend_arrow} ${nfci.trend_read}`,
        tone: nfci.tone > 0 ? "pos" : nfci.tone < 0 ? "neg" : "neu",
        pct: nfci.pct,
        basis: `${ordinal(nfci.pct)} pct · ${nfci.pct_basis}`,
        flag: nfci.flag,
      },
      {
        title: "High-Yield OAS",
        cat: "Credit Conditions",
        val: fmtVal(hy.last, "hy"),
        delta: `3M: ${fmtSigned(hy.chg_trend, "hy")} (signal ${hy.trend_z >= 0 ? "+" : ""}${hy.trend_z}σ)`,
        trend: `${hy.trend_arrow} ${hy.trend_read}`,
        tone: hy.tone > 0 ? "pos" : hy.tone < 0 ? "neg" : "neu",
        pct: hy.pct,
        basis: `${ordinal(hy.pct)} pct · ${hy.pct_basis}`,
        flag: hy.flag,
      },
    ];

    document.getElementById("kpi-grid").innerHTML = cards.map(c => `
      <article class="kpi-card">
        <div class="kpi-head">
          <div>
            <div class="kpi-cat">${c.cat}</div>
            <div class="kpi-title">${c.title}</div>
          </div>
          ${badgeHTML(c.trend, c.tone)}
        </div>
        <div class="kpi-val">${c.val}</div>
        <div class="kpi-delta"><span>${c.delta}</span></div>
        <div class="kpi-pct-wrap">
          <div class="pct-bar"><div class="pct-fill" style="width:${c.pct ?? 0}%"></div></div>
          <div class="kpi-foot">
            <span>${c.basis}</span>
            ${c.flag ? `<span class="badge warn">⚠ ${c.flag}</span>` : ""}
          </div>
        </div>
      </article>
    `).join("");
  }

  function renderMatrix() {
    const tbl = document.getElementById("matrix");
    const headers = ["Indicator", "Current", "Horizon Δ", "Trend / Status", "Historical Percentile", "Observation Period", "Data Quality"];
    tbl.style.setProperty("--label-2", '"Current"');
    tbl.style.setProperty("--label-3", '"Horizon Δ"');
    tbl.style.setProperty("--label-4", '"Trend / Status"');
    tbl.style.setProperty("--label-5", '"Percentile"');
    tbl.style.setProperty("--label-6", '"Period"');
    tbl.style.setProperty("--label-7", '"Quality"');

    const rowsHTML = D.matrix.map(m => {
      const cfg = CFG[m.key] || { name: "Sentiment Composite (0–100)", category: "Sentiment" };
      const tone = m.tone > 0 ? "pos" : m.tone < 0 ? "neg" : "neu";
      const qTone = m.quality === "High" ? "pos" : m.quality === "Medium" ? "warn" : "neu";
      return `<tr>
        <th scope="row">${cfg.name} <span class="muted">(${m.last_date})</span></th>
        <td class="num"><strong>${fmtVal(m.last, m.key)}</strong></td>
        <td class="num">${fmtSigned(m.chg_trend, m.key)} <span class="muted">(${m.trend_days}D)</span></td>
        <td>${badgeHTML(`${m.trend_arrow} ${m.trend_read}`, tone)}</td>
        <td class="num"><strong>${ordinal(m.pct)}</strong> ${m.flag ? `<span class="badge warn">⚠ ${m.flag}</span>` : ""}</td>
        <td>${m.pct_basis}</td>
        <td>${badgeHTML(m.quality, qTone)}</td>
      </tr>`;
    }).join("");

    tbl.innerHTML = `<thead><tr>${headers.map(h => `<th>${h}</th>`).join("")}</tr></thead><tbody>${rowsHTML}</tbody>`;
  }

  function renderStressTable() {
    const vix = D.stats.vix;
    const hy = D.stats.hy;
    const pc = D.stats.pc;
    const nfci = D.stats.nfci;
    const sn = D.stress_now;

    const rows = [
      ["Composite Stress Monitor", `${sn.stress_pct}th pct`, badgeHTML(sn.label, labelTone(sn.label)), "Mean of VIX pct & HY OAS pct", "Low < 50 · High ≥ 80"],
      ["VIX (S&P 500 30D Implied Vol)", fmtVal(vix.last, "vix"), `${ordinal(vix.pct)} pct`, `${vix.trend_arrow} ${vix.trend_read} (30D ${fmtSigned(vix.chg_trend, "vix")})`, `Max ${vix.hist_max.toFixed(1)} (${vix.hist_max_date}) · Since 1990`],
      ["High-Yield OAS", fmtVal(hy.last, "hy"), `${ordinal(hy.pct)} pct`, `${hy.trend_arrow} ${hy.trend_read} (3M ${fmtSigned(hy.chg_trend, "hy")})`, `Max ${hy.hist_max.toFixed(2)}% (${hy.hist_max_date}) · Since 2023-10`],
      ["CBOE Total Put/Call", fmtVal(pc.last, "pc"), `${ordinal(pc.pct)} pct`, `${pc.trend_arrow} ${pc.trend_read}`, `Max ${pc.hist_max.toFixed(2)} (${pc.hist_max_date}) · Since 1995`],
      ["Chicago Fed NFCI", fmtVal(nfci.last, "nfci"), `${ordinal(nfci.pct)} pct`, `${nfci.trend_arrow} ${nfci.trend_read}`, `Max ${nfci.hist_max.toFixed(3)} (${nfci.hist_max_date}) · Since 2023-10`],
    ];

    document.getElementById("stress-table").innerHTML =
      `<thead><tr><th>Stress Indicator</th><th>Current</th><th>Percentile / State</th><th>Trend</th><th>Historical Extreme &amp; Coverage</th></tr></thead>
       <tbody>${rows.map(r => `<tr><th scope="row">${r[0]}</th><td class="num">${r[1]}</td><td>${r[2]}</td><td>${r[3]}</td><td>${r[4]}</td></tr>`).join("")}</tbody>`;
  }

  function renderInterpretations() {
    document.getElementById("int-netliq").textContent = D.interp.net_liq;
    document.getElementById("int-components").textContent = D.interp.components;
    document.getElementById("int-sentiment").textContent = D.interp.sentiment;
    document.getElementById("int-financial").textContent = D.interp.financial;
    document.getElementById("int-relationship").textContent = D.interp.relationship;
    document.getElementById("int-stress").textContent = D.interp.stress;
  }

  // ==========================================================================
  // Charts (ECharts)
  // ==========================================================================
  const BASE_GRID = { left: 54, right: 20, top: 28, bottom: 32 };

  function initChart(id) {
    const el = document.getElementById(id);
    if (!charts[id]) {
      charts[id] = echarts.init(el, null, { renderer: "canvas" });
    }
    return charts[id];
  }

  function effectiveRangeFor(seriesArr) {
    // If the user selected a range where a short-history series has 0 points, fall back to its available window
    const sub = filterPairs(seriesArr, state.start, state.end);
    if (sub.length > 0) return { data: sub, note: null };
    return { data: seriesArr, note: "Showing full available window" };
  }

  function renderNetLiqChart() {
    const ch = initChart("ch-netliq");
    const { data } = effectiveRangeFor(D.series.net_liq);
    ch.setOption({
      grid: BASE_GRID,
      tooltip: { trigger: "axis", valueFormatter: v => `$${Number(v).toLocaleString()}bn` },
      dataZoom: [{ type: "inside" }],
      xAxis: { type: "time", axisLabel: { fontSize: 11 } },
      yAxis: { type: "value", scale: true, axisLabel: { formatter: v => `$${v}bn`, fontSize: 11 } },
      series: [{
        name: "Net Liquidity",
        type: "line",
        showSymbol: false,
        data,
        lineStyle: { width: 2, color: "#1d4ed8" },
        areaStyle: { color: "rgba(29, 78, 216, 0.08)" },
      }],
    }, true);
  }

  function renderComponentsChart() {
    const ch = initChart("ch-components");
    const subEl = document.getElementById("comp-sub");
    if (state.compMode === "contrib") {
      subEl.textContent = "weekly contribution to Δ Net Liquidity, USD bn";
      const rows = D.derived.contrib.filter(r => r[0] >= state.start && r[0] <= state.end);
      const src = rows.length ? rows : D.derived.contrib;
      ch.setOption({
        grid: { ...BASE_GRID, top: 34 },
        legend: { top: 0, itemWidth: 12, itemHeight: 8, textStyle: { fontSize: 11 } },
        tooltip: { trigger: "axis", valueFormatter: v => `${v >= 0 ? "+" : ""}${Number(v).toFixed(1)}bn` },
        dataZoom: [{ type: "inside" }],
        xAxis: { type: "time", axisLabel: { fontSize: 11 } },
        yAxis: { type: "value", axisLabel: { formatter: v => `${v}bn`, fontSize: 11 } },
        series: [
          { name: "Δ Fed Assets", type: "bar", stack: "c", data: src.map(r => [r[0], r[1]]), itemStyle: { color: "#2563eb" } },
          { name: "−Δ TGA (liquidity impact)", type: "bar", stack: "c", data: src.map(r => [r[0], r[2]]), itemStyle: { color: "#d97706" } },
          { name: "−Δ RRP (liquidity impact)", type: "bar", stack: "c", data: src.map(r => [r[0], r[3]]), itemStyle: { color: "#0d9488" } },
          { name: "Δ Net Liquidity", type: "line", showSymbol: false, data: src.map(r => [r[0], r[4]]), lineStyle: { width: 1.8, color: "#0f172a" } },
        ],
      }, true);
    } else {
      subEl.textContent = "component balances, USD bn";
      const fa = effectiveRangeFor(D.series.fed_assets).data;
      const tga = effectiveRangeFor(D.series.tga).data;
      const rrp = effectiveRangeFor(D.series.rrp).data;
      ch.setOption({
        grid: { left: 56, right: 56, top: 34, bottom: 32 },
        legend: { top: 0, itemWidth: 12, itemHeight: 8, textStyle: { fontSize: 11 } },
        tooltip: { trigger: "axis", valueFormatter: v => `$${Number(v).toLocaleString()}bn` },
        dataZoom: [{ type: "inside" }],
        xAxis: { type: "time", axisLabel: { fontSize: 11 } },
        yAxis: [
          { type: "value", name: "WALCL ($bn)", scale: true, axisLabel: { fontSize: 11 } },
          { type: "value", name: "TGA / RRP ($bn)", scale: true, axisLabel: { fontSize: 11 } },
        ],
        series: [
          { name: "Fed Assets (WALCL, weekly)", type: "line", yAxisIndex: 0, showSymbol: false, data: fa, lineStyle: { width: 2, color: "#2563eb" } },
          { name: "TGA (daily)", type: "line", yAxisIndex: 1, showSymbol: false, data: tga, lineStyle: { width: 1.8, color: "#d97706" } },
          { name: "ON RRP (daily)", type: "line", yAxisIndex: 1, showSymbol: false, data: rrp, lineStyle: { width: 1.8, color: "#0d9488" } },
        ],
      }, true);
    }
  }

  function renderSentimentCharts() {
    // 1. Composite
    const chComp = initChart("ch-composite");
    const compData = effectiveRangeFor(D.derived.comp).data;
    chComp.setOption({
      grid: BASE_GRID,
      tooltip: { trigger: "axis", valueFormatter: v => `${Number(v).toFixed(0)}th pct` },
      dataZoom: [{ type: "inside" }],
      xAxis: { type: "time", axisLabel: { fontSize: 11 } },
      yAxis: { type: "value", min: 0, max: 100, axisLabel: { formatter: "{value}", fontSize: 11 } },
      series: [{
        name: "Sentiment Composite",
        type: "line",
        showSymbol: false,
        data: compData,
        lineStyle: { width: 1.8, color: "#1d4ed8" },
        markLine: {
          silent: true,
          symbol: "none",
          lineStyle: { type: "dashed" },
          data: [
            { yAxis: 75, name: "Greed (75)", lineStyle: { color: "#0f766e" }, label: { formatter: "Greed 75", position: "insideEndTop" } },
            { yAxis: 25, name: "Fear (25)", lineStyle: { color: "#be123c" }, label: { formatter: "Fear 25", position: "insideEndBottom" } },
          ],
        },
      }],
    }, true);

    // 2. VIX
    const q = D.derived.vix_quantiles;
    initChart("ch-vix").setOption({
      grid: BASE_GRID,
      tooltip: { trigger: "axis" },
      dataZoom: [{ type: "inside" }],
      xAxis: { type: "time", axisLabel: { fontSize: 11 } },
      yAxis: { type: "value", scale: true, axisLabel: { fontSize: 11 } },
      series: [{
        name: "VIX",
        type: "line",
        showSymbol: false,
        data: effectiveRangeFor(D.series.vix).data,
        lineStyle: { width: 1.5, color: "#334155" },
        markLine: {
          silent: true,
          symbol: "none",
          lineStyle: { type: "dashed", width: 1 },
          data: [
            { yAxis: q["50"], lineStyle: { color: "#64748b" }, label: { formatter: `50th (${q["50"]})`, position: "insideEndTop" } },
            { yAxis: q["80"], lineStyle: { color: "#d97706" }, label: { formatter: `80th (${q["80"]})`, position: "insideEndTop" } },
            { yAxis: q["90"], lineStyle: { color: "#be123c" }, label: { formatter: `90th (${q["90"]})`, position: "insideEndTop" } },
          ],
        },
      }],
    }, true);

    // 3. AAII
    initChart("ch-aaii").setOption({
      grid: BASE_GRID,
      tooltip: { trigger: "axis", valueFormatter: v => `${Number(v).toFixed(1)}pp` },
      dataZoom: [{ type: "inside" }],
      xAxis: { type: "time", axisLabel: { fontSize: 11 } },
      yAxis: { type: "value", axisLabel: { formatter: "{value}pp", fontSize: 11 } },
      series: [{
        name: "AAII Bull–Bear",
        type: "line",
        showSymbol: false,
        data: effectiveRangeFor(D.series.aaii).data,
        lineStyle: { width: 1.5, color: "#0f766e" },
        markLine: { silent: true, symbol: "none", data: [{ yAxis: 0, lineStyle: { color: "#94a3b8" } }] },
      }],
    }, true);

    // 4. Put/Call
    initChart("ch-pc").setOption({
      grid: { ...BASE_GRID, top: 32 },
      legend: { top: 0, itemWidth: 12, itemHeight: 8, textStyle: { fontSize: 11 } },
      tooltip: { trigger: "axis" },
      dataZoom: [{ type: "inside" }],
      xAxis: { type: "time", axisLabel: { fontSize: 11 } },
      yAxis: { type: "value", scale: true, axisLabel: { fontSize: 11 } },
      series: [
        { name: "Daily P/C", type: "line", showSymbol: false, data: effectiveRangeFor(D.series.pc).data, lineStyle: { width: 1, color: "rgba(100,116,139,0.35)" } },
        { name: "10D Mean", type: "line", showSymbol: false, data: effectiveRangeFor(D.derived.pc10).data, lineStyle: { width: 1.8, color: "#7c3aed" } },
      ],
    }, true);

    // 5. CNN F&G
    initChart("ch-cnn").setOption({
      grid: BASE_GRID,
      tooltip: { trigger: "axis" },
      dataZoom: [{ type: "inside" }],
      xAxis: { type: "time", axisLabel: { fontSize: 11 } },
      yAxis: { type: "value", min: 0, max: 100, axisLabel: { fontSize: 11 } },
      series: [{
        name: "CNN Fear & Greed",
        type: "line",
        showSymbol: false,
        data: effectiveRangeFor(D.series.cnn).data,
        lineStyle: { width: 1.6, color: "#d97706" },
        markLine: {
          silent: true, symbol: "none", lineStyle: { type: "dashed" },
          data: [{ yAxis: 75, lineStyle: { color: "#0f766e" } }, { yAxis: 25, lineStyle: { color: "#be123c" } }],
        },
      }],
    }, true);
  }

  function renderFinancialCharts() {
    initChart("ch-nfci").setOption({
      grid: BASE_GRID,
      tooltip: { trigger: "axis" },
      dataZoom: [{ type: "inside" }],
      xAxis: { type: "time", axisLabel: { fontSize: 11 } },
      yAxis: { type: "value", scale: true, axisLabel: { fontSize: 11 } },
      series: [{
        name: "NFCI",
        type: "line",
        showSymbol: true,
        symbolSize: 4,
        data: effectiveRangeFor(D.series.nfci).data,
        lineStyle: { width: 2, color: "#0f766e" },
        itemStyle: { color: "#0f766e" },
        markLine: { silent: true, symbol: "none", data: [{ yAxis: 0, lineStyle: { color: "#be123c", type: "dashed" }, label: { formatter: "0 = 1971+ Avg" } }] },
      }],
    }, true);

    const hq = D.derived.hy_quantiles;
    initChart("ch-hy").setOption({
      grid: BASE_GRID,
      tooltip: { trigger: "axis", valueFormatter: v => `${Number(v).toFixed(2)}%` },
      dataZoom: [{ type: "inside" }],
      xAxis: { type: "time", axisLabel: { fontSize: 11 } },
      yAxis: { type: "value", scale: true, axisLabel: { formatter: "{value}%", fontSize: 11 } },
      series: [{
        name: "HY OAS",
        type: "line",
        showSymbol: false,
        data: effectiveRangeFor(D.series.hy).data,
        lineStyle: { width: 1.8, color: "#be123c" },
        markLine: {
          silent: true, symbol: "none", lineStyle: { type: "dashed" },
          data: [
            { yAxis: hq["50"], lineStyle: { color: "#64748b" }, label: { formatter: `50th (${hq["50"]}%)`, position: "insideEndTop" } },
            { yAxis: hq["80"], lineStyle: { color: "#be123c" }, label: { formatter: `80th (${hq["80"]}%)`, position: "insideEndTop" } },
          ],
        },
      }],
    }, true);

    initChart("ch-stress").setOption({
      grid: BASE_GRID,
      tooltip: { trigger: "axis", valueFormatter: v => `${Number(v).toFixed(0)}th pct` },
      dataZoom: [{ type: "inside" }],
      xAxis: { type: "time", axisLabel: { fontSize: 11 } },
      yAxis: { type: "value", min: 0, max: 100, axisLabel: { fontSize: 11 } },
      series: [{
        name: "Stress Percentile",
        type: "line",
        showSymbol: false,
        data: effectiveRangeFor(D.derived.stress_pct).data,
        lineStyle: { width: 1.6, color: "#b45309" },
        markLine: {
          silent: true, symbol: "none", lineStyle: { type: "dashed" },
          data: [
            { yAxis: 80, lineStyle: { color: "#be123c" }, label: { formatter: "High Stress (80)", position: "insideEndTop" } },
            { yAxis: 50, lineStyle: { color: "#64748b" }, label: { formatter: "Medium (50)", position: "insideEndBottom" } },
          ],
        },
      }],
    }, true);
  }

  function renderRelationshipCharts() {
    // Quadrant: [date, x_pct, x_z, y_sent]
    const chQ = initChart("ch-quadrant");
    const qAll = D.derived.quadrant;
    const isPct = state.quadMode === "pct";
    document.getElementById("quad-sub").textContent = isPct
      ? "X = Net Liquidity percentile (since 2023-10) · Y = Sentiment Composite percentile"
      : "X = Net Liquidity 3M signal (σ) · Y = Sentiment Composite percentile";

    const pts = qAll.map(r => [isPct ? r[1] : r[2], r[3], r[0]]);
    const trail = pts.slice(-13);
    const curr = pts[pts.length - 1];
    const xSplit = isPct ? 50 : 0;

    chQ.setOption({
      grid: { left: 52, right: 24, top: 28, bottom: 40 },
      tooltip: {
        formatter: p => {
          const d = p.data;
          return `<strong>${d[2]}</strong><br/>Liquidity: ${d[0]}${isPct ? "th pct" : "σ"}<br/>Sentiment: ${d[1]}th pct`;
        },
      },
      xAxis: {
        type: "value",
        name: isPct ? "Net Liquidity Percentile →" : "Net Liquidity 3M Signal (σ) →",
        nameLocation: "middle",
        nameGap: 25,
        min: isPct ? 0 : -2.5,
        max: isPct ? 100 : 2.5,
      },
      yAxis: {
        type: "value",
        name: "Sentiment Percentile →",
        min: 0,
        max: 100,
      },
      series: [
        {
          name: "Weekly History (2023–present)",
          type: "scatter",
          symbolSize: 6,
          data: pts.slice(0, -13),
          itemStyle: { color: "rgba(100, 116, 139, 0.35)" },
        },
        {
          name: "Last 13 Weeks Trajectory",
          type: "line",
          symbolSize: 6,
          data: trail,
          lineStyle: { width: 2, color: "#2563eb" },
          itemStyle: { color: "#2563eb" },
        },
        {
          name: "Current Position",
          type: "scatter",
          symbolSize: 15,
          data: [curr],
          itemStyle: { color: "#be123c", borderColor: "#fff", borderWidth: 2 },
          markLine: {
            silent: true,
            symbol: "none",
            lineStyle: { color: "#94a3b8", type: "dashed" },
            data: [{ xAxis: xSplit }, { yAxis: 50 }],
          },
        },
      ],
    }, true);

    // Rolling Correlation
    const chC = initChart("ch-corr");
    chC.setOption({
      grid: { ...BASE_GRID, top: 34 },
      legend: { top: 0, itemWidth: 12, itemHeight: 8, textStyle: { fontSize: 11 } },
      tooltip: { trigger: "axis" },
      dataZoom: [{ type: "inside" }],
      xAxis: { type: "time", axisLabel: { fontSize: 11 } },
      yAxis: { type: "value", min: -1, max: 1, axisLabel: { fontSize: 11 } },
      series: [
        { name: `13W (~90D) [now ${D.derived.corr_now["13W"]}]`, type: "line", showSymbol: false, data: D.derived.corr["13W"], lineStyle: { width: 1.6, color: "#2563eb" } },
        { name: `26W (~6M) [now ${D.derived.corr_now["26W"]}]`, type: "line", showSymbol: false, data: D.derived.corr["26W"], lineStyle: { width: 2, color: "#0f766e" } },
        { name: `52W (~1Y) [now ${D.derived.corr_now["52W"]}]`, type: "line", showSymbol: false, data: D.derived.corr["52W"], lineStyle: { width: 1.6, color: "#d97706" } },
      ],
    }, true);
  }

  const REGIME_COLORS = {
    "Risk-On": "#10b981",
    "Expanding": "#10b981",
    "Easing": "#10b981",
    "Greed": "#10b981",
    "Low": "#10b981",
    "Neutral": "#94a3b8",
    "Medium": "#f59e0b",
    "Mixed": "#f59e0b",
    "Transitional": "#6366f1",
    "Risk-Off": "#ef4444",
    "Contracting": "#ef4444",
    "Tightening": "#ef4444",
    "Fear": "#ef4444",
    "High": "#ef4444",
  };

  function renderTimelineChart() {
    const ch = initChart("ch-timeline");
    const spx = effectiveRangeFor(D.series.spx).data;
    const lanes = [
      ["Stress", D.regimes.stress],
      ["Sentiment", D.regimes.sentiment],
      ["Fin. Cond.", D.regimes.financial],
      ["Liquidity", D.regimes.liquidity],
      ["Overall", D.regimes.overall],
    ];

    const segData = [];
    lanes.forEach(([, segs], idx) => {
      segs.forEach(([s, e, lbl]) => {
        if (e >= state.start && s <= state.end) {
          const cs = s < state.start ? state.start : s;
          const ce = e > state.end ? state.end : e;
          segData.push({
            value: [idx, cs, ce, lbl],
            itemStyle: { color: REGIME_COLORS[lbl] || "#cbd5e1" },
          });
        }
      });
    });

    ch.setOption({
      tooltip: {
        trigger: "item",
        formatter: p => {
          if (p.seriesType === "custom") {
            const [laneIdx, s, e, lbl] = p.value;
            return `<strong>${lanes[laneIdx][0]}: ${lbl}</strong><br/>${s} → ${e}`;
          }
          return `<strong>${p.value[0]}</strong><br/>S&P 500: ${Number(p.value[1]).toLocaleString()}`;
        },
      },
      grid: [
        { left: 82, right: 24, top: 18, height: "42%" },
        { left: 82, right: 24, top: "66%", height: "25%" },
      ],
      xAxis: [
        { type: "time", gridIndex: 0, min: state.start, max: state.end, axisLabel: { show: false } },
        { type: "time", gridIndex: 1, min: state.start, max: state.end, axisLabel: { fontSize: 11 } },
      ],
      yAxis: [
        { type: "value", gridIndex: 0, name: "S&P 500 (log)", logBase: 10, scale: true, axisLabel: { fontSize: 11 } },
        { type: "category", gridIndex: 1, data: lanes.map(l => l[0]), axisLabel: { fontSize: 11, fontWeight: 600 } },
      ],
      series: [
        {
          name: "S&P 500",
          type: "line",
          xAxisIndex: 0,
          yAxisIndex: 0,
          showSymbol: false,
          data: spx,
          lineStyle: { width: 1.6, color: "#0f172a" },
        },
        {
          name: "Regime",
          type: "custom",
          xAxisIndex: 1,
          yAxisIndex: 1,
          renderItem: (params, api) => {
            const cat = api.value(0);
            const start = api.coord([api.value(1), cat]);
            const end = api.coord([api.value(2), cat]);
            const height = api.size([0, 1])[1] * 0.68;
            return {
              type: "rect",
              shape: echarts.graphic.clipRectByRect(
                { x: start[0], y: start[1] - height / 2, width: Math.max(end[0] - start[0], 1.5), height },
                { x: params.coordSys.x, y: params.coordSys.y, width: params.coordSys.width, height: params.coordSys.height }
              ),
              style: api.style(),
            };
          },
          encode: { x: [1, 2], y: 0 },
          data: segData,
        },
      ],
    }, true);

    const legendItems = [
      ["Risk-On / Expanding / Easing / Greed / Low Stress", "#10b981"],
      ["Neutral", "#94a3b8"],
      ["Mixed / Medium Stress", "#f59e0b"],
      ["Transitional", "#6366f1"],
      ["Risk-Off / Contracting / Tightening / Fear / High Stress", "#ef4444"],
    ];
    document.getElementById("regime-legend").innerHTML = legendItems
      .map(([t, c]) => `<span class="legend-item"><span class="swatch" style="background:${c}"></span>${t}</span>`)
      .join("");
  }

  function renderCoverageChart() {
    const ch = initChart("ch-coverage");
    const items = D.dictionary.slice().reverse();
    ch.setOption({
      grid: { left: 210, right: 30, top: 16, bottom: 28 },
      tooltip: {
        formatter: p => {
          const d = items[p.dataIndex];
          return `<strong>${d.name}</strong><br/>Available: ${d.available_from} → ${d.available_to}<br/>Genuine obs: ${d.n_obs.toLocaleString()} (${d.frequency})<br/>Quality: ${d.quality}`;
        },
      },
      xAxis: { type: "time", min: D.meta.first_date, max: D.meta.latest_date, axisLabel: { fontSize: 11 } },
      yAxis: { type: "category", data: items.map(d => d.name), axisLabel: { fontSize: 11 } },
      series: [{
        type: "custom",
        renderItem: (params, api) => {
          const idx = api.value(0);
          const s = api.coord([api.value(1), idx]);
          const e = api.coord([api.value(2), idx]);
          const h = api.size([0, 1])[1] * 0.55;
          return {
            type: "rect",
            shape: { x: s[0], y: s[1] - h / 2, width: Math.max(e[0] - s[0], 3), height: h, r: 3 },
            style: api.style(),
          };
        },
        encode: { x: [1, 2], y: 0 },
        data: items.map((d, i) => ({
          value: [i, d.available_from, d.available_to],
          itemStyle: { color: d.quality === "High" ? "#1d4ed8" : d.quality === "Medium" ? "#d97706" : "#64748b" },
        })),
      }],
    }, true);
  }

  function renderAllCharts() {
    renderNetLiqChart();
    renderComponentsChart();
    renderSentimentCharts();
    renderFinancialCharts();
    renderRelationshipCharts();
    renderTimelineChart();
    renderCoverageChart();
  }

  // ==========================================================================
  // Detailed Data Table (Sortable, Filterable, Paginated, CSV Export)
  // ==========================================================================
  const COL_LABELS = {
    date: "Date",
    spx: "S&P 500",
    net_liq: "Net Liq ($bn)",
    nl_chg13w: "Net Liq 3M Δ",
    vix: "VIX",
    aaii: "AAII (pp)",
    pc: "Put/Call",
    cnn: "CNN F&G",
    nfci: "NFCI",
    hy: "HY OAS (%)",
    fed_assets: "WALCL ($bn)",
    tga: "TGA ($bn)",
    rrp: "RRP ($bn)",
    effr: "EFFR (%)",
    breadth: "RSP/SPY",
    margin: "Margin Debt ($mn)",
    sent_comp: "Sent. Comp",
    stress: "Stress",
    regime: "Regime",
  };

  function setupTableControls() {
    const regimes = ["Risk-On", "Neutral", "Mixed", "Transitional", "Risk-Off"];
    const sel = document.getElementById("tbl-regime");
    sel.innerHTML = `<option value="">All</option>` + regimes.map(r => `<option value="${r}">${r}</option>`).join("");

    const colWrap = document.getElementById("tbl-cols");
    colWrap.innerHTML = D.table.columns.filter(c => c !== "date").map(c => `
      <label><input type="checkbox" data-col="${c}" ${state.tblVisibleCols.has(c) ? "checked" : ""}> ${COL_LABELS[c] || c}</label>
    `).join("");

    colWrap.addEventListener("change", e => {
      const col = e.target.getAttribute("data-col");
      if (!col) return;
      if (e.target.checked) state.tblVisibleCols.add(col);
      else state.tblVisibleCols.delete(col);
      renderDataTable();
    });

    document.getElementById("tbl-follow").addEventListener("change", e => {
      state.tblFollowRange = e.target.checked;
      state.tblPage = 1;
      renderDataTable();
    });
    sel.addEventListener("change", e => {
      state.tblRegime = e.target.value;
      state.tblPage = 1;
      renderDataTable();
    });
    document.getElementById("tbl-liq").addEventListener("change", e => {
      state.tblLiqOnly = e.target.checked;
      state.tblPage = 1;
      renderDataTable();
    });
    document.getElementById("pg-prev").addEventListener("click", () => {
      if (state.tblPage > 1) { state.tblPage--; renderDataTable(); }
    });
    document.getElementById("pg-next").addEventListener("click", () => {
      state.tblPage++;
      renderDataTable();
    });
    document.getElementById("tbl-export").addEventListener("click", exportFilteredCSV);
  }

  function getFilteredRows() {
    const cols = D.table.columns;
    const idxMap = Object.fromEntries(cols.map((c, i) => [c, i]));
    const iDate = idxMap.date;
    const iLiq = idxMap.net_liq;
    const iReg = idxMap.regime;

    let rows = D.table.rows.filter(r => {
      if (state.tblFollowRange && (r[iDate] < state.start || r[iDate] > state.end)) return false;
      if (state.tblRegime && r[iReg] !== state.tblRegime) return false;
      if (state.tblLiqOnly && (r[iLiq] === null || r[iLiq] === undefined)) return false;
      return true;
    });

    const sIdx = idxMap[state.tblSortCol] ?? 0;
    const dir = state.tblSortDir === "asc" ? 1 : -1;
    rows = rows.slice().sort((a, b) => {
      const va = a[sIdx], vb = b[sIdx];
      if (va === null || va === undefined) return 1;
      if (vb === null || vb === undefined) return -1;
      if (va < vb) return -1 * dir;
      if (va > vb) return 1 * dir;
      return 0;
    });
    return rows;
  }

  function renderDataTable() {
    const cols = D.table.columns.filter(c => state.tblVisibleCols.has(c));
    const idxMap = Object.fromEntries(D.table.columns.map((c, i) => [c, i]));
    const rows = getFilteredRows();

    const totalPages = Math.max(1, Math.ceil(rows.length / state.tblPageSize));
    if (state.tblPage > totalPages) state.tblPage = totalPages;
    const slice = rows.slice((state.tblPage - 1) * state.tblPageSize, state.tblPage * state.tblPageSize);

    document.getElementById("tbl-count").textContent = `${rows.length.toLocaleString()} matching rows`;
    document.getElementById("pg-info").textContent = `Page ${state.tblPage} of ${totalPages}`;

    const thead = `<thead><tr>${cols.map(c => {
      const arrow = state.tblSortCol === c ? (state.tblSortDir === "asc" ? " ▲" : " ▼") : "";
      return `<th class="sortable" data-sort="${c}">${COL_LABELS[c] || c}${arrow}</th>`;
    }).join("")}</tr></thead>`;

    const tbody = `<tbody>${slice.map(r => `<tr>${cols.map((c, ci) => {
      const v = r[idxMap[c]];
      if (ci === 0) return `<th scope="row">${v}</th>`;
      if (v === null || v === undefined) return `<td class="num muted">—</td>`;
      if (c === "regime" || c === "stress") return `<td>${badgeHTML(v, labelTone(v))}</td>`;
      return `<td class="num">${typeof v === "number" ? v.toLocaleString() : v}</td>`;
    }).join("")}</tr>`).join("")}</tbody>`;

    const tbl = document.getElementById("data-table");
    tbl.innerHTML = thead + tbody;
    tbl.querySelectorAll("th.sortable").forEach(th => {
      th.addEventListener("click", () => {
        const col = th.getAttribute("data-sort");
        if (state.tblSortCol === col) {
          state.tblSortDir = state.tblSortDir === "asc" ? "desc" : "asc";
        } else {
          state.tblSortCol = col;
          state.tblSortDir = "desc";
        }
        renderDataTable();
      });
    });
  }

  function exportFilteredCSV() {
    const cols = D.table.columns.filter(c => state.tblVisibleCols.has(c));
    const idxMap = Object.fromEntries(D.table.columns.map((c, i) => [c, i]));
    const rows = getFilteredRows();
    const lines = [cols.map(c => COL_LABELS[c] || c).join(",")];
    rows.forEach(r => {
      lines.push(cols.map(c => r[idxMap[c]] ?? "").join(","));
    });
    const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `regime_filtered_${state.start}_${state.end}.csv`;
    a.click();
  }

  // ==========================================================================
  // Methodology, Data Dictionary & Audit
  // ==========================================================================
  function renderMethodology() {
    document.getElementById("method-blocks").innerHTML = `<div class="method-grid">${D.methodology.map(m => `
      <div class="method-card">
        <h3>${m.title}</h3>
        <ul>${m.body.map(b => `<li>${b}</li>`).join("")}</ul>
      </div>
    `).join("")}</div>`;

    document.getElementById("dict").innerHTML = `
      <thead><tr>
        <th>Name / Raw Column</th><th>Category</th><th>Meaning &amp; Interpretation</th>
        <th>Unit</th><th>Native Frequency</th><th>Available From → To</th>
        <th>Missing % (in window)</th><th>Cleaning Rule</th><th>Priority</th>
      </tr></thead>
      <tbody>${D.dictionary.map(d => `<tr>
        <th scope="row">${d.name}<br/><code class="muted">${d.column}</code></th>
        <td>${d.category}</td>
        <td>${d.meaning}<br/><span class="muted"><strong>High:</strong> ${d.interp_high} · <strong>Low:</strong> ${d.interp_low}</span></td>
        <td>${d.unit}</td>
        <td>${d.frequency}</td>
        <td class="num">${d.available_from} → ${d.available_to}<br/><span class="muted">${d.n_obs.toLocaleString()} genuine obs</span></td>
        <td class="num">${d.missing_in_window_pct}% <span class="muted">(${d.missing_total_pct}% full CSV)</span></td>
        <td><code>${d.clean}</code> <span class="muted">(${d.clean_removed} repeats removed)</span></td>
        <td>${badgeHTML(d.priority, d.priority === "Core" ? "pos" : "neu")}</td>
      </tr>`).join("")}</tbody>
    `;

    const a = D.audit;
    document.getElementById("audit").innerHTML = `
      <p class="muted">Source CSV: <code>${D.meta.source_file}</code> · ${a.rows.toLocaleString()} rows × ${a.columns} columns · Date span ${a.first_date} → ${a.last_date} · Duplicate timestamps: ${a.duplicate_dates} · Non-SPX rows (1st-of-month FINRA dates): ${a.rows_without_spx}</p>
    `;

    document.getElementById("hidden-cols").innerHTML = Object.entries(D.hidden)
      .map(([col, reason]) => `<li><code>${col}</code> — ${reason}</li>`)
      .join("");

    document.getElementById("foot").textContent =
      `Generated ${D.meta.generated_at} from ${D.meta.source_file} · All calculations performed in dashboard/build_dashboard.py`;
  }

  // ==========================================================================
  // Range Controls & Event Wiring
  // ==========================================================================
  function setRange(preset, customStart, customEnd) {
    state.rangePreset = preset;
    if (preset === "CUSTOM") {
      state.start = customStart;
      state.end = customEnd;
    } else {
      state.end = D.meta.latest_date;
      state.start = computePresetStart(preset, state.end);
    }
    document.getElementById("range-start").value = state.start;
    document.getElementById("range-end").value = state.end;
    document.querySelectorAll(".range-btn").forEach(b => {
      b.classList.toggle("active", b.getAttribute("data-range") === preset);
    });
    renderAllCharts();
    if (state.tblFollowRange) {
      state.tblPage = 1;
      renderDataTable();
    }
  }

  function setupToolbar() {
    const presets = ["1M", "3M", "6M", "YTD", "1Y", "3Y", "5Y", "10Y", "MAX"];
    const wrap = document.getElementById("range-buttons");
    wrap.innerHTML = presets.map(p => `<button type="button" class="range-btn" data-range="${p}">${p}</button>`).join("");
    wrap.addEventListener("click", e => {
      const p = e.target.getAttribute("data-range");
      if (p) setRange(p);
    });

    document.getElementById("range-apply").addEventListener("click", () => {
      const s = document.getElementById("range-start").value;
      const e = document.getElementById("range-end").value;
      if (s && e && s <= e) setRange("CUSTOM", s, e);
    });

    document.getElementById("range-reset").addEventListener("click", () => {
      setRange("3Y");
    });

    document.querySelectorAll("[data-comp]").forEach(btn => {
      btn.addEventListener("click", () => {
        state.compMode = btn.getAttribute("data-comp");
        document.querySelectorAll("[data-comp]").forEach(b => b.classList.toggle("active", b === btn));
        renderComponentsChart();
      });
    });

    document.querySelectorAll("[data-quad]").forEach(btn => {
      btn.addEventListener("click", () => {
        state.quadMode = btn.getAttribute("data-quad");
        document.querySelectorAll("[data-quad]").forEach(b => b.classList.toggle("active", b === btn));
        renderRelationshipCharts();
      });
    });

    window.addEventListener("resize", () => {
      Object.values(charts).forEach(ch => ch && ch.resize());
    });
  }

  // Boot
  renderHeader();
  renderRegimeBanner();
  renderKPIs();
  renderMatrix();
  renderStressTable();
  renderInterpretations();
  setupToolbar();
  setupTableControls();
  renderMethodology();
  setRange("3Y");
})();
