"""
StarRupture Overlay Timer
=========================

A personal always-on-top game overlay that counts down to the next "rupture"
and fires staged warnings (on-screen flash + sound + voice) so you can get back
to a Habitat in time.

The overlay can't read the game, so it works off a manual SYNC hotkey: press it
the instant a rupture ends and it counts down the full cycle (default 54:00) to
the next one.

  Ctrl+Alt+R  - Sync: mark "rupture just ended", (re)start the cycle
  Ctrl+Alt+P  - Pause / resume the countdown
  Ctrl+Alt+H  - Hide / show the countdown HUD
  Ctrl+Alt+L  - Lock / unlock (click-through, so clicks pass to the game)
  Ctrl+Alt+S  - Open Settings
  Ctrl+Alt+Q  - Quit

Stdlib only (tkinter, ctypes, winsound, subprocess) -> bundles cleanly with
PyInstaller, no pip dependencies.  Windows only.
"""

import os
import sys
import json
import time
import queue
import threading
import subprocess
import ctypes
from ctypes import wintypes

import tkinter as tk
from tkinter import ttk

import winsound

try:
    from PIL import Image, ImageTk, ImageDraw, ImageFont
    _HAVE_PIL = True
except Exception:
    _HAVE_PIL = False

# --------------------------------------------------------------------------- #
# Windows API plumbing
# --------------------------------------------------------------------------- #

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# Per-monitor-ish DPI awareness so the overlay is crisp and screen coords are
# real pixels (important for snapping the HUD to the true top-right corner).
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_NOREPEAT = 0x4000

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020

CREATE_NO_WINDOW = 0x08000000

user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.RegisterHotKey.restype = wintypes.BOOL
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
user32.UnregisterHotKey.restype = wintypes.BOOL
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = ctypes.c_int
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostThreadMessageW.restype = wintypes.BOOL
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongW.restype = wintypes.LONG
user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG]
user32.SetWindowLongW.restype = wintypes.LONG
kernel32.GetCurrentThreadId.restype = wintypes.DWORD


def set_click_through(window, enabled):
    """Toggle whether mouse clicks pass straight through a tk window."""
    hwnd = window.winfo_id()
    style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    if enabled:
        style |= WS_EX_LAYERED | WS_EX_TRANSPARENT
    else:
        style &= ~WS_EX_TRANSPARENT
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)


# --------------------------------------------------------------------------- #
# Global hotkeys (work even while the game has focus)
# --------------------------------------------------------------------------- #

class HotkeyManager(threading.Thread):
    """Registers system-wide hotkeys and pumps WM_HOTKEY on its own thread.

    Each press puts the hotkey id onto `out_queue`; the tk main loop drains it.
    """

    def __init__(self, bindings, out_queue):
        super().__init__(daemon=True)
        self.bindings = bindings              # list of (id, modifiers, vk)
        self.out_queue = out_queue
        self.thread_id = 0
        self.ready = threading.Event()
        self.failed = []

    def run(self):
        self.thread_id = kernel32.GetCurrentThreadId()
        for hk_id, mods, vk in self.bindings:
            if not user32.RegisterHotKey(None, hk_id, mods | MOD_NOREPEAT, vk):
                self.failed.append(hk_id)
        self.ready.set()

        msg = wintypes.MSG()
        while True:
            res = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if res in (0, -1):           # WM_QUIT or error
                break
            if msg.message == WM_HOTKEY:
                self.out_queue.put(int(msg.wParam))

        for hk_id, _, _ in self.bindings:
            user32.UnregisterHotKey(None, hk_id)

    def stop(self):
        self.ready.wait(timeout=2.0)
        if self.thread_id:
            user32.PostThreadMessageW(self.thread_id, WM_QUIT, 0, 0)


# --------------------------------------------------------------------------- #
# Sound + voice (both run off-thread so the UI never blocks)
# --------------------------------------------------------------------------- #

def play_pattern(pattern):
    """pattern = list of (frequency_hz, duration_ms) beeps."""
    def _run():
        for freq, dur in pattern:
            try:
                winsound.Beep(int(freq), int(dur))
            except Exception:
                pass
    threading.Thread(target=_run, daemon=True).start()


_PS_SPEAK = (
    "Add-Type -AssemblyName System.Speech;"
    "$sp = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
    "$sp.Rate = 1;"
    "$t = [Console]::In.ReadToEnd();"
    "if ($t) { $sp.Speak($t) }"
)


def speak(text):
    """Speak `text` via Windows SAPI (PowerShell System.Speech), off-thread.

    The text is piped over stdin so nothing needs escaping/quoting.
    """
    def _run():
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS_SPEAK],
                input=text, text=True,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW,
            )
        except Exception:
            pass
    threading.Thread(target=_run, daemon=True).start()


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #

APP_NAME = "StarRuptureTimer"

DEFAULT_CONFIG = {
    "cycle_seconds": 54 * 60,          # ~53-55 min measured; manual fallback
    "stages_minutes": [15, 5, 1],      # info / warning / danger lead times
    "alpha": 0.85,                     # HUD opacity
    "font_size": 30,                   # HUD countdown font size
    "sound": True,
    "voice": True,
    "locked": False,
    "hud_right": None,                 # screen-x of HUD right edge (None -> snap top-right)
    "hud_top": None,                   # screen-y of HUD top
    "auto_calibrate": True,            # learn the real cycle from marked ruptures
    "history": [],                     # epoch timestamps of marked ruptures
    "coop_client": False,              # co-op client: server-timed, show estimate band
    "recipe_favorites": [],            # favorited recipe output names
}

# Visual/voice spec by rank: largest lead time = info, smallest = danger.
STAGE_SPECS = [
    {"name": "HEADS UP", "color": "#7fd0ff", "sub": "wrap things up",
     "vsub": "", "beeps": [(700, 140)]},
    {"name": "WARNING", "color": "#ffd23f", "sub": "head back to base",
     "vsub": "Head back to base.", "beeps": [(950, 160), (950, 160)]},
    {"name": "DANGER", "color": "#ff3b30", "sub": "GET TO A HABITAT",
     "vsub": "Get to a habitat now.", "beeps": [(1250, 140), (1250, 140), (1250, 140)]},
]

GREEN = "#5fe08a"
RUPTURE_COLOR = "#ff2d20"
TRANSPARENT_KEY = "#010101"   # banner background color made fully transparent
HUD_BG = "#12161c"
FG = "#dfe7ef"               # recipe panel text
DIM = "#7d8ea0"             # recipe panel dim text
TEAL = "#4dd0e1"            # StarRupture UI accent (cyan)
RKEY = "#ff00ff"            # recipe window transparent-corner key (chamfer)


def config_path():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    folder = os.path.join(base, APP_NAME)
    try:
        os.makedirs(folder, exist_ok=True)
    except Exception:
        folder = os.path.expanduser("~")
    return os.path.join(folder, "config.json")


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    try:
        with open(config_path(), "r", encoding="utf-8") as fh:
            cfg.update(json.load(fh))
    except Exception:
        pass
    return cfg


