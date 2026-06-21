"""Download community item icons listed in icons_src.json, resize them, and write
icons.json (item name -> local png path). Re-runnable; safe (web + small files).

Replace these with pristine pak-extracted icons later for true originals.
"""
import io
import json
import os
import re
import urllib.request

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "icons_src.json")
OUT_DIR = os.path.join(HERE, "icons")
INDEX = os.path.join(HERE, "icons.json")
SIZE = (160, 160)


def slug(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def main():
    with open(SRC, encoding="utf-8") as fh:
        src = json.load(fh).get("icons", {})
    os.makedirs(OUT_DIR, exist_ok=True)
    index = {}
    ok = 0
    for name, url in src.items():
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            data = urllib.request.urlopen(req, timeout=30).read()
            img = Image.open(io.BytesIO(data)).convert("RGBA")
            img.thumbnail(SIZE, Image.LANCZOS)
            fn = slug(name) + ".png"
            img.save(os.path.join(OUT_DIR, fn))
            index[name] = "icons/" + fn
            ok += 1
            print("ok  ", name)
        except Exception as e:
            print("FAIL", name, repr(e))
    with open(INDEX, "w", encoding="utf-8") as fh:
        json.dump(index, fh, indent=2)
    print(f"\n{ok}/{len(src)} icons -> {OUT_DIR}\nindex -> {INDEX}")


if __name__ == "__main__":
    main()
