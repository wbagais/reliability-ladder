#!/usr/bin/env bash
# fix_linnaeus.sh — build a cleaner taxonomy, re-run four cells, score, report.
#
# ONE command on the card. No status checks, no intermediate turns.
#
# WHAT IS BROKEN, MEASURED FROM THE RECORDS THE LAST RUN WROTE
#
# Three different failures across four models:
#
#   gpt-oss    extracts species correctly — 'Campephilus principalis',
#              'Dryocopus pileatus', 'Lutzomyia intermedia' all resolve — but
#              'human' retrieves *Human rotavirus* and 'rat' retrieves *Rat
#              norovirus*. The EXTRACTION is right and the RETRIEVAL is wrong.
#   granite4   extracts 'Selective serotonin reuptake inhibitors',
#              'pharmacology', 'However'. Not species.
#   mistral    extracts 'kidney', 'PNET', "Ewing's tumour" — DISEASES, which is
#              what CADEC's default prompt asks for. The corpus prompt did not
#              reach it.
#   llama3.1   extracted nothing at all.
#
# THE VOCABULARY FIX, AND WHY IT IS NOT TUNING ON GOLD
#
# NCBI Taxonomy carries 3.0M names, and a lexical retriever over them will find
# a match for almost any English token: 'human' hits *Human rotavirus*, 'with
# sigma' hits *Aleiodes sp. 'with gland' 1*. Two filters, both defensible
# without looking at the answer key:
#
#   --exclude-placeholders   names containing sp. / cf. / aff. / quotes /
#                            'environmental sample' / 'uncultured' /
#                            'unclassified' / 'metagenome'. These are
#                            PROVISIONAL designations for organisms nobody has
#                            named yet. No paper writes them as a mention, so
#                            removing them cannot remove a right answer.
#   --ranks-only             keep taxa whose rank is a real Linnaean rank.
#                            Most virus strains and isolates sit at 'no rank',
#                            and they are where the common-word collisions live.
#
# Neither filter looks at LINNAEUS gold. Both remove names a research paper
# would never use, which is a claim about NCBI Taxonomy, not about this corpus.
#
#   ./scripts/fix_linnaeus.sh          # everything
#   ./scripts/fix_linnaeus.sh --score  # score only, if the run is already done
set -uo pipefail
cd "$(dirname "$0")/.."

if [ "${1:-}" != "--score" ]; then

echo "=== 1 · a cleaner taxonomy index ==="
python3 - <<'PY'
import pathlib, re, sqlite3, sys, time
sys.path.insert(0, ".")
from ladder.registry import normalise_term

DUMP = pathlib.Path("data/taxonomy")
OUT = pathlib.Path("ladder/cache/taxonomy-clean.sqlite")

# Provisional designations. An organism nobody has named yet cannot be the
# right answer for a mention in a paper, so dropping these cannot drop a
# correct code — which is what makes this a filter and not a tuning knob.
JUNK = re.compile(r"\b(sp|cf|aff|nr)\.|['\"]|environmental sample|uncultured|"
                  r"unclassified|metagenome|unidentified|symbiont of", re.I)
# Real Linnaean ranks. 'no rank' is where virus strains and isolates sit, and
# where 'Human rotavirus' collides with the token 'human'.
RANKS = {"superkingdom", "kingdom", "phylum", "class", "order", "family",
         "genus", "species", "subspecies", "subfamily", "suborder", "tribe"}

def rows(p):
    with p.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            yield [c.strip() for c in line.rstrip("\n").rstrip("|").split("\t|")]

t0 = time.time()
ranks = {}
for f in rows(DUMP / "nodes.dmp"):
    if len(f) >= 3:
        ranks[f[0]] = f[2]
keep = {k for k, v in ranks.items() if v in RANKS}
print(f"  ranks: {len(keep):,} of {len(ranks):,} taxa at a real Linnaean rank")

tmp = OUT.with_suffix(".building")
if tmp.exists(): tmp.unlink()
db = sqlite3.connect(tmp)
db.executescript("""
 PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;
 CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
 CREATE TABLE concept(id TEXT PRIMARY KEY, active INT, is_finding INT, is_finding_hist INT);
 CREATE TABLE description(concept_id TEXT, term TEXT, norm TEXT, fsn INT);
""")
SPECIES = {"species", "subspecies"}
db.executemany("INSERT OR IGNORE INTO concept VALUES (?,?,?,?)",
               [(t, 1, int(ranks[t] in SPECIES), 1) for t in keep])

batch, kept, seen, dropped = [], 0, 0, 0
for f in rows(DUMP / "names.dmp"):
    if len(f) < 4: continue
    tid, name, cls = f[0], f[1], f[3]
    if cls != "scientific name" or tid not in keep:
        continue
    seen += 1
    if JUNK.search(name):
        dropped += 1
        continue
    n = normalise_term(name)
    if not n: continue
    batch.append((tid, name, n, 1)); kept += 1
    if len(batch) >= 50000:
        db.executemany("INSERT INTO description VALUES (?,?,?,?)", batch); batch.clear()
if batch:
    db.executemany("INSERT INTO description VALUES (?,?,?,?)", batch)
