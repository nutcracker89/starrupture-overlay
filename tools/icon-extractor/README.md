# Icon extractor (`srextract`)

Pulls the **real item icons** out of your own copy of StarRupture and drops them
into the overlay's `icons/` folder. Game art isn't shipped in this repo, so this is
how you get the pictures.

## Easiest: the prebuilt exe

1. Download **`srextract.exe`** from the repo's [Releases](../../releases).
2. Put it in your overlay folder (next to `overlay.py` / `recipes.json`).
3. **Double-click it.**

It will:
- auto-detect your Steam install of StarRupture,
- download the UE mappings (`.usmap`) from [AlienX's SDK](https://github.com/AlienXAXS/StarRupture-Game-SDK) if you don't have one,
- export the item icons, match them to the recipes, and fill `icons/` + update `icons.json`.

Then run the overlay (or `build.bat`) and the real icons show up. ~179 of the items
get a game icon; a handful with no in-game icon stay as text tiles.

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
