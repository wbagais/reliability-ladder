"""The Reliability Ladder app — Setup & Run + Dashboard.

Run with:  streamlit run app/streamlit_app.py
Reads any results.json (a finished run, or app/results.stub.json before one).
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.review import escalations_fit, resolver_index, run_output_path
from bench.adapters.user_upload import load_dataset, validate
from bench.flatten import flatten_json, schema_field_names
from bench.harness import run_benchmark
from bench.llm import REGISTRY_PATH
from bench.pipeline import RUNG_NAMES, run_item

import yaml

# validated reference palette (dataviz skill)
C_DET = "#2a78d6"      # determinism — blue
C_ACC = "#eb6834"      # accuracy — orange
C_COST = "#1baf7a"     # cost — aqua
C_YIELD = "#008300"    # yield — green (the headline: correct out of ALL fields)
C_MUTED = "#898781"
C_GRID = "#e1e0d9"
BAND = "rgba(42,120,214,0.15)"
BAND_ACC = "rgba(235,104,52,0.15)"

RUNG_LABELS = [f"{i}·{RUNG_NAMES[i].replace('_', ' ')}" for i in range(7)]


def yield_of(r: dict) -> float:
    """Share of ALL fields answered correctly = accuracy_on_answered x coverage.

    The honest headline: accuracy alone rises whenever a layer deletes answers,
    because it is a ratio over answered fields only.
    """
    return r["accuracy"]["accuracy_on_answered"] * r["accuracy"]["coverage"]

st.set_page_config(page_title="Reliability Ladder", page_icon="🪜", layout="wide")


def _chart_layout(fig, ytitle=""):
    fig.update_layout(
        template="plotly_white",
        margin=dict(l=10, r=10, t=30, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        yaxis_title=ytitle,
        hovermode="x unified",
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor=C_GRID)
    return fig


# ---------------------------------------------------------------- results IO
RESULTS_DIR = ROOT / "results"


def available_results() -> dict[str, tuple[dict, Path | None]]:
    """label -> (parsed results, path on disk if any — needed for the sidecar).

    Every finished run in results/ stays listed; runs never overwrite each other.
    """
    out: dict[str, tuple[dict, Path | None]] = {}
    if "results_path" in st.session_state:
        out["This session's run"] = (st.session_state["results"],
                                     Path(st.session_state["results_path"]))
    candidates = sorted(RESULTS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime,
                        reverse=True) if RESULTS_DIR.exists() else []
    candidates += [ROOT / "results.json", ROOT / "app" / "results.stub.json"]
    for p in candidates:
        if p.exists() and p.name not in out:
            try:
                out[p.name] = (json.loads(p.read_text()), p)
            except json.JSONDecodeError:
                pass
    return out


def ollama_models() -> list[str]:
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2) as r:
            return [m["name"] for m in json.load(r)["models"]]
    except Exception:
        return []


# ================================================================ SETUP PAGE
def setup_page():
    st.title("🪜 Reliability Ladder — Setup & Run")
    st.caption(
        "Bring a task (prompt + data + gold answers), pick a model, and measure "
        "what each reliability layer buys you — determinism, accuracy, and cost."
    )

    with st.expander("📄 Data format — how to prepare your input file"):
        st.markdown((ROOT / "docs" / "data-format.md").read_text())
        st.download_button(
            "Download a complete example file",
            (ROOT / "data" / "example_upload.json").read_text(),
            file_name="example_upload.json",
            mime="application/json",
        )

    # ---- data -----------------------------------------------------------
    st.subheader("1 · Data")
    src = st.radio("Dataset", ["Upload my JSON", "SROIE demo (receipts)"],
                   horizontal=True, label_visibility="collapsed")
    raw = None
    if src == "Upload my JSON":
        up = st.file_uploader("Upload your dataset (.json)", type="json")
        if up is not None:
            try:
                raw = json.load(up)
            except json.JSONDecodeError as e:
                st.error(f"That file is not valid JSON: {e}")
    else:
        sroie = ROOT / "data" / "sroie_v1.json"
        if sroie.exists():
            raw = json.loads(sroie.read_text())
        else:
            st.warning("data/sroie_v1.json not found — run "
                       "`python -m bench.adapters.sroie` first.")

    if raw is None:
        st.stop()

    errors = validate(raw)
    if errors:
        st.error("The file has problems — fix these and re-upload:")
        for e in errors[:20]:
            st.markdown(f"- {e}")
        st.stop()

    ds = load_dataset(raw)
    mode = "verification" if ds.verification_mode else "extraction"
    n_conflict = sum(
        1 for it in ds.items
        if it.trusted_record is not None and flatten_json(it.gold) != flatten_json(it.trusted_record)
    )
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Items", len(ds.items))
    c2.metric("Fields", len(schema_field_names(ds.output_schema)))
    c3.metric("Mode", mode)
    c4.metric("Items w/ conflicts", n_conflict if ds.verification_mode else "—")
    st.caption("Fields: " + ", ".join(schema_field_names(ds.output_schema)))

    # ---- prompt ---------------------------------------------------------
    st.subheader("2 · Task prompt")
    prompt = st.text_area(
        "The instruction the model gets for every item (the ladder wraps its own "
        "reliability templates around it):",
        value=ds.prompt or "", height=110,
    )

    # ---- model ----------------------------------------------------------
    st.subheader("3 · Model")
    kind = st.radio("Where does the model run?", ["Local (Ollama)", "Hosted API"],
                    horizontal=True)
    api_key = None
    if kind == "Local (Ollama)":
        st.success("🔒 Private: with a local model your documents never leave this machine.")
        models = ollama_models()
        if models:
            model_name = st.selectbox("Installed Ollama models", models)
            model_spec = f"ollama/{model_name}"
        else:
            st.error("Ollama isn't running (or has no models). Start it and pull a "
                     "model, e.g. `ollama pull llama3.1:8b`.")
            st.stop()
    else:
        providers = [p for p, cfg in yaml.safe_load(REGISTRY_PATH.read_text())["providers"].items()
                     if not cfg.get("local")]
        provider = st.selectbox("Provider", providers)
        model_name = st.text_input("Model name", value="gemini-2.5-flash"
                                   if provider == "gemini" else "")
        api_key = st.text_input("API key (kept in this session only, never stored)",
                                type="password") or None
        model_spec = f"{provider}/{model_name}"
        st.warning("⚠️ With a hosted API, every document in your dataset is sent "
                   f"to {provider}.")

    # ---- run size -------------------------------------------------------
    st.subheader("4 · Run size")
    size = st.radio("Size", ["Quick check (10 items, K=3)", "Full curve (all items, K=10)",
                             "Custom"], horizontal=True, label_visibility="collapsed")
    if size == "Custom":
        cc1, cc2 = st.columns(2)
        n_items = cc1.slider("Items", 2, len(ds.items), min(20, len(ds.items)))
        k = cc2.slider("K runs per item (determinism)", 2, 10, 5)
    elif size.startswith("Quick"):
        n_items, k = min(10, len(ds.items)), 3
    else:
        n_items, k = len(ds.items), 10
    ablations = st.checkbox("Also run single-layer ablations (needed by the composer)",
                            value=True)
    live_review = st.checkbox(
        "Rung 6: I will review escalated fields myself (live human-in-the-loop). "
        "Otherwise the run simulates the human with the gold answers.",
        value=False,
    )
    save_outputs = st.checkbox(
        "Save every rung's per-field output (browsable in the Outputs tab). "
        "Writes a sidecar file next to results.json — kept local, never committed.",
        value=True,
    )

    n_calls = n_items * k * (9 if ablations else 9)  # ~9 unique calls/item/run at the top rungs
    st.caption(f"≈ {n_calls:,} model calls (all cached — re-runs and resumed runs are free).")

    # ---- run ------------------------------------------------------------
    if st.button("▶ Run the ladder", type="primary"):
        # a new run invalidates any review state from a previous one — stale
        # escalations point at items this run may not even have
        for key in ("escalations", "review_t0", "review_pending"):
            st.session_state.pop(key, None)
        prog = st.progress(0.0, text="starting…")

        def cb(msg, frac):
            prog.progress(min(frac, 1.0), text=msg)

        raw2 = dict(raw)
        raw2["prompt"] = prompt
        ds_run = load_dataset(raw2)
        RESULTS_DIR.mkdir(exist_ok=True)
        out_path = run_output_path(RESULTS_DIR, ds_run.domain, n_items, k)
        try:
            results = run_benchmark(
                ds_run, model_spec=model_spec, k=k, n_items=n_items,
                ablations=ablations, out=str(out_path),
                api_key=api_key, progress=cb, save_outputs=save_outputs,
            )
        except Exception as e:
            st.error(f"Run failed: {e}")
            st.stop()
        prog.progress(1.0, text="done")
        st.session_state["results"] = results
        st.session_state["results_path"] = str(out_path)
        st.session_state["run_ctx"] = {
            "raw": raw2, "model_spec": model_spec, "api_key": api_key,
            "k": k, "n_items": n_items,
        }
        if live_review:
            st.session_state["review_pending"] = True
            st.rerun()
        st.success(f"Run complete — saved to `results/{out_path.name}`. "
                   "Open the **Dashboard** page (sidebar).")

    # ---- live review queue (rung 6) ------------------------------------
    if st.session_state.get("review_pending"):
        review_queue()


def review_queue():
    """Rung-6 live mode: the user resolves escalated fields; measured time
    replaces the simulated 2 minutes; rung 6 is re-scored (cached calls = free)."""
    st.subheader("👤 Review queue — rung 6 (live)")
    ctx = st.session_state["run_ctx"]
    ds = load_dataset(ctx["raw"])
    ds.items = ds.items[: ctx["n_items"]]

    # recompute if absent, or if cached escalations don't fit this run's items
    esc = st.session_state.get("escalations")
    if esc is not None and not escalations_fit(esc, len(ds.items)):
        esc = None
    if esc is None:
        from bench.llm import LLMClient

        client = LLMClient(ctx["model_spec"], api_key=ctx["api_key"])
        esc = []
        for idx, item in enumerate(ds.items):
            out = run_item(client, ds, item, layers={1, 2, 3, 4, 5}, sample_index=0)
            for f in out.fields:
                if f.value is None or f.verdict == "conflicts" or f.confidence < 0.7:
                    esc.append({"item": idx, "path": f.field, "draft": f.value,
                                "confidence": f.confidence})
        st.session_state["escalations"] = esc
        st.session_state["review_t0"] = time.monotonic()
    if not esc:
        st.info("Nothing was escalated — rungs 0–5 answered everything confidently.")
        st.session_state.pop("review_pending")
        return

    st.caption(f"{len(esc)} field(s) were escalated (abstained, low-confidence, or "
               "conflicting). Correct or confirm each; your review time is measured.")
    with st.form("review"):
        answers = {}
        for i, e in enumerate(esc):
            item = ds.items[e["item"]]
            with st.expander(f"Item {e['item']} · **{e['path']}** "
                             f"(draft: {e['draft'] or '—'}, conf {e['confidence']:.2f})",
                             expanded=i == 0):
                st.text(item.doc[:1500])
                answers[i] = st.text_input("Correct value (leave empty for 'not present')",
                                           value=e["draft"] or "", key=f"rv{i}")
        submitted = st.form_submit_button("Submit reviews")
    if not submitted:
        return

    minutes = (time.monotonic() - st.session_state["review_t0"]) / 60
    per_item_minutes = minutes / len({e["item"] for e in esc})
    lookup = {(e["item"], e["path"]): (answers[i] or None) for i, e in enumerate(esc)}
    idx_of = resolver_index(ds.items)

    def resolver(item, path, value, conf):
        idx = idx_of.get(item.doc)
        return lookup.get((idx, path), value) if idx is not None else value

    import bench.pipeline as pl

    old_minutes = pl.HUMAN_MINUTES_PER_ITEM
    pl.HUMAN_MINUTES_PER_ITEM = round(per_item_minutes, 2)
    try:
        redo = run_benchmark(
            ds, model_spec=ctx["model_spec"], k=ctx["k"], ablations=False,
            rungs=[0, 1, 2, 3, 4, 5, 6], out=None, api_key=ctx["api_key"],
            human_resolver=resolver,
        )
    finally:
        pl.HUMAN_MINUTES_PER_ITEM = old_minutes

    results = st.session_state["results"]
    results["domains"][0]["rungs"] = redo["domains"][0]["rungs"]
    results["domains"][0]["human_mode"] = "live"
    # rewrite this run's own file, never a shared results.json
    Path(st.session_state["results_path"]).write_text(json.dumps(results, indent=1))
    st.session_state["results"] = results
    st.session_state.pop("review_pending")
    st.session_state.pop("escalations")
    st.success(f"Rung 6 re-scored with your answers — measured "
               f"{per_item_minutes:.2f} min/item. Open the **Dashboard**.")


# ============================================================ DASHBOARD PAGE
def dashboard_page():
    st.title("📊 Reliability Ladder — Dashboard")

    options = available_results()
    up = st.sidebar.file_uploader("…or load another results.json", type="json")
    if up is not None:
        try:
            options[f"uploaded: {up.name}"] = (json.load(up), None)
        except json.JSONDecodeError as e:
            st.sidebar.error(f"Not valid JSON: {e}")
    if not options:
        st.info("No results yet. Run the ladder on the Setup page, or place a "
                "results.json in the repo root.")
        st.stop()
    choice = st.sidebar.selectbox("Results file", list(options))
    results, results_path = options[choice]
    if "_note" in results:
        st.warning("These are the STUB numbers (fake placeholders) — run the "
                   "benchmark to see real ones.")

    dom = results["domains"][0]
    rungs = dom["rungs"]
    st.caption(
        f"model **{results['model']}** · temp {results.get('temperature', 0)} · "
        f"K={results['k_runs']} runs/item · {dom['n_items']} items · "
        f"domain **{dom['name']}** · human mode: {dom.get('human_mode', 'simulated')}"
    )

    names = [f"{r['rung']}·{r['name'].replace('_', ' ')}" for r in rungs]
    det = [r["determinism"]["field_agreement"] for r in rungs]
    acc = [r["accuracy"]["accuracy_on_answered"] for r in rungs]
    cov = [r["accuracy"]["coverage"] for r in rungs]
    dollars = [r["cost"]["dollars"] for r in rungs]
    human_min = [r["cost"]["human_minutes"] for r in rungs]

    (tab_ladder, tab_outputs, tab_curve, tab_econ, tab_compose,
     tab_method, tab_table) = st.tabs(
        ["🪜 Rung by rung", "🔍 Outputs", "The curve", "Economics", "Composer",
         "Method", "Table"]
    )

    # ---- the walkthrough: how each rung works and what it did ------------
    with tab_ladder:
        _ladder_walkthrough(dom)

    # ---- per-field outputs, rung by rung ---------------------------------
    with tab_outputs:
        _outputs_browser(dom, results_path)

    # ---- the curve ------------------------------------------------------
    with tab_curve:
        yld = [yield_of(r) for r in rungs]
        knee = _knee_index(yld)
        st.markdown(
            "**Read the green line.** *Yield* is the share of **all** fields answered "
            "correctly. Accuracy (orange) is a ratio over *answered* fields only, so it "
            "rises whenever a layer refuses to answer — a layer that deletes correct "
            "answers can raise accuracy while making the output worse. Yield can't be "
            "gamed that way."
        )
        fig = go.Figure()
        lo = [r["accuracy"].get("ci_low") for r in rungs]
        hi = [r["accuracy"].get("ci_high") for r in rungs]
        if all(v is not None for v in lo + hi):
            fig.add_trace(go.Scatter(x=names + names[::-1], y=hi + lo[::-1],
                                     fill="toself", fillcolor=BAND_ACC,
                                     line=dict(width=0), hoverinfo="skip",
                                     showlegend=False))
        fig.add_trace(go.Scatter(x=names, y=yld, name="yield (correct out of ALL fields)",
                                 line=dict(color=C_YIELD, width=3),
                                 marker=dict(size=10)))
        fig.add_trace(go.Scatter(x=names, y=acc, name="accuracy (on answered only)",
                                 line=dict(color=C_ACC, width=2),
                                 marker=dict(size=8)))
        fig.add_trace(go.Scatter(x=names, y=cov, name="coverage (share answered)",
                                 line=dict(color=C_MUTED, width=2, dash="dot"),
                                 marker=dict(size=8)))
        fig.add_trace(go.Scatter(x=names, y=det, name="determinism (field agreement)",
                                 line=dict(color=C_DET, width=2, dash="dash"),
                                 marker=dict(size=8)))
        fig.add_annotation(x=names[knee], y=yld[knee],
                           text="best yield", showarrow=True, arrowhead=2, ay=-40)
        fig.update_yaxes(range=[0, 1.05])
        st.plotly_chart(_chart_layout(fig, "score (0–1)"), use_container_width=True)
        best_y = max(range(len(yld)), key=yld.__getitem__)
        st.caption(
            f"**Figure 1 — the reliability curve.** Yield, accuracy, coverage and "
            f"determinism per cumulative rung (shaded = 95% bootstrap CI on accuracy, "
            f"K={results['k_runs']} runs/item). Highest yield: **{names[best_y]}** "
            f"({yld[best_y]:.3f}). Where accuracy climbs while yield falls, the rung is "
            "buying its score by withholding answers — whether that's a good trade is "
            "the Economics tab's question, not the curve's."
        )

        st.divider()
        # local models cost $0 — fall back to latency as the cost axis
        if max(dollars) > 0:
            xvals, xtitle = dollars, "$ per item (compute)"
        else:
            xvals = [r["cost"]["latency_s"] for r in rungs]
            xtitle = "seconds per item (compute is local & free — cost is time)"
        fig2 = go.Figure(go.Scatter(
            x=xvals, y=acc, mode="lines+markers+text", text=[str(r["rung"]) for r in rungs],
            textposition="top center", line=dict(color=C_COST, width=2),
            marker=dict(size=9), name="rungs",
        ))
        fig2.update_xaxes(title=xtitle)
        st.plotly_chart(_chart_layout(fig2, "accuracy (on answered)"), use_container_width=True)
        st.caption("**Figure 2 — the cost frontier.** Accuracy vs compute cost per item; "
                   "points are rungs 0→6. A flat segment = paying more for the same quality.")

    # ---- economics -------------------------------------------------------
    with tab_econ:
        econ = dom.get("economics") or {}
        st.markdown("**Your error economics** — the optimal rung depends on what a "
                    "wrong answer costs *you*.")
        p1, p2, _ = st.columns([1, 1, 2])
        if p1.button("Preset: cheap errors"):
            st.session_state.update(ec_vc=1.0, ec_cw=2.0, ec_ca=0.2, ec_hm=1.0)
        if p2.button("Preset: expensive errors"):
            st.session_state.update(ec_vc=1.0, ec_cw=50.0, ec_ca=1.0, ec_hm=1.0)
        c = st.columns(4)
        v_correct = c[0].slider("$ value of a correct answer", 0.0, 10.0,
                                st.session_state.get("ec_vc", float(econ.get("value_correct", 1.0))), key="ec_vc")
        c_wrong = c[1].slider("$ cost of a wrong answer", 0.0, 100.0,
                              st.session_state.get("ec_cw", float(econ.get("cost_wrong", 10.0))), key="ec_cw")
        c_abstain = c[2].slider("$ cost of an abstention", 0.0, 10.0,
                                st.session_state.get("ec_ca", float(econ.get("cost_abstain", 0.5))), key="ec_ca")
        d_human = c[3].slider("$ per human-minute", 0.0, 5.0,
                              st.session_state.get("ec_hm", float(econ.get("dollars_per_human_min", 1.0))), key="ec_hm")

        utils = []
        for r in rungs:
            a, cvr = r["accuracy"]["accuracy_on_answered"], r["accuracy"]["coverage"]
            correct, wrong, abstain = a * cvr, (1 - a) * cvr, 1 - cvr
            u = (v_correct * correct - c_wrong * wrong - c_abstain * abstain
                 - r["cost"]["dollars"] - d_human * r["cost"]["human_minutes"])
            utils.append(u)
        best = max(range(len(utils)), key=utils.__getitem__)
        best_yield = max(range(len(rungs)), key=lambda i: yield_of(rungs[i]))
        fig = go.Figure(go.Bar(x=names, y=utils, marker_color=C_DET))
        fig.add_annotation(x=names[best], y=utils[best], text="recommended",
                           showarrow=True, arrowhead=2, ay=-35)
        st.plotly_chart(_chart_layout(fig, "net utility $ / item"), use_container_width=True)
        st.success(f"**Recommended rung: {names[best]}** — net utility "
                   f"${utils[best]:.3f} per field under your economics.")
        if best != best_yield:
            st.info(
                f"Note: **{names[best_yield]}** has the highest raw yield "
                f"({yield_of(rungs[best_yield]):.3f} of all fields correct), but "
                f"**{names[best]}** wins under *your* costs — because you priced a wrong "
                "answer at "
                f"${c_wrong:.2f} versus ${c_abstain:.2f} for a missing one. Change those "
                "sliders and the recommendation moves."
            )
        st.caption("**Figure 4 — the flip.** net utility = value·correct − cost·wrong − "
                   "cost·abstain − compute$ − human$. Try both presets: cheap-error tasks "
                   "peak at a low rung; expensive-error tasks climb toward voting/human.")

    # ---- composer --------------------------------------------------------
    with tab_compose:
        abl = dom.get("ablations") or []
        if not abl:
            st.info("This results file has no ablation data (run with ablations on "
                    "to unlock the composer).")
        else:
            st.markdown("**Compose your own stack** — estimated from the single-layer "
                        "ablations (additive approximation).")
            layer_names = {a["rung"]: f"{a['rung']}·{a['name'].replace('_', ' ')}" for a in abl}
            chosen = st.multiselect("Layers on top of the bare model",
                                    list(layer_names.values()),
                                    default=list(layer_names.values())[:2])
            base = rungs[0]
            est_det = base["determinism"]["field_agreement"]
            est_acc = base["accuracy"]["accuracy_on_answered"]
            est_dol = base["cost"]["dollars"]
            est_hum = 0.0
            for a in abl:
                if layer_names[a["rung"]] in chosen:
                    est_det += a["determinism"]["delta"]
                    est_acc += a["accuracy"]["delta"]
                    est_dol += a["cost"]["delta_dollars"]
                    est_hum += a["cost"]["human_minutes"]
            est_det, est_acc = min(est_det, 1.0), min(est_acc, 1.0)
            m = st.columns(4)
            m[0].metric("est. determinism", f"{est_det:.3f}",
                        f"{est_det - base['determinism']['field_agreement']:+.3f}")
            m[1].metric("est. accuracy", f"{est_acc:.3f}",
                        f"{est_acc - base['accuracy']['accuracy_on_answered']:+.3f}")
            m[2].metric("est. $ / item", f"{est_dol:.4f}")
            m[3].metric("human min / item", f"{est_hum:.1f}")
            st.caption("Additive estimate from ablation deltas — layers overlap in "
                       "practice (the gap between this and the cumulative curve is "
                       "redundancy across layers). Verify a chosen stack with a real run.")

    # ---- method ----------------------------------------------------------
    with tab_method:
        st.markdown(f"""
