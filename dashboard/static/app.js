/* Ladder Workbench — M1 read-only lens + the Live run tab (2026-09-09).
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
  traceRun: null, traceSpan: "exact", traceFilter: null,
  live: { options: null, job: null, timer: null, result: null, selected: null, rung: null },
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
    if (!t.shipped) {
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
  if (!t.shipped) {
    $("tab-later").hidden = false;
    $("later-title").textContent = t.label;
    $("later-note").textContent =
      `Planned for milestone ${t.milestone}. Shipped so far: the M1 ` +
      `read-only lens and the Live run tab (one document through the real ` +
      `rungs, nothing written under out/). The tab bar and data layer are ` +
      `structured so this lands without rework.`;
    return;
  }
  S.tab = t.id;
  $(`tab-${t.id}`).hidden = false;
  ({explorer: renderExplorer, results: renderResults,
    walkthrough: renderWalkthrough, trace: renderTrace, live: renderLive}[t.id])();
}

function wireControls() {
  wireLive();
  $("results-run").onchange = (e) => { S.resultsRun = e.target.value; renderResults(); };
  $("results-baseline").onchange = (e) => { S.baseline = e.target.value || null; renderResults(); };
  $("results-span").onchange = (e) => { S.span = e.target.value; renderResults(); };
  wireData();
  $("walk-run").onchange = (e) => { S.walkRun = e.target.value; S.walkDoc = null; renderWalkthrough(); };
  $("walk-doc").onchange = (e) => { S.walkDoc = e.target.value; renderWalkDoc(); };
  $("walk-span").onchange = (e) => { S.walkSpan = e.target.value; renderWalkDoc(); };
  $("walk-gold").onchange = (e) => { S.walkGold = e.target.checked; renderWalkDoc(); };
  $("trace-run").onchange = (e) => {
    S.traceRun = e.target.value; S.traceFilter = null; renderTrace(); };
  $("trace-span").onchange = (e) => { S.traceSpan = e.target.value; renderTrace(); };
}

function debounce(fn, ms) {
  let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}

/* ---------------- text highlighting (shared by Data, Live, Results) ---------------- */

function highlight(text, marks) {
  // marks: [{start, end, cls, title, rid?}] — render text with layered spans;
  // a mark's record id is emitted as data-rid so the span is addressable.
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
    const title = on.map((m) => m.title).filter(Boolean).join(" | ");
    const rids = [...new Set(on.map((m) => m.rid).filter(Boolean))];
    const rid = rids.length ? ` data-rid="${esc(rids.join(" "))}"` : "";
    html += `<span class="${cls}"${rid}${title ? ` title="${esc(title)}"` : ""}>${esc(seg)}</span>`;
  }
  return html;
}

/* ================= Data — filters, one line, then the document or the table ================= */

const D = { split: "dev", drug: "", doc: null, run: null, docs: [], sort: "doc_id",
  showExcluded: true, showDisc: true, pinned: null };

function wireData() {
  $("data-split").onchange = (e) => { D.split = e.target.value; D.doc = null; renderExplorer(); };
  $("data-drug").onchange = (e) => { D.drug = e.target.value; renderDataBody(); };
  $("data-run").onchange = (e) => { D.run = e.target.value || null; renderExplorer(); };
  $("data-show-excluded").onchange = (e) => { D.showExcluded = e.target.checked; renderDataBody(); };
  $("data-show-disc").onchange = (e) => { D.showDisc = e.target.checked; renderDataBody(); };
  const inp = $("data-doc");
  inp.onchange = () => { const v = inp.value.trim(); if (D.docs.some((d) => d.doc_id === v)) { D.doc = v; renderDataBody(); } };
  inp.onkeydown = (e) => { if (e.key === "Escape") { inp.value = ""; D.doc = null; renderDataBody(); } };
  $("data-doc-clear").onclick = () => { inp.value = ""; D.doc = null; renderDataBody(); };
}

async function renderExplorer() {
  if (!$("data-run").options.length) {
    fillRunSelect($("data-run"), S.runs, true);
    // the newest run ON THIS CORPUS's splits — a matrix cell from another
    // corpus is newer on disk and would read as "everything missed"
    const first = S.runs.find((r) => r.split === "dev" || r.split === "pool") || S.runs[0];
    if (first) { $("data-run").value = first.key; D.run = first.key; }
  }
  $("spent-banner").hidden = D.split !== "test";
  let d;
  try {
    d = await api("/api/corpus/docs", { split: D.split, run: D.run });
  } catch (err) {
    $("data-summary").innerHTML = `<div class="banner warn">${esc(err.message)}</div>`;
    return;
  }
  if (d.available === false) {
    $("data-summary").innerHTML = `<div class="banner warn">Corpus unavailable on this
      machine — ${esc(d.reason)}. Run views still work; gold views degrade.</div>`;
    $("data-doc-view").innerHTML = ""; $("data-table").innerHTML = "";
    renderReference();
    return;
  }
  D.docs = d.docs;
  // the drug filter offers what the split holds
  const drugs = [...new Set(d.docs.map((x) => x.drug_group))].sort();
  const sel = $("data-drug");
  const keep = drugs.includes(D.drug) ? D.drug : "";
  sel.innerHTML = `<option value="">any</option>` + drugs.map((g) =>
    `<option value="${esc(g)}">${esc(g)}</option>`).join("");
  sel.value = keep; D.drug = keep;
  $("data-doc-list").innerHTML = d.docs.map((x) =>
    `<option value="${esc(x.doc_id)}">${x.n_mentions} gold · ${esc(x.drug_group)}</option>`).join("");
  renderSummary(d);
  renderDataBody();
  renderReference();
}

async function renderSummary(d) {
  const docs = d.docs;
  const nMentions = docs.reduce((a, x) => a + x.n_reactions, 0);
  const drugs = new Set(docs.map((x) => x.drug_group)).size;
  let zones = "";
  try {
    const z = await api("/api/corpus/zones", { split: D.split });
    if (z.available) {
      const zz = z.zones || {}, total = z.n || 1;
      const seg = (name) => `<i style="width:${((zz[name] || 0) / total * 100).toFixed(1)}%;background:var(--z-${name.toLowerCase()})" title="${name} ${zz[name] || 0}"></i>`;
      zones = ` · gold through rung 1: <span class="zbar">${seg("ACCEPT")}${seg("BAND")}${seg("REJECT")}</span>
        ACCEPT ${zz.ACCEPT || 0} · BAND ${zz.BAND || 0} · REJECT ${zz.REJECT || 0}
        <span class="muted">(${esc(z.provenance && z.provenance.backend)}; every REJECT is false by construction)</span>`;
    }
  } catch { /* the strip is optional; the line stands without it */ }
  $("data-summary").innerHTML = `<b>${esc(D.split)}</b> · ${docs.length} documents · ${nMentions} reaction mentions
    · ${drugs} drug${drugs === 1 ? "" : "s"}${zones}`;
}

function renderDataBody() {
  const clear = $("data-doc-clear");
  clear.hidden = !D.doc;
  if (D.doc) {
    $("data-table").innerHTML = "";
    $("data-doc").value = D.doc;
    renderDataDoc(D.doc);
  } else {
    $("data-doc-view").innerHTML = "";
    renderDataTable();
  }
}

function renderDataTable() {
  let rows = D.docs.filter((x) => !D.drug || x.drug_group === D.drug);
  const hasRun = rows.length && rows[0].in_run;
  const key = D.sort;
  const val = (x) => {
    if (key === "missed") return x.in_run ? x.in_run.missed : 0;
    if (key === "exact") return x.in_run ? x.in_run.exact : 0;
    if (key === "records") return x.in_run ? x.in_run.records : 0;
    return x[key];
  };
  rows = rows.slice().sort((a, b) => {
    const va = val(a), vb = val(b);
    if (typeof va === "number") return vb - va || a.doc_id.localeCompare(b.doc_id);
    return String(va).localeCompare(String(vb));
  });
  const th = (k, label, cls = "") => `<th class="${cls} sortable ${key === k ? "sorted" : ""}" data-sort="${k}">${label}</th>`;
  const inRun = (x) => {
    const r = x.in_run;
    if (!r) return "";
    if (!r.records && !r.gold) return `<td class="l muted">—</td>`;
    const zones = Object.entries(r.zones).map(([z, n]) => `<span class="zone ${esc(z)}" title="${n} ${esc(z)}">${n}</span>`).join("");
    return `<td class="l inrun">${zones} <span class="muted">· ${r.exact} exact · ${r.overlap} overlap
      · ${r.missed} missed · ${r.model_only} model only</span></td>`;
  };
  $("data-table").innerHTML = rows.length
    ? `<table class="docs"><tr>${th("doc_id", "document", "l")}${th("drug_group", "drug", "l")}
        ${th("n_mentions", "gold")}${th("n_discontinuous", "discontinuous")}${th("n_excluded", "excluded")}
        ${hasRun ? th("missed", `in run ${esc(D.run)}`, "l") : ""}</tr>` +
      rows.map((x) => `<tr data-doc="${esc(x.doc_id)}">
        <td class="l">${esc(x.doc_id)}</td><td class="l">${esc(x.drug_group)}</td>
        <td>${x.n_mentions}</td><td>${x.n_discontinuous}</td><td>${x.n_excluded}</td>${inRun(x)}</tr>`).join("") +
      `</table><div class="muted">click a row to open the document · click a header to sort${hasRun ? " · sort by the run column to find the most missed" : ""}</div>`
    : `<div class="muted" style="padding:.5rem">no documents match</div>`;
  $("data-table").querySelectorAll("tr[data-doc]").forEach((tr) =>
    (tr.onclick = () => { D.doc = tr.dataset.doc; renderDataBody(); }));
  $("data-table").querySelectorAll("th[data-sort]").forEach((h) =>
    (h.onclick = () => { D.sort = h.dataset.sort; renderDataTable(); }));
}

function codeHtml(c, registryAvailable) {
  if (registryAvailable === false) return `<span class="code">${esc(c.code)}</span> <span class="k">no index — label unavailable</span>`;
  if (c.label) return `<span class="code">${esc(c.code)} <i>|${esc(c.label)}|</i></span>`;
  return `<span class="code">${esc(c.code)}</span> <span class="k">${c.in_vocabulary === false ? "not in this release" : "no label"}</span>`;
}

function mentionCardHtml(m, d) {
  const codes = m.concept_less ? `<div class="code k">concept-less — gold has no code here</div>`
    : m.codes.map((c) => `<div>${codeHtml(c, d.registry_available)}</div>`).join("");
  const kind = m.gold_kind === "any_of" ? "one of these codes" : m.gold_kind === "all_of" ? "all of these codes" : m.concept_less ? "" : "single code";
  return `<div><b>“${esc(m.text)}”</b> <span class="k">${esc(m.spans.map((x) => x.join("-")).join(", "))} · ${esc(m.cadec_type)}${m.discontinuous ? " · discontinuous" : ""}</span></div>
    ${codes}
    <div class="k">${kind}${m.excluded ? ` · <b>excluded</b> (${esc(m.exclusion_reason)})` : ""}</div>
    <div class="acts"><a href="#" data-act="live">send to Live ▶</a><span class="k">click a word to pin · Esc to close</span></div>`;
}

