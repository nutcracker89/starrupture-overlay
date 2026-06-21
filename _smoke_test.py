"""Headless-ish smoke test: drives the real Tk timer logic and asserts results,
then tears itself down. Sound/voice are disabled so it runs silently."""
import sys, time
import overlay

results = []
def check(name, cond, extra=""):
    results.append((name, bool(cond), str(extra)))

# pure functions
check("fmt 0", overlay.fmt_mmss(0) == "0:00", overlay.fmt_mmss(0))
check("fmt 65", overlay.fmt_mmss(65) == "1:05", overlay.fmt_mmss(65))
check("fmt 3240", overlay.fmt_mmss(3240) == "54:00", overlay.fmt_mmss(3240))

app = overlay.OverlayApp()
app.cfg["sound"] = False
app.cfg["voice"] = False

def guard(fn):
    try:
        fn()
    except Exception as e:
        check("EXCEPTION in " + fn.__name__, False, repr(e))

def step1():
    app.sync()
    check("running after sync", app.running)
    check("fired empty on full sync", len(app.fired) == 0, app.fired)
    txt = app.time_label.cget("text")
    check("hud shows countdown", txt not in ("--:--", "RUPTURE"), txt)
    check("next epoch ~ now+cycle",
          app.next_epoch > time.time() + app.cfg["cycle_seconds"] - 5)
    # switch to a fast cycle to watch the staged alerts + rupture quickly
    app.cfg["cycle_seconds"] = 4
    app.cfg["stages_minutes"] = [0.05, 0.03, 0.02]   # 3.0s / 1.8s / 1.2s
    app.rebuild_stages()
    check("3 stages built", len(app.stages) == 3, [s["sec"] for s in app.stages])
    app.sync()

def step3():
    check("rupture active after fast cycle", app.rupture_active,
          f"fired={len(app.fired)}")
    check("all 3 stages fired", len(app.fired) == 3, app.fired)
    check("hud shows RUPTURE", app.time_label.cget("text") == "RUPTURE",
          app.time_label.cget("text"))

def step_anchor():
    app.rupture_active = False
    app.cfg["history"] = []                    # isolate: test manual anchor math
    app.cfg["auto_calibrate"] = False
    app.cfg["cycle_seconds"] = 3600
    lt = time.localtime(time.time() - 1800)   # pretend rupture ended 30 min ago
    app.set_last_rupture_clock(lt.tm_hour, lt.tm_min)
    rem = app.deadline - time.monotonic()
    check("anchor ~30 min remaining", 1680 < rem < 1920, f"{rem:.0f}s")

def step_next_in():
    app.set_next_in(20)                       # next rupture in 20 minutes
    rem = app.deadline - time.monotonic()
    check("set_next_in 20 -> ~1200s", 1195 < rem < 1205, f"{rem:.0f}s")
    nxt = app.next_label.cget("text")
    check("hud shows a next-rupture time", "next rupture" in nxt, nxt)

def step_next_clock():
    target = time.localtime(time.time() + 600)   # 10 min from now
    app.set_next_rupture_clock(target.tm_hour, target.tm_min)
    rem = app.deadline - time.monotonic()
    # rounds to whole minute, so allow a minute of slack
    check("set_next_clock +10min -> ~600s", 540 < rem < 660, f"{rem:.0f}s")

def step_tracker():
    app.cfg["history"] = []
    base = 1_000_000.0
    for k in (0, 1, 2, 4):                # skip 3 -> a doubled gap to normalize
        app.record_mark(base + k * 3240)
    c, n = app.compute_learned()
    check("learned cycle ~54:00", c is not None and abs(c - 3240) < 5, f"{c} n={n}")
    check("doubled gap normalized (n=3)", n == 3, n)
    app.cfg["auto_calibrate"] = True
    app.cfg["cycle_seconds"] = 3000
    check("auto uses learned not manual", abs(app.effective_cycle() - 3240) < 5,
          app.effective_cycle())
    app.cfg["auto_calibrate"] = False
    check("auto-off uses manual", abs(app.effective_cycle() - 3000) < 1,
          app.effective_cycle())