### How each score is calculated

**Yield — the headline number** — the share of **all** field slots that came out
correct:

> yield = accuracy_on_answered x coverage = (correct fields) ÷ (items x fields x K)

Read this one first. Accuracy alone is a ratio over *answered* fields, so any
layer that refuses to answer raises it mechanically — a rung can delete 18
correct answers and 6 wrong ones, report higher accuracy, and leave you with
fewer correct fields than before. Yield cannot be gamed that way: it only goes
up when more fields are actually right.

**Accuracy (on answered)** — every leaf field of every item is scored against the
gold answer, in **all K={results['k_runs']} runs**:

> accuracy_on_answered = (answered fields that match gold) ÷ (all answered fields)

- *answered* = the pipeline produced a value (didn't abstain).
- *match* = equal **after schema-aware normalization** — numbers compared
  numerically ("RM42.00" = 42.0), dates after parsing ("25/12/2018" =
  "2018-12-25"), text case/whitespace-insensitively. So a rung is never
  rewarded or punished for formatting alone.
- Every leaf of a nested output counts as one field (e.g. `materialDocument[0].weight.value`).

**Coverage** = answered fields ÷ all field slots (items × fields × K).
Abstaining lowers coverage, never accuracy — that's the whole point of
abstention: accuracy tells you *how right the answers you got are*, coverage
tells you *how often you got an answer*.

**Determinism (field agreement)** — each item is run K={results['k_runs']} times;
for each field, the fraction of the K runs that produced the modal (most common)
value — a pure string comparison — averaged over fields, then items.

**Cost** — mean tokens / dollars / latency / human-minutes for **one** pass per
item (the K repeats are the measuring instrument, not the deployment cost).
Dollars use the per-token prices in `bench/models.yaml`; local models are $0.

**Confidence intervals** — 95% bootstrap over items (500 resamples).

**Net utility (Economics tab)** =
value·P(correct) − cost_wrong·P(wrong) − cost_abstain·P(abstain) − compute$ − human$
where P(correct) = accuracy × coverage, P(wrong) = (1−accuracy) × coverage,
P(abstain) = 1 − coverage.
""")

    # ---- table (accessibility / export) ---------------------------------
    with tab_table:
        rows = [{
            "rung": r["rung"], "name": r["name"],
            "YIELD (correct/all)": round(yield_of(r), 4),
            "accuracy_on_answered": r["accuracy"]["accuracy_on_answered"],
            "coverage": r["accuracy"]["coverage"],
            "determinism": r["determinism"]["field_agreement"],
            "$/item": r["cost"]["dollars"],
            "latency_s/item": r["cost"].get("latency_s"),
            "human_min/item": r["cost"]["human_minutes"],
            "tokens": r["cost"].get("tokens"),
        } for r in rungs]
        st.dataframe(rows, use_container_width=True)
        st.download_button("Download results.json",
                           json.dumps(results, indent=1),
                           file_name="results.json", mime="application/json")


RUNG_MECHANISM = {
    1: "**Deterministic checks** normalize formats (dates → ISO, currency → plain "
       "decimals, whitespace/case) and recompute verdicts by mechanically comparing "
       "the extracted value to the trusted record. Adds no knowledge — it stabilizes "
       "form. Its wins show up as `reformatted` and verdict corrections, not new answers.",
    2: "**Abstention** blanks any field whose confidence is below 0.7 or whose value "
       "fails the schema's format check. It converts would-be errors into 'no answer': "
       "look for `wrong→abstained` (good: an error screened out) vs `correct→abstained` "
       "(the price: a right answer withdrawn). Accuracy-on-answered rises, coverage falls.",
    3: "**Self-correction** shows the model its own draft next to the document and asks "
       "it to fix mistakes. Wins are `wrong→correct`; risks are `correct→wrong` (the "
       "model 'fixes' something that was right). With an overconfident model it often "
       "changes nothing.",
    4: "**LLM-as-judge** re-reads the document and grades each field pass/fail with a "
       "separate prompt — the first *independent* opinion in the stack. Failed fields "
       "are dropped (`wrong→abstained` = its win; `correct→abstained` = its false-positive "
       "cost). It never rewrites values.",
    5: "**Voting** asks the same question 5 ways (5 fixed prompt framings at temp 0) and "
       "keeps the per-field majority value; agreement becomes the confidence. Wins are "
       "`wrong→correct` where one framing's error is outvoted; it also stabilizes fields "
       "the single prompt got inconsistently.",
    6: "**Human-in-the-loop** escalates every field still abstained, conflicting, or "
       "low-confidence, and a human supplies the answer (simulated with gold, or live "
       "review). `abstained→correct` recoveries at the cost of human minutes.",
}


RUNG_ADDS = {
    0: "1 LLM call per item — the baseline everything above builds on",
    1: "no extra calls — pure post-processing",
    2: "no extra calls — a confidence/format threshold",
    3: "+1 review call per item",
    4: "+1 judge call per item (separate prompt)",
    5: "5 prompt-variant calls instead of 1, + revise + judge on the voted answer",
    6: "no extra calls — human minutes instead",
}


def _transition_story(t: dict, examples: list | None = None) -> tuple[str, dict]:
    reformats = sum(1 for e in (examples or []) if e.get("change") == "reformatted")
    fixed = t.get("wrong->correct", 0)
    screened = t.get("wrong->abstained", 0)
    recovered = t.get("abstained->correct", 0)
    broke = t.get("correct->wrong", 0)
    withdrew = t.get("correct->abstained", 0)
    new_err = t.get("abstained->wrong", 0)
    unchanged = sum(v for k, v in t.items() if k.split("->")[0] == k.split("->")[1])
    total = unchanged + fixed + screened + recovered + broke + withdrew + new_err
    parts = []
    if fixed:
        parts.append(f"✅ **fixed {fixed}** wrong answer{'s' if fixed > 1 else ''}")
    if screened:
        parts.append(f"🛡️ **screened out {screened}** error{'s' if screened > 1 else ''} (abstained instead of being wrong)")
    if recovered:
        parts.append(f"↩️ **recovered {recovered}** previously-unanswered field{'s' if recovered > 1 else ''}")
    if broke:
        parts.append(f"❌ **broke {broke}** previously-correct answer{'s' if broke > 1 else ''}")
    if withdrew:
        parts.append(f"⚠️ **withdrew {withdrew} correct** answer{'s' if withdrew > 1 else ''} (over-cautious)")
    if new_err:
        parts.append(f"❌ **introduced {new_err}** new error{'s' if new_err > 1 else ''}")
    if reformats:
        parts.append(f"🔤 **normalized the formatting of {reformats}** value{'s' if reformats > 1 else ''} "
                     "(same correctness, cleaner form)")
    if not parts:
        story = f"left **all {total} field-slots exactly as they were**."
    else:
        story = " · ".join(parts) + f" — {unchanged} of {total} field-slots kept their outcome ({unchanged / max(total, 1):.0%})."
    return story, {"fixed": fixed, "screened": screened, "recovered": recovered,
                   "broke": broke, "withdrew": withdrew, "new_err": new_err,
                   "unchanged": unchanged, "total": total, "reformats": reformats}


def _verdict(r: dict, counts: dict | None, y: float, y_prev: float | None) -> str:
    """Judge the rung on YIELD (correct out of all fields), not on accuracy —
    accuracy rises whenever a layer withholds answers."""
    acc_d = r["accuracy"]["delta"]
    cost_d = r["cost"]["delta_dollars"]
    human = r["cost"]["human_minutes"]
    y_d = (y - y_prev) if y_prev is not None else 0.0

    if counts is not None and counts["total"] and counts["unchanged"] == counts["total"]:
        if counts.get("reformats"):
            return ("**Verdict: no score effect — formatting only.** It standardized how "
                    "values are written (dates, currency, spacing). That matters for "
                    "downstream systems and for noisier models, but on this run it "
                    "changed no outcomes.")
        return ("**Verdict: no effect on this run.** The mechanism had nothing to act on "
                "for this model + data — that's a finding, not a failure: you'd skip "
                "this layer here.")
    if y_d < -0.002 and acc_d > 0.002:
        return (f"**Verdict: looks better, is worse.** Accuracy {acc_d:+.3f} but yield "
                f"{y_d:+.3f} — it withheld more correct answers than errors, so fewer "
                "fields are right than at the rung below. Only worth it if a wrong "
                "answer costs you far more than a missing one (check Economics).")
    if y_d < -0.002:
        return (f"**Verdict: net loss** — yield {y_d:+.3f}. Fewer fields correct than "
                "the rung below, at higher cost.")
    if human > 0 and y_d > 0.002:
        return (f"**Verdict: quality bought with people's time** — yield {y_d:+.3f} for "
                f"{human:.1f} human-min/item. Whether that pays depends on Economics.")
    if y_d > 0.002:
        cost_txt = f"{cost_d:+.4f} $/item" if cost_d else "no extra $"
        return f"**Verdict: genuine win** — yield {y_d:+.3f} at {cost_txt}."
    if cost_d > 0.0005 or (counts and counts["total"] and counts["unchanged"] < counts["total"]):
        return ("**Verdict: activity without measurable gain** — it changed outputs but "
                "yield didn't move. Cost without benefit on this run.")
    return "**Verdict: neutral on this run.**"


def _ladder_walkthrough(dom: dict) -> None:
    rungs = dom["rungs"]
    ablations = {a["rung"]: a for a in dom.get("ablations") or []}
    st.markdown(
        "Each rung **adds one reliability layer on top of everything below it**. "
        "For each: how it works, what it costs, what it actually changed in this "
        "run, and whether it earned its place."
    )
    by_rung_no = {r["rung"]: r for r in rungs}
    for r in rungs:
        st.divider()
        rung_no = r["rung"]
        prev = by_rung_no.get(rung_no - 1)
        st.subheader(f"Rung {rung_no} — {r['name'].replace('_', ' ')}")
        st.caption(f"Adds: {RUNG_ADDS.get(rung_no, '')}")
        st.markdown(RUNG_MECHANISM.get(rung_no,
                    "**Bare model** — one call with your prompt, output taken as-is. "
                    "This is the baseline every layer above tries to improve."))

        y = yield_of(r)
        y_prev = yield_of(prev) if prev is not None else None
        c = st.columns(5)
        c[0].metric("YIELD — correct of all fields", f"{y:.3f}",
                    f"{y - y_prev:+.3f}" if y_prev is not None else None,
                    help="accuracy x coverage. The honest headline: it cannot be raised "
                         "by refusing to answer.")
        c[1].metric("accuracy (answered only)", f"{r['accuracy']['accuracy_on_answered']:.3f}",
                    f"{r['accuracy']['delta']:+.3f}" if rung_no else None,
                    help="Ratio over answered fields — rises when a layer withholds answers.")
        c[2].metric("coverage", f"{r['accuracy']['coverage']:.3f}",
                    f"{r['accuracy']['coverage'] - prev['accuracy']['coverage']:+.3f}"
                    if prev is not None else None)
        c[3].metric("determinism", f"{r['determinism']['field_agreement']:.3f}",
                    f"{r['determinism']['delta']:+.3f}" if rung_no else None)
        cost_str = (f"${r['cost']['dollars']:.4f}" if r["cost"]["dollars"] > 0
                    else f"{r['cost']['latency_s']:.1f}s")
        extra = f" + {r['cost']['human_minutes']:.1f} human-min" if r["cost"]["human_minutes"] else ""
        c[4].metric("cost / item", cost_str + extra)
        if y_prev is not None and r["accuracy"]["delta"] > 0.002 and y < y_prev - 0.002:
            st.warning(
                f"⚠️ Accuracy rose {r['accuracy']['delta']:+.3f} but yield **fell** "
                f"{y - y_prev:+.3f} — this rung raised its score by withholding answers, "
                "not by getting more right. Fewer fields are correct than before."
            )

        counts = None
        if r.get("explain"):
            story, counts = _transition_story(r["explain"]["transitions"],
                                              r["explain"]["examples"])
            st.markdown(f"**What it did here:** compared with rung {rung_no - 1}, it {story}")
            examples = r["explain"]["examples"]
            if examples:
                with st.expander(f"See the {len(examples)} actual change(s) — before → after vs gold"):
                    st.dataframe(
                        [{"item": e["item"], "field": e["field"], "before": e["before"],
                          "after": e["after"], "gold": e["gold"], "what happened": e["change"]}
                         for e in examples],
                        use_container_width=True,
                    )
        elif rung_no == 0:
            acc, cov = r["accuracy"]["accuracy_on_answered"], r["accuracy"]["coverage"]
            st.markdown(
                f"**What it did here:** answered {cov:.0%} of fields; {acc:.0%} of those "
                f"answers were right — so ~{(1 - acc) * cov:.0%} of all fields are wrong "
                "answers the layers above will try to catch."
            )

        _rung_internals(r, counts)

        if rung_no in ablations and rung_no != 0:
            a = ablations[rung_no]
            st.caption(
                f"Alone on top of the bare model (ablation): accuracy "
                f"{a['accuracy']['accuracy_on_answered']:.3f}, coverage "
                f"{a['accuracy']['coverage']:.3f}, determinism "
                f"{a['determinism']['field_agreement']:.3f} — how much of this rung's "
                "value needs the rungs below it."
            )
        st.markdown(_verdict(r, counts, y, y_prev))


STATUS_MARK = {"correct": "✅", "wrong": "❌", "abstained": "—"}


def _outputs_browser(dom: dict, results_path: Path | None) -> None:
    """Every field's value at every rung, colour-coded by status vs gold."""
    from bench.outputs import read_items, read_outputs, sidecar_path

    path = None
    if results_path is not None:
        cand = results_path.parent / dom["outputs_file"] if dom.get("outputs_file") \
            else sidecar_path(results_path)
        if cand.exists():
            path = cand
    if path is None:
        st.info("No per-field outputs saved for this run. Re-run with outputs enabled "
                "(the Setup page's checkbox, or drop `--no-outputs` on the CLI) to "
                "browse what every rung produced for every field.")
        return

    items = read_items(path)
    st.caption(f"Reading {path.name} — {len(items)} items. ✅ correct · ❌ wrong · "
               "— no answer (abstained). Status is measured against gold with the "
               "same normalization the scores use.")

    c1, c2, c3, c4 = st.columns([2, 1, 2, 1])
    item_idx = c1.selectbox("Item", sorted(items), format_func=lambda i: f"item {i}")
    recs_all = read_outputs(path, item=item_idx)
    ks = sorted({r["k"] for r in recs_all})
    k = c2.selectbox("Run (k)", ks)
    only_problems = c3.checkbox("Only fields that are wrong or unanswered somewhere",
                                value=False)
    compact = c4.checkbox("Compact", value=False,
                          help="On: status marks only, so every rung fits on screen. "
                               "Off: the mark plus the value each rung produced.")

    with st.expander("The input document"):
        st.text(items[item_idx]["doc"])

    recs = sorted([r for r in recs_all if r["k"] == k], key=lambda r: r["rung"])
    if not recs:
        st.warning("No outputs recorded for that item/run.")
        return

    by_rung = {r["rung"]: {f["field"]: f for f in r["fields"]} for r in recs}
    fields = list(by_rung[min(by_rung)].keys())
    gold = {f["field"]: f["gold"] for f in recs[0]["fields"]}

    def short(v, n=48):
        if v is None:
            return "(no answer)"
        v = str(v)
        return v if len(v) <= n else v[: n - 1] + "…"

    rows = []
    for fld in fields:
        cells = {rn: by_rung[rn].get(fld) for rn in sorted(by_rung)}
        if only_problems and all(c and c["status"] == "correct" for c in cells.values()):
            continue
        row = {"field": fld, "gold": short(gold.get(fld))}
        for rn, cell in cells.items():
            if cell is None:
                row[f"R{rn}"] = ""
            elif compact:
                row[f"R{rn}"] = STATUS_MARK[cell["status"]]
            else:
                row[f"R{rn}"] = f"{STATUS_MARK[cell['status']]} {short(cell['value'], 32)}"
        rows.append(row)

    if not rows:
        st.success("Every field was correct at every rung for this item and run.")
    else:
        st.dataframe(rows, use_container_width=True,
                     height=min(600, 60 + 35 * len(rows)))
        st.caption("Columns R0–R6 are the rungs. Read a row left to right to see one "
                   "field's fate through the ladder. " + ("" if compact else
                   "Values are truncated for display; full values are in the outputs "
                   "file. Widen a column by dragging its edge, or tick Compact."))

    st.markdown("**Status count per rung, for this item and run:**")
    counts_rows = []
    for rn in sorted(by_rung):
        vals = list(by_rung[rn].values())
        counts_rows.append({
            "rung": rn,
            "✅ correct": sum(v["status"] == "correct" for v in vals),
            "❌ wrong": sum(v["status"] == "wrong" for v in vals),
            "— no answer": sum(v["status"] == "abstained" for v in vals),
        })
    st.dataframe(counts_rows, use_container_width=True)


def _rung_internals(r: dict, counts: dict | None) -> None:
    """Rung-specific internals: calibration (2), judge quality (4),
    per-variant scores (5), escalation causes (6)."""
    rung_no = r["rung"]
    diag = r.get("diagnostics")

    if rung_no == 2 and diag:
        st.markdown("**Inside this rung — is the model's confidence a usable signal?**")
        c = st.columns(3)
        c[0].metric("mean confidence when correct", f"{diag['mean_conf_correct']:.3f}"
                    if diag["mean_conf_correct"] is not None else "—")
        c[1].metric("mean confidence when wrong", f"{diag['mean_conf_wrong']:.3f}"
                    if diag["mean_conf_wrong"] is not None else "—")
        c[2].metric(f"errors above the {diag['threshold']} gate",
                    f"{diag['wrong_above_threshold']}/{diag['n_wrong']}")
        if diag["n_wrong"] and diag["wrong_above_threshold"] == diag["n_wrong"]:
            st.caption("Every wrong answer sat above the threshold — the gate cannot fire "
                       "on this model's self-reported confidence. Either recalibrate the "
                       "threshold or use a different signal (e.g. vote agreement).")

    if rung_no == 4 and counts:
        tp, fp = counts["screened"], counts["withdrew"]
        fn = counts.get("total", 0) and r["explain"]["transitions"].get("wrong->wrong", 0)
        if tp + fp:
            c = st.columns(3)
            c[0].metric("judge precision", f"{tp / (tp + fp):.2f}",
                        help="Of the answers the judge rejected, how many were actually wrong")
            c[1].metric("judge recall", f"{tp / (tp + fn):.2f}" if tp + fn else "—",
                        help="Of the actually-wrong answers, how many the judge caught")
            c[2].metric("flags: real errors / false alarms", f"{tp} / {fp}")

    if rung_no == 5 and diag:
        st.markdown("**Inside this rung — how each prompt variant scored on its own:**")
        va = diag["variant_accuracy"]
        labels = ["v0 task-first", "v1 doc-first", "v2 careful-framing",
                  "v3 field-by-field", "v4 terse"]
        fig = go.Figure(go.Bar(x=labels[: len(va)], y=va, marker_color=C_DET,
                               text=[f"{v:.3f}" if v is not None else "—" for v in va],
                               textposition="outside"))
        fig.update_yaxes(range=[0, 1.08])
        fig.update_layout(height=280)
        st.plotly_chart(_chart_layout(fig, "accuracy of this variant alone"),
                        use_container_width=True)
        st.caption(f"All 5 variants gave the identical answer on "
                   f"{diag['full_agreement_rate']:.0%} of fields. Where they disagree is "
                   "where the errors live — disagreement itself is the useful signal.")

    if rung_no == 6 and diag:
        rs = diag["reasons"]
        total = sum(rs.values())
        if total:
            st.markdown(
                f"**Inside this rung — why fields reached the human** ({total} escalations, "
                f"{diag['escalated_item_runs']}/{diag['total_item_runs']} item-runs): "
                f"{rs['abstained']} abstained/judge-rejected · "
                f"{rs['conflict_verdict']} genuine conflicts with the trusted record · "
                f"{rs['low_confidence']} low confidence."
            )
        else:
            st.caption("No fields were escalated — the human had nothing to review.")


def _knee_index(q: list[float]) -> int:
    """Elbow method on the yield curve: the rung farthest above the first→last
    chord — where marginal gains start flattening."""
    n = len(q) - 1
    if n < 1 or q[n] <= q[0]:
        return max(range(len(q)), key=q.__getitem__)
    slope = (q[n] - q[0]) / n
    dists = [v - (q[0] + slope * i) for i, v in enumerate(q)]
    return max(range(len(q)), key=dists.__getitem__)


page = st.sidebar.radio("Page", ["Setup & Run", "Dashboard"])
st.sidebar.caption("The Reliability Ladder — measure which harness layers earn "
                   "their cost, then pick your rung.")
if page == "Setup & Run":
    setup_page()
else:
    dashboard_page()
