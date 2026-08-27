/* Ladder Workbench M1 — read-only frontend.
   Visual laws (spec): provenance footer on every figure/table/drill-down;
   per-rung numbers over the denominator the ledger names; could_not_run and
   absent measurements render as a HATCH, never a color or a zero; no chart
   fuses the three cost measures; record identity is the span key. */
"use strict";

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g,
  (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

async function api(path, params) {
  const url = new URL(path, location.origin);
  for (const [k, v] of Object.entries(params || {}))
    if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, v);
  const r = await fetch(url);
  if (!r.ok) {
    let detail = r.statusText;
    try { detail = (await r.json()).detail || detail; } catch {}
    throw new Error(detail);
  }
  return r.json();
}

function provFooter(p) {
  if (!p) return "";
  return `<div class="prov">run ${esc(p.run_id ?? "—")} · split ${esc(p.split)}` +
    ` · span ${esc(p.span_match)} · backend ${esc(p.backend)}` +
    ` · manifest ${esc(p.manifest_hash)}${p.archived ? " · archived" : ""}</div>`;
}

function caveatChips(caveats) {
  if (!caveats) return "";
  return Object.entries(caveats)
    .map(([k, t]) => `<div class="caveat" title="${esc(k)}">${esc(t)}</div>`).join("");
}

const fmt = (v, d = 3) =>
  (v === null || v === undefined || v === "") ? null : Number(v).toFixed(d);
const cell = (v, d = 3) => {
  const f = fmt(v, d);
  return f === null
    ? '<td class="nonvalue" title="no measurement">·no value·</td>'
    : `<td>${f}</td>`;
};

/* ---------------- SVG helpers ---------------- */

const SVG_HATCH = `<defs><pattern id="hatch" width="6" height="6"
  patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
  <rect width="6" height="6" fill="none"/>
  <line x1="0" y1="0" x2="0" y2="6" stroke="var(--hatch-a)" stroke-width="2"/>
  </pattern></defs>`;

function svgOpen(w, h) {
  return `<svg viewBox="0 0 ${w} ${h}" width="${w}" height="${h}"
    xmlns="http://www.w3.org/2000/svg">${SVG_HATCH}`;
}

/* ---------------- state ---------------- */

const S = {
  tabs: [], runs: [], tab: "results",
  resultsRun: null, baseline: null, span: "exact",
  walkRun: null, walkDoc: null, walkSpan: "exact", walkGold: false,
  traceRun: null, traceSpan: "exact",
};

/* ---------------- boot + tab bar ---------------- */

async function boot() {
  const [tabs, runs] = await Promise.all([api("/api/tabs"), api("/api/runs")]);
  S.tabs = tabs.tabs; S.runs = runs.runs;
  const bar = $("tabbar");
  bar.innerHTML = "";
  for (const t of S.tabs) {
    const b = document.createElement("button");
    b.textContent = t.label;
    b.dataset.id = t.id;
    if (t.milestone !== "M1") {
      b.className = "later";
      b.dataset.milestone = t.milestone;
    }
    b.onclick = () => showTab(t);
    bar.appendChild(b);
  }
  fillRunSelect($("results-run"), S.runs);
  fillRunSelect($("results-baseline"), S.runs, true);
  fillRunSelect($("walk-run"), S.runs);
  fillRunSelect($("trace-run"), S.runs);
  const def = S.runs.length ? S.runs[0].key : null;
  S.resultsRun = S.walkRun = S.traceRun = def;
  wireControls();
  showTab(S.tabs.find((t) => t.id === "explorer"));
}

function fillRunSelect(sel, runs, optional) {
  sel.innerHTML = optional ? '<option value="">none</option>' : "";
  for (const r of runs) {
    const o = document.createElement("option");
    o.value = r.key;
    o.textContent = `${r.key} (${r.split}${r.archived ? ", archived" : ""})`;
    sel.appendChild(o);
  }
}

function showTab(t) {
  document.querySelectorAll(".tab").forEach((el) => (el.hidden = true));
  document.querySelectorAll(".tabbar button").forEach(
    (b) => b.classList.toggle("active", b.dataset.id === t.id));
  if (t.milestone !== "M1") {
    $("tab-later").hidden = false;
    $("later-title").textContent = t.label;
    $("later-note").textContent =
      `Planned for milestone ${t.milestone}. M1 is the read-only lens: ` +
      `no launcher, no writes. The tab bar and data layer are structured ` +
      `so this lands without rework.`;
    return;
  }
  S.tab = t.id;
  $(`tab-${t.id}`).hidden = false;
  ({explorer: renderExplorer, results: renderResults,
    walkthrough: renderWalkthrough, trace: renderTrace}[t.id])();
}

function wireControls() {
  $("results-run").onchange = (e) => { S.resultsRun = e.target.value; renderResults(); };
  $("results-baseline").onchange = (e) => { S.baseline = e.target.value || null; renderResults(); };
  $("results-span").onchange = (e) => { S.span = e.target.value; renderResults(); };
  $("explorer-split").onchange = renderDocs;
  $("explorer-q").oninput = debounce(renderDocs, 300);
  $("walk-run").onchange = (e) => { S.walkRun = e.target.value; S.walkDoc = null; renderWalkthrough(); };
  $("walk-doc").onchange = (e) => { S.walkDoc = e.target.value; renderWalkDoc(); };
  $("walk-span").onchange = (e) => { S.walkSpan = e.target.value; renderWalkDoc(); };
  $("walk-gold").onchange = (e) => { S.walkGold = e.target.checked; renderWalkDoc(); };
  $("trace-run").onchange = (e) => { S.traceRun = e.target.value; renderTrace(); };
  $("trace-span").onchange = (e) => { S.traceSpan = e.target.value; renderTrace(); };
}