def step_anchor_clip():
    sw = app.root.winfo_screenwidth()
    app.cfg["hud_right"] = sw - 24
    app.cfg["hud_top"] = 24
    app.time_label.config(font=("Consolas", 60, "bold"))   # force the HUD wider
    app.root.update_idletasks()
    app._anchor_hud()
    app.root.update_idletasks()
    x, w = app.root.winfo_x(), app.root.winfo_width()
    check("HUD right edge on-screen", x + w <= sw, f"x+w={x+w} sw={sw}")
    check("HUD left edge on-screen", x >= 0, f"x={x}")
    check("HUD pinned to right anchor", abs((x + w) - (sw - 24)) <= 2 or x == 0,
          f"x+w={x+w} anchor={sw-24}")

def step_stats():
    # crafted history -> gaps 3000 / 3240 / 3480
    app.cfg["history"] = [2_000_000.0 + g for g in (0, 3000, 6240, 9720)]
    s = app.compute_stats()
    check("stats n=3", s["n"] == 3, s["n"])
    check("stats mean ~54:00", abs(s["mean"] - 3240) < 1, s["mean"])
    check("stats min/max", s["min"] == 3000 and s["max"] == 3480, (s["min"], s["max"]))
    check("stats spread ~196 (clamped 30..300)", 30 <= s["spread"] <= 300 and abs(s["spread"] - 196) < 3,
          f"{s['spread']:.1f}")
    # delete_mark removes the right entry
    app.cfg["history"] = [100.0, 200.0, 300.0]
    app.delete_mark(1)
    check("delete_mark removed middle", app.cfg["history"] == [100.0, 300.0], app.cfg["history"])
    # HistoryWindow builds and lists every mark
    app.cfg["history"] = [1000.0, 1000.0 + 3240, 1000.0 + 6480]
    hw = overlay.HistoryWindow(app)
    app.root.update_idletasks()
    rows = hw.tree.get_children()
    check("history window lists all marks", len(rows) == 3, len(rows))
    hw.destroy()

def step_coop_setup():
    # empty history -> default spread = 90s; one stage at 600s (10 min)
    app.cfg["history"] = []
    app.cfg["coop_client"] = True
    app.cfg["stages_minutes"] = [10]
    app.rebuild_stages()
    state["sp"] = app.compute_stats()["spread"]
    rem = 600 + state["sp"] * 0.5            # in the gap zone: 600 < rem < 600+spread
    app.running = True; app.paused = False; app.rupture_active = False
    app.fired = set()
    app.deadline = time.monotonic() + rem
    app.next_epoch = time.time() + rem

def step_coop_check():
    check("coop default spread = 90s", abs(state.get("sp", 0) - 90) < 0.001, state.get("sp"))
    check("co-op fires alert early (in gap zone)", 600.0 in app.fired, app.fired)
    band = app.next_label.cget("text")
    check("co-op shows estimate band", "–" in band or "low data" in band, band)
    # now non-coop in the same gap zone must NOT fire
    app.cfg["coop_client"] = False
    app.fired = set()
    rem = 600 + state["sp"] * 0.5
    app.deadline = time.monotonic() + rem
    app.next_epoch = time.time() + rem

def step_noncoop_check():
    check("non-coop does NOT fire in gap zone", 600.0 not in app.fired, app.fired)

def finish():
    app.quit()

app.root.after(150, lambda: guard(step1))
app.root.after(4600, lambda: guard(step3))
app.root.after(4800, lambda: guard(step_anchor))
app.root.after(4900, lambda: guard(step_next_in))
app.root.after(5000, lambda: guard(step_next_clock))
app.root.after(5050, lambda: guard(step_tracker))
app.root.after(5100, lambda: guard(step_anchor_clip))
app.root.after(5150, lambda: guard(step_stats))
app.root.after(5300, lambda: guard(step_coop_setup))
app.root.after(5750, lambda: guard(step_coop_check))
app.root.after(6200, lambda: guard(step_noncoop_check))
app.root.after(6500, finish)
app.root.after(12000, lambda: app.root.destroy())   # hard safety net

app.run()

ok = all(c for _, c, _ in results)
for name, c, extra in results:
    print(("PASS" if c else "FAIL"), "-", name, ("" if not extra else f"  [{extra}]"))
print("\n=== ALL PASS ===" if ok else "\n=== SOME FAILED ===")
sys.exit(0 if ok else 1)
