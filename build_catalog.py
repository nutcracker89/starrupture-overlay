"""Crawl gmtreks per-item pages to build a COMPLETE catalog: name, machine,
output qty, unlock, description, and icon for every item. Per-craft INPUTS are
not published by the community, so they're left empty + flagged inputs_unknown
(pending pak extraction); accurate seed inputs already in recipes.json are kept.
"""
import html
import io
import json
import os
import re
import urllib.request

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
RECIPES = os.path.join(HERE, "recipes.json")
ICONS_DIR = os.path.join(HERE, "icons")
ICONS_JSON = os.path.join(HERE, "icons.json")

KNOWN = ["Basic Item Printer", "Mega Press", "Pyro Forge", "Compounder",
         "Recipe Station", "Smelter", "Fabricator", "Furnace"]
RAW = {"helium-3", "sulbon", "figler", "purfins", "serpent sticks"}


def get(u):
    req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=25).read().decode("utf-8", "ignore")


def clean(h):
    h = re.sub(r"<script.*?</script>", " ", h, flags=re.S)
    h = re.sub(r"<style.*?</style>", " ", h, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", h))).strip()


def slug(n):
    return re.sub(r"[^a-z0-9]+", "_", n.lower()).strip("_")


# preserve accurate inputs/time already present
seed = {}
try:
    for r in json.load(open(RECIPES, encoding="utf-8")).get("recipes", []):
        seed[r["output"]] = r
except Exception:
    pass

recipes, icon_urls = [], {}
for n in range(1, 144):
    try:
        h = get("https://gmtreks.com/starrupture/recipe/%d" % n)
    except Exception:
        continue
    mt = re.search(r"<title>(.*?) Recipes List", h)
    if not mt:
        continue
    name = html.unescape(mt.group(1)).strip()
    iu = re.search(r"https://lh3\.googleusercontent\.com/[A-Za-z0-9_\-]+=w\d+", h)
    if iu:
        icon_urls[name] = iu.group(0)
    t = clean(h)
    ci = t.find("Item Type")          # skip the table-of-contents; real content starts here
    if ci != -1:
        t = t[ci:]

    def grab(a, b):
        m = re.search(re.escape(name) + " " + a + r" (.*?) " + re.escape(name) + " " + b, t)
        return m.group(1).strip() if m else ""

    crafted = grab("Crafted In", "Crafting Requirements")
    machines = [k for k in KNOWN if k in crafted]
    machine = " / ".join(dict.fromkeys(machines)) or (crafted or "?")
    mo = re.search(re.escape(name) + r" Output " + re.escape(name) + r" x ([\d,]+)", t)
    oq = int(mo.group(1).replace(",", "")) if mo else None
    unlock = re.sub(r"\s*\?\s*", " ", grab("Research Requirements", "Crafted In")).strip()
    unlock = None if (not unlock or unlock.upper() == "N/A") else unlock
    desc = grab("Description / Effect", "Research Requirements") or None

    s = seed.get(name)
    inputs = s.get("inputs") if (s and s.get("inputs")) else []
    time_s = s.get("time_s") if s else None
    raw_item = name.lower() in RAW or name.lower().endswith(" ore")
    recipes.append({
        "output": name, "output_qty": oq, "machine": machine, "time_s": time_s,
        "inputs": inputs, "inputs_unknown": (not inputs) and (not raw_item),
        "unlock": unlock, "description": desc,
    })
    print("ok", n, name.encode("ascii", "replace").decode())

if len(recipes) < 50:
    raise SystemExit("Crawl returned too few (%d) -- aborting, recipes.json untouched" % len(recipes))

# icons
os.makedirs(ICONS_DIR, exist_ok=True)
idx = {}
for name, url in icon_urls.items():
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        data = urllib.request.urlopen(req, timeout=30).read()
        im = Image.open(io.BytesIO(data)).convert("RGBA")
        im.thumbnail((160, 160), Image.LANCZOS)
        fn = slug(name) + ".png"
        im.save(os.path.join(ICONS_DIR, fn))
        idx[name] = "icons/" + fn
    except Exception as e:
        print("icon FAIL", name.encode("ascii", "replace").decode(), e)
json.dump(idx, open(ICONS_JSON, "w", encoding="utf-8"), indent=2)

out = {
    "_meta": {
        "source": "gmtreks crawl: complete catalog (name/machine/output/unlock/desc/icon). "
                  "Per-craft INPUTS not published by community -> inputs_unknown, pending pak extraction. "
                  "Accurate seed inputs (starrupture.net) preserved.",
        "schema": "recipes[]: output, output_qty, machine, time_s, inputs[]:{item,qty}, "
                  "inputs_unknown, unlock, description",
    },
    "recipes": sorted(recipes, key=lambda r: r["output"].lower()),
}
json.dump(out, open(RECIPES, "w", encoding="utf-8"), indent=2)
print("\n%d recipes, %d icons -> recipes.json / icons.json" % (len(recipes), len(idx)))