function debounce(fn, ms) {
  let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}

/* ================= R1 — data explorer ================= */

async function renderExplorer() {
  const stats = await api("/api/corpus/stats");
  const w = $("explorer-warnings");
  w.innerHTML = "";
  if (!stats.available) {
    $("explorer-stats").innerHTML =
      `<div class="banner warn">Corpus unavailable on this machine — ` +
      `${esc(stats.reason)}. Run views still work; gold views degrade.</div>`;
  } else {
    w.innerHTML = (stats.warnings || []).map(
      (x) => `<div class="banner warn">⚠ ${esc(x)}</div>`).join("");
    const disc = stats.discontinuous;
    const cards = [
      ["documents", stats.n_docs],
      ["gold mentions", stats.n_mentions],
      ["reactions", stats.by_entity_type.reaction ?? 0],
      ["drugs", stats.by_entity_type.drug ?? 0],
      ["concept-less", stats.concept_less],
      ["post-coordinated", stats.post_coordinated],
      ["disjunctions", stats.disjunctions],
      [`discontinuous (${(disc.fraction * 100).toFixed(1)}%)`, disc.reaction_mentions],
    ];
    if (stats.codes.available)
      cards.push(["codes active/retired/absent",
        `${stats.codes.active ?? 0}/${stats.codes.retired ?? 0}/${stats.codes.absent ?? 0}`]);
    $("explorer-stats").innerHTML = cards.map(
      ([k, v]) => `<div class="card"><div class="big">${esc(v)}</div>` +
        `<div class="muted">${esc(k)}</div></div>`).join("") +
      provFooter(stats.provenance);
  }
  renderZoneStrip();
  renderSplits();
  renderExclusions();
  renderDocs();
}

async function renderZoneStrip() {
  const el = $("zone-strip");
  const z = await api("/api/corpus/zones", { split: "dev" });
  if (!z.available) {
    el.innerHTML = `<div class="banner warn">V4 unavailable — ${esc(z.reason)}</div>` +
      provFooter(z.provenance);
    return;
  }
  const zones = z.zones || {};
  const total = z.n || Object.values(zones).reduce((a, b) => a + b, 0);
  const w = 560, h = 46;
  let x = 0, parts = "";
  for (const name of ["ACCEPT", "BAND", "REJECT"]) {
    const n = zones[name] || 0;
    const bw = total ? (n / total) * w : 0;
    parts += `<rect x="${x}" y="0" width="${bw}" height="24"
      fill="var(--z-${name.toLowerCase()})"></rect>` +
      (bw > 40 ? `<text x="${x + bw / 2}" y="16" text-anchor="middle"
        font-size="11" fill="#fff">${name} ${n}</text>` : "");
    x += bw;
  }
  el.innerHTML = `<div class="chart">${svgOpen(w, h)}${parts}
    <text x="0" y="40" font-size="11" class="svgmuted">gold replay, split dev —
    every REJECT is false by construction (floor ${(z.false_rejection_rate * 100).toFixed(2)}%,
    BAND ${(z.band_rate * 100).toFixed(1)}%)</text></svg>
    ${caveatChips(z.caveats)}${provFooter(z.provenance)}</div>`;
}

async function renderSplits() {
  const s = await api("/api/corpus/splits");
  $("splits-view").innerHTML =
    `<table><tr><th class="l">split</th><th>docs</th></tr>` +
    Object.entries(s.splits).map(([k, v]) =>
      `<tr><td class="l">${esc(k)}</td><td>${v.n_docs}</td></tr>`).join("") +
    `</table><div class="muted">seed ${esc(s.seed)} · stratified by ${esc(s.stratified_by)}</div>` +
    provFooter(s.provenance);
}

async function renderExclusions() {
  const e = await api("/api/corpus/exclusions");
  $("exclusions").innerHTML =
    `<table><tr><th class="l">record</th><th class="l">reason</th><th class="l">detail</th></tr>` +
    e.rows.map((r) => `<tr><td class="l">${esc(r.record_id)}</td>` +
      `<td class="l">${esc(r.reason)}</td><td class="l">${esc(r.detail)}</td></tr>`).join("") +
    `</table>` + provFooter(e.provenance);
}

async function renderDocs() {
  const split = $("explorer-split").value || null;
  const q = $("explorer-q").value || null;
  const d = await api("/api/corpus/docs", { split, q });
  $("spent-banner").hidden = !d.spent_split;
  $("doc-list").innerHTML = d.docs.length || d.available === false
    ? `<table><tr><th class="l">doc</th><th class="l">group</th><th>mentions</th>
       <th>reactions</th><th>discont.</th><th>excluded</th></tr>` +
      (d.docs || []).map((x) =>
        `<tr class="rowbtn" data-doc="${esc(x.doc_id)}">
         <td class="l">${esc(x.doc_id)}</td><td class="l">${esc(x.drug_group)}</td>
         <td>${x.n_mentions}</td><td>${x.n_reactions}</td>
         <td>${x.n_discontinuous}</td><td>${x.n_excluded}</td></tr>`).join("") +
      `</table>` + provFooter(d.provenance)
    : `<div class="muted" style="padding:.5rem">no documents</div>`;
  $("doc-list").querySelectorAll("tr[data-doc]").forEach(
    (tr) => (tr.onclick = () => renderDocView(tr.dataset.doc)));
}