def save_config(cfg):
    try:
        with open(config_path(), "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, indent=2)
    except Exception:
        pass


def fmt_mmss(seconds):
    seconds = max(0, int(round(seconds)))
    return f"{seconds // 60}:{seconds % 60:02d}"


# --- recipe data (shared with the recipe search panel) --------------------- #

def _candidate_dirs():
    dirs = []
    if getattr(sys, "frozen", False):
        dirs.append(os.path.dirname(sys.executable))     # external override
        if hasattr(sys, "_MEIPASS"):
            dirs.append(sys._MEIPASS)                     # bundled default
    else:
        dirs.append(os.path.dirname(os.path.abspath(__file__)))
    return dirs


def load_recipes():
    for d in _candidate_dirs():
        path = os.path.join(d, "recipes.json")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                return data.get("recipes", []), data.get("_meta", {})
            except Exception:
                return [], {}
    return [], {}


def _qstr(v):
    return "?" if v is None else (f"{v:g}" if isinstance(v, float) else str(v))


def load_icons():
    """item name -> absolute icon path, resolved relative to icons.json's dir."""
    for d in _candidate_dirs():
        path = os.path.join(d, "icons.json")
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as fh:
                    raw = json.load(fh)
                return {name: os.path.join(d, rel) for name, rel in raw.items()}
            except Exception:
                return {}
    return {}


def _nrm(s):
    """Normalize an item name for fuzzy icon matching (case/space/plural-insensitive)."""
    s = "".join(c for c in s.lower() if c.isalnum())
    return s[:-1] if len(s) > 3 and s.endswith("s") else s


def _winfont(size, bold=True):
    base = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    for name in (["segoeuib.ttf", "arialbd.ttf"] if bold else ["segoeui.ttf", "arial.ttf"]):
        p = os.path.join(base, name)
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def render_tile(pil_icon, qty_text, size, accent=(77, 208, 225, 255)):
    """StarRupture-style item tile: chamfered dark card, teal edge, icon, and a
    flat teal quantity chip in the bottom-left -> PIL image."""
    pad = 9
    W = size + pad * 2
    img = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = max(8, size // 9)
    pts = [(0, 0), (W - 1 - c, 0), (W - 1, c), (W - 1, W - 1), (c, W - 1), (0, W - 1 - c)]
    d.polygon(pts, fill=(24, 46, 57, 255))
    d.line(pts + [pts[0]], fill=(46, 104, 120, 255), width=2)
    if pil_icon is not None:
        ic = pil_icon.copy()
        ic.thumbnail((size, size), Image.LANCZOS)
        img.alpha_composite(ic, (pad + (size - ic.width) // 2, pad + (size - ic.height) // 2))
    if qty_text:
        f = _winfont(max(12, size // 4), bold=True)
        bb = d.textbbox((0, 0), qty_text, font=f)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
        bw, bh = tw + 12, th + 7
        x0, y0 = 3, W - bh - 3
        d.rectangle([x0, y0, x0 + bw, y0 + bh], fill=accent)
        d.text((x0 + 6 - bb[0], y0 + 3 - bb[1]), qty_text, font=f, fill=(8, 18, 24, 255))
    return img


def _stepped_pts(L, T, R, B, K=22, S=9):
    """Outline points for one stepped/notched panel from (L,T) to (R,B)."""
    return [
        (L + K, T), (R - K, T),
        (R - K, T + S), (R - S, T + S), (R - S, T + K), (R, T + K),
        (R, B - K),
        (R - S, B - K), (R - S, B - S), (R - K, B - S), (R - K, B),
        (L + K, B),
        (L + K, B - S), (L + S, B - S), (L + S, B - K), (L, B - K),
        (L, T + K),
        (L + S, T + K), (L + S, T + S), (L + K, T + S),
    ]


def render_panels(w, h, rects):
    """Compose several SEPARATE stepped panels onto one transparent image; the
    gaps between them stay magenta (the key colour) so the game shows through."""
    img = Image.new("RGBA", (w, h), (255, 0, 255, 255))   # RKEY -> see-through
    d = ImageDraw.Draw(img)
    K = 22
    for (L, T, R, B) in rects:
        pts = _stepped_pts(L, T, R, B, K=K)
        d.polygon(pts, fill=(18, 22, 28, 255))
        d.line(pts + [pts[0]], fill=(150, 170, 182, 255), width=2)
        d.line([(L + K + 12, T + 4), (R - K - 12, T + 4)], fill=(77, 208, 225, 255), width=1)
    return img


# --------------------------------------------------------------------------- #
# The overlay app
# --------------------------------------------------------------------------- #

HOTKEYS = [
    (1, MOD_CONTROL | MOD_ALT, 0x52, "sync"),      # R
    (2, MOD_CONTROL | MOD_ALT, 0x50, "pause"),     # P
    (3, MOD_CONTROL | MOD_ALT, 0x48, "hide"),      # H
    (4, MOD_CONTROL | MOD_ALT, 0x4C, "lock"),      # L
    (5, MOD_CONTROL | MOD_ALT, 0x53, "settings"),  # S
    (6, MOD_CONTROL | MOD_ALT, 0x51, "quit"),      # Q
    (7, MOD_CONTROL | MOD_ALT, 0x43, "coop"),      # C
    (8, MOD_CONTROL | MOD_ALT, 0x59, "history"),   # Y
    (9, MOD_CONTROL | MOD_ALT, 0x46, "recipes"),   # F
]


class OverlayApp:
    def __init__(self):
        self.cfg = load_config()
        self.learned = (None, 0)      # (cycle_seconds, sample_count) from history
        self._last_w = None
        self._dragging = False

        # timer state
        self.running = False
        self.paused = False
        self.rupture_active = False
        self.deadline = 0.0           # time.monotonic() target
        self.next_epoch = 0.0         # wall-clock epoch of next rupture (display)
        self.pause_remaining = 0.0
        self.fired = set()            # stage seconds already announced this cycle

        self.stages = []
        self.rebuild_stages()

        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self._build_hud()
        self._build_banner()
        self._anchor_hud()
        self.settings_win = None
        self.history_win = None
        self.recipe_win = None

        # hotkeys
        self.hk_queue = queue.Queue()
        self.hk_actions = {hk_id: action for hk_id, _, _, action in HOTKEYS}
        self.hotkeys = HotkeyManager([(i, m, v) for i, m, v, _ in HOTKEYS], self.hk_queue)
        self.hotkeys.start()

        if self.cfg.get("locked"):
            self.root.after(300, lambda: self.set_locked(True))

        self.root.after(50, self._poll_hotkeys)
        self.root.after(200, self._tick)
        self.root.protocol("WM_DELETE_WINDOW", self.quit)

    # ----- stages ------------------------------------------------------ #

    def rebuild_stages(self):
        mins = sorted({float(m) for m in self.cfg["stages_minutes"]}, reverse=True)
        stages = []
        for rank, m in enumerate(mins):
            spec = STAGE_SPECS[min(rank, len(STAGE_SPECS) - 1)]
            sec = m * 60.0
            unit = "minute" if abs(m - 1) < 1e-6 else "minutes"
            mtext = f"{int(m)}" if float(m).is_integer() else f"{m:g}"
            voice = f"{mtext} {unit} to rupture."
            if spec["vsub"]:
                voice += " " + spec["vsub"]
            stages.append({
                "sec": sec,
                "name": spec["name"],
                "color": spec["color"],
                "banner": f"RUPTURE IN {fmt_mmss(sec)}  —  {spec['sub'].upper()}",
                "voice": voice,
                "beeps": spec["beeps"],
            })
        self.stages = stages

    # ----- HUD (top-right countdown) ----------------------------------- #

    def _build_hud(self):
        r = self.root
        r.overrideredirect(True)
        r.attributes("-topmost", True)
        r.attributes("-alpha", float(self.cfg["alpha"]))
        r.configure(bg=HUD_BG)

        pad = tk.Frame(r, bg=HUD_BG, padx=14, pady=8)
        pad.pack()

        self.title_label = tk.Label(pad, text="STARRUPTURE", bg=HUD_BG, fg="#6b7d91",
                                    font=("Segoe UI", 9, "bold"))
        self.title_label.pack(anchor="e")

        self.time_label = tk.Label(pad, text="--:--", bg=HUD_BG, fg=GREEN,
                                   font=("Consolas", int(self.cfg["font_size"]), "bold"))
        self.time_label.pack(anchor="e")

        self.next_label = tk.Label(pad, text="press Ctrl+Alt+R to sync", bg=HUD_BG,
                                   fg="#9fb3c8", font=("Segoe UI", 10))
        self.next_label.pack(anchor="e")

        self.status_label = tk.Label(pad, text="not synced", bg=HUD_BG, fg="#6b7d91",
                                     font=("Segoe UI", 9, "bold"))
        self.status_label.pack(anchor="e")

        self.cycle_label = tk.Label(pad, text="", bg=HUD_BG, fg="#5b6b7d",
                                    font=("Segoe UI", 8))
        self.cycle_label.pack(anchor="e")

        # dragging (anywhere on the HUD)
        for w in (r, pad, self.title_label, self.time_label, self.next_label,
                  self.status_label, self.cycle_label):
            w.bind("<Button-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)
            w.bind("<ButtonRelease-1>", self._drag_end)
            w.bind("<Button-3>", self._popup_menu)

        self._build_menu()

    def _build_menu(self):
        m = tk.Menu(self.root, tearoff=0)
        m.add_command(label="Sync now (rupture ended)", command=self.sync)
        m.add_command(label="Pause / Resume", command=self.toggle_pause)
        m.add_separator()
        m.add_command(label="Settings…", command=self.open_settings)
        m.add_command(label="History & Stats…", command=self.open_history)
        m.add_command(label="Recipe search…", command=self.open_recipes)
        self._coop_var = tk.BooleanVar(value=bool(self.cfg.get("coop_client")))
        m.add_checkbutton(label="Co-op client mode", variable=self._coop_var,
                          command=lambda: self.toggle_coop(self._coop_var.get()))
        self._lock_var = tk.BooleanVar(value=bool(self.cfg.get("locked")))
        m.add_checkbutton(label="Lock (click-through)", variable=self._lock_var,
                          command=lambda: self.set_locked(self._lock_var.get()))
        m.add_command(label="Hide HUD", command=self.toggle_hide)
        m.add_separator()
        m.add_command(label="Quit", command=self.quit)
        self.menu = m

    def _popup_menu(self, event):
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    def _anchor_hud(self):
        """Keep the HUD pinned by its RIGHT edge so it never slides off-screen
        when the content (or font) grows. Clamps fully on-screen.

        Uses winfo_reqwidth/reqheight (the content-required size, valid
        immediately) rather than winfo_width, which lags a frame behind a
        font/text change and would mis-place the window."""
        self.root.update_idletasks()
        w = self.root.winfo_reqwidth()
        h = self.root.winfo_reqheight()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()

        right = self.cfg.get("hud_right")
        top = self.cfg.get("hud_top")
        if right is None:
            right = sw - 24
        if top is None:
            top = 24

        x = int(right) - w
        x = max(0, min(x, sw - w))          # clamp horizontally on-screen
        y = max(0, min(int(top), sh - h))   # clamp vertically on-screen
        self.root.geometry(f"+{x}+{y}")
        self._last_w = w

    def _reanchor_if_resized(self):
        """Re-pin to the right edge if the HUD width changed since last layout."""
        if self._dragging:
            return
        self.root.update_idletasks()
        if self.root.winfo_reqwidth() != self._last_w:
            self._anchor_hud()

    # ----- banner (top-center warnings) -------------------------------- #

    def _build_banner(self):
        b = tk.Toplevel(self.root)
        b.overrideredirect(True)
        b.attributes("-topmost", True)
        b.attributes("-alpha", 1.0)
        b.configure(bg=TRANSPARENT_KEY)
        b.attributes("-transparentcolor", TRANSPARENT_KEY)
        self.banner_label = tk.Label(b, text="", bg=TRANSPARENT_KEY, fg=RUPTURE_COLOR,
                                     font=("Segoe UI", 40, "bold"))
        self.banner_label.pack(padx=24, pady=12)
        b.withdraw()
        self.banner = b
        self._blink_job = None
        self._hide_job = None
        self._blink_on = True
        self._blink_color = RUPTURE_COLOR
        self._blink_persist = False
        self._blink_count = 0
        # the banner must never eat clicks meant for the game
        b.update_idletasks()
        set_click_through(b, True)

    def _center_banner(self):
        self.banner.update_idletasks()
        bw = self.banner.winfo_width()
        sw = self.banner.winfo_screenwidth()
        self.banner.geometry(f"+{(sw - bw) // 2}+40")

    def show_banner(self, text, color, persist=False):
        self._cancel_banner_jobs()
        self.banner_label.config(text=text, fg=color)
        self.banner.deiconify()
        self.banner.lift()
        self._center_banner()
        self._blink_color = color
        self._blink_persist = persist
        self._blink_on = True
        self._blink_count = 0
        self._blink()

    def _blink(self):
        self.banner_label.config(fg=self._blink_color if self._blink_on else TRANSPARENT_KEY)
        self._blink_on = not self._blink_on
        self._blink_count += 1
        if not self._blink_persist and self._blink_count >= 14:
            self.banner_label.config(fg=self._blink_color)
            self._hide_job = self.root.after(2200, self._hide_banner)
            return
        self._blink_job = self.root.after(350, self._blink)

    def _hide_banner(self):
        self._cancel_banner_jobs()
        self.banner.withdraw()

    def _cancel_banner_jobs(self):
        for attr in ("_blink_job", "_hide_job"):
            job = getattr(self, attr, None)
            if job:
                try:
                    self.root.after_cancel(job)
                except Exception:
                    pass
                setattr(self, attr, None)

    # ----- dragging ---------------------------------------------------- #

    def _drag_start(self, e):
        self._dragging = True
        self._sx, self._sy = e.x_root, e.y_root
        self._wx, self._wy = self.root.winfo_x(), self.root.winfo_y()

    def _drag_move(self, e):
        x = self._wx + (e.x_root - self._sx)
        y = self._wy + (e.y_root - self._sy)
        self.root.geometry(f"+{x}+{y}")

    def _drag_end(self, e):
        self._dragging = False
        self.root.update_idletasks()
        # store the RIGHT edge + top so growth keeps the corner pinned
        self.cfg["hud_right"] = self.root.winfo_x() + self.root.winfo_width()
        self.cfg["hud_top"] = self.root.winfo_y()
        self._last_w = self.root.winfo_width()
        save_config(self.cfg)

    # ----- timer actions ----------------------------------------------- #

    def _start_cycle(self, remaining):
        now_m = time.monotonic()
        self.deadline = now_m + remaining
        self.next_epoch = time.time() + remaining
        self.running = True
        self.paused = False
        self.rupture_active = False
        # don't replay alerts for stages already in the past
        self.fired = {s["sec"] for s in self.stages if s["sec"] >= remaining}
        self._hide_banner()

    # ----- rupture tracker / auto-calibrate ---------------------------- #

    def record_mark(self, epoch=None):
        """Log an observed rupture time so the cycle can be learned from it."""
        if epoch is None:
            epoch = time.time()
        hist = self.cfg.setdefault("history", [])
        # collapse near-duplicates (e.g. double-tap within a minute)
        if hist and 0 <= epoch - hist[-1] < 60:
            hist[-1] = epoch
        else:
            hist.append(float(epoch))
        hist.sort()
        del hist[:-40]                       # keep only the last 40 marks
        save_config(self.cfg)

    def _normalized_gaps(self):
        """Gaps between consecutive marks, normalized for missed marks.

        A gap near 2x/3x the typical gap is split before being kept, and values
        outside a 30..90 min sanity window are dropped. Chronological order."""
        ts = sorted(self.cfg.get("history", []))
        gaps = [b - a for a, b in zip(ts, ts[1:]) if b > a]
        if not gaps:
            return []
        srt = sorted(gaps)
        base = srt[len(srt) // 2] or self.cfg.get("cycle_seconds", 3240)
        norm = []
        for g in gaps:
            n = max(1, int(round(g / base)))
            v = g / n
            if 30 * 60 <= v <= 90 * 60:      # sanity window: 30..90 min
                norm.append(v)
        return norm

    def compute_learned(self):
        """Estimate the true cycle (seconds) from logged marks.
        Returns (cycle_seconds_or_None, sample_count)."""
        norm = self._normalized_gaps()
        if not norm:
            return None, 0
        return sum(norm) / len(norm), len(norm)

    def compute_stats(self):
        """Summary of the learned cadence for the stats panel and co-op band.

        Returns dict: n, mean, spread (stddev clamped 30..300s), min, max, last.
        With <2 samples, spread falls back to a conservative 90s default."""
        norm = self._normalized_gaps()
        n = len(norm)
        if not norm:
            return {"n": 0, "mean": None, "spread": 90.0,
                    "min": None, "max": None, "last": None}
        mean = sum(norm) / n
        if n >= 2:
            var = sum((x - mean) ** 2 for x in norm) / n
            spread = var ** 0.5
        else:
            spread = 90.0
        spread = max(30.0, min(spread, 300.0))
        return {"n": n, "mean": mean, "spread": spread,
                "min": min(norm), "max": max(norm), "last": norm[-1]}

    def effective_cycle(self):
        """Cycle length to use right now: learned average if auto-calibrate (or
        co-op client) is on and we have data, otherwise the manual value."""
        c, n = self.compute_learned()
        self.learned = (c, n)
        if c and (self.cfg.get("auto_calibrate", True) or self.cfg.get("coop_client")):
            return c
        return self.cfg["cycle_seconds"]

    def delete_mark(self, index):
        """Remove a single logged rupture mark by its ascending-sorted index."""
        hist = self.cfg.get("history", [])
        hist.sort()
        if 0 <= index < len(hist):
            del hist[index]
            save_config(self.cfg)
            self.learned = self.compute_learned()
            self._update_display()

    def add_rupture_clock(self, hh, mm):
        """Backfill a past rupture observation by clock time (most recent
        occurrence at or before now). Does not restart the countdown."""
        now = time.time()
        lt = time.localtime(now)
        target = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday,
                              int(hh), int(mm), 0, 0, 0, -1))
        if target > now:
            target -= 24 * 3600
        self.record_mark(target)
        self.effective_cycle()
        self._update_display()

    def clear_history(self):
        self.cfg["history"] = []
        self.learned = (None, 0)
        save_config(self.cfg)
        self._update_display()

    # ----- sync / manual set ------------------------------------------- #

    def sync(self):
        """Rupture just ended -> log it and start a fresh learned cycle."""
        self.record_mark()
        self._start_cycle(self.effective_cycle())
        play_pattern([(600, 90), (800, 90)])
        if self.cfg["voice"]:
            speak("Cycle synced.")
        self._update_display()

    def set_last_rupture_clock(self, hh, mm):
        """Anchor to a wall-clock time the last rupture ended, e.g. 22:42.
        This is a real observation, so it is logged for calibration too."""
        now = time.localtime()
        target = time.mktime((now.tm_year, now.tm_mon, now.tm_mday,
                              int(hh), int(mm), 0, 0, 0, -1))
        target_epoch = target
        elapsed = time.time() - target
        if elapsed < 0:            # time given is in the future -> treat as yesterday
            elapsed += 24 * 3600
            target_epoch -= 24 * 3600
        self.record_mark(target_epoch)
        remaining = self.effective_cycle() - elapsed
        if remaining <= 0:
            # already overdue: drop straight into the rupture state
            self._start_cycle(0.001)
        else:
            self._start_cycle(remaining)
        self._update_display()

    def set_next_rupture_clock(self, hh, mm):
        """Set the wall-clock time the NEXT rupture happens, e.g. 23:36, then
        count down to it normally."""
        now = time.time()
        lt = time.localtime(now)
        target = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday,
                              int(hh), int(mm), 0, 0, 0, -1))
        remaining = target - now
        if remaining <= 0:            # time already passed today -> it's tomorrow
            remaining += 24 * 3600
        self._start_cycle(remaining)
        self._update_display()

    def set_next_in(self, minutes):
        """Set how long until the NEXT rupture (in minutes), then count down."""
        self._start_cycle(max(0.0, float(minutes) * 60.0))
        self._update_display()

    def toggle_pause(self):
        if not self.running:
            return
        if self.paused:
            self.deadline = time.monotonic() + self.pause_remaining
            self.next_epoch = time.time() + self.pause_remaining
            self.paused = False
        else:
            self.pause_remaining = max(0.0, self.deadline - time.monotonic())
            self.paused = True
        self._update_display()

    def toggle_hide(self):
        if self.root.state() == "withdrawn" or not self.root.winfo_viewable():
            self.root.deiconify()
        else:
            self.root.withdraw()

    def set_locked(self, locked):
        set_click_through(self.root, locked)
        self.cfg["locked"] = bool(locked)
        if hasattr(self, "_lock_var"):
            self._lock_var.set(bool(locked))
        save_config(self.cfg)

    def toggle_coop(self, value=None):
        if value is None:
            value = not self.cfg.get("coop_client", False)
        self.cfg["coop_client"] = bool(value)
        if hasattr(self, "_coop_var"):
            self._coop_var.set(bool(value))
        save_config(self.cfg)
        self._update_display()

    # ----- main loops -------------------------------------------------- #

    def _poll_hotkeys(self):
        try:
            while True:
                hk_id = self.hk_queue.get_nowait()
                action = self.hk_actions.get(hk_id)
                if action == "sync":
                    self.sync()
                elif action == "pause":
                    self.toggle_pause()
                elif action == "hide":
                    self.toggle_hide()
                elif action == "lock":
                    self.set_locked(not self.cfg.get("locked"))
                elif action == "settings":
                    self.open_settings()
                elif action == "coop":
                    self.toggle_coop()
                elif action == "history":
                    self.open_history()
                elif action == "recipes":
                    self.open_recipes()
                elif action == "quit":
                    self.quit()
        except queue.Empty:
            pass
        self.root.after(50, self._poll_hotkeys)

    def _tick(self):
        if self.running and not self.paused and not self.rupture_active:
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                self._enter_rupture()
            else:
                # co-op client: fire alerts early to cover the host-timing spread
                offset = self.compute_stats()["spread"] if self.cfg.get("coop_client") else 0.0
                alert_remaining = remaining - offset
                for s in self.stages:                       # desc order
                    if alert_remaining <= s["sec"] and s["sec"] not in self.fired:
                        self.fired.add(s["sec"])
                        self._fire_stage(s)
        self._update_display()
        self.root.after(250, self._tick)

    def _fire_stage(self, s):
        self.show_banner(s["banner"], s["color"], persist=False)
        if self.cfg["sound"]:
            play_pattern(s["beeps"])
        if self.cfg["voice"]:
            speak(s["voice"])

    def _enter_rupture(self):
        self.rupture_active = True
        self.rupture_at = time.monotonic()
        self.show_banner("⚠  RUPTURE NOW  —  GET TO A HABITAT  ⚠", RUPTURE_COLOR, persist=True)
        if self.cfg["sound"]:
            play_pattern([(1500, 200), (300, 250), (1500, 200), (300, 250), (1500, 250)])
        if self.cfg["voice"]:
            speak("Rupture now. Get inside.")

    def _cycle_label_text(self):
        c, n = self.compute_learned()
        self.learned = (c, n)
        auto = self.cfg.get("auto_calibrate", True)
        if c and auto:
            base = f"auto {fmt_mmss(c)} · n{n}"
        elif c:
            base = f"manual {fmt_mmss(self.cfg['cycle_seconds'])} · meas {fmt_mmss(c)}"
        else:
            base = f"manual {fmt_mmss(self.cfg['cycle_seconds'])}"
        if self.cfg.get("coop_client"):
            base += " · co-op"
        return base

    def _update_display(self):
        self.cycle_label.config(text=self._cycle_label_text())

        if not self.running:
            self.time_label.config(text="--:--", fg="#6b7d91")
            self.next_label.config(text="press Ctrl+Alt+R to sync")
            self.status_label.config(text="not synced", fg="#6b7d91")
        elif self.rupture_active:
            since = time.monotonic() - getattr(self, "rupture_at", time.monotonic())
            self.time_label.config(text="RUPTURE", fg=RUPTURE_COLOR)
            self.next_label.config(text=f"hit {fmt_mmss(since)} ago — sync at end")
            self.status_label.config(text="● RUPTURE", fg=RUPTURE_COLOR)
        else:
            if self.paused:
                remaining = self.pause_remaining
            else:
                remaining = max(0.0, self.deadline - time.monotonic())

            color, phase = GREEN, "safe"
            for s in self.stages:              # smallest matching threshold wins
                if remaining <= s["sec"]:
                    color, phase = s["color"], s["name"].lower()

            if self.cfg.get("coop_client"):
                stats = self.compute_stats()
                spread = stats["spread"]
                self.time_label.config(text="≈" + fmt_mmss(remaining), fg=color)
                if stats["n"] >= 1:
                    lo = time.strftime("%H:%M", time.localtime(self.next_epoch - spread))
                    hi = time.strftime("%H:%M", time.localtime(self.next_epoch + spread))
                    self.next_label.config(text=f"next ~ {lo}–{hi}")
                    tag = f"co-op ±{fmt_mmss(spread)} · n{stats['n']}"
                else:
                    nxt = time.strftime("%H:%M", time.localtime(self.next_epoch))
                    self.next_label.config(text=f"next ~ {nxt} (low data)")
                    tag = "co-op · sync on rupture"
                self.status_label.config(text=("paused" if self.paused else tag),
                                         fg=("#ffd23f" if self.paused else color))
            else:
                self.time_label.config(text=fmt_mmss(remaining), fg=color)
                nxt = time.strftime("%H:%M", time.localtime(self.next_epoch))
                self.next_label.config(text=f"next rupture ~ {nxt}")
                self.status_label.config(text=("paused" if self.paused else phase),
                                         fg=("#ffd23f" if self.paused else color))

        self._reanchor_if_resized()

    # ----- settings window --------------------------------------------- #

    def open_settings(self):
        if self.settings_win and tk.Toplevel.winfo_exists(self.settings_win):
            self.settings_win.lift()
            return
        self.settings_win = SettingsWindow(self)

    def open_history(self):
        if self.history_win and tk.Toplevel.winfo_exists(self.history_win):
            self.history_win.lift()
            return
        self.history_win = HistoryWindow(self)

    def open_recipes(self):
        # toggle: summon if hidden/absent, dismiss if showing
        if self.recipe_win and tk.Toplevel.winfo_exists(self.recipe_win):
            if self.recipe_win.winfo_viewable():
                self.recipe_win.hide()
            else:
                self.recipe_win.show()
            return
        self.recipe_win = RecipeWindow(self)
        self.recipe_win.show()

    def apply_settings(self, new_cfg):
        self.cfg.update(new_cfg)
        if hasattr(self, "_coop_var"):
            self._coop_var.set(bool(self.cfg.get("coop_client")))
        self.rebuild_stages()
        self.root.attributes("-alpha", float(self.cfg["alpha"]))
        self.time_label.config(font=("Consolas", int(self.cfg["font_size"]), "bold"))
        if self.running and not self.rupture_active:
            remaining = (self.pause_remaining if self.paused
                         else max(0.0, self.deadline - time.monotonic()))
            self.fired = {s["sec"] for s in self.stages if s["sec"] >= remaining}
        save_config(self.cfg)
        self._update_display()
        self._anchor_hud()              # font/size may have changed the width

    # ----- lifecycle --------------------------------------------------- #

    def quit(self):
        try:
            self.hotkeys.stop()
        except Exception:
            pass
        save_config(self.cfg)
        try:
            self.root.destroy()
        except Exception:
            pass

    def run(self):
        self.root.mainloop()


# --------------------------------------------------------------------------- #
# Settings window
# --------------------------------------------------------------------------- #

class SettingsWindow(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.title("StarRupture Timer — Settings")
        self.attributes("-topmost", True)
        self.resizable(False, False)
        self.configure(padx=16, pady=14)
        cfg = app.cfg

        row = 0

        def label(text):
            nonlocal row
            tk.Label(self, text=text, anchor="w").grid(row=row, column=0, sticky="w", pady=4)

        # cycle length
        label("Cycle length (min : sec)")
        cyc = int(cfg["cycle_seconds"])
        self.cyc_min = tk.Spinbox(self, from_=0, to=180, width=5)
        self.cyc_min.delete(0, "end"); self.cyc_min.insert(0, cyc // 60)
        self.cyc_sec = tk.Spinbox(self, from_=0, to=59, width=5)
        self.cyc_sec.delete(0, "end"); self.cyc_sec.insert(0, cyc % 60)
        self.cyc_min.grid(row=row, column=1, sticky="w")
        self.cyc_sec.grid(row=row, column=2, sticky="w")
        row += 1

        # stage thresholds
        stages = sorted({float(m) for m in cfg["stages_minutes"]}, reverse=True)
        while len(stages) < 3:
            stages.append(0)
        label("Alert lead times (minutes before)")
        self.stage_entries = []
        names = ["info", "warning", "danger"]
        for i in range(3):
            e = tk.Spinbox(self, from_=0, to=180, width=5)
            e.delete(0, "end"); e.insert(0, f"{stages[i]:g}")
            e.grid(row=row, column=1 + i, sticky="w")
            self.stage_entries.append(e)
        tk.Label(self, text="(big → small)", fg="#888").grid(row=row, column=0, sticky="e")
        row += 1

        # opacity
        label("HUD opacity")
        self.alpha = tk.Scale(self, from_=0.30, to=1.0, resolution=0.05,
                              orient="horizontal", length=160)
        self.alpha.set(float(cfg["alpha"]))
        self.alpha.grid(row=row, column=1, columnspan=2, sticky="w")
        row += 1

        # font size
        label("HUD font size")
        self.font_size = tk.Spinbox(self, from_=12, to=80, width=5)
        self.font_size.delete(0, "end"); self.font_size.insert(0, int(cfg["font_size"]))
        self.font_size.grid(row=row, column=1, sticky="w")
        row += 1

        # toggles
        self.sound_var = tk.BooleanVar(value=bool(cfg["sound"]))
        self.voice_var = tk.BooleanVar(value=bool(cfg["voice"]))
        tk.Checkbutton(self, text="Sound alarm", variable=self.sound_var).grid(
            row=row, column=0, sticky="w", pady=2)
        tk.Checkbutton(self, text="Voice (TTS)", variable=self.voice_var).grid(
            row=row, column=1, columnspan=2, sticky="w", pady=2)
        row += 1

        ttk.Separator(self, orient="horizontal").grid(
            row=row, column=0, columnspan=4, sticky="ew", pady=10)
        row += 1

        # --- auto-calibrate tracker ---
        self.auto_var = tk.BooleanVar(value=bool(cfg.get("auto_calibrate", True)))
        tk.Checkbutton(self, text="Auto-calibrate cycle from logged ruptures",
                       variable=self.auto_var, command=self._apply).grid(
            row=row, column=0, columnspan=4, sticky="w", pady=(2, 0))
        row += 1

        self.coop_var = tk.BooleanVar(value=bool(cfg.get("coop_client", False)))
        tk.Checkbutton(self, text="Co-op client mode (server-timed → show estimate band)",
                       variable=self.coop_var, command=self._apply).grid(
            row=row, column=0, columnspan=4, sticky="w")
        row += 1

        self.meas_label = tk.Label(self, fg="#3ca36b", anchor="w", font=("Segoe UI", 9))
        self.meas_label.grid(row=row, column=0, columnspan=4, sticky="w")
        row += 1

        label("Add past rupture (HH:MM)")
        self.mark_h = tk.Spinbox(self, from_=0, to=23, width=5)
        self.mark_m = tk.Spinbox(self, from_=0, to=59, width=5)
        self.mark_h.grid(row=row, column=1, sticky="w")
        self.mark_m.grid(row=row, column=2, sticky="w")
        tk.Button(self, text="Add", command=self._add_mark).grid(row=row, column=3, sticky="w")
        row += 1

        bcal = tk.Frame(self)
        bcal.grid(row=row, column=0, columnspan=4, sticky="w", pady=(0, 2))
        tk.Button(bcal, text="Mark rupture now", command=self._mark_now).pack(side="left")
        tk.Button(bcal, text="History & Stats…", command=self.app.open_history).pack(side="left", padx=8)
        tk.Button(bcal, text="Clear history", command=self._clear_hist).pack(side="left")
        row += 1

        self._refresh_meas()

        ttk.Separator(self, orient="horizontal").grid(
            row=row, column=0, columnspan=4, sticky="ew", pady=10)
        row += 1

        # --- set the NEXT rupture directly, then count down normally ---
        label("Set NEXT rupture at (HH:MM)")
        self.next_h = tk.Spinbox(self, from_=0, to=23, width=5)
        self.next_m = tk.Spinbox(self, from_=0, to=59, width=5)
        nxt = time.localtime(self.app.next_epoch) if self.app.running else time.localtime()
        self.next_h.delete(0, "end"); self.next_h.insert(0, nxt.tm_hour)
        self.next_m.delete(0, "end"); self.next_m.insert(0, nxt.tm_min)
        self.next_h.grid(row=row, column=1, sticky="w")
        self.next_m.grid(row=row, column=2, sticky="w")
        tk.Button(self, text="Set", command=self._set_next_clock).grid(row=row, column=3, sticky="w")
        row += 1

        label("…or next rupture in (min)")
        self.next_in = tk.Spinbox(self, from_=0, to=180, width=5)
        self.next_in.delete(0, "end"); self.next_in.insert(0, int(cfg["cycle_seconds"]) // 60)
        self.next_in.grid(row=row, column=1, sticky="w")
        tk.Button(self, text="Set", command=self._set_next_in).grid(row=row, column=3, sticky="w")
        row += 1

        # anchor off the LAST rupture instead
        label("Set last rupture at (HH:MM)")
        self.anchor_h = tk.Spinbox(self, from_=0, to=23, width=5)
        self.anchor_m = tk.Spinbox(self, from_=0, to=59, width=5)
        self.anchor_h.grid(row=row, column=1, sticky="w")
        self.anchor_m.grid(row=row, column=2, sticky="w")
        tk.Button(self, text="Anchor", command=self._anchor).grid(row=row, column=3, sticky="w")
        row += 1

        # hotkey reminder
        tk.Label(self, justify="left", fg="#666", font=("Segoe UI", 8),
                 text=("Hotkeys:  Ctrl+Alt+R sync · P pause · H hide · "
                       "L lock · S settings · Q quit")).grid(
            row=row, column=0, columnspan=4, sticky="w", pady=(8, 4))
        row += 1

        # buttons
        btns = tk.Frame(self)
        btns.grid(row=row, column=0, columnspan=4, sticky="e", pady=(8, 0))
        tk.Button(btns, text="Test alert", command=self._test).pack(side="left", padx=4)
        tk.Button(btns, text="Reset defaults", command=self._reset).pack(side="left", padx=4)
        tk.Button(btns, text="Apply", command=self._apply).pack(side="left", padx=4)
        tk.Button(btns, text="Save & Close", command=self._save_close).pack(side="left", padx=4)

    def _collect(self):
        try:
            cyc = int(self.cyc_min.get()) * 60 + int(self.cyc_sec.get())
        except ValueError:
            cyc = self.app.cfg["cycle_seconds"]
        cyc = max(10, cyc)
        stages = []
        for e in self.stage_entries:
            try:
                v = float(e.get())
            except ValueError:
                v = 0
            if v > 0:
                stages.append(v)
        if not stages:
            stages = [1]
        return {
            "cycle_seconds": cyc,
            "stages_minutes": stages,
            "alpha": float(self.alpha.get()),
            "font_size": int(self.font_size.get()),
            "sound": bool(self.sound_var.get()),
            "voice": bool(self.voice_var.get()),
            "auto_calibrate": bool(self.auto_var.get()),
            "coop_client": bool(self.coop_var.get()),
        }

    def _apply(self):
        self.app.apply_settings(self._collect())

    def _save_close(self):
        self.app.apply_settings(self._collect())
        self.destroy()

    def _reset(self):
        self.app.apply_settings({k: DEFAULT_CONFIG[k] for k in
                                 ("cycle_seconds", "stages_minutes", "alpha",
                                  "font_size", "sound", "voice", "auto_calibrate",
                                  "coop_client")})
        self.destroy()
        self.app.open_settings()

    def _refresh_meas(self):
        c, n = self.app.compute_learned()
        hist_n = len(self.app.cfg.get("history", []))
        meas = f"measured {fmt_mmss(c)} from {n} gap(s)" if c else "not enough data yet"
        self.meas_label.config(text=f"{meas}   ·   {hist_n} marks logged")

    def _add_mark(self):
        self.app.add_rupture_clock(self.mark_h.get(), self.mark_m.get())
        self._refresh_meas()

    def _mark_now(self):
        self.app.record_mark()
        self.app.effective_cycle()
        self.app._update_display()
        self._refresh_meas()

    def _clear_hist(self):
        self.app.clear_history()
        self._refresh_meas()

    def _test(self):
        self.app.apply_settings(self._collect())
        if self.app.stages:
            self.app._fire_stage(self.app.stages[-1])   # preview the danger stage

    def _anchor(self):
        self._apply()
        self.app.set_last_rupture_clock(self.anchor_h.get(), self.anchor_m.get())

    def _set_next_clock(self):
        self._apply()
        self.app.set_next_rupture_clock(self.next_h.get(), self.next_m.get())

    def _set_next_in(self):
        self._apply()
        try:
            mins = float(self.next_in.get())
        except ValueError:
            mins = self.app.cfg["cycle_seconds"] / 60.0
        self.app.set_next_in(mins)


# --------------------------------------------------------------------------- #
# History & stats window
# --------------------------------------------------------------------------- #

class HistoryWindow(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.title("StarRupture — History & Stats")
        self.attributes("-topmost", True)
        self.configure(padx=12, pady=12)
        self.minsize(440, 420)

        self.stats_label = tk.Label(self, anchor="w", justify="left",
                                    font=("Segoe UI", 9))
        self.stats_label.pack(fill="x", pady=(0, 8))

        cols = ("idx", "time", "gap")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=12)
        self.tree.heading("idx", text="#")
        self.tree.heading("time", text="Rupture time")
        self.tree.heading("gap", text="Gap to prev")
        self.tree.column("idx", width=40, anchor="center", stretch=False)
        self.tree.column("time", width=210, anchor="w")
        self.tree.column("gap", width=110, anchor="center", stretch=False)
        self.tree.pack(fill="both", expand=True)

        addf = tk.Frame(self)
        addf.pack(fill="x", pady=(8, 4))
        tk.Label(addf, text="Add past rupture (HH:MM)").pack(side="left")
        self.add_h = tk.Spinbox(addf, from_=0, to=23, width=4)
        self.add_m = tk.Spinbox(addf, from_=0, to=59, width=4)
        self.add_h.pack(side="left", padx=2)
        self.add_m.pack(side="left", padx=2)
        tk.Button(addf, text="Add", command=self._add).pack(side="left", padx=4)

        btns = tk.Frame(self)
        btns.pack(fill="x", pady=(6, 0))
        tk.Button(btns, text="Mark now", command=self._mark_now).pack(side="left")
        tk.Button(btns, text="Delete selected", command=self._delete).pack(side="left", padx=4)
        tk.Button(btns, text="Clear all", command=self._clear).pack(side="left")
        tk.Button(btns, text="Export CSV", command=self._export).pack(side="right")

        self.refresh()

    def refresh(self):
        s = self.app.compute_stats()
        count = len(self.app.cfg.get("history", []))
        if s["n"]:
            txt = (f"Logged ruptures: {count}    n={s['n']} gaps\n"
                   f"Avg cycle: {fmt_mmss(s['mean'])}   ± {fmt_mmss(s['spread'])}    "
                   f"Min: {fmt_mmss(s['min'])}   Max: {fmt_mmss(s['max'])}   "
                   f"Last: {fmt_mmss(s['last'])}")
        else:
            txt = f"Logged ruptures: {count}\nNot enough data for stats yet (need 2+ marks)."
        self.stats_label.config(text=txt)

        for it in self.tree.get_children():
            self.tree.delete(it)
        hist = sorted(self.app.cfg.get("history", []))
        for asc_i in range(len(hist) - 1, -1, -1):     # newest first
            t = hist[asc_i]
            when = time.strftime("%Y-%m-%d %H:%M", time.localtime(t))
            gap = fmt_mmss(t - hist[asc_i - 1]) if asc_i > 0 else "—"
            self.tree.insert("", "end", iid=str(asc_i), values=(asc_i + 1, when, gap))

    def _selected_index(self):
        sel = self.tree.selection()
        return int(sel[0]) if sel else None

    def _add(self):
        self.app.add_rupture_clock(self.add_h.get(), self.add_m.get())
        self.refresh()

    def _mark_now(self):
        self.app.record_mark()
        self.app.effective_cycle()
        self.app._update_display()
        self.refresh()

    def _delete(self):
        i = self._selected_index()
        if i is not None:
            self.app.delete_mark(i)
            self.refresh()

    def _clear(self):
        self.app.clear_history()
        self.refresh()

    def _export(self):
        from tkinter import filedialog
        import csv
        path = filedialog.asksaveasfilename(
            parent=self, defaultextension=".csv",
            filetypes=[("CSV", "*.csv")], initialfile="starrupture_history.csv")
        if not path:
            return
        hist = sorted(self.app.cfg.get("history", []))
        try:
            with open(path, "w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow(["index", "iso_time", "epoch", "gap_seconds"])
                for i, t in enumerate(hist):
                    gap = f"{t - hist[i - 1]:.0f}" if i > 0 else ""
                    w.writerow([i + 1,
                                time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t)),
                                f"{t:.0f}", gap])
        except Exception:
            pass


# --------------------------------------------------------------------------- #
# Recipe search panel (summoned with Ctrl+Alt+F)
# --------------------------------------------------------------------------- #

class RecipeWindow(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.recipes, self.meta = load_recipes()
        self.consumed_by = {}
        for r in self.recipes:
            for inp in r.get("inputs", []):
                self.consumed_by.setdefault(inp["item"].lower(), []).append(r["output"])

        self.icons = load_icons() if _HAVE_PIL else {}
        self.icons_norm = {_nrm(k): v for k, v in self.icons.items()}
        self._img_cache = {}
        self._pil_cache = {}
        self._tile_cache = {}

        RW, MW, FW, G, H = 240, 1300, 440, 32, 900      # rail / main / fav widths, gap, height
        W = RW + G + MW + G + FW
        self._pw, self._ph = W, H
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg=RKEY)
        self.attributes("-transparentcolor", RKEY)
        self.attributes("-alpha", 0.9)
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{W}x{H}+{(sw - W) // 2}+{(sh - H) // 2}")

        rail_x = RW + G                                 # left edge of main panel
        fav_x = RW + G + MW + G                         # left edge of favourites panel
        rects = [(0, 0, RW, H - 1),
                 (rail_x, 0, rail_x + MW, H - 1),
                 (fav_x, 0, W - 1, H - 1)]
        if _HAVE_PIL:
            self._bg_img = ImageTk.PhotoImage(render_panels(W, H, rects))
            tk.Label(self, image=self._bg_img, bg=RKEY, bd=0).place(
                x=0, y=0, relwidth=1, relheight=1)

        # ---- rail panel: machine filters ----
        rail = tk.Frame(self, bg=HUD_BG)
        rail.place(x=24, y=28, width=RW - 48, height=H - 56)
        tk.Label(rail, text="FILTER", bg=HUD_BG, fg=DIM,
                 font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 12))
        self.filter_machine = None
        self._rail_btns = {}
        machset = set()
        for r in self.recipes:
            for part in (r.get("machine") or "?").split(" / "):
                machset.add(part)
        for m in ["All"] + sorted(machset):
            b = tk.Button(rail, text=m, anchor="w", relief="flat", bd=0,
                          bg="#13242e", fg=FG, activebackground=TEAL,
                          activeforeground="#06121a", font=("Segoe UI", 12),
                          pady=6, command=lambda mm=m: self._set_filter(mm))
            b.pack(fill="x", pady=3)
            self._rail_btns[m] = b

        # ---- main panel: search + results + card ----
        main = tk.Frame(self, bg=HUD_BG)
        main.place(x=rail_x + 24, y=28, width=MW - 48, height=H - 56)
        top = tk.Frame(main, bg=HUD_BG)
        top.pack(fill="x")
        head = "STARRUPTURE · RECIPES" if self.recipes else "RECIPES — recipes.json missing"
        tk.Label(top, text=head, bg=HUD_BG, fg=DIM,
                 font=("Segoe UI", 14, "bold")).pack(side="left")
        tk.Label(top, text="Ctrl+Alt+F hide · Esc · ↑↓", bg=HUD_BG, fg="#566b7d",
                 font=("Segoe UI", 9)).pack(side="right")
        self.query = tk.StringVar()
        self.entry = tk.Entry(main, textvariable=self.query, bg="#13242e", fg=FG,
                              insertbackground=FG, relief="flat", font=("Segoe UI", 18))
        self.entry.pack(fill="x", pady=(10, 12), ipady=9)
        body = tk.Frame(main, bg=HUD_BG)
        body.pack(fill="both", expand=True)
        self.listbox = tk.Listbox(body, bg="#13242e", fg=FG, relief="flat",
                                  selectbackground=TEAL, selectforeground="#06121a",
                                  highlightthickness=0, activestyle="none",
                                  font=("Segoe UI", 14), width=24)
        self.listbox.pack(side="left", fill="y")
        self.card = tk.Frame(body, bg=HUD_BG)
        self.card.pack(side="left", fill="both", expand=True, padx=(14, 0))
        self._card_imgs = []

        # ---- favourites panel ----
        favp = tk.Frame(self, bg=HUD_BG)
        favp.place(x=fav_x + 24, y=28, width=FW - 48, height=H - 56)
        tk.Label(favp, text="★ FAVORITES", bg=HUD_BG, fg=TEAL,
                 font=("Segoe UI", 13, "bold")).pack(anchor="w")
        self.fav_list = tk.Listbox(favp, bg="#13242e", fg=FG, relief="flat",
                                   selectbackground=TEAL, selectforeground="#06121a",
                                   highlightthickness=0, activestyle="none",
                                   font=("Segoe UI", 13))
        self.fav_list.pack(fill="both", expand=True, pady=(10, 0))
        self.fav_list.bind("<<ListboxSelect>>", lambda e: self._on_fav_select())
        tk.Label(favp, text="use ★ on a recipe to add / remove", bg=HUD_BG, fg=DIM,
                 font=("Segoe UI", 8)).pack(anchor="w", pady=(8, 0))

        self.matches = []
        self.query.trace_add("write", lambda *_: self._refilter())
        self.entry.bind("<Down>", self._focus_list)
        self.entry.bind("<Return>", self._focus_list)
        for w in (self, self.entry, self.listbox, self.fav_list):
            w.bind("<Escape>", lambda e: self.hide())
        self.listbox.bind("<<ListboxSelect>>", lambda e: self._show_selected())

        self._refresh_favs()
        self._refilter()
        self.withdraw()

    def _place(self):
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        x = (sw - self._pw) // 2
        y = (sh - self._ph) // 2
        self.geometry(f"{self._pw}x{self._ph}+{x}+{y}")

    def _refilter(self):
        text = self.query.get().strip().lower()
        pool = self.recipes
        if self.filter_machine:
            pool = [r for r in self.recipes
                    if self.filter_machine in (r.get("machine") or "").split(" / ")]
        if not text:
            ranked = sorted(pool, key=lambda r: r["output"].lower())
        else:
            scored = []
            for r in pool:
                name = r["output"].lower()
                ins = " ".join(i["item"].lower() for i in r.get("inputs", []))
                if name.startswith(text):
                    score = 0
                elif text in name:
                    score = 1
                elif text in ins:
                    score = 2
                else:
                    continue
                scored.append((score, name, r))
            ranked = [r for _, _, r in sorted(scored, key=lambda t: (t[0], t[1]))]
        self.matches = ranked
        self.listbox.delete(0, "end")
        for r in ranked:
            self.listbox.insert("end", r["output"])
        if ranked:
            self.listbox.selection_clear(0, "end")
            self.listbox.selection_set(0)
            self._show(ranked[0])
        else:
            self._show(None)

    def _focus_list(self, _e):
        if self.matches:
            self.listbox.focus_set()
            self.listbox.selection_clear(0, "end")
            self.listbox.selection_set(0)
            self.listbox.activate(0)
            self._show(self.matches[0])
        return "break"

    def _show_selected(self):
        sel = self.listbox.curselection()
        if sel and sel[0] < len(self.matches):
            self._show(self.matches[sel[0]])

    def _set_filter(self, machine):
        self.filter_machine = None if machine == "All" else machine
        for m, b in self._rail_btns.items():
            on = (m == machine)
            b.configure(bg=(TEAL if on else "#13242e"), fg=("#06121a" if on else FG))
        self._refilter()

    def _favs(self):
        return self.app.cfg.setdefault("recipe_favorites", [])

    def _toggle_fav(self, name):
        favs = self._favs()
        if name in favs:
            favs.remove(name)
        else:
            favs.append(name)
        save_config(self.app.cfg)
        self._refresh_favs()
        sel = self.listbox.curselection()
        if sel and sel[0] < len(self.matches):
            self._show(self.matches[sel[0]])
        elif self.matches:
            self._show(self.matches[0])

    def _refresh_favs(self):
        self._fav_names = list(self._favs())
        self.fav_list.delete(0, "end")
        for n in self._fav_names:
            self.fav_list.insert("end", "  " + n)

    def _on_fav_select(self):
        sel = self.fav_list.curselection()
        if not sel:
            return
        r = next((x for x in self.recipes if x["output"] == self._fav_names[sel[0]]), None)
        if r:
            self._show(r)

    def _icon(self, name, size):
        if not _HAVE_PIL:
            return None
        path = self.icons.get(name) or self.icons_norm.get(_nrm(name))
        if not path or not os.path.exists(path):
            return None
        key = (path, size)
        if key in self._img_cache:
            return self._img_cache[key]
        try:
            im = Image.open(path).convert("RGBA")
            im.thumbnail((size, size), Image.LANCZOS)
            ph = ImageTk.PhotoImage(im)
            self._img_cache[key] = ph
            return ph
        except Exception:
            return None

    def _pil(self, name):
        path = self.icons.get(name) or self.icons_norm.get(_nrm(name))
        if not path or not os.path.exists(path):
            return None
        if path in self._pil_cache:
            return self._pil_cache[path]
        try:
            im = Image.open(path).convert("RGBA")
            self._pil_cache[path] = im
            return im
        except Exception:
            return None

    def _tile_image(self, name, qty, size):
        key = (name, qty, size)
        if key not in self._tile_cache:
            qtxt = f"×{qty}" if qty is not None else None
            self._tile_cache[key] = ImageTk.PhotoImage(render_tile(self._pil(name), qtxt, size))
        return self._tile_cache[key]

    def _show(self, r):
        for w in self.card.winfo_children():
            w.destroy()
        self._card_imgs = []
        if r is None:
            tk.Label(self.card, text="No match.", bg=HUD_BG, fg=DIM,
                     font=("Segoe UI", 13)).pack(anchor="w", padx=8, pady=8)
            return

        # header: big product icon + name + machine/time + yield
        hdr = tk.Frame(self.card, bg=HUD_BG)
        hdr.pack(anchor="w", fill="x", pady=(2, 0))
        if _HAVE_PIL:
            oic = self._tile_image(r["output"], None, 132)
            tk.Label(hdr, image=oic, bg=HUD_BG).pack(side="left")
            self._card_imgs.append(oic)
        info = tk.Frame(hdr, bg=HUD_BG)
        info.pack(side="left", padx=16)
        tk.Label(info, text=r["output"], bg=HUD_BG, fg=FG,
                 font=("Segoe UI", 28, "bold")).pack(anchor="w")
        time_s = r.get("time_s")
        sub = r.get("machine", "?") + (f"   ·   {_qstr(time_s)}s" if time_s is not None else "")
        tk.Label(info, text=sub, bg=HUD_BG, fg=TEAL,
                 font=("Segoe UI", 16)).pack(anchor="w", pady=(4, 0))
        tk.Label(info, text=f"yields ×{_qstr(r.get('output_qty'))}", bg=HUD_BG, fg=DIM,
                 font=("Segoe UI", 13)).pack(anchor="w")
        is_fav = r["output"] in self._favs()
        tk.Button(info, text=("★ Favorited" if is_fav else "☆ Favorite"),
                  relief="flat", bd=0, bg="#13242e",
                  fg=(TEAL if is_fav else FG), activebackground=TEAL,
                  activeforeground="#06121a", font=("Segoe UI", 11, "bold"),
                  padx=12, pady=5, cursor="hand2",
                  command=lambda n=r["output"]: self._toggle_fav(n)).pack(anchor="w", pady=(10, 0))

        ttk.Separator(self.card, orient="horizontal").pack(fill="x", pady=16)
        tk.Label(self.card, text="RECIPE", bg=HUD_BG, fg=DIM,
                 font=("Segoe UI", 11, "bold")).pack(anchor="w")

        # inputs  →  output, as icon tiles with quantity badges
        eq = tk.Frame(self.card, bg=HUD_BG)
        eq.pack(anchor="w", pady=12)
        inputs = r.get("inputs", [])
        if inputs:
            for idx, i in enumerate(inputs):
                if idx:
                    tk.Label(eq, text="+", bg=HUD_BG, fg=DIM,
                             font=("Segoe UI", 26)).pack(side="left", padx=4)
                self._tile(eq, i["item"], _qstr(i.get("qty")))
        else:
            msg = "inputs pending extraction" if r.get("inputs_unknown") else "raw resource"
            tk.Label(eq, text=msg, bg=HUD_BG, fg=DIM,
                     font=("Segoe UI", 14)).pack(side="left", padx=8)
        tk.Label(eq, text="→", bg=HUD_BG, fg=FG,
                 font=("Segoe UI", 34, "bold")).pack(side="left", padx=16)
        self._tile(eq, r["output"], _qstr(r.get("output_qty")))

        if r.get("unlock"):
            tk.Label(self.card, text=f"Unlock:  {r['unlock']}", bg=HUD_BG, fg=DIM,
                     font=("Segoe UI", 11), wraplength=640, justify="left").pack(anchor="w", pady=(12, 0))

        consumers = self.consumed_by.get(r["output"].lower(), [])
        if consumers:
            tk.Label(self.card, text="CONSUMED BY", bg=HUD_BG, fg=DIM,
                     font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(16, 4))
            row = tk.Frame(self.card, bg=HUD_BG)
            row.pack(anchor="w")
            for c in consumers[:10]:
                self._tile(row, c, None, size=60)

    def _tile(self, parent, item, qty, size=96):
        f = tk.Frame(parent, bg=HUD_BG)
        f.pack(side="left", padx=6)
        if _HAVE_PIL:
            ph = self._tile_image(item, qty, size)
            tk.Label(f, image=ph, bg=HUD_BG).pack()
            self._card_imgs.append(ph)
        else:
            tk.Label(f, text=(f"×{qty}" if qty is not None else "?"),
                     bg="#232b36", fg=FG, width=6, height=3).pack()
        tk.Label(f, text=item, bg=HUD_BG, fg=DIM, font=("Segoe UI", 10),
                 wraplength=size + 30, justify="center").pack(pady=(4, 0))
        return f

    def show(self):
        self.deiconify()
        self.lift()
        self.attributes("-topmost", True)
        self._place()
        self.entry.focus_force()
        self.entry.selection_range(0, "end")

    def hide(self):
        self.withdraw()


def main():
    OverlayApp().run()


if __name__ == "__main__":
    main()
