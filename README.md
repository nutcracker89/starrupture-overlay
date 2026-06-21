# StarRupture Overlay

An always-on-top **game overlay** for [StarRupture](https://store.steampowered.com/app/2547460/StarRupture/)
with two tools in one standalone Windows app:

1. **Rupture timer** — counts down to the next *rupture* and fires staged warnings
   (on-screen flash, sound, voice) so you can get to a Habitat before it hits.
2. **Recipe search** — a summon-by-hotkey panel with real per-craft inputs and the
   game's item icons, in a Satisfactory/StarRupture-style UI.

> Unofficial, fan-made, not affiliated with Creepy Jar. Windows only.

---

## Run it

Run from source:

```
pip install -r requirements.txt
python overlay.py
```

…or build the standalone exe (no Python needed afterwards):

```
build.bat
```

…which produces **`dist\StarRuptureTimer.exe`**. Double-click to launch.

> **Run the game in borderless / windowed mode.** Always-on-top overlays show over
> borderless windowed games but are usually hidden by exclusive fullscreen.

---

## Hotkeys (work even while the game is focused)

| Hotkey        | Action                                                            |
|---------------|------------------------------------------------------------------|
| `Ctrl+Alt+R`  | **Sync** — press the moment a rupture ends; (re)starts the cycle  |
| `Ctrl+Alt+F`  | Open the **recipe search** panel                                 |
| `Ctrl+Alt+P`  | Pause / resume the countdown                                      |
| `Ctrl+Alt+H`  | Hide / show the countdown HUD                                     |
| `Ctrl+Alt+L`  | Lock / unlock (click-through — clicks pass to the game)           |
| `Ctrl+Alt+C`  | Toggle **co-op / client** timing mode (estimate band)            |
| `Ctrl+Alt+Y`  | Open **History & Stats**                                          |
| `Ctrl+Alt+S`  | Open Settings                                                     |
| `Ctrl+Alt+Q`  | Quit                                                             |

You can also **right-click the HUD** for the menu and **drag it** anywhere (its
position is remembered). Right-click is unavailable while *locked*.

---

## The timer

- **Cycle defaults to 54:00**, based on the real measured ~53–55 min between
  ruptures (the in-game/web "30 min" is not what actually happens). Adjust it in **Settings**.
- The overlay can't read the game, so it works off the **manual sync hotkey**
  (`Ctrl+Alt+R`): press it the instant a rupture ends and it counts down the cycle.
- **Staged alerts** before each rupture (flash + beep + voice): *HEADS UP* (15 min),
  *WARNING* (5 min), *DANGER* (1 min), *RUPTURE* (0:00). All lead times, cycle
  length, opacity, font size, and sound/voice toggles are editable in Settings.
- **Set it manually** in Settings: next rupture at `HH:MM`, next rupture in `N` min,
  or anchor to the last rupture's `HH:MM` + cycle.

### Auto-calibrate

Every rupture you mark is logged; with **Auto-calibrate** on, the app averages the
real gaps between marks and uses that as the cycle — so it gets more accurate the
more you log (the HUD shows e.g. `auto 54:12 · n6`). A missed mark (~2× gap) is
split before averaging. **History & Stats** (`Ctrl+Alt+Y`) shows the log, averages,
spread, and CSV export.

### Co-op / client mode (`Ctrl+Alt+C`)

In co-op the rupture is host/server-driven, so a client can't predict it exactly.
This mode shows the countdown as an **estimate with an uncertainty band** and fires
warnings **early** to cover the spread.

---

## The recipe panel (`Ctrl+Alt+F`)

A centered, stepped-edge panel: filter rail · search + recipe card · favorites.
Shows each item's **real per-craft inputs and quantities** with the game's icons.

- **Recipe data** (`recipes.json`) is included — 177 recipes, real inputs extracted
  from the live game.
- **Item icons are not included** in this repo (they're Creepy Jar's copyrighted
  art). Without them the panel shows clean text tiles. To get the real icons,
  generate them from your own copy of the game with
  [`tools/icon-extractor`](tools/README.md), which fills `icons/` locally.

`recipes.json` is bundled into the exe **and** read from next to the exe if present
— so you can drop in updated/extracted data without rebuilding.

---

## Refreshing the data (advanced)

After a game patch, regenerate recipes/icons from your own game copy — see
[`tools/`](tools/README.md) (a C++ injector for recipes, a CUE4Parse extractor for
icons). Not needed for normal use.

---

## Notes

- Windows only. The timer uses only the Python standard library (`tkinter`,
  `ctypes`, `winsound`, `subprocess`); the recipe panel adds **Pillow** for icon rendering.
- Settings are saved to `%LOCALAPPDATA%\StarRuptureTimer\config.json`.
- Voice uses the built-in Windows SAPI voice via PowerShell; no setup needed.

## Credits

- **Creepy Jar** — StarRupture and all game assets/data.
- **[AlienX's StarRupture SDK](https://github.com/AlienXAXS/StarRupture-Game-SDK)** —
  reflection offsets and `.usmap` mappings used by the data tools.
- **[CUE4Parse](https://github.com/FabianFG/CUE4Parse)** — UE asset parsing for icon extraction.

## License

[MIT](LICENSE) for the source code. Game assets are not covered and are not redistributed here.