function highlight(text, marks) {
  // marks: [{start, end, cls, title}] — render text with layered spans.
  const points = new Set([0, text.length]);
  for (const m of marks) { points.add(m.start); points.add(m.end); }
  const cuts = [...points].sort((a, b) => a - b);
  let html = "";
  for (let i = 0; i + 1 < cuts.length; i++) {
    const [a, b] = [cuts[i], cuts[i + 1]];
    const seg = text.slice(a, b);
    const on = marks.filter((m) => m.start <= a && b <= m.end);
    if (!on.length) { html += esc(seg); continue; }
    const cls = [...new Set(on.map((m) => m.cls))].join(" ");
    const title = on.map((m) => m.title).join(" | ");
    html += `<span class="${cls}" title="${esc(title)}">${esc(seg)}</span>`;
  }
  return html;
}

async function renderDocView(docId) {
  try {
    const d = await api("/api/corpus/doc", { doc_id: docId });
    const marks = [];
    for (const m of d.mentions) {
      for (const [a, b] of m.spans) {
        if (a < 0) continue;
        marks.push({
          start: a, end: b,
          cls: "gold-span" + (m.excluded ? " excluded" : "") +
               (m.discontinuous ? " seg" : ""),
          title: `${m.record_id} ${m.entity_type}` +
                 (m.sct.length ? ` → ${m.sct.join(", ")}` : " (concept-less)") +
                 (m.excluded ? ` — EXCLUDED (${m.exclusion_reason})` : "") +
                 (m.discontinuous ? " — discontinuous" : ""),
        });
      }
    }
    $("doc-view").innerHTML =
      `<h3>${esc(d.doc_id)} <span class="muted">${esc(d.drug_group)}</span></h3>
       <div class="doc-text">${highlight(d.text, marks)}</div>
       <div class="muted">underline = gold span (dotted = excluded, renders as
       excluded, not as an error; dashed outline = discontinuous segment)</div>` +
      provFooter(d.provenance);
  } catch (err) {
    $("doc-view").innerHTML = `<div class="banner warn">${esc(err.message)}</div>`;
  }
}

/* ================= R3 — results & comparison ================= */

async function renderResults() {
  if (!S.resultsRun) return;
  const run = S.resultsRun, span = S.span;
  $("results-export").innerHTML =
    `<a class="export" href="/api/export/figure?run=${encodeURIComponent(run)}&span_match=${span}" target="_blank">export SVG</a>
     <a class="export" href="/api/export/results?run=${encodeURIComponent(run)}" target="_blank">export CSV</a>
     <a class="export" href="/api/export/records?run=${encodeURIComponent(run)}&span_match=${span}" target="_blank">export records (scrubbed)</a>`;
  const [res, costs, score, flow] = await Promise.all([
    api("/api/run/results", { run }),
    api("/api/run/costs", { run }),
    api("/api/run/score", { run, span_match: span }),
    api("/api/run/flow", { run, span_match: span }),
  ]);
  let base = null, cmp = null;
  if (S.baseline && S.baseline !== run) {
    try { cmp = await api("/api/run/compare", { a: run, b: S.baseline, span_match: span }); }
    catch (err) { cmp = { error: err.message }; }
    if (cmp && !cmp.error) base = cmp.b;
  }
  $("results-caveats").innerHTML = caveatChips(res.caveats) +
    (cmp && cmp.rung3_cross_draw ? `<div class="caveat">${esc(cmp.rung3_cross_draw)}</div>` : "") +
    (cmp && cmp.error ? `<div class="banner warn">comparison refused: ${esc(cmp.error)}</div>` : "");
  renderHeadline(score, base);
  renderCIChart([{ label: run, score }, base && base.score ?
    { label: S.baseline, score: { available: true, ...base.score } } : null].filter(Boolean));
  renderLadderCurve(res, costs);
  renderOutcomeBars(run);
  renderDumbbell(run, base);
  renderFlow(flow);
  renderResultsTable(res);
  renderCostPanels(costs);
}

function renderHeadline(score, base) {
  const el = $("results-headline");
  if (!score.available) {
    el.innerHTML = `<div class="banner warn">${esc(score.reason)}</div>` +
      provFooter(score.provenance);
    return;
  }
  const s = score.score, ci = score.ci;
  const det = s.detection, cod = s.coding;
  const dl = (x) => x === null ? "—" : Number(x).toFixed(3);
  let deltas = "";
  if (base && base.score) {
    const d = s.f1 - base.score.score.f1;
    deltas = `<div class="card"><div class="big">${d >= 0 ? "+" : ""}${d.toFixed(3)}</div>
      <div class="muted">Δ F1 vs baseline (both intervals shown in V6)</div></div>`;
  }
  el.innerHTML = `<div class="cards">
    <div class="card"><div class="big">${dl(s.f1)}</div>
      <div class="muted">shipped F1 (${esc(s.span_match)})
      [${dl(ci.f1.lo)}–${dl(ci.f1.hi)}]</div></div>
    <div class="card"><div class="big">${dl(det.f1)}</div>
      <div class="muted">detection F1 [${dl(ci.detection_f1.lo)}–${dl(ci.detection_f1.hi)}]</div></div>
    <div class="card"><div class="big">${dl(cod.accuracy)}</div>
      <div class="muted">coding accuracy on ${cod.n} matched
      [${dl(ci.coding_accuracy.lo)}–${dl(ci.coding_accuracy.hi)}]</div></div>
    <div class="card"><div class="big">${s.n_pred} / ${s.n_gold}</div>
      <div class="muted">predictions / scorable gold (excluded ${s.excluded})</div></div>
    ${deltas}</div>` + provFooter(score.provenance);
}

