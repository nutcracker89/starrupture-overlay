"""Match extracted game item-icon PNGs to recipe items that currently lack an icon,
copy them into the overlay's icons/ folder, and update icons.json. Fills gaps only
(keeps existing community icons). Prefers the plain item icon over Blueprint/RecV2."""
import json, re, os, shutil, glob

SRC = r"F:\sr_extract\out"
ROOT = r"F:\starrupture_timer"
ICONS_JSON = os.path.join(ROOT, "icons.json")

def norm(s): return re.sub(r"[^a-z0-9]", "", s.lower())

def variant_pri(fn):
    low = fn.lower()
    if "recv2" in low or "rec_v2" in low: return 2
    if "blueprint" in low: return 1
    return 0  # plain item icon = best

# build normalized-key -> best png
cand = {}
for path in glob.glob(os.path.join(SRC, "*.png")):
    fn = os.path.splitext(os.path.basename(path))[0]
    key = re.sub(r"^T_", "", fn)
    key = re.sub(r"_?Icon$", "", key)
    key = re.sub(r"(?i)blueprint", "", key)
    key = re.sub(r"(?i)_?recv2", "", key)
    nk = norm(key)
    pri = variant_pri(fn)
    if nk and (nk not in cand or pri < cand[nk][0]):
        cand[nk] = (pri, path, fn)

recipes = json.load(open(os.path.join(ROOT, "recipes.json"), encoding="utf-8"))["recipes"]
icons = json.load(open(ICONS_JSON, encoding="utf-8"))
existing = {norm(k) for k in icons}

items = {}
for r in recipes:
    items[r["output"]] = 1
    for i in r["inputs"]:
        items[i["item"]] = 1

added, matched_list, missing_list = 0, [], []
for disp in sorted(items):
    nk = norm(disp)
    if nk in existing:
        continue
    if nk in cand:
        slug = re.sub(r"[^a-z0-9]+", "_", disp.lower()).strip("_")
        rel = f"icons/{slug}.png"
        shutil.copy(cand[nk][1], os.path.join(ROOT, rel))
        icons[disp] = rel
        existing.add(nk)
        added += 1
        matched_list.append(f"{disp}  <-  {cand[nk][2]}")
    else:
        missing_list.append(disp)

json.dump(icons, open(ICONS_JSON, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
print(f"added {added} game icons -> icons.json now {len(icons)} entries")
print(f"\n--- still missing ({len(missing_list)}) ---")
print(", ".join(missing_list))
print(f"\n--- sample matches ---")
print("\n".join(matched_list[:25]))
