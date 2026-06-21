"""Merge the UE4SS live dump (recipes_final2.json, real per-craft inputs) into the
overlay catalog (recipes.json: gmtreks icons/machine/unlock/description).
Names matched by normalization (BasicBuildingMaterial <-> 'Basic Building Material')."""
import json, re
from collections import defaultdict

BASE = r"F:\starrupture_timer"
dump = json.load(open(BASE + r"\recipes_final2.json", encoding="utf-8"))
catobj = json.load(open(BASE + r"\recipes.json", encoding="utf-8"))
cat = catobj["recipes"]
icons = json.load(open(BASE + r"\icons.json", encoding="utf-8"))
json.dump(catobj, open(BASE + r"\recipes_catalog_backup.json", "w", encoding="utf-8"), indent=2)

def norm(s): return re.sub(r"[^a-z0-9]", "", (s or "").lower())
def pretty(s):
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", s)   # camelCase -> spaced
    return s.strip() or s

disp = {norm(r["output"]): r["output"] for r in cat}          # normalized -> catalog display name
cat_by = {norm(r["output"]): r for r in cat}

def dname(fname):
    return disp.get(norm(fname)) or pretty(fname)

groups = defaultdict(list)
for r in dump:
    if r.get("output") and r["output"] != "?":
        groups[norm(r["output"])].append(r)

def pick(recs):
    out_n = norm(recs[0]["output"])
    noncirc = [r for r in recs if all(norm(i["item"]) != out_n for i in r.get("inputs", []))]
    pool = [r for r in (noncirc or recs) if r.get("inputs")] or recs
    return max(pool, key=lambda r: (r.get("output_qty") or 0))

merged = {}
for n, recs in groups.items():
    r = pick(recs)
    c = cat_by.get(n)
    merged[n] = {
        "output": dname(r["output"]),
        "output_qty": r.get("output_qty"),
        "machine": (c.get("machine") if c else None),
        "time_s": (c.get("time_s") if c else None),
        "inputs": [{"item": dname(i["item"]), "qty": i.get("qty")} for i in r.get("inputs", [])],
        "inputs_unknown": False,
        "unlock": (c.get("unlock") if c else None),
        "description": (c.get("description") if c else None),
    }
# keep catalog-only items (raw ores etc. with no crafting recipe)
for n, c in cat_by.items():
    if n not in merged:
        merged[n] = {
            "output": c["output"], "output_qty": c.get("output_qty"),
            "machine": c.get("machine"), "time_s": c.get("time_s"),
            "inputs": c.get("inputs", []), "inputs_unknown": False,
            "unlock": c.get("unlock"), "description": c.get("description"),
        }

recipes = sorted(merged.values(), key=lambda r: r["output"].lower())
out = {"_meta": {"source": "UE4SS live dump (CrItemRecipeData) + gmtreks catalog (icons/machine/unlock). Real per-craft inputs."},
       "recipes": recipes}
json.dump(out, open(BASE + r"\recipes.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)

icon_hits = sum(1 for r in recipes if norm(r["output"]) in {norm(k) for k in icons})
print(f"{len(recipes)} recipes  |  {sum(1 for r in recipes if r['inputs'])} with inputs  |  ~{icon_hits} with icons")
