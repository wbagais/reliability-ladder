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
  run: null,
  resultsDoc: { doc: null, result: null, selected: null, col: null, rule: null },
  live: { options: null, job: null, timer: null, result: null, selected: null, rung: null },
};

/* ---------------- boot + tab bar ---------------- */

async function boot() {
  const [tabs, runs] = await Promise.all([api("/api/tabs"), api("/api/runs")]);
  S.tabs = tabs.tabs; S.runs = runs.runs;
  const bar = $("tabbar");
  bar.innerHTML = "";
  for (const t of S.tabs.filter((x) => x.shipped)) {
    const b = document.createElement("button");
    b.textContent = t.label;
    b.dataset.id = t.id;
    b.onclick = () => showTab(t);
    bar.appendChild(b);
  }
  $("later-list").innerHTML = S.tabs.filter((x) => !x.shipped).map((t) =>
    `<div><b>${esc(t.label)}</b> <span class="muted">${esc(t.milestone)}</span></div>`).join("") +
    `<div class="muted small">planned; the data layer is shaped so they land without rework</div>`;
  // ONE run for the whole app: the newest run on this corpus's splits that
  // carries records (a tracked copy is corpus-free; a matrix cell from
  // another corpus is newer on disk)
  fillRunSelect($("run-pick"), S.runs);
  fillRunSelect($("baseline-pick"), S.runs, true);
  const first = S.runs.find((r) => (r.split === "dev" || r.split === "pool") && r.files.includes("records"))
    || S.runs.find((r) => r.split === "dev" || r.split === "pool") || S.runs[0];
  setRun(first ? first.key : null);
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

/* the run strip: one run, one span mode, one baseline, read by Data and
   Results — absent on Live, which has a text, not a run */
function setRun(key) {
  S.run = key; S.resultsRun = key; D.run = key;
  S.resultsDoc.doc = null; S.resultsDoc.result = null;
  if (key) $("run-pick").value = key;
  const r = S.runs.find((x) => x.key === key);
  $("strip-split").textContent = r ? `· ${r.split}${r.archived ? " · archived" : ""}${r.files.includes("records") ? "" : " · no records file"}` : "";
  $("strip-prov").textContent = "";
  if (key) api("/api/run/results", { run: key }).then((d) => {
    const p = d.provenance || {};
    $("strip-prov").textContent = `· ${p.backend ?? "—"} · manifest ${p.manifest_hash ?? "—"}`;
  }).catch(() => {});
}

function showTab(t) {
  document.querySelectorAll(".tab").forEach((el) => (el.hidden = true));
  document.querySelectorAll(".tabbar button").forEach(
    (b) => b.classList.toggle("active", b.dataset.id === t.id));
  S.tab = t.id;
  $("runstrip").hidden = t.id === "live";
  $(`tab-${t.id}`).hidden = false;
  ({explorer: renderExplorer, results: renderResults, live: renderLive}[t.id])();
}

function wireControls() {
  wireLive();
  wireData();
  $("run-pick").onchange = (e) => { setRun(e.target.value); showTab(S.tabs.find((t) => t.id === S.tab)); };
  $("span-pick").onchange = (e) => { S.span = e.target.value; if (S.tab === "results") renderResults(); };
  $("baseline-pick").onchange = (e) => { S.baseline = e.target.value || null; if (S.tab === "results") renderResults(); };
  $("results-doc").onchange = (e) => { S.resultsDoc.doc = e.target.value || null; renderResultsDoc(); };
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
  $("data-show-excluded").onchange = (e) => { D.showExcluded = e.target.checked; renderDataBody(); };
  $("data-show-disc").onchange = (e) => { D.showDisc = e.target.checked; renderDataBody(); };
  const inp = $("data-doc");
  inp.onchange = () => { const v = inp.value.trim(); if (D.docs.some((d) => d.doc_id === v)) { D.doc = v; renderDataBody(); } };
  inp.onkeydown = (e) => { if (e.key === "Escape") { inp.value = ""; D.doc = null; renderDataBody(); } };
  $("data-doc-clear").onclick = () => { inp.value = ""; D.doc = null; renderDataBody(); };
}

async function renderExplorer() {
  D.run = S.run;
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
  D.recordsAvailable = d.records_available;
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
  const hasRun = D.run && D.recordsAvailable;
  const noRecords = D.run && D.recordsAvailable === false;
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
      `</table><div class="muted">click a row to open the document · click a header to sort${hasRun ? " · sort by the run column to find the most missed" : ""}${noRecords ? ` · <b>${esc(D.run)}</b> has no records file on this machine (a tracked copy is corpus-free by design), so no "in run" column` : ""}</div>`
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
  fillResultsDocs();
  if (S.resultsDoc.doc) renderResultsDoc(); else $("results-doc-view").innerHTML = "";
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
    ${trace("documents", { verdict: bucket })}`);
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
    a.onclick = async (ev) => {
      ev.preventDefault();
      const params = JSON.parse(a.dataset.params);
      let box = el.querySelector("#subset-docs");
      if (!box) { box = document.createElement("div"); box.id = "subset-docs"; box.className = "subset-docs"; a.closest(".dep-card, .card, div").appendChild(box); }
      box.innerHTML = `<span class="muted">loading…</span>`;
      try {
        const d = await api("/api/run/records", { run: S.resultsRun, span_match: S.span, ...params });
        const docs = {};
        for (const r of d.records) (docs[r.doc_id] = docs[r.doc_id] || []).push(r);
        const items = Object.entries(docs).sort((x, y) => y[1].length - x[1].length);
        box.innerHTML = `<div class="small">${d.records.length} record${d.records.length === 1 ? "" : "s"} in ${items.length} document${items.length === 1 ? "" : "s"} — click one to see it through the ladder (section 7)</div>` +
          items.map(([doc, recs]) => `<a href="#" class="doc-link" data-doc="${esc(doc)}">${esc(doc)} <span class="muted">${recs.length}</span></a>`).join(" · ");
        box.querySelectorAll(".doc-link").forEach((l) => (l.onclick = (e2) => { e2.preventDefault(); openResultsDoc(l.dataset.doc); }));
      } catch (err) { box.innerHTML = `<span class="bad">${esc(err.message)}</span>`; }
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
      `<option value="${n}" ${n === o.rung_order[o.rung_order.length - 1] ? "selected" : ""}>rung ${n} — ${RUNG_NAMES[n] || ""}</option>`).join("");
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
  S.live.rule = null;
  const cols = liveGridCols(res);
  S.live.col = cols.length ? cols[cols.length - 1] : res.order_run[res.order_run.length - 1];
  drawLive();
}

/* the grid's rung columns: rungs 1-4 the run ran; rung 0 is the table above,
   rungs 5 and 6 are the person column */
function liveGridCols(res) { return res.order_run.filter((n) => n >= 1 && n <= 4); }

function liveStep(d) {
  const res = S.live.result;
  const cols = liveGridCols(res);
  const i = cols.indexOf(S.live.col) + d;
  if (i >= 0 && i < cols.length) { S.live.col = cols[i]; drawLive(); }
}

/* the record as rung n left it — its state row, or the last one before n
   for a rung that did not run (disabled): nothing changed, the row stands */
function rowAt(r, n) {
  let best = null;
  for (const row of r.timeline || []) if (row.rung <= n) best = row;
  return best;
}

/* ---- words: the ones only one side has ---- */
const words = (t) => new Set(String(t || "").toLowerCase().split(/[^a-z0-9]+/).filter(Boolean));
function diffWords(text, other, cls) {
  const o = words(other);
  return String(text || "").split(/(\s+)/).map((tok) =>
    /^\s+$/.test(tok) ? tok
      : (o.has(tok.toLowerCase().replace(/[^a-z0-9]/g, "")) || !tok.replace(/[^a-z0-9]/gi, ""))
        ? esc(tok) : `<em class="${cls}">${esc(tok)}</em>`).join("");
}
const spansStr = (sp) => (sp || []).map((x) => x.join("-")).join(",");

function pairClass(p) {
  return p.span === "missed" ? "missed"
    : (p.span === "exact" && (p.code === "correct" || p.code === "withheld_correct")) ? "agree" : "differ";
}

/* ---- rung 0 against gold: one row per mention from either side ---- */

function menuCell(r) {
  const p = r && r.r0_path;
  if (!p) return `<td class="muted">—</td>`;
  const st = Object.fromEntries(p.steps.map((x) => [x.id, x]));
  const ret = st.retrieve, pick = st.pick, find = st.find;
  if (!ret || ret.state === "not_in_step")
    return `<td class="muted small">${esc((pick && pick.detail) || "no menu in this step")}</td>`;
  const cands = ret.candidates || [];
  const chosen = pick && pick.chosen ? pick.chosen.i : null;
  const fb = pick && pick.state === "fallback";
  const head = pick.state === "done" ? `picked <b>[${pick.choice}]</b>`
    : fb ? `<span class="byrule">no pick → line 0 by rule</span>`
    : pick.state === "declined" ? `declined the menu` : esc(pick.state);
  const shown = cands.slice(0, 3).map((c) => c.i);
  if (chosen !== null && !shown.includes(chosen)) shown.push(chosen);
  const lines = cands.filter((c) => shown.includes(c.i)).map((c) => {
    const isChosen = c.i === chosen;
    const cls = isChosen ? (fb ? "fb" : "pick") : "";
    return `<li class="${cls}"><span class="muted">[${c.i}]</span> ${esc(c.label)}${isChosen ? (fb ? " ← filled by rule, not picked" : " ← the model's pick") : ""}</li>`;
  }).join("");
  const all = cands.map((c) => `[${c.i}] ${c.label} · ${Number(c.score).toFixed(3)}`).join("\n");
  const denied = find && find.negated ? ' · <span class="chip signal" style="display:inline">shown as [denied]</span>' : "";
  const trim = st.trim && st.trim.state === "done" ? `<div class="small">quoted “${esc(st.trim.from)}” → kept “${esc(st.trim.to)}”</div>` : "";
  return `<td title="${esc(all)}"><div class="small">${cands.length} retrieved, ${esc(ret.retrieval)} · ${head}${denied}</div>
    <ol class="menu" start="0">${lines}${cands.length > shown.length ? `<li class="muted">… ${cands.length - shown.length} more on hover</li>` : ""}</ol>${trim}</td>`;
}

function r0Rows(res) {
  const byId = Object.fromEntries(res.records.map((r) => [r.record_id, r]));
  const rows = [];
  const at0 = (r) => rowAt(r, 0) || r;
  if (res.gold_diff) {
    for (const p of res.gold_diff.pairs) {
      const r = p.pred ? byId[p.pred] : null;
      const r0 = r ? at0(r) : null;
      rows.push({ pos: p.gold.spans[0][0], cls: pairClass(p), rid: p.pred,
        mention: `<td class="stack"><div class="g"><span class="who">gold</span>“${diffWords(p.gold.text, r0 && r0.text, "missing")}” <span class="muted">${esc(spansStr(p.gold.spans))}</span>${p.span === "missed" ? ' <span class="lg missed">gold only</span>' : ""}</div>
          ${r0 ? `<div class="m"><span class="who">model</span>“${diffWords(r0.text, p.gold.text, "extra")}” <span class="muted">${esc(spansStr(r0.spans))}</span>${p.span === "exact" ? '<span class="same">= same span</span>' : ""}</div>`
               : `<div class="m none"><span class="who">model</span>— not quoted by the model</div>`}</td>`,
        menu: r ? menuCell(r) : `<td class="muted small">— no menu: nothing was retrieved for a span the model never quoted</td>`,
        code: `<td class="stack"><div class="g"><span class="who">gold</span>${p.gold.sct.length ? p.gold.sct.map((c, i) => `${esc(c)} <i>|${esc(p.gold_labels && p.gold_labels[i] ? p.gold_labels[i] : "label unavailable")}|</i>`).join(", ") : "concept-less"}</div>
          ${r0 ? `<div class="m ${p.code && /(^|_)correct$/.test(p.code) ? "" : "off"}"><span class="who">model</span>${r0.sct ? `${esc(r0.sct)} <i>|${esc(r0.sct_label || "?")}|</i>` : "no code"}${p.code === "correct" || p.code === "withheld_correct" ? '<span class="same">= same code</span>' : ""}</div>`
               : `<div class="m none"><span class="who">model</span>—</div>`}</td>` });
    }
    for (const sp of res.gold_diff.spurious) {
      const r = byId[sp.record_id]; const r0 = at0(r);
      rows.push({ pos: (r0.spans || [[0]])[0][0], cls: "spurious", rid: sp.record_id,
        mention: `<td class="stack"><div class="g none"><span class="who">gold</span>— no mention here <span class="lg spurious">model only</span></div>
          <div class="m"><span class="who">model</span>“${esc(r0.text)}” <span class="muted">${esc(spansStr(r0.spans))}</span></div></td>`,
        menu: menuCell(r),
        code: `<td class="stack"><div class="g none"><span class="who">gold</span>—</div>
          <div class="m"><span class="who">model</span>${r0.sct ? `${esc(r0.sct)} <i>|${esc(r0.sct_label || "?")}|</i>` : "no code"}</div></td>` });
    }
  } else {
    for (const r of res.records) {
      const r0 = at0(r);
      rows.push({ pos: (r0.spans || [[0]])[0][0], cls: "", rid: r.record_id,
        mention: `<td class="stack"><div class="m"><span class="who">model</span>“${esc(r0.text)}” <span class="muted">${esc(spansStr(r0.spans))}</span></div></td>`,
        menu: menuCell(r),
        code: `<td class="stack"><div class="m"><span class="who">model</span>${r0.sct ? `${esc(r0.sct)} <i>|${esc(r0.sct_label || "?")}|</i>` : "no code"}</div></td>` });
    }
  }
  rows.sort((a, b) => a.pos - b.pos);
  return rows;
}

function r0TableHtml(res, sel) {
  const rows = r0Rows(res);
  const calls = (res.rungs["0"] || {}).calls || [];
  const find = calls.find((c) => !String(c.mode).endsWith("-pick"));
  const pick = calls.find((c) => String(c.mode).endsWith("-pick"));
  const cost = (c) => c ? `${c.tokens_in} + ${c.tokens_out}` : "—";
  const secs = (c) => c ? `${Number(c.seconds).toFixed(1)} s${c.cached ? " (cached)" : ""}` : "—";
  const d = res.gold_diff && res.gold_diff.counts;
  const line = d ? `paired ${d.found_exact + d.found_overlap} (${d.found_exact} exact, ${d.found_overlap} overlap) · model only ${d.spurious} · gold only ${d.missed}`
    : `${res.records.length} mention${res.records.length === 1 ? "" : "s"} quoted · no gold for a pasted text`;
  return `<div class="small r0line"><b>rung 0${res.gold_diff ? " against gold" : ""}</b> · ${line}</div>
    <table class="wire r0">
      <tr><th class="l" style="width:32%">mention${res.gold_diff ? " — gold over model" : ""}<small>find</small></th>
          <th class="l" style="width:34%">the menu, and the pick<small>retrieve · pick</small></th>
          <th class="l">code${res.gold_diff ? " — gold over model" : ""}<small>resolve</small></th></tr>
      ${rows.map((r) => `<tr class="${r.cls} ${sel && r.rid === sel ? "on" : (sel ? "dim" : "")}" ${r.rid ? `data-rid="${esc(r.rid)}"` : ""}>${r.mention}${r.menu}${r.code}</tr>`).join("")}
      <tr class="cost0"><td>calls · ${find ? 1 : 0}</td><td>retrieve none · pick ${pick ? 1 : 0}</td><td>none</td></tr>
      <tr class="cost0"><td>tokens · ${cost(find)}</td><td>— · ${cost(pick)}</td><td>—</td></tr>
      <tr class="cost0"><td>latency · ${secs(find)}</td><td>— · ${secs(pick)}</td><td>—</td></tr>
    </table>`;
}

/* ---- the grid: rungs 1-4 in their own words, then the person column ---- */

const BAND_WORDS = { colloquial_no_lexical_match: "no lexical match", no_lexical_match: "no lexical match" };

function cellR1(r) {
  const c = r.checks || {}, v = c.r1_verdict;
  if (!v) return `<td class="c gray">—</td>`;
  const why = v === "BAND" ? (BAND_WORDS[c.reason_band] || c.reason_band || "") : (c.r1_reason || "");
  const audit = c.r1_audit && c.r1_audit.checks ? Object.entries(c.r1_audit.checks).map(([k, x]) => `${k}: ${x}`).join("\n") : "";
  return `<td class="c" title="${esc(audit)}"><span class="zone ${esc(v)}">${esc(v)}</span>${why ? `<br><span class="small">${esc(why)}</span>` : ""}</td>`;
}
function cellR2(r) {
  const x = (r.checks || {}).r2;
  if (!x || (x.outcome === "unchanged" && !x.now)) return `<td class="c gray" title="${esc(x ? x.why || "" : "")}">skipped${x && x.why ? `<br><span class="small">${esc(x.why.replace("not a correctable rung 1 rejection", "nothing to state back"))}</span>` : ""}</td>`;
  const was = x.was || {}, now = x.now || {};
  return `<td class="c"><b>${esc(x.outcome)}</b><br><span class="small">${esc(was.sct ?? "none")} → ${esc(now.sct ?? "none")}${x.reason ? ` · on ${esc(x.reason)}` : ""}</span></td>`;
}
function cellR3(r, res) {
  const agg = (res.rungs["3"] || {}).aggregate || {};
  if (agg.disabled) return `<td class="c gray">off<br><span class="small">disabled in the manifest</span></td>`;
  const x = (r.checks || {}).r3;
  if (!x) return `<td class="c gray">—</td>`;
  const raw = (x.raw || []).filter(Boolean);
  const k = x.k || 3, seen = x.seen || 0;
  if (seen < 2) return `<td class="c"><span class="muted">not re-found</span><br><span class="small">${seen} of ${k} samples found it</span></td>`;
  const counts = {};
  for (const v of raw) counts[v] = (counts[v] || 0) + 1;
  const top = Math.max(...Object.values(counts));
  const votes = Object.entries(counts).sort((a, b) => b[1] - a[1]).map(([code, n]) => `${esc(code)} ×${n}`).join(" · ");
  return `<td class="c" title="${esc(raw.join(", "))}">${votes}<br><b>${Math.round(100 * top / k)}%</b> agree${x.tie ? " · tie" : ""}${x.changed ? " · changed the code" : ""}</td>`;
}
function cellR4(r) {
  const c = r.checks || {}, v = c.r4_verdict, x = c.r4 || {};
  if (v === undefined) return `<td class="c gray">—</td>`;
  if (v === null) return `<td class="c"><span class="muted">unparsed</span></td>`;
  const why = x.why || "";
  return `<td class="c" title="${esc(why)}"><b class="${v === "pass" ? "" : "bad"}">${esc(v)}</b> ${esc(x.confidence ?? c.r4_confidence ?? "")}${x.best !== null && x.best !== undefined ? ` · best [${esc(x.best)}]` : ""}<br><span class="small">“${esc(why.length > 140 ? why.slice(0, 137) + "…" : why)}”</span></td>`;
}
function ruleToken(rule, cls = "") {
  const st = rule.state === "hold" ? "hold" : rule.state === "ship" ? "ship" : "nr";
  const tip = `${rule.name} — ${rule.state === "not_run" ? (rule.note || "not run") : rule.state + (rule.value ? " · " + rule.value : "") + (rule.note ? " · " + rule.note : "")}`;
  return `<span class="${st} ${cls}" title="${esc(tip)}">${esc(rule.id)}</span>`;
}
function cellPerson(r, rule) {
  const rules = r.rules || [];
  if (rule) {
    const x = rules.find((q) => q.id === rule);
    if (!x) return `<td class="c gray">—</td>`;
    return `<td class="c narrow"><span class="rules v">${ruleToken(x)}</span><br><span class="small">${x.state === "not_run" ? "not run" : x.state === "hold" ? "holds it" : "ships it"}</span></td>`;
  }
  const p = r.person || {};
  const pct = p.share === null || p.share === undefined ? "—" : `${Math.round(100 * p.share)}%`;
  return `<td class="c narrow" title="${p.held} of ${p.run} rules run hold it"><b>${pct}</b><br><span class="rules v">${rules.map((x) => ruleToken(x)).join("")}</span></td>`;
}

function gridHtml(res, sel, col, rule) {
  const cols = liveGridCols(res);
  const cellFor = { 1: cellR1, 2: cellR2, 3: (r) => cellR3(r, res), 4: cellR4 };
  const meaning = { 1: "one word", 2: "skipped or did", 3: "k outputs, agreement", 4: "its words" };
  const q6 = res.rungs["6"] ? res.rungs["6"].cost : null;
  const head = cols.map((n) => `<th class="${n === col ? "on" : ""}" data-col="${n}">r${n} ${esc(RUNG_NAMES[n])}<small>${meaning[n]}</small></th>`).join("");
  const rows = res.records.map((r) => `<tr class="${sel === r.record_id ? "on" : (sel ? "dim" : "")}">
      <td class="kw ${sel === r.record_id ? "on" : ""}" data-rid="${esc(r.record_id)}">${esc(r.text)}${r.checks && (r.checks.r0_negated ?? r.checks.negated) ? ' <span class="chip signal" style="display:inline">denied</span>' : ""}</td>
      ${cols.map((n) => cellFor[n](r)).join("")}${cellPerson(r, rule)}</tr>`).join("");
  const c = (n, f) => { const x = res.rungs[String(n)] && res.rungs[String(n)].cost; return x ? f(x) : "—"; };
  const cost = `<tr class="cost first"><td class="kw">calls</td>${cols.map((n) => `<td>${c(n, (x) => x.api_calls)}</td>`).join("")}<td>—</td></tr>
    <tr class="cost"><td class="kw">tokens</td>${cols.map((n) => `<td>${c(n, (x) => x.tokens.toLocaleString())}</td>`).join("")}<td>—</td></tr>
    <tr class="cost"><td class="kw">latency p95</td>${cols.map((n) => `<td>${c(n, (x) => x.latency_p95_ms === null ? "—" : (x.latency_p95_ms / 1000).toFixed(1) + " s")}</td>`).join("")}<td>—</td></tr>`;
  return `<table class="grid cells">
    <tr><th style="border:none;min-width:0"></th>${head}
      <th class="person-h">person<small>${q6 ? `${q6.routed_to_person} queued · ${q6.human_minutes} min declared` : "rungs 5 and 6 not run"}</small></th></tr>
    ${rows || `<tr><td colspan="${cols.length + 2}" class="muted">rung 0 produced no records for this text — a parse failure or an empty answer is a real outcome; its raw reply is in the rung 0 line above</td></tr>`}
    ${cost}</table>`;
}

function legendHtml(res, rule) {
  const rows = (res.rules_legend || []).map((x) => {
    const pct = x.share === null ? "not run" : `${Math.round(100 * x.share)}%`;
    return `<tr class="${rule === x.id ? "on" : ""} ${x.share === null ? "nr" : ""}" data-rule="${esc(x.id)}">
      <td><span class="rules"><span class="${x.share === null ? "nr" : ""}">${esc(x.id)}</span></span></td>
      <td>${esc(x.name)}</td><td class="pct">${pct}</td></tr>`;
  }).join("");
  return `<div class="legendbox"><div class="small"><b>person</b> · six rules · share of keywords each holds · click one to show it alone${rule ? ` · <b>showing ${esc(rule)}</b>` : ""}</div>
    <table class="legendv">${rows}</table>
    <div class="small"><span class="rules"><span class="hold">V</span></span> holds it for a person · <span class="rules"><span class="ship">V</span></span> ships it · <span class="rules"><span class="nr">V</span></span> not run</div></div>`;
}

function drawLive() {
  if (!S.live.result) return;
  drawGrid($("live-result"), S.live.result, S.live);
}

/* ONE renderer for a document through the ladder — the Live tab's result
   and the Results drill-down draw through it. `st` holds the selection:
   {selected keyword, col (the grid column the text follows), rule}. */
function drawGrid(root, res, st) {
  if (!res) return;
  if (st.col === undefined || st.col === null) {
    const cols = liveGridCols(res);
    st.col = cols.length ? cols[cols.length - 1] : res.order_run[res.order_run.length - 1];
  }
  const sel = st.selected, col = st.col, rule = st.rule;
  const d = res.gold_diff_by_rung ? (res.gold_diff_by_rung[String(col)] || res.gold_diff) : null;
  const verdictOf = {}, goldState = {};
  if (d) {
    for (const p of d.pairs) {
      goldState[p.gold.record_id] = p.span === "missed" ? "missed" : "found";
      if (p.pred) verdictOf[p.pred] = pairClass(p);
    }
    for (const sp of d.spurious) verdictOf[sp.record_id] = "spurious";
  }
  const marks = [];
  for (const r of res.records) {
    const row = rowAt(r, col);
    if (!row || row.dropped_this_rung) continue;
    let cls = d ? (verdictOf[r.record_id] || "spurious") : "";
    if (rule) { const x = (r.rules || []).find((q) => q.id === rule); cls = x ? (x.state === "hold" ? "held" : x.state === "ship" ? "ships" : "") : ""; }
    for (const [a, b] of row.spans || [])
      if (a >= 0) marks.push({ start: a, end: b, rid: r.record_id,
        cls: "pred-span " + cls + (sel === r.record_id ? " selected" : (sel ? " dim" : "")),
        title: `${r.record_id} → ${row.sct ?? "no code"} (${row.zone}) — click to follow it` });
  }
  if (res.gold)
    for (const m of res.gold) for (const [a, b] of m.spans)
      if (a >= 0) marks.push({ start: a, end: b,
        cls: "gold-span" + (m.excluded ? " excluded" : "") + (goldState[m.record_id] === "missed" ? " missed" : ""),
        title: `GOLD ${m.record_id} “${m.text}” → ${m.sct.join(",") || "concept-less"}${goldState[m.record_id] === "missed" ? " — gold only" : ""}` });
  const legend = rule
    ? `<span class="lg held">held for a person</span> · <span class="lg ships">ships</span> under rule ${esc(rule)}`
    : d ? `<span class="lg agree">agrees</span> · <span class="lg differ">differs</span> · <span class="lg spurious">model only</span> · <span class="lg missed">gold only</span>`
        : `violet = the model's records`;
  const pv = res.provenance;
  const mj = res.menu_judge;
  root.innerHTML = `
    ${caveatChips(res.caveats)}
    <div class="doc-text live">${highlight(res.text, marks)}</div>
    <div class="small">as rung ${col} left it · ${legend} · click a keyword to follow one row · ← → walk the grid's columns${mj && mj.failed ? ` · <span class="bad">menu-shown judge failed: ${esc(mj.error)}</span>` : ""}</div>
    ${r0TableHtml(res, sel)}
    ${gridHtml(res, sel, col, rule)}
    <div class="small">hover a cell for the full value · gray = the rung did nothing here, or did not run · the three cost rows are the three measures, never fused</div>
    ${legendHtml(res, rule)}
    <div class="prov">${res.source === "run" ? `run ${esc(pv.run_id)} · ${esc(res.doc_id)} (${esc(res.split)})${pv.archived ? " · archived" : ""}` : `live ${esc(pv.run_id)} · ${esc(res.source === "corpus" ? res.doc_id + " (" + res.split + ")" : "pasted")}`} · ran rungs ${res.order_run.join(",")} · ${res.calls_total} model call${res.calls_total === 1 ? "" : "s"}${res.calls_cached ? `, ${res.calls_cached} from cache` : ""}${mj && mj.calls ? ` + ${mj.calls.length} menu-judge` : ""}
      · backend ${esc(pv.backend)} · manifest ${esc(pv.manifest_hash)} · models ${esc(JSON.stringify(pv.models || {}))}${pv.temperature !== undefined ? ` · temperature ${esc(pv.temperature)}` : ""}${pv.git ? ` · git ${esc(pv.git.sha ? pv.git.sha.slice(0, 8) : "—")}${pv.git.dirty ? " (dirty)" : ""}` : ""}${res.source === "run" ? "" : " · scratch deleted"}</div>`;
  const redraw = () => drawGrid(root, res, st);
  root.querySelectorAll("[data-rid]").forEach((el) => {
    el.onclick = (e) => { e.stopPropagation(); const rid = el.dataset.rid.split(" ")[0];
      st.selected = (st.selected === rid) ? null : rid; redraw(); };
  });
  root.querySelectorAll("th[data-col]").forEach((el) => {
    el.onclick = () => { st.col = Number(el.dataset.col); redraw(); };
  });
  root.querySelectorAll("tr[data-rule]").forEach((el) => {
    el.onclick = () => { const id = el.dataset.rule; st.rule = (st.rule === id) ? null : id; redraw(); };
  });
}

/* ---- Results drill-down: this run's document through the same grid ---- */

async function fillResultsDocs() {
  const sel = $("results-doc");
  const keep = S.resultsDoc.doc;
  sel.innerHTML = `<option value="">choose a document…</option>`;
  try {
    const d = await api("/api/run/docs", { run: S.resultsRun });
    for (const x of d.docs) {
      const o = document.createElement("option");
      o.value = x.doc_id;
      const zones = Object.entries(x.zones || {}).map(([z, n]) => `${n} ${z}`).join(", ");
      o.textContent = `${x.doc_id} — ${x.n_records} record${x.n_records === 1 ? "" : "s"}${zones ? " · " + zones : ""}`;
      sel.appendChild(o);
    }
    if (keep && [...sel.options].some((o) => o.value === keep)) sel.value = keep;
  } catch (err) {
    sel.innerHTML = `<option value="">${esc(err.message)}</option>`;
  }
}

async function renderResultsDoc() {
  const el = $("results-doc-view");
  const st = S.resultsDoc;
  if (!st.doc) { el.innerHTML = ""; return; }
  el.innerHTML = `<div class="muted">loading ${esc(st.doc)}…</div>`;
  try {
    const res = await api("/api/run/document", { run: S.resultsRun, doc_id: st.doc });
    st.result = res; st.selected = null; st.col = null; st.rule = null;
    drawGrid(el, res, st);
    el.scrollIntoView({ block: "start", behavior: "smooth" });
  } catch (err) {
    el.innerHTML = `<div class="banner warn">${esc(err.message)}</div>`;
  }
}

function openResultsDoc(docId) {
  S.resultsDoc.doc = docId;
  $("results-doc").value = docId;
  renderResultsDoc();
}

boot().catch((e) => {
  document.body.insertAdjacentHTML("beforeend",
    `<div class="banner warn">failed to start: ${esc(e.message)}</div>`);
});