db.executescript("CREATE INDEX d_concept ON description(concept_id);"
                 "CREATE INDEX d_norm ON description(norm);")
db.executemany("INSERT INTO meta VALUES (?,?)", [
    ("release", f"NCBI Taxonomy, real Linnaean ranks only, {kept:,} scientific names"),
    ("filters", "rank in a real Linnaean rank (drops 'no rank', where virus "
                "strains and isolates live); names with sp./cf./quotes/"
                "environmental-sample markers dropped as provisional"),
    ("built", time.strftime("%Y-%m-%d %H:%M:%S"))])
db.commit(); db.close(); tmp.replace(OUT)
print(f"  names: {kept:,} kept, {dropped:,} dropped as provisional, of {seen:,}")
print(f"  {OUT} · {OUT.stat().st_size/1e6:.0f} MB · {time.time()-t0:.0f}s")

# Does the fix actually remove the collisions the records showed?
from ladder.registry import Registry
old, new = Registry("ladder/cache/taxonomy.sqlite"), Registry(OUT)
print("\n  the collisions the last run produced:")
for word in ("human", "rat", "mice", "mouse"):
    for label, reg in (("before", old), ("after ", new)):
        try:
            hits = reg.codes_for_term(word) or []
        except Exception:
            hits = []
        names = [(reg.terms(c) or [""])[0] for c in hits[:3]]
        print(f"    {word:6} {label}  {len(hits):5} match(es)  {names}")
PY

echo
echo "=== 2 · point the arm at it ==="
python3 - <<'PY'
import json, pathlib
p = pathlib.Path("manifest.linnaeus.json"); m = json.loads(p.read_text())
m["vocabulary"]["snomed_db"] = "ladder/cache/taxonomy-clean.sqlite"
m["vocabulary"]["_filter_note"] = (
    "Real Linnaean ranks only, provisional names dropped. The unfiltered index "
    "retrieved *Human rotavirus* for the token 'human' and *Aleiodes sp. \"with "
    "gland\" 1* for 'with sigma' — a lexical retriever over 3.0M names finds a "
    "match for almost any English word. Neither filter looks at LINNAEUS gold.")
p.write_text(json.dumps(m, indent=2) + "\n")
print("  manifest.linnaeus.json -> taxonomy-clean.sqlite")
PY

echo
echo "=== 3 · four cells ==="
rm -rf out/matrix/linnaeus-*
for model in ollama/gpt-oss:20b ollama/llama3.1:8b ollama/mistral:7b-instruct ollama/ibm/granite4:micro-h; do
  MODELS="$model" CORPORA=linnaeus DRAWS=1 RUNGS=0-1 ./scripts/run_matrix.sh 2>&1 \
    | grep -E '^=== |rung [01] \(|FAILED'
done

fi

echo
echo "=== 4 · what changed ==="
PYTHONPATH=. python3 - <<'PY' 2>&1 | grep -v dropped
import glob, json, pathlib, re, sys
sys.path.insert(0, ".")
from ladder.registry import Registry
from ladder.run import _corpus_for, _corpus_opts, _corpus_root

m = json.loads(pathlib.Path("manifest.linnaeus.json").read_text())
docs = _corpus_for(m).load_corpus(_corpus_root(m), **_corpus_opts(m))
ids = json.load(open("data/linnaeus/splits/dev.json"))
ids = ids if isinstance(ids, list) else ids.get("doc_ids", [])
gold = {(x.doc_id, x.spans[0][0]): x.sct
        for d in ids if d in docs for x in docs[d].mentions}
reg = Registry(m["vocabulary"]["snomed_db"])

print(f"\n  {'model':<20} {'recs':>5} {'ACCEPT':>7} {'occ':>7} {'scored':>7} {'correct':>8}")
for d in sorted(glob.glob("out/matrix/linnaeus-*/")):
    model = re.sub(r"^linnaeus-|-d0/?$", "", pathlib.Path(d.rstrip('/')).name)
    fs = [f for f in glob.glob(d + "*.records.jsonl")
          if not re.search(r"\.r\d+\.records\.jsonl$", f)]
    if not fs:
        print(f"  {model:<20} {'no output':>5}"); continue
    f = max(fs, key=lambda x: pathlib.Path(x).stat().st_mtime)
    n = a = s = ok = 0
    ex = []
    for line in open(f):
        r = json.loads(line)
        if not r.get("spans"): continue
        n += 1
        ch = r.get("checks") or {}
        c = r.get("sct") or (ch.get("withheld") or {}).get("sct")
        c = c[0] if isinstance(c, list) and c else c
        if ch.get("r1_verdict") == "ACCEPT":
            a += 1
            g = gold.get((r["doc_id"], r["spans"][0][0]))
            if g is not None:
                s += 1; ok += (c in g)
        if len(ex) < 3 and c:
            ex.append((r.get("text"), (reg.terms(c) or [None])[0]))
    rate = f"{ok/s:.1%}" if s else "—"
    print(f"  {model:<20} {n:5} {a:7} {a/n if n else 0:6.1%} {s:7} {rate:>8}")
    for t, term in ex:
        print(f"      {t!r:32} -> {term!r}")
print("\n  Before this fix: gpt-oss 7 ACCEPT of 35, the other three models 0.\n")
PY