function renderCIChart(rows) {
  const el = $("ci-chart");
  const usable = rows.filter((r) => r.score && r.score.available);
  if (!usable.length) { el.innerHTML = `<div class="muted">no scored runs</div>`; return; }
  const w = 640, rh = 34, h = usable.length * rh + 40;
  const x = (v) => 120 + v * 480;
  let g = `<line x1="${x(0)}" y1="10" x2="${x(0)}" y2="${h - 26}" class="axis"/>
           <line x1="${x(1)}" y1="10" x2="${x(1)}" y2="${h - 26}" class="axis"/>`;
  usable.forEach((r, i) => {
    const y = 22 + i * rh;
    const s = r.score.score, ci = r.score.ci.f1;
    g += `<text x="4" y="${y + 4}" font-size="11">${esc(r.label).slice(0, 18)}</text>
      <line x1="${x(ci.lo)}" y1="${y}" x2="${x(ci.hi)}" y2="${y}"
        stroke="var(--accent)" stroke-width="4" opacity="0.45"/>
      <circle cx="${x(s.f1)}" cy="${y}" r="5" fill="var(--accent)"/>
      <text x="${x(ci.hi) + 8}" y="${y + 4}" font-size="11">
        ${s.f1.toFixed(3)} [${ci.lo.toFixed(3)}–${ci.hi.toFixed(3)}]</text>`;
  });
  g += `<text x="${x(0)}" y="${h - 8}" font-size="10" class="svgmuted">0</text>
        <text x="${x(1) - 8}" y="${h - 8}" font-size="10" class="svgmuted">1</text>`;
  el.innerHTML = `<div class="chart">${svgOpen(w, h)}${g}</svg>
    <div class="muted">deltas render only with both intervals visible — the
    interval is the claim</div>${provFooter(usable[0].score.provenance)}</div>`;
}

function renderLadderCurve(res, costs) {
  const el = $("ladder-curve");
  const rows = res.rows;
  if (!rows.length) { el.innerHTML = `<div class="muted">no results.csv</div>`; return; }
  const disabled = new Set((costs.non_values || [])
    .filter((n) => n.disabled).map((n) => String(n.rung)));
  const w = 900, panelH = 76, pad = 60;
  const n = rows.length, bw = Math.min(80, (w - pad - 20) / n - 12);
  const panels = [
    ["answered accuracy", (r) => r.f1_sct_strict, 1, "var(--accent)", 3],
    ["errors / 100", (r) => r.err_per_100, Math.max(...rows.map((r) => r.err_per_100 || 0), 1), "var(--o-incorrect)", 1],
    ["tokens / record", (r) => r.tokens_per_record, Math.max(...rows.map((r) => r.tokens_per_record || 0), 1), "var(--z-band)", 1],
    ["p95 s / call", (r) => r.p95_s, Math.max(...rows.map((r) => r.p95_s || 0), 1), "var(--z-abstain)", 1],
    ["reviews / 100", (r) => r.reviews_per_100, 100, "var(--z-escalate)", 1],
  ];
  const h = panels.length * panelH + 30;
  let g = "";
  panels.forEach(([label, get, max, color, dec], pi) => {
    const y0 = pi * panelH + 14;
    g += `<text x="2" y="${y0 + 8}" font-size="10" class="svgmuted">${label}</text>`;
    rows.forEach((r, i) => {
      const x = pad + i * ((w - pad - 20) / n);
      const v = get(r);
      if (disabled.has(String(r.rung)) && pi > 0) {
        g += `<rect x="${x}" y="${y0 + 14}" width="${bw}" height="40" fill="url(#hatch)">
          <title>rung ${r.rung}: did not run (disabled — recorded state)</title></rect>`;
        return;
      }
      if (v === null || v === undefined) {
        g += `<rect x="${x}" y="${y0 + 14}" width="${bw}" height="40" fill="url(#hatch)">
          <title>rung ${r.rung}: no measurement</title></rect>`;
        return;
      }
      const bh = Math.max(1, (v / max) * 40);
      g += `<rect x="${x}" y="${y0 + 54 - bh}" width="${bw}" height="${bh}" fill="${color}">
        <title>rung ${r.rung} ${label}: ${v}</title></rect>
        <text x="${x + bw / 2}" y="${y0 + 52 - bh}" text-anchor="middle"
        font-size="9">${Number(v).toFixed(dec)}</text>`;
      if (pi === panels.length - 1)
        g += `<text x="${x + bw / 2}" y="${h - 6}" text-anchor="middle"
          font-size="10">${esc(r.rung)} ${esc(r.layer)}</text>`;
    });
  });
  el.innerHTML = `<div class="chart">${svgOpen(w, h)}${g}</svg>
    <div class="muted">three cost panels are separate axes (C5); hatch = no
    measurement, never zero; denominators are the ledger's own
    (${Object.entries(costs.denominators || {}).map(([k, v]) => `r${k}: ${v.denominator ?? "—"}`).join(", ")})</div>
    ${provFooter(res.provenance)}</div>`;
}