async function renderDataDoc(docId) {
  const el = $("data-doc-view");
  el.innerHTML = `<div class="muted">loading…</div>`;
  let d;
  try { d = await api("/api/corpus/doc", { doc_id: docId }); }
  catch (err) { el.innerHTML = `<div class="banner warn">${esc(err.message)}</div>`; return; }
  const marks = [];
  const byId = {};
  for (const m of d.mentions) {
    byId[m.record_id] = m;
    if (m.excluded && !D.showExcluded) continue;
    if (m.discontinuous && !D.showDisc) continue;
    for (const [a, b] of m.spans) {
      if (a < 0) continue;
      marks.push({ start: a, end: b, rid: m.record_id,
        cls: "gold-span" + (m.excluded ? " excluded" : ""),
        title: "" });
    }
  }
  const inRun = D.docs.find((x) => x.doc_id === docId);
  const r = inRun && inRun.in_run;
  el.innerHTML = `<div class="doc-head"><h3 style="margin:0">${esc(d.doc_id)}</h3>
      <span class="muted">${esc(d.drug_group)} · ${d.mentions.length} gold mention${d.mentions.length === 1 ? "" : "s"}</span>
      ${r && (r.records || r.gold) ? `<span class="muted">· in ${esc(D.run)}: ${r.exact} exact · ${r.overlap} overlap · ${r.missed} missed · ${r.model_only} model only</span>` : ""}
      <span class="actions"><a href="#" id="data-to-live">send to Live ▶</a></span></div>
    <div class="doc-text data" id="data-text">${highlight(d.text, marks)}</div>
    <div class="muted">hover an annotated word for its code · click pins · ${d.registry_available ? "" : "no SNOMED index on this machine: codes without labels · "}green = gold${D.showExcluded ? " · dotted = excluded" : ""}</div>
    ${provFooter(d.provenance)}`;
  const text = $("data-text");
  let card = null;
  const closeCard = () => { if (card) { card.remove(); card = null; } D.pinned = null;
    text.querySelectorAll(".lit").forEach((x) => x.classList.remove("lit")); };
  const openCard = (rid, anchor, pinned) => {
    const m = byId[rid];
    if (!m) return;
    if (card) card.remove();
    text.querySelectorAll(".lit").forEach((x) => x.classList.remove("lit"));
    text.querySelectorAll(`[data-rid~="${CSS.escape(rid)}"]`).forEach((x) => x.classList.add("lit"));
    card = document.createElement("div");
    card.className = "mention-card" + (pinned ? " pinned" : "");
    card.innerHTML = mentionCardHtml(m, d);
    el.appendChild(card);
    const r0 = anchor.getBoundingClientRect(), r1 = el.getBoundingClientRect();
    card.style.left = Math.max(0, Math.min(r0.left - r1.left, el.clientWidth - card.offsetWidth - 8)) + "px";
    card.style.top = (r0.bottom - r1.top + 6) + "px";
    card.querySelector('[data-act="live"]').onclick = (e) => { e.preventDefault(); sendToLive(docId); };
  };
  text.querySelectorAll("[data-rid]").forEach((sp) => {
    const rid = sp.dataset.rid.split(" ")[0];
    sp.onmouseenter = () => { if (!D.pinned) openCard(rid, sp, false); };
    sp.onmouseleave = () => { if (!D.pinned) closeCard(); };
    sp.onclick = (e) => { e.stopPropagation();
      if (D.pinned === rid) { closeCard(); return; }
      D.pinned = rid; openCard(rid, sp, true); };
  });
  el.onclick = (e) => { if (D.pinned && !e.target.closest(".mention-card")) closeCard(); };
  document.addEventListener("keydown", function esc(e) {
    if (e.key === "Escape" && D.pinned) closeCard();
    if (!document.body.contains(el)) document.removeEventListener("keydown", esc);
  });
  $("data-to-live").onclick = (e) => { e.preventDefault(); sendToLive(docId); };
}

function sendToLive(docId) {
  const t = S.tabs.find((x) => x.id === "live");
  if (!t) return;
  showTab(t);
  const src = $("live-source");
  src.value = "corpus"; src.dispatchEvent(new Event("change"));
  setTimeout(() => { const sel = $("live-doc"); if ([...sel.options].some((o) => o.value === docId)) sel.value = docId; }, 800);
}

async function renderReference() {
  try {
    const stats = await api("/api/corpus/stats");
    const w = $("explorer-warnings");
    if (!stats.available) { $("explorer-stats").innerHTML = `<div class="muted">corpus unavailable</div>`; }
    else {
      w.innerHTML = (stats.warnings || []).map((x) => `<div class="banner warn">⚠ ${esc(x)}</div>`).join("");
      const disc = stats.discontinuous;
      const cards = [["documents", stats.n_docs], ["gold mentions", stats.n_mentions],
        ["reactions", stats.by_entity_type.reaction ?? 0], ["concept-less", stats.concept_less],
        ["post-coordinated", stats.post_coordinated], ["disjunctions", stats.disjunctions],
        [`discontinuous (${(disc.fraction * 100).toFixed(1)}%)`, disc.reaction_mentions]];
      if (stats.codes.available)
        cards.push(["codes active/retired/absent", `${stats.codes.active ?? 0}/${stats.codes.retired ?? 0}/${stats.codes.absent ?? 0}`]);
      $("explorer-stats").innerHTML = cards.map(([k, v]) =>
        `<div class="card"><div class="big">${esc(v)}</div><div class="muted">${esc(k)}</div></div>`).join("") + provFooter(stats.provenance);
    }
    const sp = await api("/api/corpus/splits");
    $("splits-view").innerHTML = `<table><tr><th class="l">split</th><th>docs</th></tr>` +
      Object.entries(sp.splits).map(([k, v]) => `<tr><td class="l">${esc(k)}</td><td>${v.n_docs}</td></tr>`).join("") +
      `</table><div class="muted">seed ${esc(sp.seed)} · stratified by ${esc(sp.stratified_by)}</div>`;
    const ex = await api("/api/corpus/exclusions");
    $("exclusions").innerHTML = `<table><tr><th class="l">record</th><th class="l">reason</th><th class="l">detail</th></tr>` +
      ex.rows.map((r) => `<tr><td class="l">${esc(r.record_id)}</td><td class="l">${esc(r.reason)}</td><td class="l">${esc(r.detail)}</td></tr>`).join("") + `</table>`;
  } catch (err) {
    $("explorer-stats").innerHTML = `<div class="banner warn">${esc(err.message)}</div>`;
  }
}

/* ================= R3 — results & comparison ================= */

// pick a subset of a run's caveats — caveats attach where their numbers
// render, never as a wall of banners at the top
function pick(caveats, keys) {
  const out = {};
  for (const k of keys) if (caveats && caveats[k]) out[k] = caveats[k];
  return out;
}

const SPAN_EXPLAINER =
  `<div class="explainer"><b>exact vs overlap:</b> the model quotes
   "extreme rectal bleed" where gold says "rectal bleed" — the same finding,
   different boundaries. <b>overlap</b> pairs them (any shared character,
   each gold mention claimed once); <b>exact</b> requires the identical span
   set, so that pair counts as one false positive AND one false negative.
   Both are reported — neither is the "true" number alone.</div>`;

async function renderResults() {
  if (!S.resultsRun) return;
  const run = S.resultsRun, span = S.span;
  $("results-export").innerHTML =
    `<a class="export" href="/api/export/figure?run=${encodeURIComponent(run)}&span_match=${span}" target="_blank">export SVG</a>
     <a class="export" href="/api/export/results?run=${encodeURIComponent(run)}" target="_blank">export CSV</a>
     <a class="export" href="/api/export/records?run=${encodeURIComponent(run)}&span_match=${span}" target="_blank">export records (scrubbed)</a>`;
  const [res, costs, scoreEx, scoreOv, flow, dep] = await Promise.all([
    api("/api/run/results", { run }),
    api("/api/run/costs", { run }),
    api("/api/run/score", { run, span_match: "exact" }),
    api("/api/run/score", { run, span_match: "overlap" }),
    api("/api/run/flow", { run, span_match: span }),
    api("/api/run/dependencies", { run }),
  ]);
  const score = span === "overlap" ? scoreOv : scoreEx;
  let base = null, cmp = null;
  if (S.baseline && S.baseline !== run) {
    try { cmp = await api("/api/run/compare", { a: run, b: S.baseline, span_match: span }); }
    catch (err) { cmp = { error: err.message }; }
    if (cmp && !cmp.error) base = cmp.b;
  }
  $("results-notices").innerHTML =
    (cmp && cmp.rung3_cross_draw ? `<div class="caveat">${esc(cmp.rung3_cross_draw)}</div>` : "") +
    (cmp && cmp.error ? `<div class="banner warn">comparison refused: ${esc(cmp.error)}</div>` : "");
  const cv = { ...res.caveats, ...(score.caveats || {}) };
  renderIntro();
  renderHeadline(score, base, flow, cv);
  renderCIChart([{ label: run, score }, base && base.score ?
    { label: S.baseline, score: { available: true, ...base.score } } : null].filter(Boolean));
  renderDependencies(dep, cv);
  renderLayers(scoreEx, scoreOv, cv);
  renderDumbbell(run, base, scoreEx, scoreOv);
  renderFlow(flow, dep);
  renderLadderCurve(res, costs);
  renderCostPanels(costs, cv);
  renderHumanBlock(flow, costs, res, cv);
  renderResultsTable(res, dep);
}

function renderIntro() {
  $("results-intro").innerHTML = `<div class="explainer">
    <b>How to read this page.</b> The run is a LADDER: rung 0 extracts every
    record, and each rung above it only checks, votes on, withdraws or
    escalates those records. Read top to bottom: what shipped, how the rungs
    produced it, the three layers a "result" decomposes into, where the
    records ended up, what it cost, and what is left for a person. Every
    number carries its provenance footer; caveats sit beside the numbers
    they qualify.</div>`;
}

const BUCKET_FILL = { ACCEPT: "var(--z-accept)", BAND: "var(--z-band)",
  REJECT: "var(--z-reject)", none: "var(--hatch-a)" };

const pctOf = (n, total) => total ? `${(100 * n / total).toFixed(1)}%` : "—";

function nodeTitle(n) {
  // fuller card detail on hover: meaning + this run's counts
  const parts = [n.meaning || ""];
  if (n.model) parts.push(`model: ${n.model}`);
  if (n.mode) parts.push(`mode: ${n.mode}`);
  if (n.verdicts && Object.keys(n.verdicts).length)
    parts.push(Object.entries(n.verdicts).map(([k, v]) => `${k} ${v}`).join(" · "));
  if (n.eligible)
    parts.push(`${n.eligible.reject} REJECT, ${n.eligible.correctable} correctable, ${n.eligible.attempted} attempted`);
  if (n.k != null && !n.disabled)
    parts.push(`k=${n.k}, T=${n.temperature}; ${n.changed} changed, ${n.not_resampled} not re-found`);
  if (n.abstained != null) parts.push(`abstained ${n.abstained} · settled ${n.settled ?? 0}`);
  if (n.queue != null) parts.push(`queue ${n.queue} · ${n.human_minutes} min (${n.minutes_source ?? "—"})`);
  if (n.disabled) parts.push("DISABLED — a recorded run state");
  return parts.filter(Boolean).join("\n");
}

/* ONE integrated dataflow diagram (round-3/4 feedback): rungs as node
   columns, records as Sankey-style ribbons in the zone tokens, widths
   proportional to counts. ACCEPT/BAND visibly bypass the r2 node (it sits
   on the REJECT lane only); dashed thin ribbons are structurally possible
   paths this run did NOT take (from flow_map, mode-aware); every ribbon is
   a clickable subset that drills to its records. */
