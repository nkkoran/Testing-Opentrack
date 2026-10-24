"""The HeadMouse window (CustomTkinter): a large status card, one on/off switch,
a live head-position view and big buttons, plus Settings and the setup wizard.

Everything here talks to the Engine, which does the real work on its own thread.
"""

import base64
import dataclasses
import math
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

from . import calibration, config, opentrack_setup, tuning, updates
from .curves import DirectionCurve
from .engine import Engine, uses_eyes
from .keys import name_from_tk_keysym
from .safety import TrackingStatus

FAMILY = "Segoe UI" if sys.platform == "win32" else "DejaVu Sans"

# (light, dark) colour pairs
BG = ("#f1f3f6", "#111317")
CARD = ("#ffffff", "#1c1f25")
BORDER = ("#e3e6eb", "#2b3039")
TEXT = ("#111827", "#f3f4f6")
MUTED = ("#6b7280", "#9aa3af")
ACCENT = ("#2563eb", "#3b82f6")
ACCENT_HOVER = ("#1d4ed8", "#2563eb")
SUBTLE = ("#eef1f5", "#262a32")
SUBTLE_HOVER = ("#e2e6ec", "#30353f")
ZONE = ("#dcfce7", "#14321f")
ZONE_LINE = ("#86efac", "#2f7a48")
DANGER = ("#dc2626", "#ef4444")
TRACK = ("#dde2e9", "#30353f")      # unfilled slider / progress / switch track
PILL = ("#ffffff", "#3b424e")       # selected option in a segmented control
KNOB = ("#e9ecf1", "#e5e7eb")
SWITCH_OFF = ("#c5ccd6", "#434a56")
STATE_COLORS = {
    "ACTIVE": ("#16a34a", "#15803d"), "PAUSED": ("#d97706", "#b45309"), "OFF": ("#64748b", "#3f4a5a"),
    "STOPPED": ("#dc2626", "#b91c1c"), "BUSY": ("#2563eb", "#1d4ed8"), "WAITING": ("#7c3aed", "#6d28d9"),
    "CENTER": ("#7c3aed", "#6d28d9"), "STARTING": ("#64748b", "#3f4a5a"),
}
DIRECTIONS = ("right", "left", "up", "down")
PAIRS = {"right": "left", "left": "right", "up": "down", "down": "up"}


ICON = None  # path to headmouse.ico, set by run_gui


def set_icon(window, delay=0):
    """Use the HeadMouse icon (Windows). CustomTkinter sets its own on new windows, so allow a delay."""
    if ICON and sys.platform == "win32":
        apply = lambda: window.winfo_exists() and window.iconbitmap(ICON)
        window.after(delay, apply) if delay else apply()


def pick(pair):
    """The light or dark colour of a pair, for plain Tk widgets like the canvas."""
    return pair[1] if ctk.get_appearance_mode() == "Dark" else pair[0]


def font(size, weight="normal"):
    return ctk.CTkFont(family=FAMILY, size=size, weight=weight)


def overlay(base, changes):
    """Apply {section: {key: value}} on top of a Settings object."""
    for section, values in changes.items():
        base = dataclasses.replace(base, **{section: dataclasses.replace(getattr(base, section), **values)})
    return base


def replace(settings, section, **values):
    return overlay(settings, {section: values})


def png_photo(data):
    return tk.PhotoImage(data=base64.b64encode(data).decode("ascii"))


def segmented(parent, values, command, **kw):
    """iOS-style segmented control: dark text, the selected option is a raised pill."""
    kw.setdefault("height", 38)
    return ctk.CTkSegmentedButton(parent, values=values, command=command, font=font(14, "bold"),
                                  fg_color=SUBTLE, unselected_color=SUBTLE, unselected_hover_color=SUBTLE_HOVER,
                                  selected_color=PILL, selected_hover_color=PILL, text_color=TEXT,
                                  corner_radius=10, **kw)


def switch(parent, text, command, big=False, **kw):
    size = dict(switch_width=62, switch_height=32) if big else dict(switch_width=44, switch_height=22)
    return ctk.CTkSwitch(parent, text=text, command=command, fg_color=SWITCH_OFF, progress_color=kw.pop(
        "progress_color", ACCENT), button_color=KNOB, button_hover_color=KNOB, border_width=0, **size, **kw)


def small_button(parent, text, command, **kw):
    kw.setdefault("height", 34)
    kw.setdefault("fg_color", ACCENT)
    kw.setdefault("hover_color", ACCENT_HOVER)
    return ctk.CTkButton(parent, text=text, command=command, corner_radius=10, font=font(13, "bold"),
                         text_color_disabled=MUTED, **kw)


def dropdown(parent, values, command=None, **kw):
    return ctk.CTkOptionMenu(parent, values=values, command=command, corner_radius=10, font=font(13),
                             fg_color=PILL, button_color=PILL, button_hover_color=SUBTLE_HOVER, text_color=TEXT,
                             dropdown_font=font(13), **kw)


def scroll_frame(parent):
    return ctk.CTkScrollableFrame(parent, fg_color="transparent", scrollbar_button_color=TRACK,
                                  scrollbar_button_hover_color=BORDER)


def card(parent, **kw):
    kw.setdefault("fg_color", CARD)
    return ctk.CTkFrame(parent, corner_radius=16, border_width=1, border_color=BORDER, **kw)


def primary_button(parent, text, command, **kw):
    kw.setdefault("height", 48)
    return ctk.CTkButton(parent, text=text, command=command, corner_radius=12, font=font(15, "bold"),
                         fg_color=ACCENT, hover_color=ACCENT_HOVER, **kw)


def secondary_button(parent, text, command, **kw):
    kw.setdefault("height", 48)
    return ctk.CTkButton(parent, text=text, command=command, corner_radius=12, font=font(15, "bold"),
                         fg_color=SUBTLE, hover_color=SUBTLE_HOVER, text_color=TEXT, **kw)


def keycap(parent, key, caption):
    box = ctk.CTkFrame(parent, fg_color="transparent")
    ctk.CTkLabel(box, text=key, font=font(12, "bold"), fg_color=SUBTLE, corner_radius=6, width=46,
                 height=26, text_color=TEXT).pack(side="left")
    ctk.CTkLabel(box, text=caption, font=font(12), text_color=MUTED).pack(side="left", padx=(8, 0))
    return box


def window_scaling(widget):
    try:
        return ctk.ScalingTracker.get_window_scaling(widget.winfo_toplevel())
    except Exception:
        return 1.0


def rounded_rect(canvas, x1, y1, x2, y2, r, **kw):
    r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2, x2 - r, y2,
           x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return canvas.create_polygon(pts, smooth=True, **kw)


def describe(snap):
    """(title, subtitle, colour key) for the big status card."""
    s = snap.settings
    k = s.keys
    state = snap.state
    if snap.source_error:
        return "Tracking problem", snap.source_error, "STOPPED"
    if state.startswith("BUSY"):
        return "Paused for setup", "Head control is paused while setup runs.", "BUSY"
    if snap.tracking != TrackingStatus.OK:
        if snap.source_kind == "webcam":
            if snap.source_status != "running":
                return "Starting camera", snap.source_status.capitalize(), "STARTING"
            return "Can't see your face", "Sit facing the camera, with light on your face.", "STOPPED"
        if snap.tracking == TrackingStatus.FROZEN:
            return "Tracking froze", "OpenTrack may have lost your face.", "STOPPED"
        return "No tracking", "Start OpenTrack with the HeadMouse profile and press Start.", "STOPPED"
    if state == "PRACTICE":
        return "Practice game", "The game's camera isn't moved while you practise", "BUSY"
    if not snap.enabled:
        game = s.general.game_window_title
        if s.general.auto_enable_in_game and game:
            return "Off", f"Turns on by itself in {game}  ·  or press {k.enable_toggle}", "OFF"
        return "Off", f"Press {k.enable_toggle} or flip the switch to start", "OFF"
    if state.startswith("WAITING"):
        return "Waiting for the game", f"Moves the camera only in {s.general.game_window_title}", "WAITING"
    if snap.paused:
        return "Frozen", f"Release {k.pause_hold} to continue", "PAUSED"
    if snap.glancing:
        return "Looking away", "The camera waits until you look back at the screen", "CENTER"
    if state.startswith("CENTER"):
        return "Center your head", "Movement resumes once your head is back in the middle", "CENTER"
    if "precision" in state:
        return "Precision aim", f"Slow mode while {k.precision_hold} is held", "ACTIVE"
    return "On", f"Hold {k.pause_hold} to freeze the camera", "ACTIVE"


CUSTOM_PRESET = "Custom (not saved as a preset)"
SAVE_PRESET = "Save current as a preset..."


def save_preset_as(engine, settings, parent):
    """Ask for a name and save the feel part of `settings` as a preset. Returns the name, or None."""
    dialog = ctk.CTkInputDialog(title="Save preset", text='Name for this preset (for example "Evening"):')
    name = (dialog.get_input() or "").strip()
    if not name:
        return None
    filename = config.preset_filename(name)
    if (filename and not config.is_builtin_preset(name)
            and (config.preset_folder(engine.path) / filename).exists()
            and not messagebox.askyesno("HeadMouse", f'Replace the preset "{name}"?', parent=parent)):
        return None
    try:
        return config.save_preset(engine.path, name, settings).stem
    except (OSError, config.SettingsError) as e:
        messagebox.showerror("HeadMouse", f"Could not save the preset: {e}", parent=parent)
        return None


class HeadView:
    """Canvas showing the head position, dead zone, full-speed box and direction arrows."""

    def __init__(self, parent, width, height):
        self.scale = window_scaling(parent)
        self.w, self.h = int(width * self.scale), int(height * self.scale)
        self.canvas = tk.Canvas(parent, width=self.w, height=self.h, highlightthickness=0, bd=0)

    def draw(self, snap, bg=CARD):
        c, w, h, k = self.canvas, self.w, self.h, self.scale
        c.delete("all")
        c.configure(bg=pick(bg))
        s = snap.settings
        cx, cy = w / 2, h / 2
        xr = max(s.right.full_speed_angle, s.left.full_speed_angle) * 1.3
        yr = max(s.up.full_speed_angle, s.down.full_speed_angle) * 1.3
        sx, sy = (w / 2 - 26 * k) / xr, (h / 2 - 22 * k) / yr
        muted = pick(MUTED)
        if snap.tracking != TrackingStatus.OK or snap.source_error:
            c.create_text(cx, cy - 10 * k, text="No tracking", fill=pick(DANGER), font=(FAMILY, 15, "bold"))
            c.create_text(cx, cy + 14 * k, text="Movement is stopped for safety", fill=muted, font=(FAMILY, 10))
            return
        c.create_line(cx, 8 * k, cx, h - 8 * k, fill=pick(BORDER), width=1)
        c.create_line(8 * k, cy, w - 8 * k, cy, fill=pick(BORDER), width=1)
        rounded_rect(c, cx - s.left.full_speed_angle * sx, cy - s.up.full_speed_angle * sy,
                     cx + s.right.full_speed_angle * sx, cy + s.down.full_speed_angle * sy, 14 * k,
                     fill="", outline=pick(BORDER), width=2, dash=(6, 4))
        rounded_rect(c, cx - s.left.deadzone * sx, cy - s.up.deadzone * sy,
                     cx + s.right.deadzone * sx, cy + s.down.deadzone * sy, 8 * k,
                     fill=pick(ZONE), outline=pick(ZONE_LINE), width=1)
        moving = {"right": snap.yaw_speed > 0, "left": snap.yaw_speed < 0,
                  "up": snap.pitch_speed > 0, "down": snap.pitch_speed < 0}
        a = 9 * k
        arrows = {"right": [(w - 6 * k, cy), (w - 6 * k - a, cy - a), (w - 6 * k - a, cy + a)],
                  "left": [(6 * k, cy), (6 * k + a, cy - a), (6 * k + a, cy + a)],
                  "up": [(cx, 4 * k), (cx - a, 4 * k + a), (cx + a, 4 * k + a)],
                  "down": [(cx, h - 4 * k), (cx - a, h - 4 * k - a), (cx + a, h - 4 * k - a)]}
        for name, pts in arrows.items():
            c.create_polygon(*[v for p in pts for v in p],
                             fill=pick(ACCENT) if moving[name] else pick(BORDER), outline="")
        x = cx + max(-xr, min(xr, snap.yaw)) * sx
        y = cy - max(-yr, min(yr, snap.pitch)) * sy
        color = pick(ACCENT) if any(moving.values()) else pick(STATE_COLORS["ACTIVE"])
        r = 11 * k
        c.create_oval(x - r - 5 * k, y - r - 5 * k, x + r + 5 * k, y + r + 5 * k, fill="", outline=color, width=2)
        c.create_oval(x - r, y - r, x + r, y + r, fill=color, outline=pick(bg), width=3)
        c.create_text(12 * k, 10 * k, text="your head", anchor="nw", fill=muted, font=(FAMILY, 9))