async function renderOutcomeBars(run) {
  const el = $("outcome-bars");
  const [ex, ov] = await Promise.all([
    api("/api/run/score", { run, span_match: "exact" }),
    api("/api/run/score", { run, span_match: "overlap" }),
  ]);
  if (!ex.available) { el.innerHTML = `<div class="muted">${esc(ex.reason)}</div>`; return; }
  const order = ["correct", "outdated", "abstained", "incorrect", "modernised"];
  const rows = [["exact", ex.score], ["overlap", ov.score]];
  const w = 640, h = 96;
  let g = "";
  rows.forEach(([label, s], ri) => {
    const total = order.reduce((a, o) => a + s[o], 0) || 1;
    let x = 90; const y = 16 + ri * 36;
    g += `<text x="2" y="${y + 14}" font-size="11">${label}</text>`;
    for (const o of order) {
      const bw = (s[o] / total) * (w - 110);
      if (!bw) continue;
      g += `<rect x="${x}" y="${y}" width="${bw}" height="20" fill="var(--o-${o})">
        <title>${o}: ${s[o]}</title></rect>` +
        (bw > 28 ? `<text x="${x + bw / 2}" y="${y + 14}" text-anchor="middle"
          font-size="10" fill="#fff">${s[o]}</text>` : "");
      x += bw;
    }
  });
  const legend = order.map((o) =>
    `<span class="outcome ${o}">■ ${o}</span>`).join(" ");
  el.innerHTML = `<div class="chart">${svgOpen(w, h)}${g}</svg>
    <div class="muted">${legend} — report order; outdated/modernised are never
    folded into correct</div>${provFooter(ex.provenance)}</div>`;
}

async function renderDumbbell(run, base) {
  const el = $("dumbbell");
  const entries = [];
  for (const [label, key] of [[run, run]].concat(
    base ? [[S.baseline, S.baseline]] : [])) {
    for (const span of ["exact", "overlap"]) {
      const s = await api("/api/run/score", { run: key, span_match: span });
      if (s.available) entries.push({ label: `${label} · ${span}`, s });
    }
  }
  if (!entries.length) { el.innerHTML = `<div class="muted">needs the corpus</div>`; return; }
  const w = 640, rh = 30, h = entries.length * rh + 34;
  const x = (v) => 180 + v * 420;
  let g = "";
  entries.forEach((e, i) => {
    const y = 20 + i * rh;
    const det = e.s.score.detection.f1, cod = e.s.score.coding.accuracy;
    g += `<text x="2" y="${y + 4}" font-size="10">${esc(e.label).slice(0, 26)}</text>
      <line x1="${x(Math.min(det, cod))}" y1="${y}" x2="${x(Math.max(det, cod))}" y2="${y}"
        stroke="var(--line)" stroke-width="2"/>
      <circle cx="${x(det)}" cy="${y}" r="5" fill="var(--accent)"><title>detection F1 ${det.toFixed(3)}</title></circle>
      <circle cx="${x(cod)}" cy="${y}" r="5" fill="var(--o-correct)"><title>coding accuracy ${cod.toFixed(3)}</title></circle>`;
  });
  g += `<text x="${x(0)}" y="${h - 8}" font-size="10" class="svgmuted">0</text>
    <text x="${x(1) - 8}" y="${h - 8}" font-size="10" class="svgmuted">1</text>`;
  el.innerHTML = `<div class="chart">${svgOpen(w, h)}${g}</svg>
    <div class="muted"><span style="color:var(--accent)">●</span> detection F1
    · <span style="color:var(--o-correct)">●</span> coding accuracy on matched
    spans — the oracle ceiling (dev only) moves coding, not detection</div>
    ${provFooter(entries[0].s.provenance)}</div>`;
}

function renderFlow(flow) {
  const el = $("flow-chart");
  const v = flow.rung1_verdicts || {};
  const total = flow.n_records || 1;
  const w = 720, h = 240, colw = 150, x1 = 10, x2 = 250, x3 = 500;
  const scale = (n) => (n / total) * 180;
  function col(x, items, title) {
    let y = 30, g = `<text x="${x}" y="18" font-size="11" font-weight="bold">${title}</text>`;
    for (const it of items) {
      const bh = Math.max(2, scale(it.n));
      g += `<rect x="${x}" y="${y}" width="${colw}" height="${bh}"
        fill="${it.fill}" ${it.hatch ? 'fill="url(#hatch)"' : ""}>
        <title>${it.label}: ${it.n}</title></rect>` +
        (bh > 12 ? `<text x="${x + 6}" y="${y + bh / 2 + 4}" font-size="10"
          fill="#fff">${it.label} ${it.n}</text>` :
          `<text x="${x + colw + 4}" y="${y + bh / 2 + 4}" font-size="9">${it.label} ${it.n}</text>`);
      y += bh + 6;
    }
    return g;
  }
  const scored = flow.scored;
  let g = col(x1, [
    { label: "ACCEPT", n: v.ACCEPT || 0, fill: "var(--z-accept)" },
    { label: "BAND", n: v.BAND || 0, fill: "var(--z-band)" },
    { label: "REJECT", n: v.REJECT || 0, fill: "var(--z-reject)" },
  ], `records ${total} → rung 1 verdicts`);
  g += col(x2, [
    { label: "shipped", n: flow.shipped.n, fill: "var(--z-verified)" },
    { label: "escalated", n: flow.escalated.n, fill: "var(--z-escalate)" },
    { label: "open", n: flow.open.n, fill: "var(--hatch-a)" },
  ], "→ final state");
  g += col(x3, scored ? [
    { label: "shipped correct", n: flow.shipped.correct, fill: "var(--o-correct)" },
    { label: "shipped wrong", n: flow.shipped.wrong, fill: "var(--o-incorrect)" },
    { label: "withheld-correct", n: flow.escalated.withheld_correct, fill: "var(--o-abstained)" },
    { label: "unlocatable", n: flow.escalated.unlocatable, fill: "var(--hatch-a)" },
    { label: "escalated other", n: flow.escalated.n - flow.escalated.withheld_correct - flow.escalated.unlocatable, fill: "var(--z-escalate)" },
  ] : [{ label: "needs corpus to split", n: total, fill: "var(--hatch-a)", hatch: true }],
    "→ correctness (COUNTS)");
  el.innerHTML = `<div class="chart">${svgOpen(w, h)}${g}</svg>
    <div class="muted">abstention's bill is a count: ${flow.escalated.n} of
    ${total} routed to a person${scored ? `; ${flow.escalated.withheld_correct}
    withheld answers were already correct` : ""}</div>
    ${caveatChips(flow.caveats)}${provFooter(flow.provenance)}</div>`;
}

