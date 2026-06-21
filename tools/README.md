# Data tools (advanced / optional)

These generate the overlay's data from **your own copy of the game** — recipes and
item icons. **No game data is shipped in this repo**; this is how you produce it
locally. For normal use just grab `srextract.exe` from Releases (see
[`icon-extractor`](icon-extractor/README.md)) — it does recipes *and* icons in one
double-click. The rest here is the source / a legacy alternative.

> ⚠️ These read/parse game files (and the legacy dumper injects into the game).
> Use them only on a game you own, for personal use. Don't redistribute the
> generated data/art, and note injection may breach the game's EULA. You're
> responsible for how you use them.

## icon-extractor (`srextract`) — recipes + icons from the .pak  ⭐ use this

The main tool. A [CUE4Parse](https://github.com/FabianFG/CUE4Parse) program that
mounts the game's UE5.6 IoStore, generates `recipes.json` from the `CR_*` recipe
assets, and exports item icons — see [`icon-extractor/README.md`](icon-extractor/README.md).

## recipe-dumper — legacy live-memory recipe dumper

> Superseded by `srextract` (which reads recipes straight from the paks, no
> injection). Kept for reference.

A C++ DLL that reads `CrItemRecipeData` from the live game and writes the real
recipe inputs to JSON.

- `recipe_dumper.cpp` — the injected DLL (SEH-guarded memory reads; press **F10**
  in-game to dump). Offsets come from [AlienX's StarRupture SDK](https://github.com/AlienXAXS/StarRupture-Game-SDK)
  (Dumper-7) and are build-specific — update them when the game updates.
- `inject.cpp` — a LoadLibrary injector that loads the DLL into the running game.
- `build.bat` — builds both with MSVC (`vcvars64` + `cl /EHa`).

Run the game, get in-game, run the injector, press F10 → writes a recipes JSON.
Then `../merge_recipes.py` merges it into `recipes.json`.

## icon-extractor — real item icons from the .pak

A headless [CUE4Parse](https://github.com/FabianFG/CUE4Parse) program that mounts
the game's UE5.6 IoStore and exports item-icon textures to PNG.

- `extract.csproj` / `Program.cs` — mounts the paks (needs CUE4Parse **built from
  master source** — the nuget release can't read UE5.6 container headers — and
  **.NET 10**), exports textures from `/Game/Chimera/UI/ItemIcons/`.
- `usmap_v4_to_v3.py` — converts the v4 `.usmap` mappings file to v3 (only needed
  for older CUE4Parse; master reads v4 directly). The `.usmap` comes from AlienX's SDK.
- `match_icons.py` / `match_aliases.py` — copy the exported PNGs into `../icons/`
  and update `../icons.json`, matching by item name.

Then rebuild the overlay (`../build.bat`) to bundle the new icons.

See the project's saved notes for the exact gotchas (UE5.6 container-header
version 5, usmap v4, which usmap to use, etc.).
