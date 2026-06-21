# Data generator (`srextract`)

Generates the overlay's data from **your own copy of StarRupture** — both the recipe
list and the item icons. No game data is shipped in this repo, so this is how you
populate the recipe panel.

## Easiest: the prebuilt exe

1. Download **`srextract.exe`** from the repo's [Releases](../../releases).
2. Put it in your overlay folder (next to `overlay.py`).
3. **Double-click it.**

It will:
- auto-detect your Steam install of StarRupture,
- download the UE mappings (`.usmap`) from [AlienX's SDK](https://github.com/AlienXAXS/StarRupture-Game-SDK) if you don't have one,
- generate **`recipes.json`** from the game's recipe assets (real inputs/outputs, ~185 recipes) — only if you don't already have one,
- export the item icons and fill `icons/` + write `icons.json`.

Then run the overlay (or `build.bat`) and the recipe panel is fully populated. Most
crafted items get a game icon; raw-ore variants and a few others stay as text tiles.
Machine/station per recipe isn't populated by the local generator.

> Needs the game installed and internet on first run (for the mappings + the oodle
> dll CUE4Parse downloads once). You own the game — extracting its art for your own
> use is the clean line; **don't redistribute the extracted PNGs.**

**Options** (if auto-detect can't find something):
```
srextract.exe --paks "D:\...\StarRupture\StarRupture\Content\Paks"
srextract.exe --usmap "C:\path\to\Client.usmap"
srextract.exe --overlay "C:\path\to\overlay-folder"
```

## Build it yourself

`Program.cs` + `extract.csproj`. Requires **.NET 10 SDK** and **git**. The NuGet
release of CUE4Parse can't read UE5.6 IoStore container headers, so it must be
built from master — `build.bat` clones it and publishes a self-contained exe:

```
build.bat   ->   publish\srextract.exe
```

## Python alternative (FModel route)

If you'd rather use [FModel](https://fmodel.app) (GUI) to export
`Game/Chimera/UI/ItemIcons/` as PNGs, then `match_icons.py` + `match_aliases.py`
copy/rename them into `../icons/` and update `../icons.json`. `usmap_v4_to_v3.py`
is only needed for older CUE4Parse (FModel and master read v4 directly).