function renderResultsTable(res) {
  const el = $("results-table");
  const cols = ["rung", "layer", "n_records", "accept", "band", "reject",
    "abstained", "escalated", "verified", "r1_reject_pct", "r1_mode",
    "coverage", "f1_sct_strict", "corrupted", "sct_outdated", "sct_abstained",
    "sct_modernised", "err_per_100"];
  el.innerHTML = `<table><tr>${cols.map((c) => `<th${["layer","r1_mode"].includes(c)?' class="l"':''}>${c}</th>`).join("")}</tr>` +
    res.rows.map((r) => `<tr>` + cols.map((c) => {
      const v = r[c];
      if (v === null || v === undefined)
        return '<td class="nonvalue" title="no measurement">·</td>';
      if (["layer", "r1_mode"].includes(c)) return `<td class="l">${esc(v)}</td>`;
      return `<td>${esc(v)}</td>`;
    }).join("") + `</tr>`).join("") + `</table>` +
    `<div class="muted">counts drawn over each rung's snapshot (the ledger's
     denominator), never the run total; · = no measurement</div>` +
    provFooter(res.provenance);
}

function renderCostPanels(costs) {
  const el = $("cost-panels");
  const rungs = Object.keys(costs.denominators || {});
  const panel = (title, rows) =>
    `<div class="card" style="min-width:260px"><b>${title}</b><table><tr>
     <th>rung</th>${rungs.map((r) => `<th>${r}</th>`).join("")}</tr>` +
    rows.map(([label, get, d]) =>
      `<tr><td class="l">${label}</td>` + rungs.map((r) => cell(get(r), d)).join("") +
      `</tr>`).join("") + `</table></div>`;
  const t = costs.panels.tokens, l = costs.panels.latency, rv = costs.panels.reviews;
  const failures = Object.entries(costs.failure_labels || {});
  el.innerHTML = `<div class="cards">` +
    panel("tokens", [
      ["tokens/record", (r) => t[r] && t[r].tokens_per_record, 1],
      ["api calls", (r) => t[r] && t[r].api_calls, 0]]) +
    panel("latency", [["p95 s/call", (r) => l[r] && l[r].p95_s, 2]]) +
    panel("routed to a person", [
      ["count", (r) => rv[r] && rv[r].routed, 0],
      ["reviews/100", (r) => rv[r] && rv[r].reviews_per_100, 2],
      ["minutes (declared rate)", (r) => rv[r] && rv[r].human_minutes, 1]]) +
    panel("usd (carried alongside, never fused)", [["usd", (r) => costs.usd[r], 4]]) +
    `</div>` +
    (failures.length ? `<h3>failure labels <span class="muted">most specific
      first: timed_out &gt; truncated &gt; json_decode — filed under cost, not
      accuracy</span></h3><table><tr><th>rung</th><th>timed_out</th>
      <th>truncated</th><th>json_decode</th></tr>` +
      failures.map(([r, f]) => `<tr><td>${r}</td><td>${f.timed_out}</td>
        <td>${f.truncated}</td><td>${f.json_decode}</td></tr>`).join("") +
      `</table>` : `<div class="muted">failure labels: none recorded
      (timed_out / truncated / json_decode all zero)</div>`) +
    ((costs.non_values || []).length ?
      `<div class="banner warn">could_not_run (hatched, never a color): ` +
      costs.non_values.map((n) => `rung ${n.rung} × ${n.count} (${esc(n.reason)})`).join("; ") +
      `</div>` : "") +
    caveatChips(costs.caveats) + provFooter(costs.provenance);
}

/* ================= R4 — walkthrough ================= */

async function renderWalkthrough() {
  if (!S.walkRun) return;
  const docs = await api("/api/run/docs", { run: S.walkRun });
  const sel = $("walk-doc");
  sel.innerHTML = "";
  for (const d of docs.docs) {
    const o = document.createElement("option");
    o.value = d.doc_id;
    const oc = Object.entries(d.outcomes).map(([k, v]) => `${k[0]}${v}`).join(" ");
    o.textContent = `${d.doc_id} (${d.n_records} rec${oc ? " · " + oc : ""})`;
    sel.appendChild(o);
  }
  $("walk-caveats").innerHTML = caveatChips(docs.caveats);
  S.walkDoc = S.walkDoc && docs.docs.some((d) => d.doc_id === S.walkDoc)
    ? S.walkDoc : (docs.docs[0] && docs.docs[0].doc_id);
  sel.value = S.walkDoc || "";
  renderWalkDoc();
}