function integratedFlowSvg(dep, sel) {
  const fm = dep.flow_map;
  if (!fm || !fm.buckets.length || !fm.total) return "";
  const nodes = {};
  for (const n of dep.nodes) nodes[n.rung] = n;
  const gate = fm.mode === "gate";
  const total = fm.total;
  const lanes = fm.buckets.filter((b) => b.n > 0);
  const laneArea = 200, gap = 26, top = 84;
  const k = laneArea / total;
  const H = (n) => Math.max(4, n * k);
  const X = { r0: 8, r1: 168, r2: 322, r3: 462, r4: 602, r5: 742, r6: 920, sink: 1056 };
  const NODE_W = 96, W = 1190;
  let y = top;
  for (const l of lanes) { l.y = y; l.h = H(l.n); y += l.h + gap; }
  const shippedTotal = lanes.reduce((a, l) => a + ((l.shipped && l.shipped.n) || 0), 0);
  const personTotal = lanes.reduce((a, l) => a + ((l.person && l.person.n) || 0), 0);
  const height = Math.max(y + 70, top + 250);
  const shipY = top - 6;
  const personY = Math.min(y + 6, height - 60 - H(personTotal));

  const dim = (bucket) => sel && sel !== bucket ? 0.25 : 0.85;
  let g = "";

  // --- node columns (the rung cards, folded into headers) ---
  const nodeBox = (rung, x, y0, h, extraCls) => {
    const n = nodes[rung] || {};
    const cls = n.disabled ? "url(#hatch)" : "var(--panel)";
    return `<g class="flownode"><rect x="${x}" y="${y0}" width="${NODE_W}" height="${h}"
      rx="6" fill="${cls}" stroke="${n.routes ? "var(--warn-ink)" : "var(--line)"}"
      stroke-width="${n.routes ? 2 : 1}"/>
      <title>${esc(`r${rung} ${n.label || ""}\n${nodeTitle(n)}`)}</title></g>`;
  };
  const nodeHead = (rung, x) => {
    const n = nodes[rung] || {};
    const mode = n.mode ? ` [${n.mode}]` : "";
    return `<text x="${x + NODE_W / 2}" y="26" text-anchor="middle" font-size="11"
      font-weight="bold">r${rung} ${esc(n.label || "")}${esc(mode)}</text>
      <text x="${x + NODE_W / 2}" y="38" text-anchor="middle" font-size="8.5"
      class="svgmuted">${esc((n.model || "").split("/").pop() || "")}</text>
      <text x="${x + NODE_W / 2}" y="50" text-anchor="middle" font-size="8"
      class="svgmuted">${esc(headline(rung))}</text>`;
  };
  function headline(rung) {
    const n = nodes[rung] || {};
    if (rung === 0) return `${n.documents ?? "—"} docs → ${n.records ?? "—"} records`;
    if (rung === 1) return n.routes ? "routes (gate)" : "judges, does not route";
    if (rung === 2) return "touches REJECT only";
    if (rung === 3) return n.disabled ? "disabled" : `k=${n.k ?? "—"} resamples`;
    if (rung === 4) return "verdict, not a route";
    if (rung === 5) return "verdicts act here";
    if (rung === 6) return "queue to a person";
    return "";
  }

  const lanesTop = top - 12, lanesBot = y - gap + 12, lanesH = lanesBot - lanesTop;
  g += nodeBox(0, X.r0, lanesTop, lanesH) + nodeHead(0, X.r0);
  g += nodeBox(1, X.r1 - NODE_W / 2, lanesTop, lanesH) + nodeHead(1, X.r1 - NODE_W / 2);
  const rej = lanes.find((l) => l.verdict === "REJECT");
  if (rej)  // r2 sits ON the REJECT lane only — ACCEPT/BAND flow past it
    g += nodeBox(2, X.r2 - NODE_W / 2, rej.y - 14, rej.h + 28) + nodeHead(2, X.r2 - NODE_W / 2);
  else g += nodeHead(2, X.r2 - NODE_W / 2);
  g += nodeBox(3, X.r3 - NODE_W / 2, lanesTop, lanesH) + nodeHead(3, X.r3 - NODE_W / 2);
  g += nodeBox(4, X.r4 - NODE_W / 2, lanesTop, lanesH) + nodeHead(4, X.r4 - NODE_W / 2);
  g += nodeBox(5, X.r5 - NODE_W / 2, lanesTop, lanesH) + nodeHead(5, X.r5 - NODE_W / 2);
  if (personTotal)
    g += nodeBox(6, X.r6 - NODE_W / 2, personY - 14, H(personTotal) + 28) +
      nodeHead(6, X.r6 - NODE_W / 2);

  // --- source ribbon: r0 emits the whole batch ---
  const srcH = H(total);
  const srcY = lanesTop + lanesH / 2 - srcH / 2;
  g += `<g class="ribbon" data-bucket="ALL"><rect x="${X.r0 + NODE_W}" y="${srcY}"
    width="${X.r1 - NODE_W / 2 - X.r0 - NODE_W}" height="${srcH}"
    fill="var(--accent)" opacity="${sel ? 0.3 : 0.6}"/>
    <title>rung 0 extracted ${total} records (100% of the batch)</title></g>
    <text x="${X.r0 + NODE_W + 4}" y="${srcY - 5}" font-size="10">${total} records · 100%</text>`;
  for (const l of lanes)
    g += `<polygon points="${X.r1 - NODE_W / 2},${srcY} ${X.r1 - NODE_W / 2},${srcY + srcH}
      ${X.r1 + NODE_W / 2},${l.y + l.h} ${X.r1 + NODE_W / 2},${l.y}"
      fill="var(--accent)" opacity="0.14"/>`;

  // --- bucket ribbons through r2..r5 ---
  for (const l of lanes) {
    const fill = BUCKET_FILL[l.verdict] || "var(--hatch-a)";
    const x0 = X.r1 + NODE_W / 2;
    const xEnd = l.exit_at_r1 ? X.r2 - NODE_W / 2 : X.r5 - NODE_W / 2;
    g += `<g class="ribbon" data-bucket="${l.verdict}">
      <rect x="${x0}" y="${l.y}" width="${xEnd - x0}" height="${l.h}"
      fill="${fill}" opacity="${dim(l.verdict)}"/>
      <title>${l.verdict}: ${l.n} of ${total} (${pctOf(l.n, total)}) — click to follow this subset</title></g>`;
    g += `<text x="${x0 + 6}" y="${l.y - 5}" font-size="10" font-weight="bold">
      ${l.verdict} ${l.n} · ${pctOf(l.n, total)}</text>`;
    if (l.exit_at_r1) {
      g += `<polygon points="${xEnd},${l.y} ${xEnd + 26},${l.y + l.h / 2}
        ${xEnd},${l.y + l.h}" fill="${fill}" opacity="${dim(l.verdict)}"/>
        <text x="${xEnd + 30}" y="${l.y + l.h / 2 + 3}" font-size="9">
        left the stack at r1 (gate) — ${l.exit_at_r1.n} · ${pctOf(l.exit_at_r1.n, total)}</text>`;
      continue;
    }
    // per-lane annotations at the nodes (what happened to THIS subset there)
    const ann = (x, text) => {
      const inside = l.h >= 15;
      return `<text x="${x}" y="${inside ? l.y + l.h / 2 + 3 : l.y + l.h + 10}"
        font-size="8.5" text-anchor="middle"
        ${inside ? 'fill="#fff"' : 'class="svgmuted"'}>${text}</text>`;
    };
    if (l.through_r2 && l.r2)
      g += ann(X.r2, `${l.r2.reject ?? l.n} offered · ${l.r2.correctable} correctable · ${l.r2.attempted} attempted`);
    if (l.r3_changed) g += ann(X.r3, `changed ${l.r3_changed}`);
    const r4 = l.r4 || {};
    if ((r4.pass || 0) + (r4.fail || 0) + (r4.parse_failed || 0) > 0)
      g += ann(X.r4, `pass ${r4.pass || 0} · fail ${r4.fail || 0}${r4.parse_failed ? ` · unparsed ${r4.parse_failed}` : ""}`);
    // rescue path at r2 (possible or actual)
    if (l.through_r2 && l.r2 && l.r2.rescue) {
      const r = l.r2.rescue;
      const dash = r.kind === "possible" ? 'stroke-dasharray="5 4"' : "";
      g += `<path d="M ${X.r2} ${l.y - 2} C ${X.r2 + 30} ${l.y - 30},
        ${X.r3 - 60} ${l.y - 30}, ${X.r3 - NODE_W / 2} ${l.y + 2}"
        fill="none" stroke="${fill}" stroke-width="2" ${dash} opacity="0.9"/>
        <text x="${(X.r2 + X.r3) / 2}" y="${l.y - 26}" font-size="8.5"
        text-anchor="middle" class="svgmuted">${r.n} ${esc(r.label)}</text>`;
    }
    // --- r5 branches: actual = ribbon polygon, possible = thin dashed ---
    const xb = X.r5 + NODE_W / 2 - NODE_W;  // branch start (r5 node right edge)
    const x5 = X.r5 + NODE_W / 2;
    const branch = (legName, leg, sinkYpos, sinkOff, sinkLabel) => {
      if (!leg) return "";
      if (leg.kind === "possible")
        return `<path d="M ${x5 - NODE_W} ${l.y + l.h / 2} C ${x5 + 40} ${l.y + l.h / 2},
          ${X.sink - 80} ${sinkYpos + 8}, ${X.sink} ${sinkYpos + 8}"
          fill="none" stroke="${fill}" stroke-width="1.5" stroke-dasharray="4 4"
          opacity="0.7"/>
          <text x="${(x5 + X.sink) / 2}" y="${(l.y + l.h / 2 + sinkYpos) / 2}"
          font-size="8.5" class="svgmuted">0 — ${esc(leg.label || legName)} (option)</text>`;
      const h = Math.max(3, leg.n * k);
      const yOff = legName === "shipped" ? 0 : l.h - h;
      const xTo = legName === "shipped" ? X.sink : X.r6 - NODE_W / 2;
      return `<g class="ribbon" data-bucket="${l.verdict}">
        <polygon points="${x5},${l.y + yOff} ${x5},${l.y + yOff + h}
        ${xTo},${sinkYpos + sinkOff + h} ${xTo},${sinkYpos + sinkOff}"
        fill="${fill}" opacity="${dim(l.verdict) * 0.7}"/>
        <title>${l.verdict} → ${sinkLabel}: ${leg.n} (${pctOf(leg.n, l.n)} of ${l.verdict}, ${pctOf(leg.n, total)} of batch)</title></g>` +
        (h >= 10 ? `<text x="${x5 + 6}" y="${l.y + yOff + h / 2 + 3}" font-size="8.5">
          ${legName} ${leg.n} · ${pctOf(leg.n, l.n)}</text>` : "");
    };
    const shipOff = lanes.slice(0, lanes.indexOf(l))
      .reduce((a, x) => a + ((x.shipped && x.shipped.kind === "actual" && x.shipped.n) || 0), 0) * k;
    const qOff = lanes.slice(0, lanes.indexOf(l))
      .reduce((a, x) => a + ((x.person && x.person.kind === "actual" && x.person.n) || 0), 0) * k;
    g += branch("shipped", l.shipped, shipY, shipOff, "SHIPPED");
    g += branch("person", l.person, personY, qOff, "TO A PERSON");
  }

  // person bundle continues through the r6 node to the sink
  if (personTotal) {
    const h = H(personTotal);
    g += `<rect x="${X.r6 + NODE_W / 2}" y="${personY}" width="${X.sink - X.r6 - NODE_W / 2}"
      height="${h}" fill="var(--z-escalate)" opacity="0.55"/>`;
  }
  // --- sinks ---
  if (shippedTotal || lanes.some((l) => l.shipped))
    g += `<rect x="${X.sink}" y="${shipY}" width="120" height="${Math.max(H(shippedTotal), 10)}"
      fill="var(--z-verified)"/><text x="${X.sink}" y="${shipY - 6}" font-size="10"
      font-weight="bold">SHIPPED ${shippedTotal} · ${pctOf(shippedTotal, total)}</text>`;
  if (personTotal || lanes.some((l) => l.person))
    g += `<rect x="${X.sink}" y="${personY}" width="120" height="${Math.max(H(personTotal), 10)}"
      fill="var(--z-escalate)"/><text x="${X.sink}" y="${personY - 6}" font-size="10"
      font-weight="bold">TO A PERSON ${personTotal} of ${total} · ${pctOf(personTotal, total)}</text>`;

  return `<div class="depflow-scroll">${svgOpen(W, height)}${g}</svg></div>`;
}

