# Data tools (advanced / optional)

These regenerate the overlay's data from **your own copy of the game**. You do
**not** need them to use the overlay — they only refresh `recipes.json` and the
item icons (e.g. after a game patch). Game art is intentionally not shipped in
this repo; this is how you produce it locally.

> ⚠️ These are reverse-engineering / memory-injection tools. Use them only on a
> game you own, for personal use. Distributing extracted game assets may infringe
> Creepy Jar's copyright, and injecting into the game may breach its EULA. You are
> responsible for how you use them.

## recipe-dumper — real per-craft recipe inputs

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