async function renderWalkDoc() {
  if (!S.walkRun || !S.walkDoc) { $("walk-records").innerHTML = ""; return; }
  const wt = await api("/api/run/walkthrough",
    { run: S.walkRun, doc_id: S.walkDoc, span_match: S.walkSpan });
  const textEl = $("walk-doc-text");
  if (wt.text) {
    const marks = [];
    for (const r of wt.records)
      for (const [a, b] of r.spans)
        if (a >= 0) marks.push({ start: a, end: b, cls: "pred-span",
          title: `${r.record_id} → ${r.sct ?? "no code"} (${r.zone})` });
    if (S.walkGold && wt.gold_mentions)
      for (const m of wt.gold_mentions)
        for (const [a, b] of m.spans)
          if (a >= 0) marks.push({ start: a, end: b,
            cls: "gold-span" + (m.excluded ? " excluded" : ""),
            title: `GOLD ${m.record_id} → ${m.sct.join(",") || "concept-less"}` });
    textEl.innerHTML = `<div class="doc-text">${highlight(wt.text, marks)}</div>
      <div class="muted">blue = this run's records; green = gold overlay
      (toggle)</div>`;
  } else {
    textEl.innerHTML = `<div class="banner warn">document text unavailable
      (corpus not on this machine) — panels below still render from recorded
      checks</div>`;
  }
  const stateLabel = { changed: "changed", judged: "judged",
    did_not_fire: "did not fire", did_not_run: "did not run (recorded)",
    not_in_run: "not in run" };
  $("walk-records").innerHTML = wt.records.map((r) => {
    const tl = r.timeline.map((n, i) =>
      (i ? '<div class="tl-link"></div>' : "") +
      `<div class="tl-node ${n.state}" title="${esc(n.detail)}">
        <div class="tl-dot"></div><div>r${n.rung}</div>
        <div class="muted">${esc(stateLabel[n.state] || n.state)}</div></div>`).join("");
    const g = r.gold;
    const goldLine = g ? (g.matched
      ? `<span class="outcome ${g.outcome}">${g.outcome}</span>
         <span class="muted">gold ${g.gold_sct ? g.gold_sct.join(", ") : "—"}
         (${S.walkSpan})${g.withheld_outcome ? ` · withheld answer would be ${g.withheld_outcome}` : ""}</span>`
      : `<span class="outcome ${g.outcome === "excluded" ? "abstained" : "incorrect"}">${g.outcome}</span>`)
      : `<span class="muted">unscored (no corpus)</span>`;
    const p = r.panels;
    return `<div class="record-card">
      <div><b>${esc(r.record_id)}</b>
        ${r.unlocatable ? '<span class="zone REJECT" title="(-1,-1) spans">unlocatable — schema-invalid</span>' : ""}
        <span class="zone ${esc(r.zone)}">${esc(r.zone)}</span>
        “${esc(r.text)}” → ${esc(r.sct ?? "no code")}
        ${r.sct_label ? `<span class="muted">“${esc(r.sct_label)}”</span>` : ""}
        · final: <b>${esc(r.final.state)}</b> · ${goldLine}</div>
      <div class="timeline">${tl}</div>
      <details><summary>per-rung panels (recorded checks — no re-derivation)</summary>
        <dl class="kv">
        <dt>r0</dt><dd>step ${esc(p.r0.rung0_step ?? "—")}, retrieval
          ${esc(p.r0.rung0_retrieval ?? "—")}, ${p.r0.n_candidates} candidates,
          negated ${esc(p.r0.r0_negated ?? p.r0.negated ?? "—")}</dd>
        <dt>r1</dt><dd>verdict ${esc(p.r1.verdict ?? "—")}
          ${p.r1.reason ? `(${esc(p.r1.reason)})` : ""}; lexical
          ${esc(p.r1.lexical_match ?? "—")}, exists ${esc(p.r1.sct_exists ?? "—")},
          active ${esc(p.r1.sct_active ?? "—")}</dd>
        <dt>r2</dt><dd>${p.r2.fired ? esc(p.r2.outcome || "fired") :
          `did not fire — ${esc(p.r2.why)}`}</dd>
        <dt>r3</dt><dd>${esc(p.r3.outcome ?? "")} seen ${esc(p.r3.seen ?? "—")}/${esc(p.r3.k ?? "—")}
          ${p.r3.single_sample ? " · single-sample (withheld by rule)" : ""}
          ${p.r3.votes ? " · votes " + esc(JSON.stringify(p.r3.votes)) : ""}</dd>
        <dt>r4</dt><dd>${p.r4.verdict === null || p.r4.verdict === undefined ?
          "no verdict" : `${esc(p.r4.verdict)} conf ${esc(p.r4.confidence)}`}
          ${p.r4.why ? ` — “${esc(p.r4.why)}”` : ""}</dd>
        <dt>r5</dt><dd>${p.r5.withheld ?
          `withdrew; withheld answer ${esc(p.r5.withheld.sct)} conf ${esc(p.r5.withheld.confidence)}` :
          "kept"}</dd>
        <dt>r6</dt><dd>${p.r6 ? esc(JSON.stringify(p.r6)) :
          (r.zone === "ESCALATE" ? "queued for a person (count is the cost)" : "—")}</dd>
        </dl></details>
    </div>`;
  }).join("") + provFooter(wt.provenance);
}

/* ================= R5 — traceability ================= */

async function renderTrace() {
  if (!S.traceRun) return;
  const run = S.traceRun, span = S.traceSpan;
  const score = await api("/api/run/score", { run, span_match: span });
  const agg = $("trace-aggregates");
  if (!score.available) {
    agg.innerHTML = `<div class="banner warn">${esc(score.reason)} — record
      list below still works, outcomes unscored.</div>` +
      provFooter(score.provenance);
    listRecords();
    return;
  }
  const s = score.score;
  const order = ["correct", "outdated", "abstained", "incorrect", "modernised"];
  agg.innerHTML = `<div class="cards">` + order.map((o) =>
    `<div class="card rowbtn" data-outcome="${o}">
      <div class="big outcome ${o}">${s[o]}</div>
      <div class="muted">${o} — click for the records</div></div>`).join("") +
    `</div>` + caveatChips(score.caveats) + provFooter(score.provenance);
  agg.querySelectorAll("[data-outcome]").forEach(
    (el) => (el.onclick = () => listRecords(el.dataset.outcome)));
  listRecords();
}