function subsetDetail(dep, bucket) {
  // the clicked subset's own sub-flow: counts AND % at every split, with
  // read-only drill-through to Traceability filtered to those records
  const fm = dep.flow_map;
  const b = fm.buckets.find((x) => x.verdict === bucket);
  if (!b) return "";
  const run = S.resultsRun;
  const trace = (label, params) =>
    `<a href="#" class="trace-link" data-params='${JSON.stringify(params)}'>${label}</a>`;
  const rows = [];
  rows.push(`<b>${esc(bucket)}</b>: ${b.n} of ${fm.total} records
    (${pctOf(b.n, fm.total)} of the batch) —
    ${trace("open in Traceability", { verdict: bucket })}`);
  if (b.through_r2 && b.r2)
    rows.push(`r2: ${b.r2.reject} offered · ${b.r2.correctable} correctable ·
      ${b.r2.attempted} attempted · ${b.r2.rescued} rescued`);
  if (b.r3_changed) rows.push(`r3 changed ${b.r3_changed} · ${pctOf(b.r3_changed, b.n)} of subset`);
  const r4 = b.r4 || {};
  rows.push(`r4: pass ${r4.pass || 0} (${pctOf(r4.pass || 0, b.n)}) ·
    fail ${r4.fail || 0} (${pctOf(r4.fail || 0, b.n)})${r4.parse_failed ?
    ` · unparsed ${r4.parse_failed}` : ""}`);
  if (b.exit_at_r1)
    rows.push(`left the stack at r1 (gate): ${b.exit_at_r1.n}`);
  if (b.shipped)
    rows.push(`→ shipped: ${b.shipped.n} (${pctOf(b.shipped.n, b.n)} of subset,
      ${pctOf(b.shipped.n, fm.total)} of batch)${b.shipped.kind === "possible" ?
      " — possible, untaken" : " — " +
      trace("records", { verdict: bucket, disposition: "shipped" })}`);
  if (b.person)
    rows.push(`→ to a person: ${b.person.n} (${pctOf(b.person.n, b.n)} of subset,
      ${pctOf(b.person.n, fm.total)} of batch)${b.person.kind === "possible" ?
      " — possible, untaken" : " — " +
      trace("records", { verdict: bucket, disposition: "escalated" })}`);
  return `<div class="explainer subset">${rows.join("<br>")}
    <span class="muted">(click the ribbon again to deselect)</span></div>`;
}

function renderDependencies(dep, cv, sel) {
  const el = $("dep-diagram");
  let banner = "";
  if (dep.run_kind === "ablate")
    banner = `<div class="banner warn">ABLATE run — only rung(s)
      ${esc(dep.rungs_present.join(", "))} ran over a saved input; the diagram
      shows the full stack for orientation, absent rungs hatched.</div>`;
  el.innerHTML = `<div class="chart">${banner}
    ${integratedFlowSvg(dep, sel)}
    ${sel ? subsetDetail(dep, sel) : ""}
    <div class="muted">One batch, left to right: ribbons are records, widths
    proportional to counts, colors are rung 1's verdict buckets. The r2 node
    sits on the REJECT ribbon only — ACCEPT and BAND bypass it by
    construction. Dashed thin paths are structurally possible routes this
    run did not take (labeled 0). Click a ribbon to follow that subset and
    drill to its records; hover a node for the rung's meaning and counts.
    Section 4 shows the same records by disposition stage and correctness.</div>
    ${caveatChips(dep.caveats && dep.caveats.r1_gate ?
      { r1_gate: dep.caveats.r1_gate } : null)}
    ${caveatChips(pick(cv, ["rung3_samples", "judge_2b"]))}
    ${provFooter(dep.provenance)}</div>`;
  el.querySelectorAll(".ribbon").forEach((r) => {
    r.style.cursor = "pointer";
    r.onclick = () => {
      const b = r.dataset.bucket;
      renderDependencies(dep, cv, sel === b || b === "ALL" ? null : b);
    };
  });
  el.querySelectorAll(".trace-link").forEach((a) => {
    a.onclick = (ev) => {
      ev.preventDefault();
      S.traceRun = S.resultsRun;
      S.traceFilter = JSON.parse(a.dataset.params);
      const t = S.tabs.find((x) => x.id === "trace");
      $("trace-run").value = S.traceRun;
      showTab(t);
    };
  });
}

