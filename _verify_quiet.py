"""Quiet verification of the co-op + history additions: windows stay withdrawn,
no banners, no disk writes (save_config is stubbed). Safe to run mid-game."""
import sys, time
import overlay

overlay.save_config = lambda cfg: None          # don't touch the real config

results = []
def check(n, c, e=""):
    results.append((n, bool(c), str(e)))

app = overlay.OverlayApp()
app.root.withdraw()
app.cfg["sound"] = False
app.cfg["voice"] = False

# stats
app.cfg["history"] = [2_000_000.0 + g for g in (0, 3000, 6240, 9720)]
s = app.compute_stats()
check("stats n=3", s["n"] == 3, s["n"])
check("stats mean ~3240", abs(s["mean"] - 3240) < 1, s["mean"])
check("stats spread 30..300", 30 <= s["spread"] <= 300, s["spread"])
check("stats min/max", s["min"] == 3000 and s["max"] == 3480, (s["min"], s["max"]))

# delete_mark
app.cfg["history"] = [100.0, 200.0, 300.0]
app.delete_mark(1)
check("delete_mark middle", app.cfg["history"] == [100.0, 300.0], app.cfg["history"])

# co-op prefers learned cadence even with auto-calibrate off
app.cfg["history"] = [2_000_000.0 + g for g in (0, 3240, 6480)]
app.cfg["auto_calibrate"] = False
app.cfg["coop_client"] = True
app.cfg["cycle_seconds"] = 3000
check("coop prefers learned", abs(app.effective_cycle() - 3240) < 5, app.effective_cycle())

# co-op display path executes without error
app.running = True; app.rupture_active = False; app.paused = False
app.deadline = time.monotonic() + 1000
app.next_epoch = time.time() + 1000
try:
    app._update_display()
    check("coop _update_display ok", True)
except Exception as e:
    check("coop _update_display ok", False, repr(e))

# history window builds and lists all marks
app.cfg["history"] = [1000.0, 1000.0 + 3240, 1000.0 + 6480]
try:
    hw = overlay.HistoryWindow(app)
    hw.withdraw()
    app.root.update_idletasks()
    rows = len(hw.tree.get_children())
    check("history window rows==3", rows == 3, rows)
    hw.destroy()
except Exception as e:
    check("history window builds", False, repr(e))

# toggle_coop both ways
app.toggle_coop(False); check("toggle_coop off", app.cfg["coop_client"] is False)
app.toggle_coop(True);  check("toggle_coop on", app.cfg["coop_client"] is True)

# merged recipe search panel builds, loads data, and filters
try:
    rw = overlay.RecipeWindow(app)
    rw.withdraw()
    app.root.update_idletasks()
    check("recipe panel loaded recipes", len(rw.matches) >= 10, len(rw.matches))
    rw.query.set("titanium")
    check("recipe filter has matches", len(rw.matches) > 0, len(rw.matches))
    check("recipe filter relevant", any("titanium" in m["output"].lower() for m in rw.matches),
          [m["output"] for m in rw.matches][:3])
    # pictures
    check("icons loaded (>=15)", len(rw.icons) >= 15, len(rw.icons))
    check("icon resolves (Titanium Bar)", rw._icon("Titanium Bar", 40) is not None)
    rw._show(rw.matches[0])
    check("recipe _show with icons ok", True)
    rw.destroy()
except Exception as e:
    check("recipe panel builds", False, repr(e))

app.quit()

ok = all(c for _, c, _ in results)
for n, c, e in results:
    print(("PASS" if c else "FAIL"), "-", n, ("" if not e else f"  [{e}]"))
print("\n=== ALL PASS ===" if ok else "\n=== SOME FAILED ===")
sys.exit(0 if ok else 1)
