import json, pathlib, inspect
from collections import Counter
from ladder.registry import Registry
from ladder import corpus as C

man = json.loads(pathlib.Path("manifest.json").read_text())
reg = Registry(man["vocabulary"]["snomed_db"])

root = man.get("corpus", {}).get("root") or "data/cadec"
docs = C.load_corpus(root)
print("documents:", len(docs))

golds = C.gold_records(docs, list(docs))
print("gold mentions:", len(golds))
print("GoldMention fields:", [f for f in vars(golds[0])] if golds else "none")

codes, per_type = set(), Counter()
for g in golds:
    d = g.to_dict()
    sct = d.get("sct") or d.get("codes") or []
    if isinstance(sct, str):
        sct = [sct]
    ent = d.get("type") or d.get("label") or "?"
    for c in sct:
        c = str(c)
        codes.add(c)
        per_type[(ent, c)] += 0
print("distinct codes:", len(codes))
print("sample:", sorted(codes)[:5])

c, absent = Counter(), []
for code in codes:
    if not reg.exists(code):
        c["absent"] += 1; absent.append(code)
    elif reg.is_active(code):
        c["active"] += 1
    else:
        c["inactive"] += 1
print(dict(c), "sum:", sum(c.values()))
print("absent:", sorted(absent))