function renderHeadline(score, base, flow, cv) {
  const el = $("results-headline");
  if (!score.available) {
    el.innerHTML = `<div class="banner warn">${esc(score.reason)}</div>` +
      provFooter(score.provenance);
    return;
  }
  const s = score.score, ci = score.ci;
  const dl = (x) => x === null ? "—" : Number(x).toFixed(3);
  let deltas = "";
  if (base && base.score) {
    const d = s.f1 - base.score.score.f1;
    deltas = `<div class="card"><div class="big">${d >= 0 ? "+" : ""}${d.toFixed(3)}</div>
      <div class="muted">Δ F1 vs baseline (both intervals shown below)</div></div>`;
  }
  // one plain-language line, composed entirely from the run's numbers
  const routed = flow ? flow.escalated.n : null;
  const reading =
    `Of ${s.n_gold} scorable gold mentions, ${s.correct} shipped with the ` +
    `right code (${esc(s.span_match)} spans) — F1 ${dl(s.f1)}, and the ` +
    `interval [${dl(ci.f1.lo)}–${dl(ci.f1.hi)}] is the claim` +
    (routed !== null ? `; ${routed} of ${flow.n_records} records ` +
      `(${pctOf(routed, flow.n_records)}) were routed to a person instead ` +
      `of shipped.` : ".");
  el.innerHTML = `<div class="explainer">${reading}</div>
    <div class="cards">
    <div class="card"><div class="big">${dl(s.f1)}</div>
      <div class="muted">shipped F1 (${esc(s.span_match)})
      [${dl(ci.f1.lo)}–${dl(ci.f1.hi)}]</div></div>
    <div class="card"><div class="big">${s.correct} / ${s.n_gold}</div>
      <div class="muted">shipped correct / scorable gold (excluded ${s.excluded})</div></div>
    <div class="card"><div class="big">${routed ?? "—"}${routed !== null ?
      ` <span class="muted" style="font-size:1rem">of ${flow.n_records} ·
      ${pctOf(routed, flow.n_records)}</span>` : ""}</div>
      <div class="muted">records routed to a person (rung 6 — the count is
      the headline cost)</div></div>
    ${deltas}</div>` +
    caveatChips(pick(cv, ["spent_test"])) +
    provFooter(score.provenance);
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

// one horizontal composition bar in a layer's OWN outcome vocabulary,
// exact and overlap side by side (from score_run / checks — no new accounting)
function compBar(rowsSpec, items) {
  const w = 320, rh = 22;
  let g = "";
  rowsSpec.forEach(([label, counts], ri) => {
    const total = items.reduce((a, [k]) => a + (counts[k] || 0), 0) || 1;
    let x = 62; const y = 4 + ri * (rh + 12);
    g += `<text x="0" y="${y + 14}" font-size="10">${label}</text>`;
    for (const [key, color] of items) {
      const n = counts[key] || 0;
      if (!n) continue;
      const bw = (n / total) * (w - 66);
      g += `<rect x="${x}" y="${y}" width="${bw}" height="${rh}" fill="${color}">
        <title>${key}: ${n} (${pctOf(n, total)})</title></rect>` +
        (bw > 26 ? `<text x="${x + bw / 2}" y="${y + 15}" text-anchor="middle"
          font-size="9" fill="#fff">${n}</text>` : "");
      x += bw;
    }
  });
  const legend = items.map(([k, c]) =>
    `<span style="color:${c}">■</span> ${k}`).join(" · ");
  const h = rowsSpec.length * (rh + 12) + 6;
  return `${svgOpen(w, h)}${g}</svg><div class="muted" style="font-size:.7rem">${legend}</div>`;
}

function renderLayers(ex, ov, cv) {
  const el = $("layers-block");
  if (!ex.available) {
    el.innerHTML = SPAN_EXPLAINER +
      `<div class="banner warn">${esc(ex.reason)}</div>` +
      provFooter(ex.provenance);
    return;
  }
  const dl = (x) => Number(x).toFixed(3);
  const ciTxt = (c) => `[${dl(c.lo)}–${dl(c.hi)}]`;
  const cx = ex.composition, co = ov.composition;
  const twoNum = (label, vEx, ciEx, vOv, ciOv, nEx, nOv) => `
    <table class="layer-nums"><tr><th></th><th>exact</th><th>overlap</th></tr>
    <tr><td class="l">${label}</td>
      <td>${dl(vEx)} <span class="muted">${ciEx ? ciTxt(ciEx) : ""}</span></td>
      <td>${dl(vOv)} <span class="muted">${ciOv ? ciTxt(ciOv) : ""}</span></td></tr>
    ${nEx != null ? `<tr><td class="l muted">over</td>
      <td class="muted">${nEx}</td><td class="muted">${nOv}</td></tr>` : ""}
    </table>`;
  const lc = ex.label_check || { verified: 0, flagged: 0, unchecked: 0 };
  el.innerHTML = SPAN_EXPLAINER + `<div class="cards layers">
    <div class="card layer">
      <h4>Correct annotation <span class="muted">(detection layer)</span></h4>
      <div class="explainer">Was the mention found at all? Codes are ignored
      here — only whether a predicted span pairs with a gold mention.</div>
      ${twoNum("detection F1",
        ex.score.detection.f1, ex.ci.detection_f1,
        ov.score.detection.f1, ov.ci.detection_f1,
        `${ex.score.detection.n_matched} matched`,
        `${ov.score.detection.n_matched} matched`)}
      ${compBar([["exact", cx.detection], ["overlap", co.detection]], [
        ["matched", "var(--o-correct)"],
        ["missed", "var(--o-abstained)"],
        ["spurious", "var(--o-incorrect)"]])}
    </div>
    <div class="card layer">
      <h4>Code extraction <span class="muted">(coding layer)</span></h4>
      <div class="explainer">Given a found mention, is the SNOMED code
      right? Conditional on the match, so recall = detection × coding by
      construction.</div>
      ${twoNum("coding accuracy",
        ex.score.coding.accuracy, ex.ci.coding_accuracy,
        ov.score.coding.accuracy, ov.ci.coding_accuracy,
        `${ex.score.coding.n} matched`, `${ov.score.coding.n} matched`)}
      ${compBar([["exact", cx.coding], ["overlap", co.coding]], [
        ["correct", "var(--o-correct)"],
        ["outdated", "var(--o-outdated)"],
        ["abstained", "var(--o-abstained)"],
        ["incorrect", "var(--o-incorrect)"],
        ["modernised", "var(--o-modernised)"]])}
      <div class="muted" style="font-size:.72rem">report order; outdated and
        modernised are never folded into correct</div>
    </div>
    <div class="card layer">
      <h4>Vocabulary label <span class="muted">(rung 1 label_check — a flag,
        never a rejection)</span></h4>
      <div class="explainer">Does the model's OWN label agree with the
      vocabulary's terms for the code it chose? Catches a real code with the
      wrong meaning. Span-independent.</div>
      <table class="layer-nums">
        <tr><td class="l">label agrees</td><td>${lc.verified}</td></tr>
        <tr><td class="l">label flagged</td><td>${lc.flagged}</td></tr>
        <tr><td class="l">unchecked <span class="muted">(no code or no
          label)</span></td><td>${lc.unchecked}</td></tr>
      </table>
      ${compBar([["records", cx.label]], [
        ["verified", "var(--o-correct)"],
        ["flagged", "var(--o-incorrect)"],
        ["unchecked", "var(--hatch-a)"]])}
    </div></div>` +
    caveatChips(pick(cv, ["outdated_separate"])) +
    provFooter(ex.provenance);
}

async function renderDumbbell(run, base, scoreEx, scoreOv) {
  const el = $("dumbbell");
  const entries = [];
  if (scoreEx && scoreEx.available) entries.push({ label: `${run} · exact`, s: scoreEx });
  if (scoreOv && scoreOv.available) entries.push({ label: `${run} · overlap`, s: scoreOv });
  if (base) {
    for (const span of ["exact", "overlap"]) {
      const s = await api("/api/run/score", { run: S.baseline, span_match: span });
      if (s.available) entries.push({ label: `${S.baseline} · ${span}`, s });
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
  // the boundary-disagreement reading, composed from the run's own numbers
  let gapLine = "";
  if (scoreEx && scoreEx.available && scoreOv && scoreOv.available) {
    const dEx = scoreEx.score.detection.f1, dOv = scoreOv.score.detection.f1;
    gapLine = `<div class="explainer">detection ${dEx.toFixed(3)} exact vs
      ${dOv.toFixed(3)} overlap: the same mentions are being found — the gap
      between the two is boundary disagreement over where a mention starts
      and ends, not missed mentions.</div>`;
  }
  el.innerHTML = `<div class="chart">
    <div><b>Detection vs coding</b> <span class="muted">(V3 — the residual
    gap is span boundaries)</span></div>
    ${svgOpen(w, h)}${g}</svg>
    <div class="muted"><span style="color:var(--accent)">●</span> detection F1
    · <span style="color:var(--o-correct)">●</span> coding accuracy on matched
    spans — the oracle ceiling (dev only) moves coding, not detection</div>
    ${gapLine}${provFooter(entries[0].s.provenance)}</div>`;
}

function renderFlow(flow, dep) {
  const el = $("flow-chart");
  const v = flow.rung1_verdicts || {};
  const total = flow.n_records || 1;
  const r1mode = dep ? dep.r1_mode : "observe";
  const w = 760, h = 290, colw = 160, x1 = 10, x2 = 265, x3 = 520;
  const scale = (n) => (n / total) * 180;
  function col(x, items, title, subtitle) {
    let g = `<text x="${x}" y="16" font-size="11" font-weight="bold">${title}</text>
      <text x="${x}" y="30" font-size="9" class="svgmuted">${subtitle}</text>`;
    let y = 42;
    // side labels for thin bars collide when consecutive bars are thin —
    // track the last label baseline and push each next one below it
    let lastSideLabelY = 30;
    for (const it of items) {
      const bh = Math.max(2, scale(it.n));
      g += `<rect x="${x}" y="${y}" width="${colw}" height="${bh}"
        fill="${it.fill}" ${it.hatch ? 'fill="url(#hatch)"' : ""}>
        <title>${it.label}: ${it.n}${it.tip ? " — " + it.tip : ""}</title></rect>`;
      if (bh > 12) {
        g += `<text x="${x + 6}" y="${y + bh / 2 + 4}" font-size="10"
          fill="#fff">${it.label} ${it.n}</text>`;
      } else {
        const ly = Math.max(y + bh / 2 + 4, lastSideLabelY + 11);
        lastSideLabelY = ly;
        g += `<line x1="${x + colw}" y1="${y + bh / 2}" x2="${x + colw + 3}"
          y2="${ly - 3}" stroke="var(--hatch-a)" stroke-width="1"/>
          <text x="${x + colw + 5}" y="${ly}" font-size="9">${it.label} ${it.n}</text>`;
      }
      y += bh + 6;
      lastSideLabelY = Math.max(lastSideLabelY, 30);
    }
    return g;
  }
  const scored = flow.scored;
  // Stage 1 — extraction + judgement: rung 0 made the records, rung 1
  // judged them (observe mode: a verdict, not a route).
  let g = col(x1, [
    { label: "ACCEPT", n: v.ACCEPT || 0, fill: "var(--z-accept)",
      tip: "vocabulary uses these very words" },
    { label: "BAND", n: v.BAND || 0, fill: "var(--z-band)",
      tip: "plausible, unverifiable by code alone" },
    { label: "REJECT", n: v.REJECT || 0, fill: "var(--z-reject)",
      tip: "provably wrong" },
  ], `1 · extracted &amp; judged (${total})`,
     `rung 0 made the records; rung 1 ${r1mode === "gate" ?
       "ROUTED them (gate mode)" : "judged them (verdict only, no routing)"}`);
  // Stage 2 — disposition: rung 5 withdraws, rung 6 routes the residue.
  g += col(x2, [
    { label: "shipped", n: flow.shipped.n, fill: "var(--z-verified)",
      tip: "rung 5 kept it — this is the system's answer" },
    { label: "escalated", n: flow.escalated.n, fill: "var(--z-escalate)",
      tip: "rung 5 withdrew it; rung 6 routed it to a person" },
    { label: "open", n: flow.open.n, fill: "var(--hatch-a)",
      tip: "no disposition recorded" },
  ], "2 · disposition",
     "rung 5 withdraws (ABSTAIN); rung 6 routes the residue (ESCALATE)");
  // Stage 3 — scored against gold (no rung: the evaluation, outside the run).
  g += col(x3, scored ? [
    { label: "shipped correct", n: flow.shipped.correct, fill: "var(--o-correct)" },
    { label: "shipped wrong", n: flow.shipped.wrong, fill: "var(--o-incorrect)" },
    { label: "withheld-correct", n: flow.escalated.withheld_correct, fill: "var(--o-abstained)",
      tip: "routed to a person although the withheld answer was already right — rung 5's price" },
    { label: "unlocatable", n: flow.escalated.unlocatable, fill: "var(--hatch-a)",
      tip: "(-1,-1) spans — a span-keyed desk cannot review these" },
    { label: "escalated other", n: flow.escalated.n - flow.escalated.withheld_correct - flow.escalated.unlocatable, fill: "var(--z-escalate)" },
  ] : [{ label: "needs corpus to split", n: total, fill: "var(--hatch-a)", hatch: true }],
    "3 · scored against gold",
    "not a rung — the evaluation layer, exclusions applied");
  el.innerHTML = `<div class="chart">${svgOpen(w, h)}${g}</svg>
    <div class="muted">abstention's bill is a count: ${flow.escalated.n} of
    ${total} routed to a person${scored ? `; ${flow.escalated.withheld_correct}
    withheld answers were already correct` : ""}</div>
    ${provFooter(flow.provenance)}</div>`;
}

function renderResultsTable(res, dep) {
  const el = $("results-table");
  const dens = {};
  for (const d of (dep && dep.denominators) || []) dens[d.rung] = d;
  const byRung = {};
  for (const n of (dep && dep.nodes) || []) byRung[n.rung] = n;
  // shared metrics only — rung-specific metrics (verdict counts, reject %,
  // eligible counts, queue size) live on that rung's own line, not as a
  // column of blanks for every other rung
  const cols = ["rung", "layer", "n_records", "coverage", "f1_sct_strict",
    "corrupted", "err_per_100", "tokens_per_record"];
  const names = { rung: "rung", layer: "layer", n_records: "records",
    coverage: "coverage", f1_sct_strict: "answered acc.",
    corrupted: "errors", err_per_100: "err/100",
    tokens_per_record: "tokens/rec" };
  const denomCell = (rung) => {
    const d = dens[Number(rung)];
    if (!d || !d.denominator)
      return '<td class="l nonvalue" title="no ledger rows">·</td>';
    const src = d.source_rung === null || d.source_rung === undefined
      ? "" : ` ← r${d.source_rung}`;
    return `<td class="l" title="${esc(d.source_label ?? "")}">
      ${esc(d.denominator)}${esc(src)}</td>`;
  };
  const ownCell = (rung, row) => {
    // the metrics that exist for exactly this rung, from its node + csv row
    const n = byRung[Number(rung)] || {};
    const bits = [];
    if (Number(rung) === 1) {
      if (n.verdicts) bits.push(Object.entries(n.verdicts)
        .map(([k, v]) => `${k} ${v}`).join(" · "));
      if (row.r1_reject_pct != null) bits.push(`reject ${row.r1_reject_pct}%`);
      if (row.r1_mode) bits.push(`mode ${row.r1_mode}`);
    }
    if (Number(rung) === 2 && n.eligible)
      bits.push(`${n.eligible.reject} REJECT, ${n.eligible.correctable}
        correctable, ${n.eligible.attempted} attempted`);
    if (Number(rung) === 3 && !n.disabled && n.k != null)
      bits.push(`k=${n.k} · ${n.changed} changed · ${n.not_resampled} not re-found`);
    if (Number(rung) === 3 && n.disabled) bits.push("DISABLED (recorded)");
    if (Number(rung) === 4 && n.verdicts)
      bits.push(Object.entries(n.verdicts).map(([k, v]) => `${k} ${v}`).join(" · "));
    if (Number(rung) === 5 && n.abstained != null)
      bits.push(`abstained ${n.abstained} · settled ${n.settled ?? 0}`);
    if (Number(rung) === 6 && n.queue != null)
      bits.push(`queue ${n.queue}` +
        (row.reviews_per_100 != null ? ` · reviews/100 ${row.reviews_per_100}` : ""));
    return `<td class="l muted">${bits.join("; ") || ""}</td>`;
  };
  el.innerHTML =
    // stack semantics stated with the table (computed run kind, never baked in)
    `<div class="stack-caption">${esc((dep && dep.stack_semantics) || "")}</div>` +
    `<table><tr>${cols.map((c) => `<th${c === "layer" ? ' class="l"' : ""}>${names[c]}</th>`).join("")}
     <th class="l">this rung's own metrics</th>
     <th class="l" title="the denominator the ledger names, and the rung whose output it is">denominator ← source</th></tr>` +
    res.rows.map((r) => `<tr>` + cols.map((c) => {
      const v = r[c];
      if (v === null || v === undefined)
        return '<td class="nonvalue" title="no measurement">·</td>';
      if (c === "layer") return `<td class="l">${esc(v)}</td>`;
      return `<td>${esc(v)}</td>`;
    }).join("") + ownCell(r.rung, r) + denomCell(r.rung) + `</tr>`).join("") +
    `</table>` +
    `<div class="muted">shared metrics only — each rung's specific numbers sit
     on its own line; counts drawn over each rung's snapshot (the ledger's
     denominator), never the run total; · = no measurement; hover a
     denominator for what feeds it</div>` +
    provFooter(res.provenance);
}

function renderCostPanels(costs, cv) {
  const el = $("cost-panels");
  const rungs = Object.keys(costs.denominators || {});
  const panel = (title, rows) =>
    `<div class="card" style="min-width:260px"><b>${title}</b><table><tr>
     <th>rung</th>${rungs.map((r) => `<th>${r}</th>`).join("")}</tr>` +
    rows.map(([label, get, d]) =>
      `<tr><td class="l">${label}</td>` + rungs.map((r) => cell(get(r), d)).join("") +
      `</tr>`).join("") + `</table></div>`;
  const t = costs.panels.tokens, l = costs.panels.latency, rv = costs.panels.reviews;
  // routed-to-a-person is a rung-6 fact, not a per-rung column of zeros
  const routedRung = rungs.find((r) => rv[r] && rv[r].routed > 0);
  const rr = routedRung ? rv[routedRung] : null;
  const nAll = Object.values(costs.denominators || {})
    .reduce((a, d) => Math.max(a, d.rows || 0), 0);
  const reviewsCard = `<div class="card" style="min-width:260px">
    <b>routed to a person</b>
    <div class="big">${rr ? rr.routed : 0}${rr && nAll ?
      ` <span class="muted" style="font-size:1rem">of ${nAll} ·
      ${pctOf(rr.routed, nAll)}</span>` : ""}</div>
    <div class="muted">${rr ? `${pctOf(rr.routed, nAll)} of the batch, at
      rung ${routedRung} only; ${rr.human_minutes} minutes at the declared
      rate, never measured` :
      "no records routed in this run"}</div></div>`;
  // usd: all zeros for local models — one line, not a table (still three
  // separate measures; usd stays carried in exports)
  const usdVals = Object.values(costs.usd || {});
  const usdAllZero = usdVals.every((v) => !v);
  const usdBlock = usdAllZero
    ? `<div class="muted">usd 0.00 across every rung — local models; carried
       in exports alongside the three measures, never summed into them</div>`
    : `<div class="cards">${panel("usd (carried alongside, never fused)",
        [["usd", (r) => costs.usd[r], 4]])}</div>`;
  const failures = Object.entries(costs.failure_labels || {});
  el.innerHTML = `<div class="cards">` +
    panel("tokens", [
      ["tokens/record", (r) => t[r] && t[r].tokens_per_record, 1],
      ["api calls", (r) => t[r] && t[r].api_calls, 0]]) +
    panel("latency", [["p95 s/call", (r) => l[r] && l[r].p95_s, 2]]) +
    reviewsCard +
    `</div>` + usdBlock +
    (failures.length ? `<h4>failure labels <span class="muted">most specific
      first: timed_out &gt; truncated &gt; json_decode — filed under cost, not
      accuracy</span></h4><table><tr><th>rung</th><th>timed_out</th>
      <th>truncated</th><th>json_decode</th></tr>` +
      failures.map(([r, f]) => `<tr><td>${r}</td><td>${f.timed_out}</td>
        <td>${f.truncated}</td><td>${f.json_decode}</td></tr>`).join("") +
      `</table>` : `<div class="muted">failure labels: none recorded
      (timed_out / truncated / json_decode all zero)</div>`) +
    ((costs.non_values || []).length ?
      `<div class="banner warn">could_not_run (hatched, never a color): ` +
      costs.non_values.map((n) => `rung ${n.rung} × ${n.count} (${esc(n.reason)})`).join("; ") +
      `</div>` : "") +
    caveatChips(pick(cv, ["minutes_declared"])) + provFooter(costs.provenance);
}

function renderHumanBlock(flow, costs, res, cv) {
  const el = $("human-block");
  const scored = flow.scored;
  const q = flow.escalated;
  const r6row = (res.rows || []).find((r) => String(r.rung) === "6");
  el.innerHTML = `<div class="cards">
    <div class="card"><div class="big">${q.n}
      <span class="muted" style="font-size:1rem">of ${flow.n_records} ·
      ${pctOf(q.n, flow.n_records)}</span></div>
      <div class="muted">records in the rung-6 queue — the COUNT is the
      headline cost${r6row && r6row.reviews_per_100 != null ?
        ` (${r6row.reviews_per_100} per 100 cases)` : ""}</div></div>
    <div class="card"><div class="big">${scored ? q.withheld_correct : "—"}</div>
      <div class="muted">withheld answers that were already correct — what
      rung 5 pays for its shipped accuracy${scored ? "" :
        " (needs the corpus to score)"}</div></div>
    <div class="card"><div class="big">${q.unlocatable}</div>
      <div class="muted">unlocatable (-1,-1) records a span-keyed desk cannot
      review — they stay escalated</div></div>
    </div>` +
    caveatChips(pick(cv, ["minutes_declared", "oracle_ceiling", "spent_test"])) +
    provFooter(flow.provenance);
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

/* ================= Live run — one document, the real rungs ================= */

const LIVE_EXAMPLE =
  "Started the tablets three weeks ago for my knee. Since then constant " +
  "nausea most mornings and a pounding headache by the afternoon, but so far " +
  "no stomach pain, which is what I was warned about.";

const RUNG_NAMES = { 0: "bare LLM", 1: "deterministic", 2: "self-correction",
  3: "voting", 4: "LLM judge", 5: "abstention", 6: "human loop" };

function wireLive() {
  $("live-source").onchange = () => {
    const corpus = $("live-source").value === "corpus";
    $("live-split-wrap").hidden = !corpus;
    $("live-doc-wrap").hidden = !corpus;
    $("live-text").hidden = corpus;
    if (corpus) liveFillDocs();
  };
  $("live-split").onchange = liveFillDocs;
  $("live-run").onclick = liveStart;
  $("live-through").onchange = liveDials;
  if (!$("live-text").value) $("live-text").value = LIVE_EXAMPLE;
  // ← → step the rung rail while the live result is on screen
  document.addEventListener("keydown", (e) => {
    if (S.tab !== "live" || !S.live.result) return;
    if (/^(TEXTAREA|INPUT|SELECT)$/.test(e.target.tagName)) return;
    if (e.key === "ArrowLeft") { liveStep(-1); e.preventDefault(); }
    if (e.key === "ArrowRight") { liveStep(1); e.preventDefault(); }
  });
}

async function renderLive() {
  if (S.live.options) return;
  try {
    const o = await api("/api/live/options");
    S.live.options = o;
    const th = $("live-through");
    th.innerHTML = o.rung_order.map((n) =>
      `<option value="${n}" ${n === 1 ? "selected" : ""}>rung ${n} — ${RUNG_NAMES[n] || ""}</option>`).join("");
    const sp = $("live-split");
    sp.innerHTML = o.splits_offered.map((s) => `<option value="${s}">${s}</option>`).join("");
    if (!o.corpus_available) {
      $("live-source").querySelector('[value="corpus"]').disabled = true;
      $("live-source").title = "corpus unavailable on this machine";
    }
    if (!o.registry_available)
      $("live-status").textContent = "no SNOMED index on this machine — rung 0's S2 pick and rung 1 will refuse";
    liveDials();
  } catch (e) {
    $("live-result").innerHTML = `<div class="banner warn">${esc(e.message)}</div>`;
  }
}

function liveDials() {
  const o = S.live.options;
  if (!o) return;
  const through = Number($("live-through").value);
  const run = o.rung_order.slice(0, o.rung_order.indexOf(through) + 1);
  const bits = run.map((n) => {
    const c = o.rungs[String(n)] || {};
    let note = "";
    if (n === 0) note = `step ${c.rung0_step ?? "bare"}, retrieval ${c.rung0_retrieval ?? "—"} → 1 find + 1 pick call (${o.models.extractor})`;
    if (n === 1) note = `mode ${c.mode ?? "observe"} — free, no model`;
    if (n === 2) note = `fires only on a rung-1 REJECT with a statable fact — one call per such record`;
    if (n === 3) note = c.enabled === false ? "DISABLED in the manifest (a recorded state)"
      : `k=${c.k ?? "?"} samples at temperature ${c.temperature ?? "?"} — ${c.k ?? "k"} more extractions of the whole text`;
    if (n === 4) note = `judge ${o.models.judge}, menu ${c.menu ?? "off"} — one call per record`;
    if (n === 5) note = `abstains on ${(c.abstain_zones || ["BAND"]).join("/")}${c.abstain_on_reject === false ? "" : " and REJECT"} — free`;
    if (n === 6) note = `${c.mode ?? "simulated"} at ${c.minutes_per_record ?? "?"} min/record — a count, priced at the declared rate`;
    return `<div><b>r${n}</b> ${esc(RUNG_NAMES[n])}: ${esc(note)}</div>`;
  });
  $("live-dials").innerHTML = bits.join("") +
    `<div>temperature ${esc(o.temperature)} · calls go through .llm_cache, so the
     same text twice is a hit (shown as such) · the extractor is a 20B reasoning
     model: a cold rung-0 call takes tens of seconds to minutes${o.busy ? " · <b>a live run is in progress</b>" : ""}</div>`;
}

async function liveFillDocs() {
  const split = $("live-split").value;
  const sel = $("live-doc");
  sel.innerHTML = `<option>loading…</option>`;
  try {
    const d = await api("/api/corpus/docs", { split });
    sel.innerHTML = (d.docs || []).map((x) =>
      `<option value="${esc(x.doc_id)}">${esc(x.doc_id)} (${x.n_mentions} gold)</option>`).join("")
      || `<option value="">no documents</option>`;
  } catch (e) {
    sel.innerHTML = `<option value="">${esc(e.message)}</option>`;
  }
}

async function liveStart() {
  const body = { through_rung: Number($("live-through").value) };
  if ($("live-source").value === "corpus") body.doc_id = $("live-doc").value;
  else body.text = $("live-text").value;
  $("live-result").innerHTML = "";
  $("live-run").disabled = true;
  $("live-status").textContent = "starting…";
  try {
    const r = await fetch("/api/live/run", { method: "POST",
      headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
    const j = await r.json();
    if (!r.ok) throw new Error(j.detail || r.statusText);
    S.live.job = j;
    livePoll(j.job_id);
  } catch (e) {
    $("live-run").disabled = false;
    $("live-status").textContent = "";
    $("live-result").innerHTML = `<div class="banner warn">refused: ${esc(e.message)}</div>`;
  }
}

function liveProgress(j) {
  const p = j.progress || {};
  const steps = j.order_run.map((n) => {
    const cls = p.rungs_done.includes(n) ? "done" : (p.rung_running === n ? "running" : "");
    const calls = p.calls && p.calls[String(n)] !== undefined ? ` · ${p.calls[String(n)]} call${p.calls[String(n)] === 1 ? "" : "s"}` : "";
    return `<span class="step ${cls}">r${n} ${esc(RUNG_NAMES[n])}${calls}</span>`;
  }).join("");
  $("live-progress").innerHTML = `<div class="live-progress">${steps}
    <span class="muted">${p.elapsed_s ?? 0}s</span></div>`;
}

async function livePoll(id) {
  try {
    const j = await api("/api/live/job", { id });
    liveProgress(j);
    if (j.status === "running") {
      $("live-status").textContent = j.progress.rung_running !== null
        ? `running rung ${j.progress.rung_running}…` : "running…";
      S.live.timer = setTimeout(() => livePoll(id), 1500);
      return;
    }
    $("live-run").disabled = false;
    if (j.status === "error") {
      $("live-status").textContent = "failed";
      $("live-result").innerHTML = `<div class="banner warn">the run died — ${esc(j.error)}</div>`;
      return;
    }
    $("live-status").textContent = `done in ${j.progress.elapsed_s}s`;
    renderLiveResult(j.result);
  } catch (e) {
    $("live-run").disabled = false;
    $("live-status").textContent = "";
    $("live-result").innerHTML = `<div class="banner warn">${esc(e.message)}</div>`;
  }
}

function renderLiveResult(res) {
  S.live.result = res;
  S.live.selected = null;
  S.live.rung = res.order_run[res.order_run.length - 1];
  drawLive();
}

const STATION = { input: "INPUT", find: "FIND", retrieve: "RETRIEVE", pick: "PICK",
  resolve: "RESOLVE", trim: "TRIM", output: "OUTPUT" };

function liveSelect(rid) {
  S.live.selected = (S.live.selected === rid) ? null : rid;
  drawLive();
}

function liveGoto(n) {
  const res = S.live.result;
  if (!res || !res.order_run.includes(n)) return;
  S.live.rung = n;
  drawLive();
}

function liveStep(d) {
  const res = S.live.result;
  const i = res.order_run.indexOf(S.live.rung) + d;
  if (i >= 0 && i < res.order_run.length) liveGoto(res.order_run[i]);
}

/* the record as rung n left it — its state row, or the last one before n
   for a rung that did not run (disabled): nothing changed, the row stands */
function rowAt(r, n) {
  let best = null;
  for (const row of r.timeline || []) if (row.rung <= n) best = row;
  return best;
}

function stationBox(st) {
  const one = {
    input: () => `step ${esc(st.step)}`,
    find: () => st.mention ? `“${esc(st.mention.span_text)}”${st.mention.negated ? " · denied" : ""}`
      : esc(st.state === "no_call" ? "no find call" : "not in reply"),
    retrieve: () => st.state === "not_in_step" ? "no menu in this step"
      : `${st.n} candidates · ${esc(st.retrieval)}`,
    pick: () => st.state === "not_in_step" ? "from memory"
      : st.state === "done" ? `line [${st.choice}] ${esc(st.chosen && st.chosen.label)}`
      : st.state === "fallback" ? `NO PICK → line 0 by rule`
      : esc(st.state),
    resolve: () => st.sct ? `${esc(st.sct)} |${esc(st.sct_label || "?")}|` : "no code",
    trim: () => st.state === "done" ? `“${esc(st.from)}” → “${esc(st.to)}”` : "unchanged",
    output: () => `“${esc(st.text)}” → ${esc(st.sct || "no code")}`,
  }[st.id]();
  return `<div class="station ${esc(st.state)}" title="${esc(st.detail)}">
    <div class="st-name">${STATION[st.id]}</div><div class="st-one">${one}</div></div>`;
}

function menuHtml(retrieve, pick) {
  const chosen = pick && pick.chosen ? pick.chosen.i : null;
  const fb = pick && pick.state === "fallback";
  return `<ol class="menu" start="0">` + (retrieve.candidates || []).map((c) => {
    const isChosen = c.i === chosen;
    const cls = isChosen ? (fb ? "fallback" : "chosen") : "";
    return `<li class="${cls}"><span class="muted">[${c.i}]</span> ${esc(c.label)}
      <span class="muted">${esc(c.code)} · ${Number(c.score).toFixed(3)} ${esc(c.via)}</span>
      ${isChosen ? `<b>← ${fb ? "filled by the fallback rule, not picked" : "the model's pick"}</b>` : ""}</li>`;
  }).join("") + `</ol>`;
}

function r0PathHtml(p, open) {
  if (!p) return "";
  const by = Object.fromEntries(p.steps.map((s) => [s.id, s]));
  const stations = p.steps.map(stationBox).join('<div class="st-arrow">→</div>');
  const details = p.steps.map((st) => {
    let extra = "";
    if (st.id === "find" && st.mention)
      extra = `<pre class="raw">${esc(JSON.stringify(st.mention, null, 1))}</pre>
        <div class="muted">offsets by ${esc(st.offsets)} · grounded ${esc(st.span_grounded)}
        ${st.negation_cue ? ` · rung-1 negation cue “${esc(st.negation_cue)}”` : ""}</div>`;
    if (st.id === "retrieve" && st.candidates) extra = menuHtml(st, by.pick);
    if (st.id === "pick" && st.state !== "not_in_step")
      extra = `<div class="muted">reaction ${esc(st.reaction ?? "?")} in the pick prompt
        ${st.denied ? "· shown as [denied]" : ""} · reply choice ${esc(st.choice ?? "none")}
        ${st.fallback ? ` · fallback <b>${esc(st.fallback)}</b>` : ""}
        ${st.declined ? " · declined" : ""}${st.bad_pick !== null && st.bad_pick !== undefined ? ` · bad pick ${esc(st.bad_pick)}` : ""}</div>`;
    if (st.id === "resolve")
      extra = `<div class="muted">code from ${esc(st.code_source || "model")}, label from
        ${esc(st.label_source || "model")}${st.labels_proposed && st.labels_proposed.length
          ? ` · labels proposed ${esc(st.labels_proposed.join(", "))}` : ""}
        ${st.label_unresolved ? " · label unresolved" : ""}${st.code_unknown ? " · code unknown to the table" : ""}</div>`;
    return `<div class="st-detail"><b>${STATION[st.id]}</b> <span class="muted">${esc(st.state)}</span>
      — ${esc(st.detail)}${extra}</div>`;
  }).join("");
  return `<div class="r0path"><div class="stations">${stations}</div>
    <details ${open ? "open" : ""}><summary>what happened at each station</summary>${details}</details></div>`;
}

/* ---- gold vs model, stacked in one cell ---- */

const words = (t) => new Set(String(t || "").toLowerCase().split(/[^a-z0-9]+/).filter(Boolean));

function diffWords(text, other, cls) {
  // the words of `text` that `other` does not have, emphasised
  const o = words(other);
  return String(text || "").split(/(\s+)/).map((tok) =>
    /^\s+$/.test(tok) ? tok
      : (o.has(tok.toLowerCase().replace(/[^a-z0-9]/g, "")) || !tok.replace(/[^a-z0-9]/gi, ""))
        ? esc(tok) : `<em class="${cls}">${esc(tok)}</em>`).join("");
}

const spansStr = (sp) => (sp || []).map((x) => x.join("-")).join(",");

function stackMention(goldText, goldSpans, predText, predSpans, how) {
  const g = `<div class="g"><span class="who">gold</span> “${diffWords(goldText, predText, "missing")}”
    <span class="muted">${esc(spansStr(goldSpans))}</span></div>`;
  const m = predText === null || predText === undefined
    ? `<div class="m none"><span class="who">model</span> — not found</div>`
    : `<div class="m"><span class="who">model</span> “${diffWords(predText, goldText, "extra")}”
      <span class="muted">${esc(spansStr(predSpans))}</span>${how === "exact" ? '<span class="same">= same span</span>' : ""}</div>`;
  return `<td class="l stack">${g}${m}</td>`;
}

function stackCode(goldCodes, goldLabels, predSct, predLabel, withheld, found) {
  const gl = goldCodes.length
    ? goldCodes.map((c, i) => `${esc(c)} <i>|${esc(goldLabels && goldLabels[i] ? goldLabels[i] : "label unavailable")}|</i>`).join(", ")
    : "concept-less";
  const same = predSct !== null && predSct !== undefined && goldCodes.map(String).includes(String(predSct));
  const ml = !found ? "— not found"
    : predSct === null || predSct === undefined ? "no code"
    : `${esc(predSct)} <i>|${esc(predLabel || "?")}|</i>${withheld ? '<span class="wh">withheld</span>' : ""}${same ? '<span class="same">= same code</span>' : ""}`;
  return `<td class="l stack"><div class="g"><span class="who">gold</span> ${gl}</div>
    <div class="m ${same ? "" : (found && predSct ? "off" : "none")}"><span class="who">model</span> ${ml}</div></td>`;
}

const codeWord = { correct: "right", incorrect: "wrong", withheld_correct: "right, withheld",
  withheld_incorrect: "wrong, withheld", no_code: "no code" };

function pairClass(p) {
  return p.span === "missed" ? "missed"
    : (p.span === "exact" && (p.code === "correct" || p.code === "withheld_correct")) ? "agree" : "differ";
}

function goldDiffHtml(d, sel, n) {
  const c = d.counts;
  const rows = d.pairs.map((p) => {
    const cls = pairClass(p);
    return `<tr class="${cls} ${sel && p.pred === sel ? "on" : ""}" ${p.pred ? `data-rid="${esc(p.pred)}"` : ""}>
      ${stackMention(p.gold.text, p.gold.spans, p.pred ? p.pred_text : null, p.pred_spans, p.span)}
      ${stackCode(p.gold.sct, p.gold_labels, p.pred ? p.pred_sct : null, p.pred_label, p.withheld, !!p.pred)}
      <td class="l"><span class="lg ${cls}">${p.span === "missed" ? "missed" : "found, " + p.span + " span"}</span>
        ${p.code ? `<div><span class="outcome ${/(^|_)correct$/.test(p.code) ? "correct" : "incorrect"}">${esc(codeWord[p.code] || p.code)}</span></div>` : ""}
        ${p.final_zone ? `<span class="zone ${esc(p.final_zone)}">${esc(p.final_zone)}</span>` : ""}</td></tr>`;
  }).join("");
  const spur = d.spurious.map((sp) => `<tr class="spurious ${sel && sp.record_id === sel ? "on" : ""}" data-rid="${esc(sp.record_id)}">
      <td class="l stack"><div class="g none"><span class="who">gold</span> — no mention here</div>
        <div class="m"><span class="who">model</span> “${esc(sp.text)}” <span class="muted">${esc(spansStr(sp.spans))}</span></div></td>
      <td class="l stack"><div class="g none"><span class="who">gold</span> —</div>
        <div class="m off"><span class="who">model</span> ${esc(sp.sct ?? "no code")}${sp.sct_label ? ` <i>|${esc(sp.sct_label)}|</i>` : ""}</div></td>
      <td class="l"><span class="lg spurious">spurious${sp.unlocatable ? " · unlocatable" : ""}</span>
        ${sp.zone ? `<div><span class="zone ${esc(sp.zone)}">${esc(sp.zone)}</span></div>` : ""}</td></tr>`).join("");
  return `<h3>against the gold annotations, as rung ${n} left it
      <span class="muted">· the scorer's own pairing: exact span first, then overlap · <em class="missing">words only gold has</em> · <em class="extra">words only the model has</em></span></h3>
    <div class="cards small">
      <div class="card"><div class="big">${c.gold}</div><div class="muted">gold mentions</div></div>
      <div class="card"><div class="big">${c.found_exact}</div><div class="muted">found, exact span</div></div>
      <div class="card"><div class="big">${c.found_overlap}</div><div class="muted">found, overlapping</div></div>
      <div class="card"><div class="big">${c.missed}</div><div class="muted">missed</div></div>
      <div class="card"><div class="big">${c.spurious}</div><div class="muted">spurious of ${c.predictions}</div></div>
    </div>
    <table class="tl-table diff"><tr><th class="l">mention — gold over model</th>
      <th class="l">code — gold over model</th><th class="l">at rung ${n}</th></tr>
      ${rows}${spur}</table>`;
}

/* ---- the rail ---- */

function railHtml(res, n) {
  const nodes = res.order_run.map((k) => {
    const sm = res.rungs[String(k)].summary || {};
    const zones = Object.entries(sm.zones || {}).map(([z, c]) =>
      `<span class="zone ${esc(z)}" title="${c} in ${esc(z)}">${c}</span>`).join(" ");
    return `<button class="rail-node ${k === n ? "on" : ""} ${sm.disabled ? "disabled" : ""}" data-rung="${k}"
      title="${sm.disabled ? "disabled in the manifest — a recorded state" : `${sm.records} records · ${sm.changed} changed · ${sm.calls} calls`}">
      <div class="rn-name">r${k} <span>${esc(RUNG_NAMES[k])}</span></div>
      <div class="rn-sum">${sm.disabled ? "off" : `${sm.changed} changed · ${sm.calls} call${sm.calls === 1 ? "" : "s"}`}</div>
      <div class="rn-zones">${zones}</div></button>`;
  }).join('<div class="rail-link"></div>');
  const i = res.order_run.indexOf(n);
  return `<div class="rail">
    <button class="rail-step" id="rail-prev" ${i <= 0 ? "disabled" : ""} title="← previous rung">‹</button>
    ${nodes}
    <button class="rail-step" id="rail-next" ${i >= res.order_run.length - 1 ? "disabled" : ""} title="→ next rung">›</button>
    <span class="muted rail-hint">← → step the rungs · everything below is the run as rung ${n} left it</span>
  </div>`;
}

function pathDots(res, r, n) {
  return `<div class="dots">` + res.order_run.map((k) => {
    const row = rowAt(r, k);
    const z = row ? (row.dropped_this_rung ? "DROPPED" : row.zone) : "none";
    const chg = row && row.rung === k && row.changed_this_rung;
    return `<button class="dot ${k === n ? "on" : ""} ${chg ? "chg" : ""}" data-rung="${k}"
      title="r${k} ${esc(RUNG_NAMES[k])}: ${esc(z)}${row && row.rung !== k ? " (did not run)" : ""}${chg ? " · changed here" : ""}">
      <i class="zone ${esc(z)}"></i><span>r${k}</span></button>`;
  }).join('<span class="dot-link"></span>') + `</div>`;
}

function liveRecordCard(res, r, n, pair, open) {
  const row = rowAt(r, n) || {};
  const ran = row.rung === n;
  const was = (row.was_sct !== undefined && ran) ? row : null;
  const label = row.sct_label ? ` <i>|${esc(row.sct_label)}|</i>` : "";
  const header = pair
    ? `<div class="stackline"><div class="g"><span class="who">gold</span> “${diffWords(pair.gold.text, row.text, "missing")}”
         → ${esc(pair.gold.sct.join(", ") || "concept-less")}${pair.gold_labels && pair.gold_labels[0] ? ` <i>|${esc(pair.gold_labels[0])}|</i>` : ""}</div>
       <div class="m"><span class="who">model</span> “${diffWords(row.text, pair.gold.text, "extra")}”
         → ${esc(row.sct ?? "no code")}${label}</div></div>`
    : `<div class="stackline"><div class="m"><span class="who">model</span> “${esc(row.text)}” → ${esc(row.sct ?? "no code")}${label}
       ${res.gold ? '<span class="lg spurious">no gold mention here</span>' : ""}</div></div>`;
  const change = row.dropped_this_rung ? `<b>dropped here</b>`
    : !ran ? `<span class="muted">did not run — the record stands as rung ${row.rung ?? "?"} left it</span>`
    : row.created_this_rung ? `<b>created here</b> by rung 0`
    : row.changed_this_rung
      ? `<b>changed here:</b> ${(row.changed_fields || []).filter((f) => f !== "reason").map((f) => f === "sct"
          ? `code ${esc(row.was_sct ?? "none")} → ${esc(row.sct ?? "none")}`
          : f === "zone" ? `zone ${esc(row.was_zone)} → ${esc(row.zone)}` : esc(f)).join(" · ")}`
      : `<span class="muted">unchanged by this rung</span>`;
  const verdict = [
    n === 1 && row.r1_verdict ? `rung 1 says <b>${esc(row.r1_verdict)}</b>${row.r1_reason ? ` (${esc(row.r1_reason)})` : ""}` : "",
    n === 4 && row.r4_verdict ? `rung 4 says <b>${esc(row.r4_verdict)}</b>` : "",
    n === 3 && row.r3_changed !== null && row.r3_changed !== undefined ? `rung 3 ${row.r3_changed ? "changed it" : "left it"}` : "",
    row.reason && ran && (row.changed_fields || []).includes("reason") ? `reason ${esc(row.reason)}` : "",
  ].filter(Boolean).join(" · ");
  const outcome = res.gold && row.outcome
    ? `<span class="outcome ${esc(row.outcome)}">${esc(row.outcome)}</span>
       <span class="muted">exact / ${esc(row.outcome_overlap)} overlap${row.gold_codes && row.gold_codes.length ? ` · gold ${esc(row.gold_codes.join(","))}` : ""}</span>`
    : "";
  return `<div class="record-card ${S.live.selected === r.record_id ? "on" : ""}" id="live-rec-${esc(r.record_id)}">
    <div class="rc-head">
      <button class="kw ${S.live.selected === r.record_id ? "on" : ""}" data-rid="${esc(r.record_id)}">“${esc(r.text)}”</button>
      ${row.dropped_this_rung ? '<span class="zone REJECT">dropped</span>' : `<span class="zone ${esc(row.zone)}">${esc(row.zone)}</span>`}
      ${r.checks && (r.checks.r0_negated ?? r.checks.negated) ? '<span class="chip signal" style="display:inline">denied in the text</span>' : ""}
      <span class="muted">· ${esc(r.record_id)}</span>
    </div>
    ${header}
    ${pathDots(res, r, n)}
    <div class="at-rung"><b>at rung ${n}:</b> ${change}${verdict ? ` · ${verdict}` : ""}${outcome ? ` · ${outcome}` : ""}</div>
    ${n === 0 ? `<h4>rung 0, station by station</h4>${r0PathHtml(r.r0_path, open)}`
      : `<div class="muted small"><a href="#" class="goto-r0" data-rung="0">↩ rung 0, station by station</a></div>`}
    <details><summary>recorded checks (final)</summary>
      <pre class="raw">${esc(JSON.stringify(r.checks || {}, null, 1))}</pre></details>
  </div>`;
}

function liveCallsHtml(res, n, p, sel) {
  const rec = sel ? res.records.find((r) => r.record_id === sel) : null;
  let calls = p.calls || [];
  if (rec && (n === 2 || n === 4) && rec.text) {
    // a per-record prompt embeds the whole post, so the text alone matches
    // every record's call; the code the record held AT THAT RUNG separates them
    const row = rowAt(rec, n - 1) || {};
    const code = row.sct ?? (rec.checks && rec.checks.withheld ? rec.checks.withheld.sct : null);
    calls = calls.filter((c) => (c.prompt || "").includes(rec.text)
      && (!code || (c.prompt || "").includes(String(code))));
  }
  return calls.map((c) => `<details class="call-card">
    <summary>call ${c.call_index} · <b>${esc(c.mode)}</b> · ${esc(c.model)}
      · ${c.tokens_in}+${c.tokens_out} tok · ${Number(c.seconds).toFixed(1)}s
      ${c.cached ? '<span class="badge cached">cached</span>' : ""}
      ${c.timed_out ? '<span class="badge bad">timed out</span>' : ""}
      ${c.truncated ? '<span class="badge bad">truncated</span>' : ""}
      ${c.sample_index ? `<span class="badge">sample ${c.sample_index}</span>` : ""}
      ${c.temperature ? `<span class="badge">t=${c.temperature}</span>` : ""}
      ${rec && (n === 0 || n === 3) ? '<span class="badge">whole post — every keyword shares it</span>' : ""}</summary>
    <div class="muted">prompt (local-only, never exported):</div>
    <pre class="raw">${rec ? markText(c.prompt, rec.text) : esc(c.prompt)}</pre>
    <div class="muted">raw reply:</div><pre class="raw">${rec ? markText(c.raw, rec.text) : esc(c.raw)}</pre>
    ${c.normalised !== c.raw ? `<div class="muted">after the transport repairs (fence / brace / unwrap):</div><pre class="raw">${esc(c.normalised)}</pre>` : ""}
  </details>`).join("");
}

function markText(text, needle) {
  // the keyword's own lines, highlighted inside a prompt or reply
  if (!needle) return esc(String(text ?? ""));
  return esc(String(text ?? "")).split(esc(needle)).join(`<mark>${esc(needle)}</mark>`);
}

function drawLive() {
  const res = S.live.result;
  if (!res) return;
  const sel = S.live.selected;
  const n = S.live.rung;
  const d = res.gold_diff_by_rung ? res.gold_diff_by_rung[String(n)] : null;
  const verdictOf = {};
  const goldState = {};
  const pairOf = {};
  if (d) {
    for (const p of d.pairs) {
      goldState[p.gold.record_id] = p.span === "missed" ? "missed" : "found";
      if (p.pred) { verdictOf[p.pred] = pairClass(p); pairOf[p.pred] = p; }
    }
    for (const sp of d.spurious) verdictOf[sp.record_id] = "spurious";
  }
  const marks = [];
  for (const r of res.records) {
    const row = rowAt(r, n);
    if (!row || row.dropped_this_rung) continue;
    for (const [a, b] of row.spans || [])
      if (a >= 0) marks.push({ start: a, end: b, rid: r.record_id,
        cls: "pred-span" + (d ? " " + (verdictOf[r.record_id] || "spurious") : "")
          + (sel === r.record_id ? " selected" : (sel ? " dim" : "")),
        title: `${r.record_id} → ${row.sct ?? "no code"} (${row.zone})`
          + (d ? ` — ${verdictOf[r.record_id] || "spurious"} vs gold` : "") + " — click to follow it" });
  }
  if (res.gold)
    for (const m of res.gold) for (const [a, b] of m.spans)
      if (a >= 0) marks.push({ start: a, end: b,
        cls: "gold-span" + (m.excluded ? " excluded" : "") + (goldState[m.record_id] === "missed" ? " missed" : ""),
        title: `GOLD ${m.record_id} “${m.text}” → ${m.sct.join(",") || "concept-less"}${goldState[m.record_id] === "missed" ? " — MISSED" : ""}` });

  const shown = sel ? res.records.filter((r) => r.record_id === sel) : res.records;
  const chips = res.records.map((r) =>
    `<button class="kw ${sel === r.record_id ? "on" : ""}" data-rid="${esc(r.record_id)}"
      title="${esc(r.record_id)}">“${esc(r.text)}”</button>`).join("");
  const cards = shown.map((r) => liveRecordCard(res, r, n, pairOf[r.record_id], !!sel)).join("") ||
    `<div class="banner warn">rung 0 produced no records for this text
     (see its aggregate and raw reply below — a parse failure or an empty answer is a real outcome)</div>`;

  const p = res.rungs[String(n)];
  const cost = p.cost;
  const agg = p.aggregate || {};
  const aggHtml = agg.disabled ? `<span class="zone NEW">disabled in the manifest — a recorded state, not a silent skip</span>`
    : `<details><summary>aggregate the rung reported</summary><pre class="raw">${esc(JSON.stringify(agg, null, 1))}</pre></details>`;
  const routed = n === 6 ? `<div class="card"><div class="big">${cost.routed_to_person}</div>
      <div class="muted">routed to a person (the headline cost)</div></div>
    <div class="card"><div class="big">${cost.human_minutes}</div>
      <div class="muted">minutes at the declared rate</div></div>` : "";
  const calls = liveCallsHtml(res, n, p, sel);
  const panel = `<div class="rung-panel"><h3>rung ${n} ${esc(RUNG_NAMES[n])}: cost and ${sel ? "the calls that carry this keyword" : "every model call"}
    <span class="muted">· ${p.ledger.length} ledger row${p.ledger.length === 1 ? "" : "s"} · wall ${cost.wall_s ?? "—"}s</span></h3>
    <div class="cards small">
      <div class="card"><div class="big">${cost.tokens}</div><div class="muted">tokens (${cost.tokens_in} in + ${cost.tokens_out} out)</div></div>
      <div class="card"><div class="big">${cost.api_calls}</div><div class="muted">model calls</div></div>
      <div class="card"><div class="big">${cost.latency_p95_ms === null ? "·no value·" : (cost.latency_p95_ms / 1000).toFixed(1) + "s"}</div>
        <div class="muted">latency p95 (cold calls only)</div></div>
      ${routed}
    </div>
    ${aggHtml}
    ${calls || `<div class="muted">${sel && (p.calls || []).length ? "no call of this rung carries the selected keyword" : "no model calls — this rung has no model"}</div>`}
  </div>`;

  const pv = res.provenance;
  $("live-result").innerHTML = `
    ${caveatChips(res.caveats)}
    ${railHtml(res, n)}
    <div class="live-frame" key="${n}">
    <h3>the text, as rung ${n} left it <span class="muted">· ${esc(res.source === "corpus" ? res.doc_id + " (" + res.split + ")" : "pasted")}
      · ran rungs ${res.order_run.join(",")} · ${res.calls_total} model call${res.calls_total === 1 ? "" : "s"}${res.calls_cached ? `, ${res.calls_cached} from cache` : ""}</span></h3>
    <div class="doc-text live">${highlight(res.text, marks)}</div>
    <div class="muted">${d ? `<span class="lg agree">agrees</span> exact span and right code (a withheld right answer counts) ·
        <span class="lg differ">differs</span> found but the span or the code is off ·
        <span class="lg spurious">spurious</span> a record with no gold mention ·
        <span class="lg missed">missed</span> gold the extractor never quoted`
      : `blue = the records rung ${n} left`}
      · <b>click a keyword</b> in the text or below to follow just that one</div>
    ${d ? goldDiffHtml(d, sel, n) : ""}
    <div id="live-keywords" class="kwstrip">
      <button class="kw ${sel ? "" : "on"}" data-rid="">all ${res.records.length}</button>${chips}
      ${sel ? `<span class="muted">following “${esc((res.records.find((r) => r.record_id === sel) || {}).text)}” — the calls below are narrowed to it</span>` : ""}
    </div>
    ${cards}
    ${panel}
    </div>
    <div class="prov">live ${esc(pv.run_id)} · split ${esc(pv.split)} · backend ${esc(pv.backend)}
      · manifest ${esc(pv.manifest_hash)} · models ${esc(JSON.stringify(pv.models))}
      · temperature ${esc(pv.temperature)} · git ${esc(pv.git && pv.git.sha ? pv.git.sha.slice(0, 8) : "—")}${pv.git && pv.git.dirty ? " (dirty)" : ""}
      · cache ${esc(pv.llm_cache)} · scratch deleted</div>`;
  const root = $("live-result");
  root.querySelectorAll("[data-rid]").forEach((el) => {
    el.onclick = (e) => {
      e.stopPropagation();
      const rid = el.dataset.rid.split(" ")[0];
      if (!rid) { S.live.selected = null; drawLive(); return; }
      liveSelect(rid);
    };
  });
  root.querySelectorAll("[data-rung]").forEach((el) => {
    el.onclick = (e) => { e.preventDefault(); e.stopPropagation(); liveGoto(Number(el.dataset.rung)); };
  });
  const prev = $("rail-prev"), next = $("rail-next");
  if (prev) prev.onclick = () => liveStep(-1);
  if (next) next.onclick = () => liveStep(1);
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
  const f = S.traceFilter || {};
  const body = await api("/api/run/records",
    { run: S.traceRun, span_match: S.traceSpan, outcome,
      verdict: f.verdict, disposition: f.disposition });
  const filterChip = (f.verdict || f.disposition)
    ? `<div class="caveat">subset from the flow diagram:
       ${f.verdict ? `rung 1 verdict ${esc(f.verdict)}` : ""}
       ${f.disposition ? ` · disposition ${esc(f.disposition)}` : ""}
       (${body.records.length} records)
       <a href="#" id="trace-clear">clear</a></div>`
    : "";
  $("trace-records").innerHTML = filterChip +
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
  const clear = $("trace-clear");
  if (clear) clear.onclick = (ev) => {
    ev.preventDefault();
    S.traceFilter = null;
    listRecords(outcome);
  };
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