class MainWindow:
    def __init__(self, root, engine):
        self.root = root
        self.engine = engine
        self.children = {}
        self.preview_photo = None
        self._last_title = None
        self._notice_until = 0.0  # keep a notice in the message line until then
        s = engine.settings
        root.title("HeadMouse" + ("  (test mode - the mouse will not move)" if engine.dry_run else ""))
        root.configure(fg_color=BG)
        root.resizable(False, False)
        root.attributes("-topmost", s.general.always_on_top)
        outer = ctk.CTkFrame(root, fg_color="transparent")
        outer.pack(fill="both", expand=True, padx=18, pady=16)

        header = ctk.CTkFrame(outer, fg_color="transparent")
        header.pack(fill="x")
        ctk.CTkLabel(header, text="HeadMouse", font=font(22, "bold"), text_color=TEXT).pack(side="left")
        self.chip = ctk.CTkLabel(header, text="", font=font(12, "bold"), corner_radius=12, height=26,
                                 fg_color=SUBTLE, text_color=MUTED)
        self.chip.pack(side="right")
        self.update_button = ctk.CTkButton(header, text="", command=self._update, height=26, corner_radius=12,
                                           font=font(12, "bold"), fg_color=ACCENT, hover_color=ACCENT_HOVER)
        self.update_info = None
        if getattr(sys, "frozen", False) and s.general.check_for_updates:
            threading.Thread(target=self._check_update, daemon=True).start()

        self.status = ctk.CTkFrame(outer, corner_radius=20, fg_color=STATE_COLORS["OFF"], height=110)
        self.status.pack(fill="x", pady=(12, 10))
        self.status.pack_propagate(False)
        self.status_title = ctk.CTkLabel(self.status, text="", font=font(32, "bold"), text_color="white")
        self.status_title.pack(anchor="w", padx=22, pady=(14, 0))
        self.status_sub = ctk.CTkLabel(self.status, text="", font=font(14), text_color="white",
                                       wraplength=380, justify="left")
        self.status_sub.pack(anchor="w", padx=22)

        sw = card(outer)
        sw.pack(fill="x")
        ctk.CTkLabel(sw, text="Head control", font=font(17, "bold"), text_color=TEXT).pack(
            side="left", padx=18, pady=16)
        self.switch = switch(sw, "", self._switch_flipped, big=True, progress_color=STATE_COLORS["ACTIVE"])
        self.switch.pack(side="right", padx=14)

        view = card(outer)
        view.pack(fill="x", pady=10)
        self.head = HeadView(view, 380, 170)
        self.head.canvas.pack(padx=12, pady=(12, 4))
        self.speed = ctk.CTkLabel(view, text="", font=font(14, "bold"), text_color=TEXT)
        self.speed.pack(pady=(0, 12))

        buttons = ctk.CTkFrame(outer, fg_color="transparent")
        buttons.pack(fill="x")
        buttons.columnconfigure((0, 1), weight=1, uniform="b")
        secondary_button(buttons, "Re-center", engine.recenter).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        primary_button(buttons, "Settings", self.open_settings).grid(row=0, column=1, sticky="ew", padx=(6, 0))

        presets = ctk.CTkFrame(outer, fg_color="transparent")
        presets.pack(fill="x", pady=(12, 0))
        ctk.CTkLabel(presets, text="Feel", font=font(14, "bold"), text_color=TEXT).pack(side="left")
        self.preset_menu = dropdown(presets, [CUSTOM_PRESET], command=self._preset_picked, height=34)
        self.preset_menu.pack(side="right", fill="x", expand=True, padx=(14, 0))
        self._preset_values = None
        self._preset_next_check = 0.0

        self.keys = ctk.CTkFrame(outer, fg_color="transparent")
        self.keys.pack(fill="x", pady=(14, 4))
        self._keys_shown = None


        footer = ctk.CTkFrame(outer, fg_color="transparent")
        footer.pack(fill="x", side="bottom", pady=(8, 0))
        self.camera_switch = switch(footer, "Camera", self._camera_toggled, font=font(12), text_color=MUTED)
        self.camera_switch.pack(side="left")
        self.top_switch = switch(footer, "Stay on top", self._top_toggled, font=font(12), text_color=MUTED)
        self.top_switch.pack(side="right")
        if s.general.always_on_top:
            self.top_switch.select()
        self.message = ctk.CTkLabel(outer, text="", font=font(11), text_color=MUTED, anchor="w")
        self.message.pack(fill="x", side="bottom")

        root.protocol("WM_DELETE_WINDOW", self.close)
        imported = self._import_earlier_settings(s)
        if imported:
            s = imported
        self.refresh()
        if imported:
            self.message.configure(text="Brought back your settings from the earlier HeadMouse.")
            self._notice_until = time.monotonic() + 20
        elif not s.general.setup_done:
            root.after(700, self.open_wizard)
        elif uses_eyes(s) and s.tracking.source == "webcam" and s.glance.eye_neutral == 0.0:
            # Set up before glance detection existed: suggest teaching it once.
            self.message.configure(text="New: HeadMouse can ignore glances at the keyboard. "
                                        "Run the setup wizard once (Settings > Tracking) to teach it.")
            self._notice_until = time.monotonic() + 20

    def _import_earlier_settings(self, s):
        """A fresh install that finds settings from an earlier (source) install uses those."""
        earlier = config.earlier_install_settings()
        if not getattr(sys, "frozen", False) or s.general.setup_done or earlier is None:
            return None
        if earlier.resolve() == self.engine.path.resolve():
            return None
        try:
            config.restore_backup(self.engine.path, earlier)
            new = config.load(self.engine.path)[0]
        except (OSError, config.SettingsError):
            return None
        self.engine.apply_settings(new, save=False)
        return new

    # --- actions ---------------------------------------------------------------

    def _check_update(self):
        self.update_info = updates.available_update()  # read by refresh() on the Tk thread

    def _update(self):
        version, url = self.update_info
        if not messagebox.askyesno("HeadMouse", f"Install HeadMouse {version} now?\n\nHeadMouse will close, "
                                                "update, and start again. Your settings are kept.",
                                   parent=self.root):
            return
        self.update_button.configure(text="Downloading...", state="disabled")

        def work():
            try:
                updates.download_and_install(url)
            except OSError as e:
                error = str(e)
                self.root.after(0, lambda: messagebox.showerror("HeadMouse", f"The update failed: {error}",
                                                                parent=self.root))
                self.root.after(0, lambda: self.update_button.configure(text="Update", state="normal"))
                return
            self.root.after(0, self.close)
        threading.Thread(target=work, daemon=True).start()

    def _show_presets(self, settings, force=False):
        values = config.preset_values(settings)
        now = time.monotonic()
        if not force and values == self._preset_values and now < self._preset_next_check:
            return
        self._preset_values, self._preset_next_check = values, now + 3.0
        current = config.matching_preset(self.engine.path, settings)
        names = config.list_presets(self.engine.path) + ([] if current else [CUSTOM_PRESET]) + [SAVE_PRESET]
        if names != self.preset_menu.cget("values"):
            self.preset_menu.configure(values=names)
        if self.preset_menu.get() != (current or CUSTOM_PRESET):
            self.preset_menu.set(current or CUSTOM_PRESET)

    def _preset_picked(self, name):
        settings = self.engine.settings
        try:
            if name == SAVE_PRESET:
                saved = save_preset_as(self.engine, settings, self.root)
                if saved:
                    self.message.configure(text=f'Saved the current feel as "{saved}".')
                return
            if name == CUSTOM_PRESET or name == config.matching_preset(self.engine.path, settings):
                return
            practice = self.children.get("practice")
            if practice is not None and practice.alive():
                messagebox.showinfo("HeadMouse", "Finish the practice game first.", parent=self.root)
                return
            if not self._close_settings():
                return
            settings = self.engine.settings
            if config.matching_preset(self.engine.path, settings) is None:
                answer = messagebox.askyesnocancel(
                    "HeadMouse", f'Switch to "{name}"?\n\nYour current feel is not saved as a preset. '
                                 "Save it first so you can come back to it?", parent=self.root)
                if answer is None or (answer and not save_preset_as(self.engine, settings, self.root)):
                    return
            try:
                new = config.load_preset(self.engine.path, name, self.engine.settings)
            except config.SettingsError as e:
                messagebox.showerror("HeadMouse", str(e), parent=self.root)
                return
            self.engine.apply_settings(new, save=True)
            self.message.configure(text=f'Feel: "{name}"')
            self._notice_until = time.monotonic() + 5
        finally:
            self._show_presets(self.engine.settings, force=True)

    def _switch_flipped(self):
        self.engine.set_enabled(bool(self.switch.get()))

    def _camera_toggled(self):
        if self.camera_switch.get():
            self._open("camera", lambda: CameraWindow(self))
        else:
            win = self.children.get("camera")
            if win is not None and win.alive():
                win.close()

    def _top_toggled(self):
        on = bool(self.top_switch.get())
        self.root.attributes("-topmost", on)
        self.engine.apply_settings(replace(self.engine.settings, "general", always_on_top=on))

    def _open(self, name, factory):
        win = self.children.get(name)
        if win is not None and win.top.winfo_exists():
            win.top.lift()
            win.top.focus_force()
            return win
        win = self.children[name] = factory()
        return win

    def open_settings(self, tab="Feel"):
        win = self._open("settings", lambda: SettingsWindow(self, tab))
        win.tabs.set(tab)
        win.tab_changed()
        return win

    def _close_settings(self):
        settings = self.children.get("settings")
        if settings is not None and settings.top.winfo_exists():
            return settings.close()
        return True

    def open_wizard(self):
        if not self._close_settings():
            return None
        return self._open("wizard", lambda: WizardWindow(self))

    def open_practice(self):
        if not self._close_settings():
            return None
        return self._open("practice", lambda: PracticeWindow(self))

    def close(self):
        self.engine.stop()
        self.root.destroy()

    # --- live updates ----------------------------------------------------------

    def _show_keys(self, k):
        shown = (k.enable_toggle, k.pause_hold, k.precision_hold, k.recenter)
        if shown == self._keys_shown:
            return
        self._keys_shown = shown
        for w in self.keys.winfo_children():
            w.destroy()
        self.keys.columnconfigure((0, 1), weight=1, uniform="k")
        for i, (key, caption) in enumerate(((k.enable_toggle, "on / off"), (k.pause_hold, "hold to freeze"),
                                            (k.precision_hold, "hold to aim slowly"), (k.recenter, "re-center"))):
            keycap(self.keys, key, caption).grid(row=i // 2, column=i % 2, sticky="w", pady=3)

    def refresh(self):
        if not self.root.winfo_exists():
            return
        snap = self.engine.snapshot()
        title, sub, key = describe(snap)
        if (title, sub, key) != self._last_title:
            self._last_title = (title, sub, key)
            self.status.configure(fg_color=STATE_COLORS[key])
            self.status_title.configure(text=title)
            self.status_sub.configure(text=sub)
        if bool(self.switch.get()) != snap.enabled:
            self.switch.select() if snap.enabled else self.switch.deselect()
        ok = snap.tracking == TrackingStatus.OK and not snap.source_error
        source = "Webcam" if snap.source_kind == "webcam" else "OpenTrack"
        rate = f" · {snap.rate:.0f}/s" if ok and snap.rate else ""
        self.chip.configure(text=f"  ●  {source}{rate}  ", text_color=STATE_COLORS["ACTIVE"] if ok else DANGER)
        self.head.draw(snap)
        if snap.yaw_speed or snap.pitch_speed:
            parts = []
            if snap.yaw_speed:
                parts.append(f"{'Right' if snap.yaw_speed > 0 else 'Left'}  {abs(snap.yaw_speed):.0f}°/s")
            if snap.pitch_speed:
                parts.append(f"{'Up' if snap.pitch_speed > 0 else 'Down'}  {abs(snap.pitch_speed):.0f}°/s")
            self.speed.configure(text="   ·   ".join(parts), text_color=ACCENT)
        else:
            self.speed.configure(text="Camera still", text_color=MUTED)
        self.camera_switch.configure(state="normal" if snap.source_kind == "webcam" else "disabled")
        self._show_keys(snap.settings.keys)
        self._show_presets(snap.settings)
        if self.update_info and not self.update_button.winfo_ismapped():
            self.update_button.configure(text=f"Update to {self.update_info[0]}")
            self.update_button.pack(side="right", padx=(0, 8))
        messages = self.engine.drain_messages()
        if messages and time.monotonic() >= self._notice_until:
            self.message.configure(text=f"{time.strftime('%H:%M')}   {messages[-1][1]}")
        self.root.after(40, self.refresh)


class Child:
    """Base for secondary windows."""

    def __init__(self, main, title, size):
        self.main = main
        self.engine = main.engine
        self.top = ctk.CTkToplevel(main.root)
        self.top.title(title)
        if size:
            self.top.geometry(size)
        self.top.configure(fg_color=BG)
        self.top.transient(main.root)
        self.top.protocol("WM_DELETE_WINDOW", self.close)
        set_icon(self.top, delay=250)
        self.top.after(150, self.top.lift)  # CustomTkinter windows can open behind on Windows
        self.top.after(160, self.top.focus_force)

    def close(self):
        self.top.destroy()
        return True

    def alive(self):
        return self.top.winfo_exists()


class CameraWindow(Child):
    """Small floating window with the camera picture (green dot = face found)."""

    def __init__(self, main):
        super().__init__(main, "HeadMouse camera", "")
        self.top.resizable(False, False)
        root = main.root
        self.top.geometry(f"+{root.winfo_rootx() + root.winfo_width() + 12}+{root.winfo_rooty()}")  # beside it
        self.photo = None
        frame = card(self.top)
        frame.pack(padx=12, pady=12)
        self.label = tk.Label(frame, bd=0, text="Waiting for the camera...", font=(FAMILY, 11))
        self.label.pack(padx=10, pady=10)
        self.engine.set_preview(True)
        self.poll()

    def close(self):
        self.engine.set_preview(False)
        self.main.camera_switch.deselect()
        self.top.destroy()
        return True

    def poll(self):
        if not self.alive():
            return
        png = self.engine.preview_png()
        if png:
            self.photo = png_photo(png)
            self.label.configure(image=self.photo, text="", bg=pick(CARD))
        else:
            self.label.configure(bg=pick(CARD), fg=pick(MUTED))
        self.top.after(100, self.poll)


class SliderRow:
    """Label, value chip and slider, in one row."""

    def __init__(self, parent, label, lo, hi, step, fmt, command, help_text="", chip=SUBTLE):
        self.fmt = fmt
        self.frame = ctk.CTkFrame(parent, fg_color="transparent")
        top = ctk.CTkFrame(self.frame, fg_color="transparent")
        top.pack(fill="x")
        ctk.CTkLabel(top, text=label, font=font(14, "bold"), text_color=TEXT).pack(side="left")
        self.value = ctk.CTkLabel(top, text="", font=font(13, "bold"), fg_color=chip, corner_radius=8,
                                  text_color=TEXT, width=70, height=26)
        self.value.pack(side="right")
        if help_text:
            ctk.CTkLabel(self.frame, text=help_text, font=font(11), text_color=MUTED, anchor="w").pack(fill="x")
        self.slider = ctk.CTkSlider(self.frame, from_=lo, to=hi, number_of_steps=max(1, round((hi - lo) / step)),
                                    command=self._moved, height=20, button_length=0,
                                    button_color=ACCENT, button_hover_color=ACCENT_HOVER, progress_color=ACCENT,
                                    fg_color=TRACK)
        self.slider.pack(fill="x", pady=(4, 0))
        self.command = command

    def _moved(self, value):
        self.value.configure(text=self.fmt(value))
        self.command(value)

    def set(self, value):
        self.slider.set(value)
        self.value.configure(text=self.fmt(value))

    def get(self):
        return self.slider.get()

    def enable(self, on):
        self.slider.configure(state="normal" if on else "disabled")


class SettingsWindow(Child):
    """All settings in four tabs. Changes are tried live; Save keeps them."""

    KEYCAP = dict(fg_color=PILL, hover_color=SUBTLE_HOVER, text_color=TEXT, border_width=1, border_color=BORDER)
    KEYCAP_ACTIVE = dict(fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color="white", border_width=0)

    def __init__(self, main, tab="Feel"):
        super().__init__(main, "HeadMouse settings", "600x760")
        self.original = self.engine.settings
        self.work = self.engine.settings
        self.dirty = False
        self._pending = None
        self._capturing = None
        self.direction = "right"

        bar = ctk.CTkFrame(self.top, fg_color="transparent")
        bar.pack(side="bottom", fill="x", padx=18, pady=(6, 16))
        self.saved_label = ctk.CTkLabel(self.top, text="", font=font(12), text_color=MUTED)
        self.saved_label.pack(side="bottom", fill="x", padx=22)
        primary_button(bar, "Save", self.save, width=130, height=44).pack(side="right")
        secondary_button(bar, "Undo changes", self.discard, width=150, height=44).pack(side="right", padx=8)

        self.tabs = ctk.CTkTabview(self.top, fg_color=CARD, corner_radius=16, command=self.tab_changed,
                                   border_width=1, border_color=BORDER, segmented_button_fg_color=SUBTLE,
                                   segmented_button_unselected_color=SUBTLE,
                                   segmented_button_unselected_hover_color=SUBTLE_HOVER,
                                   segmented_button_selected_color=PILL, segmented_button_selected_hover_color=PILL,
                                   text_color=TEXT)
        self.tabs.pack(fill="both", expand=True, padx=18, pady=(12, 0))
        for name in ("Feel", "Tracking", "Game", "Keys & sound"):
            self.tabs.add(name)
        self.tabs._segmented_button.configure(font=font(14, "bold"), height=36)
        self._feel_tab(self.tabs.tab("Feel"))
        self._tracking_tab(self.tabs.tab("Tracking"))
        self._game_tab(self.tabs.tab("Game"))
        self._keys_tab(self.tabs.tab("Keys & sound"))
        self.tabs.set(tab)
        self.tab_changed()
        self.poll()

    # --- change handling -----------------------------------------------------

    def changes(self):
        return config.diff(self.original, self.work)

    def _set(self, section, **values):
        self.work = replace(self.work, section, **values)
        self.dirty = bool(self.changes())
        self.saved_label.configure(text="You're trying out changes - press Save to keep them" if self.dirty else "")
        if self._pending:
            self.top.after_cancel(self._pending)
        self._pending = self.top.after(200, self._apply_live)

    def _apply_live(self):
        self._pending = None
        self.engine.apply_settings(overlay(self.engine.settings, self.changes()), save=False)
        self._show_presets()

    def save(self):
        final = overlay(self.engine.settings, self.changes())
        try:
            config.validate(final)
        except config.SettingsError as e:
            messagebox.showerror("HeadMouse", str(e), parent=self.top)
            return False
        if self._pending:
            self.top.after_cancel(self._pending)
        self.engine.apply_settings(final, save=True)
        self.dirty = False
        return self._close_window()

    def discard(self):
        if self._pending:
            self.top.after_cancel(self._pending)
        back = config.diff(self.work, self.original)
        self.engine.apply_settings(overlay(self.engine.settings, back), save=False)
        self.dirty = False
        return self._close_window()

    def close(self):
        if not self.dirty:
            return self._close_window()
        answer = messagebox.askyesnocancel("HeadMouse", "Save your changes?", parent=self.top)
        if answer is None:
            return False
        return self.save() if answer else self.discard()

    def _close_window(self):
        self.engine.set_hold("calibration", False)
        self.engine.calibration_mode = False
        self.top.destroy()
        return True

    def tab_changed(self):
        game = self.tabs.get() == "Game"
        self.engine.calibration_mode = game
        self.engine.set_hold("calibration", game)  # the head must not turn the camera while calibrating

    # --- Feel ----------------------------------------------------------------

    def _feel_tab(self, tab):
        scroll = scroll_frame(tab)
        scroll.pack(fill="both", expand=True)
        self.feel_top = ctk.CTkFrame(scroll, fg_color="transparent")
        self.feel_top.pack(fill="x", pady=(0, 12))
        primary_button(self.feel_top, "Find my best settings (practice game)", self.main.open_practice,
                       height=42).pack(fill="x")
        row = ctk.CTkFrame(self.feel_top, fg_color="transparent")
        row.pack(fill="x", pady=(10, 0))
        ctk.CTkLabel(row, text="Preset", font=font(13, "bold"), text_color=TEXT).pack(side="left")
        small_button(row, "Delete", self._delete_preset, width=70, fg_color=SUBTLE, hover_color=SUBTLE_HOVER,
                     text_color=TEXT).pack(side="right")
        small_button(row, "Save as...", self._save_preset, width=90).pack(side="right", padx=6)
        self.preset_menu = dropdown(row, [CUSTOM_PRESET], command=self._preset_chosen, height=34)
        self.preset_menu.pack(side="left", fill="x", expand=True, padx=(10, 0))
        self._show_presets()
        ctk.CTkLabel(scroll, text="Which direction?", font=font(13), text_color=MUTED).pack(anchor="w")
        self.dir_buttons = segmented(scroll, ["Right", "Left", "Up", "Down"], self._direction_selected)
        self.dir_buttons.pack(fill="x", pady=(4, 10))
        self.dir_buttons.set("Right")
        graph_card = ctk.CTkFrame(scroll, fg_color=SUBTLE, corner_radius=14)
        graph_card.pack(fill="x")
        self.graph_scale = window_scaling(tab)
        self.graph = tk.Canvas(graph_card, width=int(500 * self.graph_scale), height=int(150 * self.graph_scale),
                               highlightthickness=0, bd=0)
        self.graph.pack(padx=8, pady=8)
        self.points_note = ctk.CTkFrame(scroll, fg_color="transparent")
        ctk.CTkLabel(self.points_note, text="This direction uses a custom table from the settings file.",
                     font=font(12), text_color=MUTED).pack(side="left")
        small_button(self.points_note, "Use sliders", self._drop_points, width=110).pack(side="right")

        deg = lambda v: f"{v:.1f}°"
        speed = lambda v: f"{v:.0f}°/s"
        self.rows = {
            "full_speed_angle": SliderRow(scroll, "Head turn for full speed", 3, 45, 0.5, deg,
                                          lambda v: self._dir_changed("full_speed_angle", v),
                                          "Smaller = less head movement needed"),
            "max_speed": SliderRow(scroll, "Top speed", 10, 360, 5, speed,
                                   lambda v: self._dir_changed("max_speed", v), "Fastest camera turn"),
            "deadzone": SliderRow(scroll, "Dead zone", 0, 10, 0.1, deg,
                                  lambda v: self._dir_changed("deadzone", v),
                                  "How far you can move before the camera starts turning"),
            "start_delay": SliderRow(scroll, "Start delay", 0, 1.0, 0.01, lambda v: f"{v:.2f} s",
                                     lambda v: self._dir_changed("start_delay", v),
                                     "Wait this long before turning - lets you glance without moving"),
            "min_speed": SliderRow(scroll, "Slowest speed", 0, 60, 0.5, speed,
                                   lambda v: self._dir_changed("min_speed", v), "Speed just outside the dead zone"),
            "curve": SliderRow(scroll, "Curve", 0.5, 4, 0.05, lambda v: f"{v:.2f}",
                               lambda v: self._dir_changed("curve", v),
                               "Higher = finer control near the middle, faster further out"),
        }
        for name in ("full_speed_angle", "max_speed", "deadzone", "start_delay"):
            self.rows[name].frame.pack(fill="x", pady=(12, 0))
        self.advanced = switch(scroll, "Show advanced", self._advanced, font=font(13), text_color=TEXT)
        self.advanced.pack(anchor="w", pady=(14, 0))
        self.adv_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        for name in ("min_speed", "curve"):
            self.rows[name].frame.pack(in_=self.adv_frame, fill="x", pady=(10, 0))
        self.link_switch = switch(scroll, "Keep left and right the same", self._link_toggled,
                                  font=font(13, "bold"), text_color=TEXT)
        self.link_switch.pack(anchor="w", pady=(14, 0))
        ctk.CTkFrame(scroll, height=1, fg_color=BORDER).pack(fill="x", pady=16)
        self.precision = SliderRow(scroll, "Precision aim speed", 5, 100, 5, lambda v: f"{v:.0f}%",
                                   lambda v: self._set("motion", precision_speed_factor=round(v / 100, 2)),
                                   "Camera speed while the precision key is held")
        self.precision.frame.pack(fill="x")
        self.precision.set(self.work.motion.precision_speed_factor * 100)
        self._assist_section(scroll)
        ctk.CTkFrame(scroll, height=1, fg_color=BORDER).pack(fill="x", pady=16)
        ctk.CTkLabel(scroll, text="Glancing away", font=font(15, "bold"), text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(scroll, text="Keep the camera still when you look away from the screen, e.g. at the keyboard.",
                     font=font(11), text_color=MUTED, wraplength=470, justify="left").pack(anchor="w")
        g = self.work.glance
        self.glance_switch = switch(scroll, "Pause the camera when I look away from the screen",
                                    self._glance_toggled, font=font(14, "bold"), text_color=TEXT)
        if g.enabled:
            self.glance_switch.select()
        self.glance_switch.pack(anchor="w", pady=(8, 0))
        self.eye_switch = switch(scroll, "Use my eyes (built-in webcam): pause when I look below the screen",
                                 lambda: self._set("glance", eye_check=bool(self.eye_switch.get())),
                                 font=font(13), text_color=TEXT)
        if g.eye_check:
            self.eye_switch.select()
        self.eye_switch.pack(anchor="w", pady=(8, 0))
        self.eye_row = SliderRow(scroll, "How far below the screen", 5, 40, 1, lambda v: f"{v:.0f}°",
                                 lambda v: self._set("glance", eye_threshold=round(v, 1)),
                                 "Smaller = pauses sooner when you look down")
        self.eye_row.frame.pack(fill="x", pady=(8, 0))
        self.eye_row.set(g.eye_threshold)
        self.far_switch = switch(scroll, "Pause when I turn my head far away from the screen",
                                 lambda: self._set("glance", look_away=bool(self.far_switch.get())),
                                 font=font(13), text_color=TEXT)
        if g.look_away:
            self.far_switch.select()
        self.far_switch.pack(anchor="w", pady=(12, 0))
        self.far_row = SliderRow(scroll, "Far away means", 1.2, 3.0, 0.1, lambda v: f"{v:.1f}x",
                                 lambda v: self._set("glance", look_away_factor=round(v, 2)),
                                 "Times the head turn for full speed")
        self.far_row.frame.pack(fill="x", pady=(8, 0))
        self.far_row.set(g.look_away_factor)
        self._load_direction()

    def _show_presets(self):
        current = config.matching_preset(self.engine.path, self.work)
        names = config.list_presets(self.engine.path) + ([] if current else [CUSTOM_PRESET])
        self.preset_menu.configure(values=names)
        self.preset_menu.set(current or CUSTOM_PRESET)

    def _preset_chosen(self, name):
        if name == CUSTOM_PRESET:
            return
        try:
            new = config.load_preset(self.engine.path, name, self.work)
        except config.SettingsError as e:
            messagebox.showerror("HeadMouse", str(e), parent=self.top)
            self._show_presets()
            return
        for section in config.PRESET_SECTIONS:
            self._set(section, **dataclasses.asdict(getattr(new, section)))
        self._load_direction()
        self.precision.set(self.work.motion.precision_speed_factor * 100)
        self._show_presets()
        self.saved_label.configure(text=f'Trying "{name}" - press Save to keep it')

    def _save_preset(self):
        name = save_preset_as(self.engine, self.work, self.top)
        if name:
            self._show_presets()
            self.saved_label.configure(text=f'Saved as preset "{name}"' +
                                       (" - press Save to keep these settings too" if self.dirty else ""))

    def _delete_preset(self):
        name = self.preset_menu.get()
        if name == CUSTOM_PRESET or config.is_builtin_preset(name):
            messagebox.showinfo("HeadMouse", "Choose one of your own presets to delete. "
                                             "The built-in ones can't be deleted.", parent=self.top)
            return
        if messagebox.askyesno("HeadMouse", f'Delete the preset "{name}"?\n\nYour current settings stay '
                                            "as they are.", parent=self.top):
            config.delete_preset(self.engine.path, name)
            self._show_presets()

    def _assist_section(self, scroll):
        a = self.work.assist
        heading = lambda text, sub: (
            ctk.CTkFrame(scroll, height=1, fg_color=BORDER).pack(fill="x", pady=16),
            ctk.CTkLabel(scroll, text=text, font=font(15, "bold"), text_color=TEXT).pack(anchor="w"),
            ctk.CTkLabel(scroll, text=sub, font=font(11), text_color=MUTED, wraplength=470,
                         justify="left").pack(anchor="w"))
        heading("Precise aiming", "Optional helpers - each one is off until you switch it on.")
        self.hybrid_switch = switch(scroll, "Mouse-like for small moves, joystick for big turns", self._hybrid_toggled,
                                    font=font(14, "bold"), text_color=TEXT)
        if a.hybrid:
            self.hybrid_switch.select()
        self.hybrid_switch.pack(anchor="w", pady=(8, 0))
        ctk.CTkLabel(scroll, text="Small head movements move the camera like a mouse - it goes exactly as far as you "
                                  "move and stays there, for very precise aiming. Turn your head further and it "
                                  "spins like a joystick, as now. The Dead zone (above) sets how big the mouse-like "
                                  "area is in each direction - make it bigger for more room.",
                     font=font(11), text_color=MUTED, wraplength=470, justify="left").pack(anchor="w")
        self.hybrid_rows = {
            "hybrid_gain_x": SliderRow(scroll, "Left/right sensitivity", 0.5, 12, 0.5, lambda v: f"{v:.1f}x",
                                       lambda v: self._set("assist", hybrid_gain_x=round(v, 1)),
                                       "Camera turn for each degree of head turn (lower = more precise)"),
            "hybrid_gain_y": SliderRow(scroll, "Up/down sensitivity", 0.5, 12, 0.5, lambda v: f"{v:.1f}x",
                                       lambda v: self._set("assist", hybrid_gain_y=round(v, 1)),
                                       "Camera tilt for each degree of head tilt"),
            "hybrid_blend": SliderRow(scroll, "Blend into turning", 0, 6, 0.5, lambda v: f"{v:.1f}°",
                                      lambda v: self._set("assist", hybrid_blend=round(v, 1)),
                                      "0 = sharp switch at the dead zone edge; more = smoother hand-over"),
        }
        for field, row in self.hybrid_rows.items():
            row.frame.pack(fill="x", pady=(8, 0))
            row.set(getattr(a, field))
        ctk.CTkLabel(scroll, text="The practice game (top of this tab) can tune these for you.",
                     font=font(11), text_color=MUTED, wraplength=470, justify="left").pack(anchor="w", pady=(6, 0))
        heading("Steadier control", "Also optional, and they work together with the other helpers.")
        self.return_switch = switch(scroll, "Stop when I come back to the middle", lambda: self._set(
            "assist", return_stop=bool(self.return_switch.get())), font=font(14, "bold"), text_color=TEXT)
        if a.return_stop:
            self.return_switch.select()
        self.return_switch.pack(anchor="w", pady=(8, 0))
        ctk.CTkLabel(scroll, text="After a turn, the camera stays still once your head is back near the middle "
                                  "(even slightly past it) until you clearly turn again. No more slow creeping.",
                     font=font(11), text_color=MUTED, wraplength=470, justify="left").pack(anchor="w")
        self.release_row = SliderRow(scroll, "Turn again by", 1, 6, 0.5, lambda v: f"{v:.1f}°",
                                     lambda v: self._set("assist", return_stop_release=round(v, 1)),
                                     "How far you turn from where you rested to start moving again")
        self.release_row.frame.pack(fill="x", pady=(8, 0))
        self.release_row.set(a.return_stop_release)
        self.center_switch = switch(scroll, "Follow my posture (re-center slowly by itself)", lambda: self._set(
            "assist", auto_center=bool(self.center_switch.get())), font=font(14, "bold"), text_color=TEXT)
        if a.auto_center:
            self.center_switch.select()
        self.center_switch.pack(anchor="w", pady=(14, 0))
        ctk.CTkLabel(scroll, text="While you rest, the middle slowly moves to where your head actually is - if "
                                  "you lean or slouch you don't have to press re-center. Never while turning.",
                     font=font(11), text_color=MUTED, wraplength=470, justify="left").pack(anchor="w")
        heading("Up and down", "Looking up and down has less room, because you still need to see the screen.")
        self.follow_switch = switch(scroll, "Up/down follows my head (like a mouse)", self._follow_toggled,
                                    font=font(14, "bold"), text_color=TEXT)
        if a.vertical_follow:
            self.follow_switch.select()
        self.follow_switch.pack(anchor="w", pady=(8, 0))
        ctk.CTkLabel(scroll, text=f"A small head tilt tilts the camera several times as much, and it stays where "
                                  f"you leave it - no holding your head up. Hold {self.work.keys.pause_hold} to "
                                  f"move your head without moving the camera. Left/right still work as now.",
                     font=font(11), text_color=MUTED, wraplength=470, justify="left").pack(anchor="w")
        self.gain_row = SliderRow(scroll, "Strength", 1, 12, 0.5, lambda v: f"{v:.1f}x",
                                  lambda v: self._set("assist", vertical_follow_gain=round(v, 1)),
                                  "Camera tilt for each degree of head tilt")
        self.gain_row.frame.pack(fill="x", pady=(8, 0))
        self.gain_row.set(a.vertical_follow_gain)

    def _hybrid_toggled(self):
        self._set("assist", hybrid=bool(self.hybrid_switch.get()))

    def _follow_toggled(self):
        self._set("assist", vertical_follow=bool(self.follow_switch.get()))
        self._load_direction()

    def _link_field(self):
        return "link_left_right" if self.direction in ("right", "left") else "link_up_down"

    def _link_toggled(self):
        on = bool(self.link_switch.get())
        self._set("general", **{self._link_field(): on})
        if on:
            self._copy()

    def _glance_toggled(self):
        on = bool(self.glance_switch.get())
        self._set("glance", enabled=on)
        if on:
            self.saved_label.configure(text="Tip: run the setup wizard (Tracking tab) so it learns your glances")

    def _advanced(self):
        if self.advanced.get():
            self.adv_frame.pack(fill="x", after=self.advanced)
        else:
            self.adv_frame.pack_forget()

    def _direction_selected(self, value):
        self.direction = value.lower()
        self._load_direction()

    def _load_direction(self):
        d = getattr(self.work, self.direction)
        for name, row in self.rows.items():
            row.set(getattr(d, name))
        if d.points:
            self.points_note.pack(fill="x", pady=(8, 0), after=self.graph.master)
        else:
            self.points_note.pack_forget()
        pair = sorted((self.direction, PAIRS[self.direction]), key=DIRECTIONS.index)
        self.link_switch.configure(text=f"Keep {pair[0]} and {pair[1]} the same")
        if getattr(self.work.general, self._link_field()):
            self.link_switch.select()
        else:
            self.link_switch.deselect()
        follow = self.work.assist.vertical_follow and self.direction in ("up", "down")
        for name, row in self.rows.items():
            row.enable(not d.points and not follow)

    def _linked(self):
        return getattr(self.work.general, self._link_field())

    def _drop_points(self):
        self._set(self.direction, points=[])
        if self._linked():
            self._set(PAIRS[self.direction], points=[])
        self._load_direction()

    def _dir_changed(self, field, value):
        d = getattr(self.work, self.direction)
        values = {f: round(r.get(), 3) for f, r in self.rows.items()}
        values[field] = round(value, 3)
        if values["full_speed_angle"] <= values["deadzone"]:
            values["full_speed_angle"] = values["deadzone"] + 0.5
            self.rows["full_speed_angle"].set(values["full_speed_angle"])
        if values["min_speed"] > values["max_speed"]:
            values["min_speed"] = values["max_speed"]
            self.rows["min_speed"].set(values["min_speed"])
        if d.points:
            return
        self._set(self.direction, **values)
        if self._linked():
            self._set(PAIRS[self.direction], **values)

    def _copy(self):
        src = getattr(self.work, self.direction)
        self._set(PAIRS[self.direction], **{f: getattr(src, f) for f in self.rows} | {"points": list(src.points)})
        self.saved_label.configure(text=f"{PAIRS[self.direction].title()} now matches {self.direction} "
                                        "and will follow its changes")

    def _plot(self, snap):
        c, k = self.graph, self.graph_scale
        d = getattr(self.work, self.direction)
        curve = DirectionCurve(d)
        bg = pick(SUBTLE)
        c.delete("all")
        c.configure(bg=bg)
        w, h = int(c["width"]), int(c["height"])
        x_max = max(20.0, (max(p[0] for p in d.points) if d.points else d.full_speed_angle) * 1.4)
        y_top = max(10.0, max(curve.speed(i * x_max / 100) for i in range(101)))
        left, bottom, top = 44 * k, h - 22 * k, 12 * k
        px = lambda a: left + a / x_max * (w - left - 12 * k)
        py = lambda v: bottom - v / (y_top * 1.1) * (bottom - top)
        muted = pick(MUTED)
        for a in range(0, int(x_max) + 1, 5):
            c.create_text(px(a), bottom + 11 * k, text=f"{a}°", fill=muted, font=(FAMILY, 9))
        for v in (0, y_top / 2, y_top):
            c.create_line(left, py(v), w - 12 * k, py(v), fill=pick(BORDER))
            c.create_text(left - 6 * k, py(v), text=f"{v:.0f}", anchor="e", fill=muted, font=(FAMILY, 9))
        c.create_rectangle(left, top, px(d.deadzone), bottom, fill=pick(ZONE), outline="")
        assist = self.work.assist
        hybrid = assist.hybrid and not (assist.vertical_follow and self.direction in ("up", "down"))

        def fade(a):  # mouse-like aiming: the joystick only fades in past the dead zone
            if not hybrid:
                return 1.0
            if assist.hybrid_blend <= 0:
                return float(a > d.deadzone)
            return min(1.0, max(0.0, (a - d.deadzone) / assist.hybrid_blend))
        pts = []
        for i in range(161):
            a = x_max * i / 160
            pts += [px(a), py(curve.speed(a) * fade(a))]
        c.create_line(*pts, fill=pick(ACCENT), width=3, smooth=True)
        c.create_text(left + 6 * k, top, text="camera °/s", anchor="nw", fill=muted, font=(FAMILY, 9))
        if hybrid:
            gain = assist.hybrid_gain_x if self.direction in ("right", "left") else assist.hybrid_gain_y
            c.create_text(left + 6 * k, top + 14 * k, text=f"mouse-like ×{gain:g}", anchor="nw",
                          fill=pick(TEXT), font=(FAMILY, 9, "bold"))
        if self.work.assist.vertical_follow and self.direction in ("up", "down"):
            c.create_rectangle(0, 0, w, h, fill=bg, outline="")
            c.create_text(w / 2, h / 2, text="Up/down follows your head like a mouse.\n"
                                             "Set its strength under \"Up and down\" below.",
                          fill=pick(TEXT), font=(FAMILY, 12), justify="center")
            return
        if snap.tracking == TrackingStatus.OK:
            value = {"right": snap.yaw, "left": -snap.yaw, "up": snap.pitch, "down": -snap.pitch}[self.direction]
            if value > 0:
                a = min(value, x_max)
                x, y, r = px(a), py(curve.speed(a) * fade(a)), 7 * k
                c.create_oval(x - r, y - r, x + r, y + r, fill=pick(DANGER), outline=bg, width=2)

    # --- Tracking ------------------------------------------------------------

    def _tracking_tab(self, tab):
        scroll = scroll_frame(tab)
        scroll.pack(fill="both", expand=True)
        primary_button(scroll, "Measure my head movement (setup wizard)", self.main.open_wizard).pack(
            fill="x", pady=(0, 14))
        ctk.CTkLabel(scroll, text="How is your head tracked?", font=font(15, "bold"), text_color=TEXT).pack(
            anchor="w")
        self.source = segmented(scroll, ["Built-in webcam", "OpenTrack"], self._source_selected)
        self.source.pack(fill="x", pady=(6, 4))
        self.source.set("Built-in webcam" if self.work.tracking.source == "webcam" else "OpenTrack")
        self.track_status = ctk.CTkLabel(scroll, text="", font=font(13), anchor="w")
        self.track_status.pack(fill="x", pady=(0, 10))

        cam = ctk.CTkFrame(scroll, fg_color=SUBTLE, corner_radius=14)
        cam.pack(fill="x")
        row = ctk.CTkFrame(cam, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(12, 0))
        ctk.CTkLabel(row, text="Webcam", font=font(14, "bold"), text_color=TEXT).pack(side="left")
        self.camera = dropdown(row, [f"Camera {i}" for i in range(6)], width=140,
                               command=lambda v: self._set("webcam", camera_index=int(v.split()[-1])))
        self.camera.set(f"Camera {self.work.webcam.camera_index}")
        self.camera.pack(side="right")
        self.steady = SliderRow(cam, "Steadiness", 0.2, 4.0, 0.1,
                                lambda v: "steady" if v < 0.8 else "quick" if v > 2 else "balanced",
                                lambda v: self._set("webcam", smoothing_min_cutoff=round(v, 2)),
                                "Left = steadier (less jitter), right = quicker (less lag)", chip=PILL)
        self.steady.frame.pack(fill="x", padx=14, pady=(10, 14))
        self.steady.set(self.work.webcam.smoothing_min_cutoff)

        ot = ctk.CTkFrame(scroll, fg_color=SUBTLE, corner_radius=14)
        ot.pack(fill="x", pady=(12, 0))
        ctk.CTkLabel(ot, text="OpenTrack", font=font(14, "bold"), text_color=TEXT).pack(anchor="w", padx=14,
                                                                                      pady=(12, 0))
        ctk.CTkLabel(ot, text="Make a 'HeadMouse' profile from one of yours. Your camera and tracker settings "
                              "are kept and your existing profiles are not changed.", font=font(12),
                     text_color=MUTED, wraplength=470, justify="left").pack(anchor="w", padx=14)
        self.folder = next((f for f in opentrack_setup.profile_folders(self.work.opentrack.opentrack_exe)
                            if f.is_dir()), None)
        profiles = opentrack_setup.list_profiles(self.folder) if self.folder else []
        profiles = [p for p in profiles if p != opentrack_setup.PROFILE_NAME] or profiles
        row = ctk.CTkFrame(ot, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=8)
        self.profile = dropdown(row, profiles or ["No profiles found"], width=210)
        current = opentrack_setup.current_profile()
        self.profile.set(current if current in profiles else (profiles[0] if profiles else "No profiles found"))
        if not profiles:
            self.profile.configure(state="disabled")
        self.profile.pack(side="left")
        small_button(row, "Create profile", self._make_profile,
                     state="normal" if profiles else "disabled").pack(side="right")
        row2 = ctk.CTkFrame(ot, fg_color="transparent")
        row2.pack(fill="x", padx=14, pady=(0, 12))
        ctk.CTkButton(row2, text="Start OpenTrack", command=self._launch, height=34, corner_radius=10,
                      font=font(13, "bold"), fg_color=PILL, text_color=TEXT, hover_color=SUBTLE_HOVER).pack(side="left")
        self.autolaunch = switch(row2, "Start it with HeadMouse", lambda: self._set(
            "opentrack", launch_opentrack=bool(self.autolaunch.get())), font=font(12), text_color=TEXT)
        if self.work.opentrack.launch_opentrack:
            self.autolaunch.select()
        self.autolaunch.pack(side="right")

    def _source_selected(self, value):
        self._set("tracking", source="webcam" if value == "Built-in webcam" else "opentrack")

    def _make_profile(self):
        try:
            dest, backup = opentrack_setup.make_headmouse_profile(self.folder, self.profile.get(),
                                                                  self.work.opentrack.port)
        except OSError as e:
            messagebox.showerror("HeadMouse", f"Could not create the profile: {e}", parent=self.top)
            return
        note = f"\n\nThe previous one was backed up as {backup.name}." if backup else ""
        messagebox.showinfo("HeadMouse", f"Created the HeadMouse profile.{note}\n\nIn OpenTrack, choose "
                                         "'HeadMouse' in the profile list, then press Start.", parent=self.top)

    def _launch(self):
        messagebox.showinfo("HeadMouse", opentrack_setup.launch_if_needed(self.work.opentrack.opentrack_exe),
                            parent=self.top)

    # --- Game ----------------------------------------------------------------

    def _game_tab(self, tab):
        scroll = scroll_frame(tab)
        scroll.pack(fill="both", expand=True)
        ctk.CTkLabel(scroll, text="Match HeadMouse to the game", font=font(15, "bold"), text_color=TEXT).pack(
            anchor="w")
        ctk.CTkLabel(scroll, text="Head control is paused while this tab is open.", font=font(12),
                     text_color=MUTED).pack(anchor="w")
        k = self.work.keys
        steps = ("Start Enshrouded and set its mouse sensitivity how you like it.",
                 f"Face something easy to recognise. Press Test turn (or {k.calibrate_turn} in the game).",
                 "The camera should turn exactly one full circle.",
                 "If it didn't, say how far it turned and press Fix it. Repeat until it's right.")
        for i, text in enumerate(steps, 1):
            row = ctk.CTkFrame(scroll, fg_color="transparent")
            row.pack(fill="x", pady=4)
            ctk.CTkLabel(row, text=str(i), width=28, height=28, corner_radius=14, fg_color=ACCENT,
                         text_color="white", font=font(13, "bold")).pack(side="left", anchor="n")
            ctk.CTkLabel(row, text=text, font=font(13), text_color=TEXT, wraplength=430, justify="left").pack(
                side="left", padx=10)
        self.turn_button = primary_button(scroll, "Test turn in 5 seconds", self._countdown)
        self.turn_button.pack(fill="x", pady=(10, 8))
        fix = ctk.CTkFrame(scroll, fg_color=SUBTLE, corner_radius=14)
        fix.pack(fill="x")
        ctk.CTkLabel(fix, text="It actually turned about", font=font(13), text_color=TEXT).pack(
            side="left", padx=(14, 6), pady=12)
        self.degrees = ctk.CTkEntry(fix, width=70, font=font(13, "bold"), justify="center", corner_radius=8,
                                    fg_color=PILL, border_color=BORDER, text_color=TEXT)
        self.degrees.insert(0, "360")
        self.degrees.pack(side="left")
        ctk.CTkLabel(fix, text="°", font=font(13), text_color=TEXT).pack(side="left", padx=(2, 8))
        small_button(fix, "Fix it", self._correct, width=90).pack(side="right", padx=12)
        self.counts_label = ctk.CTkLabel(scroll, text="", font=font(11), text_color=MUTED)
        self.counts_label.pack(anchor="w", pady=(4, 0))
        self._show_counts()
        ctk.CTkLabel(scroll, text="Tip: one and a half turns = 540°, three quarters = 270°.", font=font(11),
                     text_color=MUTED).pack(anchor="w")
        ctk.CTkFrame(scroll, height=1, fg_color=BORDER).pack(fill="x", pady=14)
        g = self.work.general
        self.auto = switch(scroll, f"Turn on by itself in {g.game_window_title or 'the game'}", lambda: self._set(
            "general", auto_enable_in_game=bool(self.auto.get())), font=font(13), text_color=TEXT)
        if g.auto_enable_in_game:
            self.auto.select()
        self.auto.pack(anchor="w", pady=4)
        self.invert = switch(scroll, "Reverse up/down (look up = camera down)", lambda: self._set(
            "mouse", invert_vertical=bool(self.invert.get())), font=font(13), text_color=TEXT)
        if self.work.mouse.invert_vertical:
            self.invert.select()
        self.invert.pack(anchor="w", pady=4)

    def _show_counts(self):
        self.counts_label.configure(text=f"Currently {self.work.mouse.counts_per_360:g} mouse counts per full turn")

    def _countdown(self, n=5):
        if not self.alive():
            return
        if n == 0:
            self.turn_button.configure(text="Test turn in 5 seconds", state="normal")
            self.engine.start_test_turn()
            return
        self.turn_button.configure(text=f"Click into the game...  {n}", state="disabled")
        self.top.after(1000, lambda: self._countdown(n - 1))

    def _correct(self):
        try:
            turned = float(self.degrees.get())
            if not 10 <= turned <= 3600:
                raise ValueError
        except ValueError:
            messagebox.showerror("HeadMouse", "Type how many degrees it turned, e.g. 400.", parent=self.top)
            return
        counts = round(self.work.mouse.counts_per_360 * 360.0 / turned, 1)
        self._set("mouse", counts_per_360=counts)
        self._show_counts()
        self.degrees.delete(0, "end")
        self.degrees.insert(0, "360")

    # --- Keys & sound ----------------------------------------------------------

    def _keys_tab(self, tab):
        scroll = scroll_frame(tab)
        scroll.pack(fill="both", expand=True)
        ctk.CTkLabel(scroll, text="Keys", font=font(15, "bold"), text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(scroll, text="Click a key, then press the key you want - or tap your foot pedal.",
                     font=font(12), text_color=MUTED).pack(anchor="w", pady=(0, 6))
        self.key_buttons = {}
        for field, label in (("pause_hold", "Freeze camera (hold)"), ("enable_toggle", "Head control on/off"),
                             ("precision_hold", "Precision aim (hold)"), ("recenter", "Re-center"),
                             ("calibrate_turn", "Test turn (game calibration)")):
            row = ctk.CTkFrame(scroll, fg_color=SUBTLE, corner_radius=12)
            row.pack(fill="x", pady=3)
            ctk.CTkLabel(row, text=label, font=font(13), text_color=TEXT).pack(side="left", padx=14, pady=10)
            b = ctk.CTkButton(row, text=getattr(self.work.keys, field) or "none", width=120, height=34,
                              corner_radius=8, font=font(13, "bold"), command=lambda f=field: self._capture(f),
                              **self.KEYCAP)
            b.pack(side="right", padx=10)
            self.key_buttons[field] = b
        ctk.CTkFrame(scroll, height=1, fg_color=BORDER).pack(fill="x", pady=14)
        ctk.CTkLabel(scroll, text="Sound", font=font(15, "bold"), text_color=TEXT).pack(anchor="w")
        self.sound = switch(scroll, "Play sounds (on, off, tracking lost)", lambda: self._set(
            "sounds", enabled=bool(self.sound.get())), font=font(13), text_color=TEXT)
        if self.work.sounds.enabled:
            self.sound.select()
        self.sound.pack(anchor="w", pady=6)
        self.volume = SliderRow(scroll, "Volume", 0, 100, 5, lambda v: f"{v:.0f}%",
                                lambda v: self._set("sounds", volume=round(v / 100, 2)))
        self.volume.frame.pack(fill="x")
        self.volume.set(self.work.sounds.volume * 100)
        secondary_button(scroll, "Play a test sound", lambda: self.top.after(250, lambda: self.engine.play_sound(
            "enabled")), height=36).pack(anchor="w", pady=8)
        ctk.CTkFrame(scroll, height=1, fg_color=BORDER).pack(fill="x", pady=10)
        ctk.CTkLabel(scroll, text="Appearance", font=font(15, "bold"), text_color=TEXT).pack(anchor="w")
        self.theme = segmented(scroll, ["System", "Light", "Dark"], self._theme, width=300)
        self.theme.set(self.work.general.theme.title())
        self.theme.pack(anchor="w", pady=6)
        ctk.CTkFrame(scroll, height=1, fg_color=BORDER).pack(fill="x", pady=10)
        ctk.CTkLabel(scroll, text="Restore earlier settings", font=font(15, "bold"), text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(scroll, text="HeadMouse keeps a copy of your settings every time they change.",
                     font=font(11), text_color=MUTED).pack(anchor="w")
        self.restore_choices = self._restore_choices()
        row = ctk.CTkFrame(scroll, fg_color="transparent")
        row.pack(fill="x", pady=6)
        names = list(self.restore_choices) or ["No earlier settings yet"]
        self.restore_menu = dropdown(row, names, width=320)
        self.restore_menu.set(names[0])
        self.restore_menu.pack(side="left")
        small_button(row, "Restore", self._restore, width=100,
                     state="normal" if self.restore_choices else "disabled").pack(side="right")
        self.updates = switch(scroll, "Check for updates when HeadMouse starts", lambda: self._set(
            "general", check_for_updates=bool(self.updates.get())), font=font(13), text_color=TEXT)
        if self.work.general.check_for_updates:
            self.updates.select()
        self.updates.pack(anchor="w", pady=(10, 0))
        from . import __version__
        ctk.CTkLabel(scroll, text=f"HeadMouse {__version__}", font=font(11), text_color=MUTED).pack(
            anchor="w", pady=(8, 0))

    def _restore_choices(self):
        choices = {}
        earlier = config.earlier_install_settings()
        if earlier is not None and earlier.resolve() != self.engine.path.resolve():
            choices["From the earlier HeadMouse"] = earlier
        for b in config.list_backups(self.engine.path):
            choices[time.strftime("Before the change on %d %b at %H:%M:%S",
                                  time.localtime(b.stat().st_mtime))] = b
        return choices

    def _restore(self):
        choice = self.restore_menu.get()
        source = self.restore_choices.get(choice)
        if source is None or not messagebox.askyesno(
                "HeadMouse", f"Go back to these settings?\n\n{choice}\n\nYour current settings are kept "
                             "as a backup too.", parent=self.top):
            return
        try:
            config.restore_backup(self.engine.path, source)
            restored = config.load(self.engine.path)[0]
        except (OSError, config.SettingsError) as e:
            messagebox.showerror("HeadMouse", f"Could not restore: {e}", parent=self.top)
            return
        self.engine.apply_settings(restored, save=False)
        self.dirty = False
        self._close_window()
        messagebox.showinfo("HeadMouse", "Your earlier settings are back.", parent=self.main.root)

    def _theme(self, value):
        ctk.set_appearance_mode(value.lower())
        self._set("general", theme=value.lower())

    def _capture(self, field):
        if self._capturing:
            self.key_buttons[self._capturing].configure(text=getattr(self.work.keys, self._capturing) or "none",
                                                        **self.KEYCAP)
        self._capturing = field
        self.key_buttons[field].configure(text="Press a key...", **self.KEYCAP_ACTIVE)
        self.top.bind("<KeyPress>", self._key_pressed)
        self.top.focus_force()

    def _key_pressed(self, event):
        field = self._capturing
        if field is None:
            return
        if event.keysym == "Escape":
            name = getattr(self.work.keys, field)
        else:
            name = name_from_tk_keysym(event.keysym)
            if name is None:
                self.saved_label.configure(text=f"'{event.keysym}' can't be used - try another key")
                return
            clash = next((f for f in self.key_buttons if f != field and getattr(self.work.keys, f) == name), None)
            if clash:
                self.saved_label.configure(text=f"{name} is already used - choose another key")
                return
            self._set("keys", **{field: name})
        self.key_buttons[field].configure(text=name or "none", **self.KEYCAP)
        self._capturing = None
        self.top.unbind("<KeyPress>")

    # --- live ----------------------------------------------------------------

    def poll(self):
        if not self.alive():
            return
        snap = self.engine.snapshot()
        if self.tabs.get() == "Feel":
            self._plot(snap)
        ok = snap.tracking == TrackingStatus.OK and not snap.source_error
        self.track_status.configure(text="●  Tracking OK" if ok else f"●  {snap.source_status}",
                                    text_color=STATE_COLORS["ACTIVE"] if ok else DANGER)
        self.top.after(60, self.poll)


class WizardWindow(Child):
    """Step-by-step setup: choose tracker, then measure comfortable head movement."""

    STEPS = [  # name, axis, title, (dx, dy) for the drawing
        ("right", 0, "Turn your head to the right", (1, 0)),
        ("left", 0, "Turn your head to the left", (-1, 0)),
        ("up", 1, "Tilt your head up", (0, -1)),
        ("down", 1, "Tilt your head down", (0, 1)),
    ]

    def __init__(self, main):
        super().__init__(main, "HeadMouse setup", "640x640")
        self.engine.set_hold("wizard", True)
        self.samples = []
        self.capturing = None
        self.neutral = None
        self.movements = {}
        self.recorded = {}
        self.page = "intro"
        self.dir_index = 0
        self.photo = None

        buttons = ctk.CTkFrame(self.top, fg_color="transparent")
        buttons.pack(side="bottom", fill="x", padx=24, pady=(6, 20))
        self.back = secondary_button(buttons, "Cancel", self.close, width=140)
        self.back.pack(side="left")
        self.next_button = primary_button(buttons, "Next", self.next, width=200)
        self.next_button.pack(side="right")

        body = card(self.top)
        body.pack(fill="both", expand=True, padx=24, pady=(20, 6))
        top = ctk.CTkFrame(body, fg_color="transparent")
        top.pack(fill="x", padx=24, pady=(20, 0))
        self.step_label = ctk.CTkLabel(top, text="", font=font(12, "bold"), text_color=MUTED)
        self.step_label.pack(anchor="w")
        self.progress = ctk.CTkProgressBar(top, height=8, progress_color=ACCENT, fg_color=TRACK)
        self.progress.pack(fill="x", pady=(6, 0))
        self.heading = ctk.CTkLabel(body, text="", font=font(24, "bold"), text_color=TEXT, wraplength=540,
                                    justify="left", anchor="w")
        self.heading.pack(fill="x", padx=24, pady=(18, 4))
        self.text = ctk.CTkLabel(body, text="", font=font(15), text_color=MUTED, wraplength=540, justify="left",
                                 anchor="w")
        self.text.pack(fill="x", padx=24)
        self.content = ctk.CTkFrame(body, fg_color="transparent")
        self.content.pack(fill="both", expand=True, padx=24, pady=10)
        self.status = ctk.CTkLabel(body, text="", font=font(14, "bold"))
        self.status.pack(pady=(0, 16))
        self.show_intro()
        self.poll()

    def close(self):
        self.engine.set_hold("wizard", False)
        camera = self.main.children.get("camera")
        self.engine.set_preview(camera is not None and camera.alive())
        self.top.destroy()
        return True

    def _clear(self):
        for w in self.content.winfo_children():
            w.destroy()
        self.photo = None
        self.preview = None
        self.figure = None
        self.meter = None

    def _webcam(self):
        return self.engine.settings.tracking.source == "webcam"

    def _glance_step(self):
        """The glance step needs the webcam's eye data and glance detection switched on."""
        return self._webcam() and uses_eyes(self.engine.settings)

    def _set_step(self, n):
        total = 8 if self._glance_step() else 7
        n = min(n, total - 1)
        self.step_label.configure(text=f"STEP {n + 1} OF {total}")
        self.progress.set((n + 1) / total)

    # pages -------------------------------------------------------------------

    def show_intro(self):
        self._clear()
        self.page = "intro"
        self._set_step(0)
        self.heading.configure(text="Let's set up head control")
        self.text.configure(text="About a minute. HeadMouse measures how far you can comfortably move your head "
                                 "and sets itself up to suit you. First, how should it track your head?")
        self.source = tk.StringVar(value=self.engine.settings.tracking.source)
        for value, title, desc in (("webcam", "Built-in webcam", "Recommended - nothing else to run"),
                                   ("opentrack", "OpenTrack", "OpenTrack must be running with the HeadMouse profile")):
            opt = ctk.CTkFrame(self.content, fg_color=SUBTLE, corner_radius=12)
            opt.pack(fill="x", pady=4)
            ctk.CTkRadioButton(opt, text=title, value=value, variable=self.source, font=font(15, "bold"),
                               command=self._source_changed, fg_color=ACCENT, border_color=MUTED,
                               hover_color=ACCENT_HOVER, text_color=TEXT).pack(anchor="w", padx=14, pady=(10, 0))
            ctk.CTkLabel(opt, text=desc, font=font(12), text_color=MUTED).pack(anchor="w", padx=46, pady=(0, 10))
        self.preview = tk.Label(self.content, bd=0)  # packed when the first picture arrives
        self.engine.set_preview(True)
        self.next_button.configure(text="Next", state="disabled")

    def _source_changed(self):
        value = self.source.get()
        if value != self.engine.settings.tracking.source:
            self.engine.apply_settings(replace(self.engine.settings, "tracking", source=value))
            self.top.after(600, lambda: self.engine.set_preview(True))

    def _figure(self, direction):
        self.figure = tk.Canvas(self.content, width=int(170 * window_scaling(self.top)),
                                height=int(150 * window_scaling(self.top)), highlightthickness=0, bd=0)
        self.figure.pack(pady=(4, 0))
        self.figure_dir = direction

    def _draw_figure(self):
        if not self.figure:
            return
        c = self.figure
        c.delete("all")
        c.configure(bg=pick(CARD))
        w, h = int(c["width"]), int(c["height"])
        k = w / 170
        cx, cy, r = w / 2, h / 2, 42 * k
        dx, dy = self.figure_dir
        face = pick(SUBTLE_HOVER)
        c.create_oval(cx - r, cy - r, cx + r, cy + r, fill=face, outline=pick(BORDER), width=2)
        ox, oy = dx * 18 * k, dy * 14 * k
        for ex in (-14, 14):
            c.create_oval(cx + ox + ex * k - 5 * k, cy + oy - 10 * k, cx + ox + ex * k + 5 * k, cy + oy,
                          fill=pick(TEXT), outline="")
        c.create_oval(cx + ox - 4 * k, cy + oy + 6 * k, cx + ox + 4 * k, cy + oy + 14 * k, fill=pick(ACCENT),
                      outline="")
        if dx or dy:
            sx, sy = cx + dx * (r + 12 * k), cy + dy * (r + 10 * k)
            ex_, ey = cx + dx * (r + 40 * k), cy + dy * (r + 26 * k)
            c.create_line(sx, sy, ex_, ey, fill=pick(ACCENT), width=5 * k, arrow="last",
                          arrowshape=(14 * k, 16 * k, 6 * k), capstyle="round")

    def _meter(self):
        frame = ctk.CTkFrame(self.content, fg_color="transparent")
        frame.pack(fill="x", pady=(10, 0))
        self.meter = ctk.CTkProgressBar(frame, height=16, progress_color=ACCENT, fg_color=TRACK)
        self.meter.pack(side="left", fill="x", expand=True)
        self.meter.set(0)
        self.meter_label = ctk.CTkLabel(frame, text="0°", font=font(15, "bold"), width=60, text_color=TEXT)
        self.meter_label.pack(side="right")

    def show_neutral(self):
        self._clear()
        self.page = "neutral"
        self._set_step(1)
        self.heading.configure(text="Look at the middle of the screen")
        self.text.configure(text="Sit the way you normally play and relax. Press Start, then hold still "
                                 "until you hear the beep (3 seconds).")
        self._figure((0, 0))
        self.next_button.configure(text="Start", state="normal")
        self.back.configure(text="Cancel", command=self.close)
        self.status.configure(text="")

    def show_direction(self, index):
        self._clear()
        self.page = "direction"
        self.dir_index = index
        self._set_step(index + 2)
        name, axis, title, vec = self.STEPS[index]
        self.heading.configure(text=title)
        eyes = " Keep your eyes on the screen." if axis == 1 else ""
        self.text.configure(text="As far as is comfortable - no straining." + eyes + " Press Start, turn, "
                                 "and hold until the beep (4 seconds).")
        self._figure(vec)
        self._meter()
        self.next_button.configure(text="Start", state="normal")
        self.status.configure(text="")

    def show_glance(self):
        self._clear()
        self.page = "glance"
        self._set_step(6)
        self.heading.configure(text="Glance at your keyboard")
        self.text.configure(text="Press Start, then look down at your keyboard as if checking a key, and back "
                                 "at the screen. Do it twice, until the beep (6 seconds). This teaches "
                                 "HeadMouse to ignore glances.")
        self._figure((0, 1))
        self.next_button.configure(text="Start", state="normal")
        self.status.configure(text="")

    def _glance_settings(self, old, new, report, problems):
        """Fit the glance settings from the recorded eye data (webcam only)."""
        neutral = self.recorded.get("neutral", [])
        flip = -1.0 if new.webcam.pitch_up_is_positive != old.webcam.pitch_up_is_positive else 1.0
        rel = lambda rows: [(flip * (r[1] - self.neutral.pitch), r[2]) for r in rows if r[2] is not None]
        screen = rel(self.recorded.get("up", []) + self.recorded.get("down", []) + neutral)
        glance = rel(self.recorded.get("glance", []))
        neutral_eye = [r[2] for r in neutral if r[2] is not None]
        new, glance_report, glance_problems = calibration.propose_glance(new, neutral_eye, screen, glance)
        return new, report + glance_report, problems + glance_problems

    def show_results(self):
        self._clear()
        self.page = "results"
        self._set_step(99)
        old = self.engine.settings
        new, report, problems, offset = calibration.propose(old, old.tracking.source, self.neutral, self.movements)
        if self._glance_step() and "glance" in self.recorded:
            new, report, problems = self._glance_settings(old, new, report, problems)
        self.result = (new, offset)
        self.old_settings = old
        self.heading.configure(text="All set!" if not problems else "Almost there")
        self.text.configure(text="Here's what HeadMouse measured. You can fine-tune it later in Settings.")
        grid = ctk.CTkFrame(self.content, fg_color="transparent")
        grid.pack(fill="x")
        grid.columnconfigure((0, 1), weight=1, uniform="r")
        for i, name in enumerate(DIRECTIONS):
            m = self.movements.get(name)
            d = getattr(new, name)
            cell = ctk.CTkFrame(grid, fg_color=SUBTLE, corner_radius=12)
            cell.grid(row=i // 2, column=i % 2, sticky="ew", padx=4, pady=4)
            ctk.CTkLabel(cell, text=name.title(), font=font(14, "bold"), text_color=TEXT).pack(anchor="w", padx=12,
                                                                                            pady=(8, 0))
            o = getattr(old, name)
            ctk.CTkLabel(cell, text=f"range {m.extent:.0f}°", font=font(12), text_color=MUTED).pack(
                anchor="w", padx=12)
            ctk.CTkLabel(cell, text=f"dead zone {o.deadzone:g}° → {d.deadzone:g}°\n"
                                    f"full speed {o.full_speed_angle:g}° → {d.full_speed_angle:g}°",
                         font=font(11), text_color=MUTED, justify="left").pack(anchor="w", padx=12, pady=(0, 8))
        self.update_tuning = ctk.CTkCheckBox(
            self.content, text="Also update my sensitivity (dead zone and full-speed angle)", font=font(13),
            text_color=TEXT, fg_color=ACCENT, hover_color=ACCENT_HOVER, border_color=MUTED)
        if not old.general.setup_done:
            self.update_tuning.select()  # first setup: use the measurements
        self.update_tuning.pack(anchor="w", pady=(8, 0))
        for line in [r for r in report if r.startswith("Glances")]:
            ctk.CTkLabel(self.content, text=line, font=font(12), text_color=TEXT, wraplength=540,
                         justify="left", anchor="w").pack(fill="x", pady=(6, 0))
        for line in problems + [r for r in report if "reversed" in r]:
            ctk.CTkLabel(self.content, text=line, font=font(12), text_color=pick(STATE_COLORS["PAUSED"]),
                         wraplength=540, justify="left", anchor="w").pack(fill="x", pady=(6, 0))
        self.back.configure(text="Try again", command=self.show_neutral)
        self.next_button.configure(text="Save", state="normal")

    # flow --------------------------------------------------------------------

    def next(self):
        if self.capturing:
            return
        if self.page == "intro":
            self.engine.set_preview(False)
            self.show_neutral()
        elif self.page == "neutral":
            self._capture(3.0, 0.5, self._neutral_done)
        elif self.page == "direction":
            self._capture(4.0, 1.5, self._direction_done)
        elif self.page == "glance":
            self._capture(6.0, 0.3, self._glance_done)
        else:
            new, offset = self.result
            if not self.update_tuning.get():
                # Keep the player's own sensitivity; only the tracking calibration is updated.
                old = self.old_settings
                new = dataclasses.replace(new, right=old.right, left=old.left, up=old.up, down=old.down)
            self.engine.apply_settings(replace(new, "general", setup_done=True))
            if new.tracking.source == "opentrack":
                self.engine.set_offset(offset)
            self.engine.play_sound("done")
            self.close()

    def _capture(self, seconds, settle, done):
        self.samples = []
        now = time.monotonic()
        self.capturing = (now + settle, now + seconds, done)
        self.next_button.configure(state="disabled")

    def _neutral_done(self):
        if len(self.samples) < 10:
            self.status.configure(text="Not enough tracking data - make sure your face is tracked",
                                  text_color=DANGER)
            self.next_button.configure(state="normal")
            return
        self.neutral = calibration.measure_neutral(self.samples)
        self.recorded["neutral"] = self.samples
        self.show_direction(0)

    def _direction_done(self):
        name, axis, *_ = self.STEPS[self.dir_index]
        self.movements[name] = calibration.measure_movement(self.samples, self.neutral, axis)
        self.recorded[name] = self.samples
        if self.dir_index + 1 < len(self.STEPS):
            self.show_direction(self.dir_index + 1)
        elif self._glance_step():
            self.show_glance()
        else:
            self.show_results()

    def _glance_done(self):
        self.recorded["glance"] = self.samples
        self.show_results()

    def poll(self):
        if not self.alive():
            return
        snap = self.engine.snapshot()
        ok = snap.tracking == TrackingStatus.OK and not snap.source_error
        if self.page == "intro":
            if snap.source_error:
                self.status.configure(text=snap.source_error, text_color=DANGER)
            elif ok:
                self.status.configure(text="●  Tracking is working", text_color=STATE_COLORS["ACTIVE"])
            else:
                self.status.configure(text=f"Waiting for tracking...  ({snap.source_status})", text_color=DANGER)
            self.next_button.configure(state="normal" if ok else "disabled")
            png = self.engine.preview_png() if snap.source_kind == "webcam" else None
            if png and self.preview is not None:
                self.photo = png_photo(png)
                self.preview.configure(image=self.photo, bg=pick(CARD))
                if not self.preview.winfo_ismapped():
                    self.preview.pack(pady=6)
        self._draw_figure()
        if self.meter is not None and snap.raw_angles is not None and self.neutral is not None:
            name, axis, *_ = self.STEPS[self.dir_index]
            center = self.neutral.yaw if axis == 0 else self.neutral.pitch
            value = abs(snap.raw_angles[axis] - center)
            self.meter.set(min(1.0, value / 30.0))
            self.meter_label.configure(text=f"{value:.0f}°")
        if self.capturing:
            settle_until, end, done = self.capturing
            now = time.monotonic()
            if now >= settle_until and snap.raw_angles is not None:
                self.samples.append((snap.raw_angles[0], snap.raw_angles[1], snap.eye_pitch))
            left = end - now
            self.status.configure(text=f"Hold it...  {max(0, left):.0f}" if ok else "Keep your face in view",
                                  text_color=ACCENT if ok else DANGER)
            if left <= 0:
                self.capturing = None
                self.engine.play_sound("tracking_ok")
                self.status.configure(text="")
                done()
        self.top.after(30, self.poll)


def _initial_theme(settings_path):
    try:
        return config.load(settings_path)[0].general.theme
    except Exception:
        return "system"


def run_gui(settings_path, base_dir, dry_run=False, engine=None):
    global ICON
    for folder in (Path(base_dir), Path(getattr(sys, "_MEIPASS", base_dir))):
        if (folder / "headmouse.ico").is_file():
            ICON = str(folder / "headmouse.ico")
            break
    ctk.set_appearance_mode(_initial_theme(settings_path))
    ctk.set_default_color_theme("blue")
    root = ctk.CTk()
    set_icon(root)
    engine = engine or Engine(settings_path, base_dir, dry_run=dry_run)
    try:
        engine.start()
    except config.SettingsError as e:
        root.withdraw()
        messagebox.showerror("HeadMouse", f"There is a problem in the settings file:\n\n{e}\n\n{settings_path}")
        root.destroy()
        return 1
    MainWindow(root, engine)
    root.mainloop()
    return 0


class PracticeWindow(Child):
    """Practice game: steer onto targets, then HeadMouse suggests settings that suit you."""

    SCENE = ("#0f172a", "#0b1120")
    GRID = ("#1e293b", "#172033")
    PX_PER_DEG = 8.0

    def __init__(self, main):
        super().__init__(main, "HeadMouse practice", "780x700")
        self.original = self.engine.settings
        self.round = 0
        self.scores = []
        self.proposal = None
        self.notes = {}
        self.trial = None
        self.trials = []
        self.targets = []
        self.cam_start = (0.0, 0.0)
        self.next_at = None
        self.last_t = None
        self.playing = False
        self.engine.set_practice(True)

        buttons = ctk.CTkFrame(self.top, fg_color="transparent")
        buttons.pack(side="bottom", fill="x", padx=24, pady=(6, 18))
        self.secondary = secondary_button(buttons, "Cancel", self.close, width=180)
        self.secondary.pack(side="left")
        self.primary = primary_button(buttons, "Start", self.start_round, width=220)
        self.primary.pack(side="right")
        body = card(self.top)
        body.pack(fill="both", expand=True, padx=24, pady=(18, 6))
        self.heading = ctk.CTkLabel(body, text="Find your best settings", font=font(22, "bold"),
                                    text_color=TEXT, anchor="w")
        self.heading.pack(fill="x", padx=22, pady=(18, 2))
        self.text = ctk.CTkLabel(body, font=font(14), text_color=MUTED, wraplength=680, justify="left", anchor="w",
                                 text="Steer the crosshair onto each blue target with your head, just like in the "
                                      "game, and hold it there for a moment. Two short rounds of 12 targets (about "
                                      "a minute each). The first uses your current settings, the second tries "
                                      "adjusted ones. Nothing changes unless you choose to keep it.")
        self.text.pack(fill="x", padx=22)
        self.k = window_scaling(self.top)
        self.canvas = tk.Canvas(body, width=int(700 * self.k), height=int(380 * self.k), highlightthickness=0, bd=0)
        self.canvas.pack(padx=20, pady=12)
        self.status = ctk.CTkLabel(body, text="", font=font(14, "bold"), text_color=TEXT)
        self.status.pack(pady=(0, 6))
        self.progress = ctk.CTkProgressBar(body, height=8, progress_color=ACCENT, fg_color=TRACK)
        self.progress.pack(fill="x", padx=22, pady=(0, 16))
        self.progress.set(0)
        self.poll()

    # flow --------------------------------------------------------------------

    def start_round(self):
        self.round += 1
        self.targets = tuning.make_targets(hybrid=self.original.assist.hybrid)
        self.trials = []
        self.trial = None
        self.next_at = time.monotonic() + 0.8
        self.playing = True
        self.primary.configure(state="disabled", text="Playing...")
        self.secondary.configure(text="Stop", command=self.close)
        self.heading.configure(text=f"Round {self.round} of 2" + ("  -  adjusted settings" if self.round == 2 else ""))
        self.text.configure(text="Steer onto the blue target and hold still until it turns green.")

    def _next_target(self, snap):
        if len(self.trials) == len(self.targets):
            self._round_done()
            return
        target = self.targets[len(self.trials)]
        self.trial = tuning.Trial(target)
        self.cam_start = snap.practice_camera
        self.status.configure(text=f"Target {len(self.trials) + 1} of {len(self.targets)}")

    def _round_done(self):
        settings = self.engine.settings
        score = tuning.score(self.trials, settings)
        self.scores.append(score)
        self.trial = None
        self.playing = False
        if self.round == 1:
            self.proposal, self.notes = tuning.propose(settings, self.trials)
            if not self.notes:
                self._show_result(no_change=True)
                return
            self.engine.apply_settings(self.proposal, save=False)   # try them in round 2
            self.heading.configure(text="Round 1 done")
            self.text.configure(text=f"Average {score:.1f} s per target. HeadMouse has adjusted your settings - "
                                     "now try them in round 2.")
            self.primary.configure(state="normal", text="Start round 2")
            self.status.configure(text="")
        else:
            self._show_result()

    def _show_result(self, no_change=False):
        self.round = 99
        self.primary.configure(state="normal")
        if no_change:
            self.heading.configure(text="Your settings already suit you")
            self.text.configure(text=f"Average {self.scores[0]:.1f} s per target, without overshooting or "
                                     "struggling. No changes needed.")
            self.primary.configure(text="Done", command=self.close)
            self.secondary.configure(text="Practice again", command=self._restart)
            return
        before, after = self.scores
        better = tuning.worth_keeping(before, after)
        lines = [f"Average time per target: {before:.1f} s with your settings, {after:.1f} s with the new ones."]
        for name in DIRECTIONS:
            if name not in self.notes:
                continue
            o, n = getattr(self.original, name), getattr(self.proposal, name)
            changes = [f"{label} {getattr(o, f):g} → {getattr(n, f):g}"
                       for f, label in (("deadzone", "dead zone"), ("full_speed_angle", "full speed at"),
                                        ("min_speed", "slowest"), ("max_speed", "top speed"), ("curve", "curve"))
                       if getattr(o, f) != getattr(n, f)]
            lines.append(f"{name.title()}: {'; '.join(self.notes[name])}" + (f"  ({', '.join(changes)})" if changes else ""))
        if "aiming" in self.notes:
            o, n = self.original.assist, self.proposal.assist
            changes = [f"{label} {getattr(o, f):g} → {getattr(n, f):g}"
                       for f, label in (("hybrid_gain_x", "left/right sensitivity"),
                                        ("hybrid_gain_y", "up/down sensitivity"), ("hybrid_blend", "blend"))
                       if getattr(o, f) != getattr(n, f)]
            lines.append(f"Mouse-like aiming: {'; '.join(self.notes['aiming'])}  ({', '.join(changes)})")
        self.heading.configure(text="The new settings worked better" if better else "Your old settings did better")
        self.text.configure(text="\n".join(lines))
        self.status.configure(text="")
        if better:
            self.primary.configure(text="Use the new settings", command=self._use_new)
            self.secondary.configure(text="Keep my old settings", command=self.close)
        else:
            self.primary.configure(text="Keep my old settings", command=self.close)
            self.secondary.configure(text="Use the new ones anyway", command=self._use_new)

    def _use_new(self):
        new = self.proposal
        self.engine.set_practice(False)
        self.engine.apply_settings(new, save=True)      # saved (and the old settings backed up)
        self.engine.play_sound("done")
        self.top.destroy()

    def _restart(self):
        self.engine.apply_settings(self.original, save=False)
        self.round = 0
        self.scores = []
        self.primary.configure(text="Start", command=self.start_round)
        self.secondary.configure(text="Cancel", command=self.close)
        self.start_round()

    def close(self):
        self.engine.set_practice(False)
        self.engine.apply_settings(self.original, save=False)  # nothing kept unless chosen
        self.top.destroy()
        return True

    # drawing -----------------------------------------------------------------

    def _draw(self, snap):
        c, k = self.canvas, self.k
        w, h = int(c["width"]), int(c["height"])
        c.delete("all")
        c.configure(bg=pick(self.SCENE))
        cx, cy = w / 2, h / 2
        cam = snap.practice_camera
        ppd = self.PX_PER_DEG * k
        step = 10 * ppd
        ox = (-cam[0] * ppd) % step
        oy = (cam[1] * ppd) % step
        grid = pick(self.GRID)
        x = ox - step
        while x < w + step:
            c.create_line(cx + x - w / 2, 0, cx + x - w / 2, h, fill=grid)
            x += step
        y = oy - step
        while y < h + step:
            c.create_line(0, cy + y - h / 2, w, cy + y - h / 2, fill=grid)
            y += step
        if self.trial is not None:
            tx = cx + (self.cam_start[0] + self.trial.target[0] - cam[0]) * ppd
            ty = cy - (self.cam_start[1] + self.trial.target[1] - cam[1]) * ppd
            on = self.trial._inside
            r = tuning.RADIUS * ppd
            if 0 <= tx <= w and 0 <= ty <= h:
                color = "#22c55e" if on else "#3b82f6"
                c.create_oval(tx - r * 2.2, ty - r * 2.2, tx + r * 2.2, ty + r * 2.2, outline=color, width=3)
                c.create_oval(tx - r * 0.7, ty - r * 0.7, tx + r * 0.7, ty + r * 0.7, fill=color, outline="")
            else:  # off screen: arrow at the edge pointing to it
                ang = math.atan2(ty - cy, tx - cx)
                ex = cx + math.cos(ang) * (w / 2 - 24 * k)
                ey = cy + math.sin(ang) * (h / 2 - 24 * k)
                ex, ey = min(max(ex, 24 * k), w - 24 * k), min(max(ey, 24 * k), h - 24 * k)
                s = 16 * k
                pts = [(ex + math.cos(ang) * s, ey + math.sin(ang) * s),
                       (ex + math.cos(ang + 2.5) * s, ey + math.sin(ang + 2.5) * s),
                       (ex + math.cos(ang - 2.5) * s, ey + math.sin(ang - 2.5) * s)]
                c.create_polygon(*[v for p in pts for v in p], fill="#3b82f6", outline="")
        a = 14 * k
        c.create_line(cx - a, cy, cx - a / 3, cy, fill="white", width=2)
        c.create_line(cx + a / 3, cy, cx + a, cy, fill="white", width=2)
        c.create_line(cx, cy - a, cx, cy - a / 3, fill="white", width=2)
        c.create_line(cx, cy + a / 3, cx, cy + a, fill="white", width=2)
        if snap.tracking != TrackingStatus.OK:
            c.create_text(cx, cy + 50 * k, text="Can't see you - face the camera", fill="#f87171",
                          font=(FAMILY, 14, "bold"))

    def poll(self):
        if not self.alive():
            return
        snap = self.engine.snapshot()
        now = time.monotonic()
        dt = 0.0 if self.last_t is None else now - self.last_t
        self.last_t = now
        if self.playing:
            if self.trial is None and self.next_at is not None and now >= self.next_at:
                self.next_at = None
                self._next_target(snap)
            elif self.trial is not None:
                if snap.tracking != TrackingStatus.OK:
                    if self.trial.start is not None:
                        self.trial.start += dt  # the clock stops while tracking is lost
                else:
                    cam = snap.practice_camera
                    rel = (cam[0] - self.cam_start[0], cam[1] - self.cam_start[1])
                    if self.trial.add(now, rel, (snap.yaw, snap.pitch), (snap.yaw_speed, snap.pitch_speed)):
                        if self.trial.acquired:
                            self.engine.play_sound("target")
                        self.trials.append(self.trial)
                        self.trial = None
                        self.next_at = now + 0.5
            self.progress.set((len(self.trials) + (self.round - 1) * len(self.targets)) / (2 * len(self.targets)))
        self._draw(snap)
        self.top.after(16, self.poll)