async function listRecords(outcome) {
  const body = await api("/api/run/records",
    { run: S.traceRun, span_match: S.traceSpan, outcome });
  $("trace-records").innerHTML =
    `<table><tr><th class="l">record</th><th class="l">spans</th>
     <th class="l">zone</th><th class="l">code</th><th class="l">outcome</th></tr>` +
    body.records.map((r) =>
      `<tr class="rowbtn" data-doc="${esc(r.doc_id)}" data-spans="${esc(r.span_param)}">
       <td class="l">${esc(r.record_id)}</td>
       <td class="l">${r.unlocatable ? "unlocatable" : esc(r.span_param)}</td>
       <td class="l"><span class="zone ${esc(r.zone)}">${esc(r.zone)}</span></td>
       <td class="l">${esc(r.sct ?? "—")}</td>
       <td class="l outcome ${esc(r.outcome ?? "")}">${esc(r.outcome ?? "unscored")}</td></tr>`).join("") +
    `</table>` + provFooter(body.provenance);
  $("trace-records").querySelectorAll("tr[data-doc]").forEach((tr) =>
    (tr.onclick = () => recordDetail(tr.dataset.doc, tr.dataset.spans)));
}

async function recordDetail(docId, spans) {
  const el = $("trace-detail");
  el.innerHTML = `<div class="muted">loading…</div>`;
  try {
    const [d, llm] = await Promise.all([
      api("/api/run/record", { run: S.traceRun, doc_id: docId, spans,
        span_match: S.traceSpan }),
      api("/api/run/record_llm", { run: S.traceRun, doc_id: docId, spans }),
    ]);
    const r = d.record;
    const ledger = `<table><tr><th>rung</th><th class="l">outcome</th>
      <th class="l">reason</th><th class="l">verdict</th><th>tok in</th>
      <th>tok out</th><th>calls</th><th>ms</th><th>usd</th><th>min</th>
      <th class="l">denominator</th></tr>` +
      d.ledger_rows.map((x) => `<tr${x.evaluable === "could_not_run" ? ' class="hatch"' : ""}>
        <td>${x.rung}</td><td class="l">${esc(x.outcome)}${x.per_document ? " (per-document)" : ""}</td>
        <td class="l">${esc(x.reason ?? "")}</td><td class="l">${esc(x.verdict ?? "")}</td>
        <td>${x.tokens_in}</td><td>${x.tokens_out}</td><td>${x.api_calls}</td>
        <td>${x.latency_ms.toFixed(0)}</td><td>${x.usd}</td><td>${x.human_minutes}</td>
        <td class="l">${esc(x.denominator ?? "")}</td></tr>`).join("") + `</table>`;
    const calls = (llm.calls || []).map((c) => c.status === "retained"
      ? `<details open><summary>rung ${c.rung} ${esc(c.call)} — ${esc(c.model)}
          (${c.prompt_tokens}+${c.completion_tokens} tok, ${c.latency_s}s${c.truncated ? ", TRUNCATED" : ""})</summary>
          <div class="muted">prompt (local-only, excluded from exports):</div>
          <pre class="raw">${esc(c.prompt)}</pre>
          <div class="muted">raw reply:</div><pre class="raw">${esc(c.reply)}</pre></details>`
      : `<div class="muted">rung ${c.rung} ${esc(c.call ?? "")}: not retained
          ${c.note ? `(${esc(c.note)})` : "— cache holds no entry for this exact request"}</div>`
    ).join("") || `<div class="muted">${esc(llm.note ?? "no calls reconstructable")}</div>`;
    const gold = d.gold ? `<dl class="kv"><dt>exact</dt>
        <dd class="outcome ${esc(d.gold.exact.outcome)}">${esc(d.gold.exact.outcome)}</dd>
        <dt>overlap</dt>
        <dd class="outcome ${esc(d.gold.overlap.outcome)}">${esc(d.gold.overlap.outcome)}</dd></dl>`
      : `<div class="muted">unscored (no corpus)</div>`;
    el.innerHTML = `<div class="record-card">
      <h3>${esc(r.record_id)} <span class="zone ${esc(r.zone)}">${esc(r.zone)}</span>
        ${r.unlocatable ? '<span class="zone REJECT">unlocatable — schema-invalid</span>' : ""}</h3>
      <div>“${esc(r.text)}” → ${esc(r.sct ?? "no code")}
        ${r.sct_label ? `(“${esc(r.sct_label)}”)` : ""}</div>
      <h4>outcome vs gold</h4>${gold}
      <h4>ledger rows <span class="muted">(hatched = could_not_run)</span></h4>${ledger}
      <h4>checks (recorded)</h4>
      <details><summary>show</summary><pre class="raw">${esc(JSON.stringify(r.checks, null, 1))}</pre></details>
      <h4>zone history</h4>
      <pre class="raw">${esc(JSON.stringify(r.history, null, 1))}</pre>
      <h4>prompt &amp; raw reply <span class="muted">(from .llm_cache; misses
        say "not retained", never an empty reply)</span></h4>${calls}
      ${provFooter(d.provenance)}</div>`;
  } catch (err) {
    el.innerHTML = `<div class="banner warn">${esc(err.message)}</div>`;
  }
}

boot().catch((e) => {
  document.body.insertAdjacentHTML("beforeend",
    `<div class="banner warn">failed to start: ${esc(e.message)}</div>`);
});
