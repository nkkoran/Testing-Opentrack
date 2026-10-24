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

from . import actions, calibration, config, guide, opentrack_setup, practice, quickfix, situations, updates
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
        if snap.frozen_by_action:
            return "Frozen", "Do the freeze gesture or key again to continue", "PAUSED"
        return "Frozen", f"Release {k.pause_hold} to continue", "PAUSED"
    if snap.glancing:
        return "Looking away", "The camera waits until you look back at the screen", "CENTER"
    if state.startswith("CENTER"):
        return "Center your head", "Movement resumes once your head is back in the middle", "CENTER"
    feel = f"{config.SITUATION_NAMES[snap.situation]} feel  ·  " if snap.situation else ""
    if "precision" in state:
        if s.general.precision_toggle:
            return "Precision aim", f"{feel}Slow mode - press {k.precision_hold} again to end it", "ACTIVE"
        return "Precision aim", f"{feel}Slow mode while {k.precision_hold} is held", "ACTIVE"
    return "On", f"{feel}Hold {k.pause_hold} to freeze the camera", "ACTIVE"


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
        s = snap.feel or snap.settings   # what moves the camera now (e.g. the aiming feel)
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
        area = "mouse-like area" if "hybrid" in config.axis_modes(s) else "dead zone"
        c.create_text(12 * k, h - 8 * k, text=f"green: {area}", anchor="sw", fill=muted, font=(FAMILY, 9))


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
        buttons.columnconfigure((0, 1, 2), weight=1, uniform="b")
        secondary_button(buttons, "Re-center", engine.recenter).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        secondary_button(buttons, "Quick fixes", self.open_quickfix).grid(row=0, column=1, sticky="ew", padx=4)
        primary_button(buttons, "Settings", self.open_settings).grid(row=0, column=2, sticky="ew", padx=(4, 0))

        presets = ctk.CTkFrame(outer, fg_color="transparent")
        presets.pack(fill="x", pady=(12, 0))
        ctk.CTkLabel(presets, text="Feel", font=font(14, "bold"), text_color=TEXT).pack(side="left")
        self.preset_menu = dropdown(presets, [CUSTOM_PRESET], command=self._preset_picked, height=34)
        self.preset_menu.pack(side="right", fill="x", expand=True, padx=(14, 0))
        self._preset_values = None
        self._preset_next_check = 0.0

        self.guide_button = ctk.CTkButton(outer, text="", command=self.open_guide, height=30, corner_radius=10,
                                          font=font(12, "bold"), fg_color=SUBTLE, hover_color=SUBTLE_HOVER,
                                          text_color=TEXT, anchor="w")
        self.guide_button.pack(fill="x", pady=(10, 0))
        self._guide_shown = None

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

    def open_guide(self):
        return self._open("guide", lambda: GuideWindow(self))

    def _show_guide(self, settings):
        done, total = guide.progress(settings)
        text = f"Getting started  ·  {done} of {total} done  ›" if done < total else "Getting started  ·  all set ✓"
        if text != self._guide_shown:
            self._guide_shown = text
            self.guide_button.configure(text=text)

    def open_quickfix(self, axis="x"):
        if not self._close_settings():
            return None
        return self._open("quickfix", lambda: QuickFixWindow(self, axis))

    def close(self):
        self.engine.stop()
        self.root.destroy()

    # --- live updates ----------------------------------------------------------

    def _show_keys(self, k):
        toggle = self.engine.settings.general.precision_toggle
        shown = (k.enable_toggle, k.pause_hold, k.precision_hold, k.recenter, toggle)
        if shown == self._keys_shown:
            return
        self._keys_shown = shown
        for w in self.keys.winfo_children():
            w.destroy()
        self.keys.columnconfigure((0, 1), weight=1, uniform="k")
        for i, (key, caption) in enumerate(((k.enable_toggle, "on / off"), (k.pause_hold, "hold to freeze"),
                                            (k.precision_hold, "tap: slow aim on/off" if toggle else
                                             "hold to aim slowly"), (k.recenter, "re-center"))):
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
        self._show_guide(snap.settings)
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
    """Label, value chip and slider, in one row. With log=True the slider is logarithmic
    (step is then the number of steps), so small values get as much room as big ones."""

    def __init__(self, parent, label, lo, hi, step, fmt, command, help_text="", chip=SUBTLE, log=False):
        self.fmt = fmt
        self.log = (lo, hi) if log else None
        if log:
            lo, hi, step = 0.0, 1.0, 1.0 / step
        self.frame = ctk.CTkFrame(parent, fg_color="transparent")
        top = ctk.CTkFrame(self.frame, fg_color="transparent")
        top.pack(fill="x")
        ctk.CTkLabel(top, text=label, font=font(14, "bold"), text_color=TEXT).pack(side="left")
        self.value = ctk.CTkLabel(top, text="", font=font(13, "bold"), fg_color=chip, corner_radius=8,
                                  text_color=TEXT, width=70, height=26)
        self.value.pack(side="right")
        if help_text:
            ctk.CTkLabel(self.frame, text=help_text, font=font(11), text_color=MUTED, anchor="w", justify="left",
                         wraplength=470).pack(fill="x")
        self.slider = ctk.CTkSlider(self.frame, from_=lo, to=hi, number_of_steps=max(1, round((hi - lo) / step)),
                                    command=self._moved, height=20, button_length=0,
                                    button_color=ACCENT, button_hover_color=ACCENT_HOVER, progress_color=ACCENT,
                                    fg_color=TRACK)
        self.slider.pack(fill="x", pady=(4, 0))
        self.command = command

    def _to_value(self, position):
        if self.log is None:
            return position
        lo, hi = self.log
        return lo * (hi / lo) ** position

    def _moved(self, position):
        value = self._to_value(position)
        self.value.configure(text=self.fmt(value))
        self.command(value)

    def set(self, value):
        position = value
        if self.log is not None:
            lo, hi = self.log
            position = math.log(min(max(value, lo), hi) / lo) / math.log(hi / lo)
        self.slider.set(position)
        self.value.configure(text=self.fmt(value))

    def get(self):
        return self._to_value(self.slider.get())

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
        self._touched = {}   # {section: {keys}} changed in this window, even if changed back
        self.dirty = False
        self._pending = None
        self._capturing = None

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
        for name in ("Feel", "Situations", "Clicks", "Tracking", "Game", "Keys & sound"):
            self.tabs.add(name)
        self.tabs._segmented_button.configure(font=font(13, "bold"), height=36)
        self._feel_tab(self.tabs.tab("Feel"))
        self._situations_tab(self.tabs.tab("Situations"))
        self._clicks_tab(self.tabs.tab("Clicks"))
        self._tracking_tab(self.tabs.tab("Tracking"))
        self._game_tab(self.tabs.tab("Game"))
        self._keys_tab(self.tabs.tab("Keys & sound"))
        self.tabs.set(tab)
        self.tab_changed()
        self.poll()

    # --- change handling -----------------------------------------------------

    def changes(self):
        """Every setting touched in this window, with its value now. Includes ones changed back to
        where they started, so trying something and undoing it really undoes it."""
        return {section: {key: getattr(getattr(self.work, section), key) for key in keys}
                for section, keys in self._touched.items()}

    def _set(self, section, **values):
        self.work = replace(self.work, section, **values)
        self._touched.setdefault(section, set()).update(values)
        self.dirty = bool(config.diff(self.original, self.work))
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
        back = {section: {key: getattr(getattr(self.original, section), key) for key in keys}
                for section, keys in self._touched.items()}
        self.engine.apply_settings(overlay(self.engine.settings, back), save=False)
        self.dirty = False
        return self._close_window()

    def close(self):
        if not self.dirty:
            return self.discard()   # also undoes anything tried and changed back, and pending live updates
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
    # One pair of directions at a time (left & right, or up & down). First how the head
    # moves the camera there (the mode), then only the settings that mode uses, grouped
    # as mouse-like movement and joystick turning. Each stored value appears in one place.

    AXES = {"x": ("right", "left", "Left & right"), "y": ("up", "down", "Up & down")}
    MODE_LABELS = {"joystick": "Joystick", "hybrid": "Mouse + joystick", "follow": "Mouse only"}
    MODE_HELP = {
        "joystick": "Turn your head past the dead zone and the camera keeps turning - further = faster. "
                    "Come back to the middle and it stops.",
        "hybrid": "Small head movements move the camera like a mouse: exactly as far as you move, and it "
                  "stays there. Turn further than the mouse-like area and it keeps turning like a joystick.",
        "follow": "The camera follows your head like a mouse, all the way - it never keeps turning by itself. "
                  "Hold {pause} to move your head back without moving the camera.",
    }
    SIDE_FIELDS = ("deadzone", "start_delay", "full_speed_angle", "max_speed", "min_speed", "curve")

    def _feel_tab(self, tab):
        scroll = scroll_frame(tab)
        scroll.pack(fill="both", expand=True)
        self.feel_scroll = scroll
        self.feel_top = ctk.CTkFrame(scroll, fg_color="transparent")
        self.feel_top.pack(fill="x", pady=(0, 12))
        helpers = ctk.CTkFrame(self.feel_top, fg_color="transparent")
        helpers.pack(fill="x")
        helpers.columnconfigure(0, weight=3)
        helpers.columnconfigure(1, weight=2)
        primary_button(helpers, "Find my best settings (practice game)", self.main.open_practice,
                       height=42).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        secondary_button(helpers, "Quick fixes", lambda: self.main.open_quickfix(self.axis),
                         height=42).grid(row=0, column=1, sticky="ew")
        row = ctk.CTkFrame(self.feel_top, fg_color="transparent")
        row.pack(fill="x", pady=(10, 0))
        ctk.CTkLabel(row, text="Preset", font=font(13, "bold"), text_color=TEXT).pack(side="left")
        small_button(row, "Delete", self._delete_preset, width=70, fg_color=SUBTLE, hover_color=SUBTLE_HOVER,
                     text_color=TEXT).pack(side="right")
        small_button(row, "Save as...", self._save_preset, width=90).pack(side="right", padx=6)
        self.preset_menu = dropdown(row, [CUSTOM_PRESET], command=self._preset_chosen, height=34)
        self.preset_menu.pack(side="left", fill="x", expand=True, padx=(10, 0))
        self._show_presets()

        self.axis, self.side = "x", "right"
        self.axis_buttons = segmented(scroll, [v[2] for v in self.AXES.values()], self._axis_selected, height=42)
        self.axis_buttons.pack(fill="x", pady=(2, 4))
        self.axis_buttons.set(self.AXES["x"][2])
        box = ctk.CTkFrame(scroll, fg_color="transparent")
        box.pack(fill="x")
        items = []   # (widget, shown when, pack options) - laid out by _load_axis
        always = lambda: True
        mode_of = lambda *modes: lambda: self._mode() in modes

        def add(item, when=always, **pack):
            """Lay out a widget (or a SliderRow's frame) when `when()` is true; returns the item."""
            items.append((getattr(item, "frame", item), when, {"fill": "x", **pack}))
            return item

        def heading(text, sub):
            frame = ctk.CTkFrame(box, fg_color="transparent")
            ctk.CTkFrame(frame, height=1, fg_color=BORDER).pack(fill="x", pady=(18, 12))
            ctk.CTkLabel(frame, text=text, font=font(16, "bold"), text_color=TEXT, anchor="w").pack(fill="x")
            ctk.CTkLabel(frame, text=sub, font=font(11), text_color=MUTED, wraplength=470, justify="left",
                         anchor="w").pack(fill="x")
            return frame

        def row(label, lo, hi, step, fmt, command, help_text):
            return SliderRow(box, label, lo, hi, step, fmt, command, help_text)

        deg = lambda v: f"{v:.1f}°"
        speed = lambda v: f"{round(v, 1):g}°/s"
        secs = lambda v: f"{v:.2f} s"
        add(ctk.CTkLabel(box, text="How your head moves the camera", font=font(13, "bold"), text_color=TEXT,
                         anchor="w"), pady=(8, 0))
        self.mode_buttons = add(segmented(box, ["Joystick"], self._mode_selected), pady=(4, 0))
        self.mode_help = add(ctk.CTkLabel(box, text="", font=font(12), text_color=MUTED, wraplength=470,
                                          justify="left", anchor="w"), pady=(6, 8))
        graph_card = add(ctk.CTkFrame(box, fg_color=SUBTLE, corner_radius=14))
        self.graph_scale = window_scaling(tab)
        self.graph = tk.Canvas(graph_card, width=int(500 * self.graph_scale), height=int(170 * self.graph_scale),
                               highlightthickness=0, bd=0)
        self.graph.pack(padx=8, pady=8)
        self.points_note = add(ctk.CTkFrame(box, fg_color="transparent"),
                               lambda: bool(getattr(self.work, self.side).points), pady=(8, 0))
        ctk.CTkLabel(self.points_note, text="This direction uses a custom table from the settings file.",
                     font=font(12), text_color=MUTED).pack(side="left")
        small_button(self.points_note, "Use sliders", self._drop_points, width=110).pack(side="right")
        not_follow = mode_of("joystick", "hybrid")
        self.link_switch = add(switch(box, "Same settings for left and right", self._link_toggled,
                                      font=font(13, "bold"), text_color=TEXT), not_follow, pady=(12, 0), anchor="w")
        self.side_row = add(ctk.CTkFrame(box, fg_color="transparent"),
                            lambda: not_follow() and not self._linked(), pady=(8, 0))
        ctk.CTkLabel(self.side_row, text="Settings for", font=font(13), text_color=MUTED).pack(side="left")
        self.side_buttons = segmented(self.side_row, ["Right", "Left"], self._side_selected, height=32)
        self.side_buttons.pack(side="left", fill="x", expand=True, padx=(10, 0))

        add(heading("Mouse-like movement", "For small, exact aiming: the camera moves as far as your head "
                                           "does, times the sensitivity, and stays there."),
            mode_of("hybrid", "follow"))
        self.rows = {}   # per-direction settings (the side chosen above)
        self.axis_rows = {}
        self.rows["area"] = add(row("Mouse-like area", 0, 20, 0.5, deg, lambda v: self._dir_changed("deadzone", v),
                                    "How far your head can move before the joystick takes over"),
                                mode_of("hybrid"), pady=(10, 0))
        self.axis_rows["gain"] = add(
            SliderRow(box, "Sensitivity", 0.1, 10, 200, lambda v: f"{v:.2f}x" if v < 1 else f"{v:.1f}x",
                      self._gain_changed, "Camera turn for each degree of head movement - lower is more precise",
                      log=True), mode_of("hybrid", "follow"), pady=(10, 0))
        self.axis_rows["slow"] = add(
            row("Slow-movement precision", 10, 100, 5, lambda v: "off" if v >= 99.5 else f"{v:.0f}%",
                lambda v: self._axis_changed("slow", round(v / 100, 2)),
                "Slow head movements turn the camera only this share of the sensitivity, for fine "
                "corrections (like mouse acceleration). 100% = off"),
            mode_of("hybrid", "follow"), pady=(10, 0))
        self.axis_rows["fast"] = add(
            row("Full sensitivity from", 2, 90, 1, lambda v: f"{v:.0f}°/s",
                lambda v: self._axis_changed("fast", round(v)),
                "Head speed where the full sensitivity is reached, so quick moves still cover distance"),
            lambda: self._mode() in ("hybrid", "follow") and self._axis_value("slow") < 1, pady=(10, 0))
        self.axis_rows["wobble"] = add(
            row("Wobble filter", 0.05, 1.5, 0.05, lambda v: f"{v:.2f}°",
                lambda v: self._axis_changed("wobble", round(v, 2)),
                "Head movement smaller than this is ignored. Smaller = fine corrections respond sooner; "
                "bigger = steadier when holding still"),
            mode_of("hybrid", "follow"), pady=(10, 0))
        self.axis_rows["mouse_delay"] = add(
            row("Start delay", 0, 1.0, 0.01, secs, lambda v: self._axis_changed("mouse_delay", round(v, 2)),
                "Movement from rest waits this long; a quick glance that comes back sooner is ignored"),
            mode_of("hybrid", "follow"), pady=(10, 0))

        add(heading("Joystick turning", "For turning further: the camera keeps turning while your head is "
                                        "turned - further = faster."), mode_of("joystick", "hybrid"))
        side_rows = (
            ("deadzone", "Dead zone", 0, 20, 0.1, deg, "How far you can move before the camera starts turning",
             mode_of("joystick")),
            ("blend", None, 0, 10, 0.5, deg, None, mode_of("hybrid")),
            ("start_delay", "Start delay", 0, 2.0, 0.01, secs,
             "Wait this long before turning - a quick glance past the edge doesn't turn", not_follow),
            ("full_speed_angle", "Head turn for full speed", 3, 60, 0.5, deg,
             "Smaller = less head turn needed for top speed", not_follow),
            ("max_speed", "Top speed", 10, 720, 5, speed, "Fastest camera turn", not_follow),
            ("min_speed", "Slowest speed", 0, 120, 0.5, speed, "Speed where turning starts", not_follow),
            ("curve", "Curve", 0.5, 6, 0.05, lambda v: f"{v:.2f}",
             "1 = even; higher = gentler at first, faster further out", not_follow),
        )
        for field, label, lo, hi, step, fmt, help_text, when in side_rows:
            if field == "blend":
                self.axis_rows["blend"] = add(
                    row("Blend from mouse-like", lo, hi, step, fmt,
                        lambda v: self._axis_changed("blend", round(v, 1)),
                        "0 = sharp switch at the edge of the mouse-like area; more = smoother hand-over"),
                    when, pady=(10, 0))
                continue
            self.rows[field] = add(row(label, lo, hi, step, fmt, lambda v, f=field: self._dir_changed(f, v),
                                       help_text), when, pady=(10, 0))

        webcam = lambda: self.work.tracking.source == "webcam"
        add(heading("Steadiness", "Smooths out tracking jitter for these directions. Steadier means a "
                                  "little more lag."))
        self.axis_rows["steady"] = add(
            row("Steadiness", 0.1, 8.0, 0.1,
                lambda v: f"{'steady' if v < 0.8 else 'quick' if v > 2 else 'balanced'} {v:.1f}",
                lambda v: self._axis_changed("steady", round(v, 2)),
                "Left = steadier (less jitter), right = quicker (less lag)"), webcam, pady=(10, 0))
        add(ctk.CTkLabel(box, text="Using OpenTrack: its own filter does the smoothing - set it in OpenTrack.",
                         font=font(11), text_color=MUTED, anchor="w"),
            lambda: self.work.tracking.source != "webcam", pady=(4, 0))
        self._feel_items = items

        self._helpers_section(scroll)
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
        self._load_axis()

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
        for section, values in config.preset_values(new).items():
            self._set(section, **values)
        self._load_axis()
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

    def _helpers_section(self, scroll):
        a = self.work.assist
        ctk.CTkFrame(scroll, height=1, fg_color=BORDER).pack(fill="x", pady=(22, 12))
        ctk.CTkLabel(scroll, text="For all directions", font=font(16, "bold"), text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(scroll, text="Optional helpers - each one is off until you switch it on.", font=font(11),
                     text_color=MUTED, wraplength=470, justify="left").pack(anchor="w")
        self.precision = SliderRow(scroll, "Precision aim speed", 5, 100, 5, lambda v: f"{v:.0f}%",
                                   lambda v: self._set("motion", precision_speed_factor=round(v / 100, 2)),
                                   f"Camera speed while {self.work.keys.precision_hold or 'the precision key'} "
                                   "is held")
        self.precision.frame.pack(fill="x", pady=(10, 0))
        self.precision.set(self.work.motion.precision_speed_factor * 100)
        key = self.work.keys.precision_hold or "the precision key"
        self.toggle_switch = switch(scroll, f"Tap {key} to switch precision aim on and off (instead of holding it)",
                                    lambda: self._set("general", precision_toggle=bool(self.toggle_switch.get())),
                                    font=font(13), text_color=TEXT)
        if self.work.general.precision_toggle:
            self.toggle_switch.select()
        self.toggle_switch.pack(anchor="w", pady=(8, 0))
        self.return_switch = switch(scroll, "Stop when I come back to the middle (joystick)", lambda: self._set(
            "assist", return_stop=bool(self.return_switch.get())), font=font(14, "bold"), text_color=TEXT)
        if a.return_stop:
            self.return_switch.select()
        self.return_switch.pack(anchor="w", pady=(14, 0))
        ctk.CTkLabel(scroll, text="After a joystick turn, the camera stays still once your head is back near the "
                                  "middle (even slightly past it) until you clearly turn again. No slow creeping.",
                     font=font(11), text_color=MUTED, wraplength=470, justify="left").pack(anchor="w")
        self.release_row = SliderRow(scroll, "Turn again by", 0.5, 10, 0.5, lambda v: f"{v:.1f}°",
                                     lambda v: self._set("assist", return_stop_release=round(v, 1)),
                                     "How far you turn from where you rested to start turning again")
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

    # mode, axis and side --------------------------------------------------

    def _axis_index(self):
        return 0 if self.axis == "x" else 1

    def _mode(self):
        return config.axis_modes(self.work)[self._axis_index()]

    def _axis_selected(self, label):
        self.axis = next(k for k, v in self.AXES.items() if v[2] == label)
        self.side = self.AXES[self.axis][0]
        self._load_axis()

    def _side_selected(self, label):
        self.side = label.lower()
        self._load_axis()

    def _mode_selected(self, label):
        mode = next(k for k, v in self.MODE_LABELS.items() if v == label)
        modes = list(config.axis_modes(self.work))
        modes[self._axis_index()] = mode
        self._set("assist", **config.mode_values(*modes))
        self._load_axis()

    def _link_field(self):
        return "link_left_right" if self.axis == "x" else "link_up_down"

    def _linked(self):
        return getattr(self.work.general, self._link_field())

    def _link_toggled(self):
        on = bool(self.link_switch.get())
        self._set("general", **{self._link_field(): on})
        if on:
            self.side = self.AXES[self.axis][0]
            self._copy()
        self._load_axis()

    def _copy(self):
        src = getattr(self.work, self.side)
        self._set(PAIRS[self.side], **{f: getattr(src, f) for f in self.SIDE_FIELDS} | {"points": list(src.points)})
        self.saved_label.configure(text=f"{PAIRS[self.side].title()} now matches {self.side} "
                                        "and will follow its changes")

    def _axis_field(self, name):
        """(section, field) of a setting shared by both directions of the current axis."""
        x = self.axis == "x"
        if name == "gain":
            if self._mode() == "follow":
                return "assist", "vertical_follow_gain"
            return "assist", "hybrid_gain_x" if x else "hybrid_gain_y"
        return {"mouse_delay": ("assist", "mouse_delay_x" if x else "mouse_delay_y"),
                "slow": ("assist", "slow_precision_x" if x else "slow_precision_y"),
                "fast": ("assist", "fast_speed_x" if x else "fast_speed_y"),
                "wobble": ("assist", "wobble_x" if x else "wobble_y"),
                "blend": ("assist", "hybrid_blend" if x else "hybrid_blend_y"),
                "steady": ("webcam", "smoothing_min_cutoff" if x else "vertical_smoothing_min_cutoff")}[name]

    def _axis_value(self, name):
        section, field = self._axis_field(name)
        return getattr(getattr(self.work, section), field)

    def _axis_changed(self, name, value):
        section, field = self._axis_field(name)
        self._set(section, **{field: value})
        if name == "slow":
            self._relayout()   # "Full sensitivity from" only matters with slow-movement precision on

    def _gain_changed(self, value):
        self._axis_changed("gain", round(value, 2) if value < 1 else round(value, 1))

    def _load_axis(self):
        """Show the settings the current axis and mode use, with their current values."""
        pos, neg, _ = self.AXES[self.axis]
        mode = self._mode()
        modes = config.AXIS_MODES[self._axis_index()]
        self.mode_buttons.configure(values=[self.MODE_LABELS[m] for m in modes])
        self.mode_buttons.set(self.MODE_LABELS[mode])
        self.mode_help.configure(text=self.MODE_HELP[mode].format(pause=self.work.keys.pause_hold or "pause"))
        self.link_switch.configure(text=f"Same settings for {pos} and {neg}")
        if self._linked():
            self.link_switch.select()
            self.side = pos
        else:
            self.link_switch.deselect()
        self.side_buttons.configure(values=[pos.title(), neg.title()])
        self.side_buttons.set(self.side.title())
        d = getattr(self.work, self.side)
        for name, row in self.rows.items():
            row.set(getattr(d, "deadzone" if name == "area" else name))
            row.enable(not d.points)
        for name, row in self.axis_rows.items():
            value = self._axis_value(name)
            row.set(value * 100 if name == "slow" else value)
        self._relayout()

    def _relayout(self):
        for widget, _, _ in self._feel_items:
            widget.pack_forget()
        for widget, when, pack in self._feel_items:
            if when():
                widget.pack(**pack)

    def _glance_toggled(self):
        on = bool(self.glance_switch.get())
        self._set("glance", enabled=on)
        if on:
            self.saved_label.configure(text="Tip: run the setup wizard (Tracking tab) so it learns your glances")

    def _drop_points(self):
        self._set(self.side, points=[])
        if self._linked():
            self._set(PAIRS[self.side], points=[])
        self._load_axis()

    @staticmethod
    def _consistent(d, values):
        """`values` plus whatever else must change with them to keep direction `d` valid."""
        new = dataclasses.replace(d, **values)
        values = dict(values)
        if new.full_speed_angle <= new.deadzone:
            values["full_speed_angle"] = round(new.deadzone + 0.5, 3)
        if new.min_speed > new.max_speed:
            values["min_speed"] = new.max_speed
        return values

    def _dir_changed(self, field, value):
        """A per-direction slider moved: store it for the chosen side (and its pair when linked)."""
        d = getattr(self.work, self.side)
        if d.points:
            return
        values = self._consistent(d, {field: round(value, 3)})
        for name, v in values.items():   # deadzone is shown as "Mouse-like area" or "Dead zone"
            for row in ([self.rows["area"]] if name == "deadzone" else []) + [self.rows[name]]:
                if abs(row.get() - v) > 1e-6:
                    row.set(v)
        self._set(self.side, **values)
        pair = getattr(self.work, PAIRS[self.side])
        if self._linked() and not pair.points:   # only what changed, so other differences stay
            self._set(PAIRS[self.side], **self._consistent(pair, values))

    def _plot(self, snap):
        """Camera speed against head angle for both directions of the axis, with the mouse-like
        area (or dead zone) in the middle and a red dot where the head is now."""
        c, k = self.graph, self.graph_scale
        pos, neg, _ = self.AXES[self.axis]
        mode = self._mode()
        a = self.work.assist
        bg, muted = pick(SUBTLE), pick(MUTED)
        c.delete("all")
        c.configure(bg=bg)
        w, h = int(c["width"]), int(c["height"])
        if mode == "follow":
            c.create_text(w / 2, h / 2, text=f"Up/down follows your head like a mouse: "
                                             f"{a.vertical_follow_gain:g}° of camera per degree of head tilt.\n"
                                             "It never keeps turning by itself.",
                          fill=pick(TEXT), font=(FAMILY, 11), justify="center", width=w - 30 * k)
            return
        hybrid = mode == "hybrid"
        blend = a.hybrid_blend if self.axis == "x" else a.hybrid_blend_y
        dp, dn = getattr(self.work, pos), getattr(self.work, neg)
        sides = ((1, DirectionCurve(dp), dp), (-1, DirectionCurve(dn), dn))

        def speed(curve, d, angle):  # joystick speed (angle >= 0), faded in past the mouse-like area
            s = curve.speed(angle)
            if hybrid:
                over = angle - d.deadzone
                s *= 0.0 if over <= 0 else 1.0 if blend <= 0 or over >= blend else over / blend
            return s

        reach = max((max(p[0] for p in d.points) if d.points else d.full_speed_angle) for _, _, d in sides)
        x_max = max(15.0, reach * 1.25)
        y_top = max(10.0, max(speed(curve, d, x_max * i / 100) for _, curve, d in sides for i in range(101)))
        top, bottom = 16 * k, h - 24 * k
        half = w / 2 - 14 * k
        px = lambda angle: w / 2 + angle / x_max * half
        py = lambda v: bottom - v / (y_top * 1.1) * (bottom - top)
        for v in (y_top / 2, y_top):
            c.create_line(8 * k, py(v), w - 8 * k, py(v), fill=pick(BORDER))
            c.create_text(10 * k, py(v) - 2 * k, text=f"{v:.0f}°/s", anchor="sw", fill=muted, font=(FAMILY, 8))
        step = 10 if x_max > 30 else 5
        for angle in range(-int(x_max // step) * step, int(x_max) + 1, step):
            c.create_text(px(angle), bottom + 12 * k, text=f"{abs(angle)}°", fill=muted, font=(FAMILY, 8))
        c.create_rectangle(px(-dn.deadzone), top, px(dp.deadzone), bottom, fill=pick(ZONE), outline="")
        if hybrid:
            gain = a.hybrid_gain_x if self.axis == "x" else a.hybrid_gain_y
            c.create_text(w / 2, top + 2 * k, text=f"mouse-like ×{gain:g}", anchor="n", fill=pick(TEXT),
                          font=(FAMILY, 9, "bold"))
        else:
            c.create_text(w / 2, top + 2 * k, text="dead zone", anchor="n", fill=muted, font=(FAMILY, 9))
        for sign, curve, d in sides:
            pts = []
            for i in range(121):
                angle = x_max * i / 120
                pts += [px(sign * angle), py(speed(curve, d, angle))]
            c.create_line(*pts, fill=pick(ACCENT), width=3)
        c.create_text(14 * k, bottom - 4 * k, text=f"◀ {neg}", anchor="sw", fill=pick(TEXT), font=(FAMILY, 9, "bold"))
        c.create_text(w - 14 * k, bottom - 4 * k, text=f"{pos} ▶", anchor="se", fill=pick(TEXT),
                      font=(FAMILY, 9, "bold"))
        if snap.tracking == TrackingStatus.OK:
            value = snap.yaw if self.axis == "x" else snap.pitch
            sign, curve, d = sides[0] if value >= 0 else sides[1]
            angle = min(abs(value), x_max)
            x, y, r = px(sign * angle), py(speed(curve, d, angle)), 7 * k
            c.create_oval(x - r, y - r, x + r, y + r, fill=pick(DANGER), outline=bg, width=2)

    # --- Situations ----------------------------------------------------------

    OFF = "Off (normal feel)"

    def _situations_tab(self, tab):
        scroll = scroll_frame(tab)
        scroll.pack(fill="both", expand=True)
        ctk.CTkLabel(scroll, text="A different feel for parts of the game", font=font(16, "bold"), text_color=TEXT,
                     anchor="w").pack(fill="x")
        ctk.CTkLabel(scroll, text="HeadMouse can switch to another preset while you aim, build or use a menu, "
                                  "and back again afterwards - for example slow, exact aiming but quick turning "
                                  "while exploring. Press \"Make suggested\" to start from a ready-made feel, "
                                  "then fine-tune it like any preset (Feel tab).",
                     font=font(12), text_color=MUTED, wraplength=470, justify="left", anchor="w").pack(fill="x")
        self.now_label = ctk.CTkLabel(scroll, text="", font=font(13, "bold"), text_color=TEXT, anchor="w")
        self.now_label.pack(fill="x", pady=(8, 0))
        self.situation_widgets = {}
        for name in config.SITUATIONS[1:] + config.SITUATIONS[:1]:   # aiming, building, then menus
            self._situation_card(scroll, name)
        self.situation_sound = switch(scroll, "Short blip when the feel changes",
                                      lambda: self._set("situations", sound=bool(self.situation_sound.get())),
                                      font=font(13), text_color=TEXT)
        if self.work.situations.sound:
            self.situation_sound.select()
        self.situation_sound.pack(anchor="w", pady=(14, 0))
        self._capturing_situation = None

    def _situation_card(self, parent, name):
        s = self.work.situations
        title, text = situations.DESCRIPTIONS[name]
        box = ctk.CTkFrame(parent, fg_color=SUBTLE, corner_radius=14)
        box.pack(fill="x", pady=(12, 0))
        ctk.CTkLabel(box, text=title, font=font(15, "bold"), text_color=TEXT, anchor="w").pack(
            fill="x", padx=14, pady=(12, 0))
        ctk.CTkLabel(box, text=text, font=font(11), text_color=MUTED, wraplength=440, justify="left",
                     anchor="w").pack(fill="x", padx=14)
        row = ctk.CTkFrame(box, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(8, 0))
        ctk.CTkLabel(row, text="Feel", font=font(13, "bold"), text_color=TEXT, width=50, anchor="w").pack(side="left")
        small_button(row, "Make suggested", lambda: self._make_suggested(name), width=130).pack(side="right")
        menu = dropdown(row, [self.OFF], command=lambda v: self._situation_preset(name, v), height=32)
        menu.pack(side="left", fill="x", expand=True, padx=(0, 8))
        row = ctk.CTkFrame(box, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(8, 0))
        ctk.CTkLabel(row, text="Key", font=font(13, "bold"), text_color=TEXT, width=50, anchor="w").pack(side="left")
        key = ctk.CTkButton(row, text=getattr(s, f"{name}_key") or "none", width=130, height=32, corner_radius=8,
                            font=font(13, "bold"), command=lambda: self._capture_situation(name), **self.KEYCAP)
        key.pack(side="left")
        how = segmented(row, ["Hold", "Tap on/off"], lambda v: self._set(
            "situations", **{f"{name}_toggle": v != "Hold"}), height=32)
        how.set("Tap on/off" if getattr(s, f"{name}_toggle") else "Hold")
        how.pack(side="left", fill="x", expand=True, padx=(8, 0))
        widgets = {"menu": menu, "key": key, "how": how}
        if name == "menu":
            pointer = switch(box, "Also when the game shows a mouse pointer", lambda: self._set(
                "situations", menu_pointer=bool(pointer.get())), font=font(13), text_color=TEXT)
            if s.menu_pointer:
                pointer.select()
            pointer.pack(anchor="w", padx=14, pady=(10, 0))
            widgets["pointer"] = pointer
        ctk.CTkFrame(box, height=10, fg_color="transparent").pack()
        self.situation_widgets[name] = widgets
        self._show_situation_presets(name)

    def _show_situation_presets(self, name):
        menu = self.situation_widgets[name]["menu"]
        chosen = getattr(self.work.situations, f"{name}_preset")
        names = [self.OFF] + config.list_presets(self.engine.path)
        if chosen and chosen not in names:
            names.append(chosen)
        menu.configure(values=names)
        menu.set(chosen or self.OFF)

    def _situation_preset(self, name, value):
        self._set("situations", **{f"{name}_preset": "" if value == self.OFF else value})
        if value != self.OFF and not getattr(self.work.situations, f"{name}_key") \
                and not (name == "menu" and self.work.situations.menu_pointer):
            self.saved_label.configure(text=f"Now choose the key for {config.SITUATION_NAMES[name].lower()}")

    def _make_suggested(self, name):
        preset = situations.suggested_name(name)
        try:
            config.save_preset(self.engine.path, preset, situations.suggested_feel(self.work, name))
        except config.SettingsError as e:
            messagebox.showerror("HeadMouse", str(e), parent=self.top)
            return
        key, toggle = situations.SUGGESTED_KEYS[name]
        values = {f"{name}_preset": preset}
        if key and not getattr(self.work.situations, f"{name}_key"):
            values.update({f"{name}_key": key, f"{name}_toggle": toggle})
            self.situation_widgets[name]["key"].configure(text=key)
            self.situation_widgets[name]["how"].set("Tap on/off" if toggle else "Hold")
        self._set("situations", **values)
        for other in config.SITUATIONS:
            self._show_situation_presets(other)
        self._show_presets()
        self.saved_label.configure(text=f'Made the preset "{preset}" - change it on the Feel tab, press Save to use it')

    def _capture_situation(self, name):
        self._capturing_situation = name
        self.situation_widgets[name]["key"].configure(text="Press a key...", **self.KEYCAP_ACTIVE)
        self.top.bind("<KeyPress>", self._situation_key)
        self.top.bind("<ButtonPress>", self._situation_key)
        self.top.focus_force()

    def _situation_key(self, event):
        name = self._capturing_situation
        if name is None:
            return
        mouse = {2: "MIDDLEMOUSE", 3: "RIGHTMOUSE", 4: "MOUSE4", 5: "MOUSE5"}
        if getattr(event, "num", "??") in mouse:
            key = mouse[event.num]
        elif getattr(event, "num", "??") == 1:
            return   # the click that started choosing
        elif event.keysym == "Escape":
            key = getattr(self.work.situations, f"{name}_key")
        elif event.keysym in ("Delete", "BackSpace"):
            key = ""
        else:
            key = name_from_tk_keysym(event.keysym)
            if key is None:
                self.saved_label.configure(text=f"'{event.keysym}' can't be used - try another key")
                return
            own = next((f for f in dataclasses.fields(config.KeySettings) if getattr(self.work.keys, f.name) == key),
                       None)
            if own:
                self.saved_label.configure(text=f"{key} is one of HeadMouse's own keys - choose the game's key")
                return
        self._set("situations", **{f"{name}_key": key})
        self.situation_widgets[name]["key"].configure(text=key or "none", **self.KEYCAP)
        self._capturing_situation = None
        self.top.unbind("<KeyPress>")
        self.top.unbind("<ButtonPress>")

    # --- Clicks ---------------------------------------------------------------

    def _clicks_tab(self, tab):
        a = self.work.actions
        scroll = scroll_frame(tab)
        scroll.pack(fill="both", expand=True)
        ctk.CTkLabel(scroll, text="Click without the mouse", font=font(16, "bold"), text_color=TEXT,
                     anchor="w").pack(fill="x")
        ctk.CTkLabel(scroll, text="Let a key, a foot pedal or a face gesture press the mouse buttons - e.g. open "
                                  "your mouth to hold the right button while you aim, or tap a key to attack. "
                                  "Buttons are only pressed while head control is on and the game is in front.",
                     font=font(12), text_color=MUTED, wraplength=470, justify="left", anchor="w").pack(fill="x")
        self.actions_switch = switch(scroll, "Use click actions", lambda: self._set(
            "actions", enabled=bool(self.actions_switch.get())), font=font(14, "bold"), text_color=TEXT)
        if a.enabled:
            self.actions_switch.select()
        self.actions_switch.pack(anchor="w", pady=(10, 0))
        self.actions_now = ctk.CTkLabel(scroll, text="", font=font(12, "bold"), text_color=TEXT, anchor="w")
        self.actions_now.pack(fill="x", pady=(4, 0))
        labels = list(actions.ACTIONS.values())
        to_key = {v: k for k, v in actions.ACTIONS.items()}

        box = ctk.CTkFrame(scroll, fg_color=SUBTLE, corner_radius=14)
        box.pack(fill="x", pady=(12, 0))
        ctk.CTkLabel(box, text="Keys or a foot pedal", font=font(15, "bold"), text_color=TEXT, anchor="w").pack(
            fill="x", padx=14, pady=(12, 0))
        ctk.CTkLabel(box, text="The game still gets the key too, so choose keys it doesn't use (or a pedal).",
                     font=font(11), text_color=MUTED, wraplength=440, justify="left", anchor="w").pack(fill="x", padx=14)
        self.action_keys = {}
        for i in (1, 2, 3):
            row = ctk.CTkFrame(box, fg_color="transparent")
            row.pack(fill="x", padx=14, pady=(8, 0))
            b = ctk.CTkButton(row, text=getattr(a, f"key{i}") or "choose key", width=120, height=32, corner_radius=8,
                              font=font(13, "bold"), command=lambda i=i: self._capture_action_key(i), **self.KEYCAP)
            b.pack(side="left")
            menu = dropdown(row, labels, command=lambda v, i=i: self._set("actions", **{f"key{i}_action": to_key[v]}),
                            height=32)
            menu.set(actions.ACTIONS[getattr(a, f"key{i}_action")])
            menu.pack(side="left", fill="x", expand=True, padx=(8, 0))
            self.action_keys[i] = b
        ctk.CTkFrame(box, height=10, fg_color="transparent").pack()

        box = ctk.CTkFrame(scroll, fg_color=SUBTLE, corner_radius=14)
        box.pack(fill="x", pady=(12, 0))
        ctk.CTkLabel(box, text="Face gestures (built-in webcam)", font=font(15, "bold"), text_color=TEXT,
                     anchor="w").pack(fill="x", padx=14, pady=(12, 0))
        ctk.CTkLabel(box, text="The bar shows how strongly each gesture is seen right now; the slider is how far "
                               "it must go to count. Make the gesture a few times and set the slider a little "
                               "below your usual peak - high enough that talking doesn't reach it.",
                     font=font(11), text_color=MUTED, wraplength=440, justify="left", anchor="w").pack(fill="x", padx=14)
        small_button(box, "Measure my gestures", self._measure_gestures, width=180).pack(anchor="w", padx=14,
                                                                                          pady=(8, 0))
        self.gesture_meters = {}
        self.gesture_thresholds = {}
        for g, name in actions.GESTURES.items():
            row = ctk.CTkFrame(box, fg_color="transparent")
            row.pack(fill="x", padx=14, pady=(10, 0))
            ctk.CTkLabel(row, text=name, font=font(13, "bold"), text_color=TEXT, width=120, anchor="w").pack(side="left")
            menu = dropdown(row, labels, command=lambda v, g=g: self._set("actions", **{f"{g}_action": to_key[v]}),
                            height=30)
            menu.set(actions.ACTIONS[getattr(a, f"{g}_action")])
            menu.pack(side="left", fill="x", expand=True)
            meter = ctk.CTkProgressBar(box, height=10, progress_color=ACCENT, fg_color=TRACK)
            meter.pack(fill="x", padx=14, pady=(6, 0))
            meter.set(0)
            threshold = SliderRow(box, "Counts from", 0.05, 1.0, 0.05, lambda v: f"{v * 100:.0f}%",
                                  lambda v, g=g: self._set("actions", **{f"{g}_threshold": round(v, 2)}))
            threshold.frame.pack(fill="x", padx=14, pady=(2, 0))
            threshold.set(getattr(a, f"{g}_threshold"))
            self.gesture_meters[g] = meter
            self.gesture_thresholds[g] = threshold
        self.hold_row = SliderRow(box, "Hold the gesture for", 0, 0.6, 0.05, lambda v: f"{v:.2f} s",
                                  lambda v: self._set("actions", gesture_hold=round(v, 2)),
                                  "Shorter reacts sooner; longer ignores quick expressions like talking")
        self.hold_row.frame.pack(fill="x", padx=14, pady=(12, 0))
        self.hold_row.set(a.gesture_hold)
        self.steady_switch = switch(box, "Keep the aim still while a gesture starts or ends", lambda: self._set(
            "actions", steady_gestures=bool(self.steady_switch.get())), font=font(13), text_color=TEXT)
        if a.steady_gestures:
            self.steady_switch.select()
        self.steady_switch.pack(anchor="w", padx=14, pady=(12, 0))
        ctk.CTkLabel(box, text="Opening your mouth tilts your face a little, which would nudge the aim as you "
                               "click. Switch this off if the camera pauses while you talk.", font=font(11),
                     text_color=MUTED, wraplength=440, justify="left", anchor="w").pack(fill="x", padx=14)
        ctk.CTkFrame(box, height=12, fg_color="transparent").pack()

    def _measure_gestures(self):
        def done(thresholds):
            for g, value in thresholds.items():
                self.gesture_thresholds[g].set(value)
            self._set("actions", **{f"{g}_threshold": v for g, v in thresholds.items()})
            if thresholds:
                self.saved_label.configure(text="Gesture thresholds set from your measurement - press Save to keep them")
        GestureCalWindow(self.main, done)

    def _capture_action_key(self, i):
        self._capturing_action = i
        self.action_keys[i].configure(text="Press a key...", **self.KEYCAP_ACTIVE)
        self.top.bind("<KeyPress>", self._action_key)
        self.top.focus_force()

    def _action_key(self, event):
        i = getattr(self, "_capturing_action", None)
        if i is None:
            return
        if event.keysym == "Escape":
            key = getattr(self.work.actions, f"key{i}")
        elif event.keysym in ("Delete", "BackSpace"):
            key = ""
        else:
            key = name_from_tk_keysym(event.keysym)
            if key is None:
                self.saved_label.configure(text=f"'{event.keysym}' can't be used - try another key")
                return
            if any(getattr(self.work.keys, f.name) == key for f in dataclasses.fields(config.KeySettings)):
                self.saved_label.configure(text=f"{key} is one of HeadMouse's own keys - choose another")
                return
        self._set("actions", **{f"key{i}": key})
        self.action_keys[i].configure(text=key or "choose key", **self.KEYCAP)
        self._capturing_action = None
        self.top.unbind("<KeyPress>")

    def _show_clicks(self, snap):
        face = snap.face or {}
        for g, meter in self.gesture_meters.items():
            meter.set(min(1.0, face.get(g, 0.0)))
            meter.configure(progress_color=STATE_COLORS["ACTIVE"] if g in snap.gestures else ACCENT)
        held = ", ".join(snap.buttons) or "none"
        seen = ", ".join(actions.GESTURES[g].lower() for g in snap.gestures) or "none"
        note = "" if face or not self.work.actions.enabled else "  ·  (gestures need the built-in webcam)"
        self.actions_now.configure(text=f"Mouse buttons held: {held}  ·  gestures: {seen}{note}")

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
        ctk.CTkLabel(cam, text="Steadiness (smoothing) is set separately for left/right and up/down on the "
                               "Feel tab.", font=font(11), text_color=MUTED, wraplength=470, justify="left",
                     anchor="w").pack(fill="x", padx=14, pady=(8, 14))

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
                             ("precision_hold", "Precision aim"), ("recenter", "Re-center"),
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
        if self.tabs.get() == "Clicks":
            self._show_clicks(snap)
        if self.tabs.get() == "Situations":
            now = config.SITUATION_NAMES[snap.situation] if snap.situation else "normal feel"
            pointer = ""
            if self.work.situations.menu_pointer and hasattr(self.engine, "pointer_visible"):
                pointer = "  ·  mouse pointer " + ("shown" if self.engine.pointer_visible() else "hidden")
            self.now_label.configure(text=f"Using now: {now}{pointer}")
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


class GestureCalWindow(Child):
    """Measures each face gesture: relaxed first, then each gesture held, and suggests thresholds."""

    PROMPTS = {"mouth": "Open your mouth wide", "brows": "Raise your eyebrows", "smile": "Smile broadly",
               "pucker": "Pucker your lips (like a kiss)"}
    RELAX, HOLD, LEAD = 3.0, 2.5, 0.8   # seconds: relaxed, holding a gesture, getting into it

    def __init__(self, main, on_done):
        super().__init__(main, "HeadMouse - measure gestures", "520x420")
        self.on_done = on_done
        self.rest = {g: [] for g in actions.GESTURES}
        self.peak = {g: [] for g in actions.GESTURES}
        self.plan = [("rest", None)] + [(g, g) for g in actions.GESTURES]
        self.step, self.step_start = -1, None
        self.results = {}
        bar = ctk.CTkFrame(self.top, fg_color="transparent")
        bar.pack(side="bottom", fill="x", padx=24, pady=(6, 18))
        self.primary = primary_button(bar, "Start", self.start, width=180)
        self.primary.pack(side="right")
        secondary_button(bar, "Cancel", self.close, width=140).pack(side="left")
        body = card(self.top)
        body.pack(fill="both", expand=True, padx=24, pady=(18, 6))
        self.title = ctk.CTkLabel(body, text="Measure my gestures", font=font(22, "bold"), text_color=TEXT,
                                  anchor="w")
        self.title.pack(fill="x", padx=20, pady=(18, 4))
        self.text = ctk.CTkLabel(body, text="Face the camera. First relax your face for a few seconds, then make "
                                            "each gesture when asked and hold it. It takes about 20 seconds.",
                                 font=font(14), text_color=MUTED, wraplength=440, justify="left", anchor="w")
        self.text.pack(fill="x", padx=20)
        self.meter = ctk.CTkProgressBar(body, height=12, progress_color=ACCENT, fg_color=TRACK)
        self.meter.pack(fill="x", padx=20, pady=(18, 0))
        self.meter.set(0)

    def start(self):
        if not self.engine.snapshot().face:
            self.text.configure(text="The camera isn't reading your face yet. Switch on \"Use click actions\", "
                                     "wait a few seconds and face the camera.", text_color=DANGER)
            return
        self.primary.configure(state="disabled", text="Measuring...")
        self._next()
        self._poll()

    def _next(self):
        self.step += 1
        self.step_start = time.monotonic()
        if self.step >= len(self.plan):
            self._finish()
            return
        what, gesture = self.plan[self.step]
        if gesture is None:
            self.title.configure(text="Relax your face")
            self.text.configure(text="Look at the screen with a normal face.", text_color=MUTED)
        else:
            self.title.configure(text=self.PROMPTS[gesture])
            self.text.configure(text="...and hold it until the bar is full.", text_color=MUTED)

    def _poll(self):
        if not self.alive() or self.step >= len(self.plan):
            return
        what, gesture = self.plan[self.step]
        elapsed = time.monotonic() - self.step_start
        length = self.RELAX if gesture is None else self.LEAD + self.HOLD
        face = self.engine.snapshot().face or {}
        if face:
            if gesture is None:
                for g in actions.GESTURES:
                    self.rest[g].append(face.get(g, 0.0))
            elif elapsed >= self.LEAD:
                self.peak[gesture].append(face.get(gesture, 0.0))
        self.meter.set(min(1.0, elapsed / length))
        if elapsed >= length:
            self._next()
        self.top.after(50, self._poll)

    def _finish(self):
        lines = []
        for g, name in actions.GESTURES.items():
            threshold, verdict = actions.suggest_threshold(self.rest[g], self.peak[g])
            self.results[g] = threshold
            lines.append(f"{name}: {verdict}" + (f"  (counts from {threshold * 100:.0f}%)" if threshold else ""))
        self.title.configure(text="Done")
        self.text.configure(text="\n".join(lines) + "\n\nUse the clear ones for actions you need often.",
                            text_color=TEXT)
        self.meter.set(1)
        self.primary.configure(state="normal", text="Use these", command=self.use)

    def use(self):
        self.on_done({g: t for g, t in self.results.items() if t is not None})
        self.close()


class GuideWindow(Child):
    """Getting started: the steps that make HeadMouse work well, ticked off as they are done."""

    def __init__(self, main):
        super().__init__(main, "HeadMouse - getting started", "560x760")
        bar = ctk.CTkFrame(self.top, fg_color="transparent")
        bar.pack(side="bottom", fill="x", padx=24, pady=(6, 18))
        primary_button(bar, "Done", self.close, width=150).pack(side="right")
        outer = card(self.top)
        outer.pack(fill="both", expand=True, padx=24, pady=(18, 6))
        self.body = scroll_frame(outer)
        self.body.pack(fill="both", expand=True, padx=4, pady=4)
        self._shown = None
        self.refresh()

    def refresh(self):
        if not self.alive():
            return
        settings = self.engine.settings
        steps = guide.steps(settings)
        state = [(st.key, st.done) for st in steps]
        if state != self._shown:
            self._shown = state
            for w in self.body.winfo_children():
                w.destroy()
            ctk.CTkLabel(self.body, text="Getting started", font=font(22, "bold"), text_color=TEXT,
                         anchor="w").pack(fill="x", padx=14, pady=(14, 2))
            ctk.CTkLabel(self.body, text="These steps make HeadMouse fit you. Do them in order; the optional ones "
                                         "help with particular things.", font=font(13), text_color=MUTED,
                         wraplength=440, justify="left", anchor="w").pack(fill="x", padx=14)
            for st in steps:
                self._step(st)
        self.top.after(1000, self.refresh)

    def _step(self, st):
        box = ctk.CTkFrame(self.body, fg_color=SUBTLE, corner_radius=14)
        box.pack(fill="x", padx=14, pady=(10, 0))
        top = ctk.CTkFrame(box, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=(10, 0))
        mark = "✓" if st.done else "○"
        ctk.CTkLabel(top, text=mark, font=font(18, "bold"), width=28,
                     text_color=STATE_COLORS["ACTIVE"] if st.done else MUTED).pack(side="left")
        ctk.CTkLabel(top, text=st.title, font=font(14, "bold"), text_color=TEXT, anchor="w", wraplength=300,
                     justify="left").pack(side="left", fill="x", expand=True)
        small_button(top, "Open" if st.done else "Start", lambda k=st.key: self.open(k), width=80,
                     **({} if not st.done else dict(fg_color=PILL, hover_color=SUBTLE_HOVER,
                                                     text_color=TEXT))).pack(side="right")
        ctk.CTkLabel(box, text=st.why, font=font(11), text_color=MUTED, wraplength=360, justify="left",
                     anchor="w").pack(fill="x", padx=(52, 12), pady=(0, 10))

    def open(self, key):
        m = self.main
        target = {"wizard": m.open_wizard, "game": lambda: m.open_settings("Game"),
                  "feel": lambda: m.open_settings("Feel"), "practice": m.open_practice,
                  "situations": lambda: m.open_settings("Situations"), "clicks": lambda: m.open_settings("Clicks"),
                  "glance": lambda: m.open_settings("Feel")}[key]
        target()


class QuickFixWindow(Child):
    """Say what feels wrong; each tap makes a small change that is used and saved straight away."""

    def __init__(self, main, axis="x"):
        super().__init__(main, "HeadMouse quick fixes", "560x760")
        self.axis = axis
        self.current = self.engine.settings   # the engine applies changes a moment later
        self.target = None                     # None = the normal feel, else a situation's feel
        self.history = []   # (normal settings, situation, preset name, feel) before each change, for Undo
        buttons = ctk.CTkFrame(self.top, fg_color="transparent")
        buttons.pack(side="bottom", fill="x", padx=24, pady=(6, 18))
        primary_button(buttons, "Done", self.close, width=150).pack(side="right")
        self.undo_button = secondary_button(buttons, "Undo last change", self.undo, width=200, state="disabled")
        self.undo_button.pack(side="left")
        outer = card(self.top)
        outer.pack(fill="both", expand=True, padx=24, pady=(18, 6))
        body = scroll_frame(outer)
        body.pack(fill="both", expand=True, padx=4, pady=4)
        ctk.CTkLabel(body, text="What feels wrong?", font=font(22, "bold"), text_color=TEXT,
                     anchor="w").pack(fill="x", padx=14, pady=(18, 2))
        ctk.CTkLabel(body, text="Tap the problem. HeadMouse makes a small change and uses it straight away - "
                                "try it in the game, and tap again if it needs more. Every change is saved "
                                "and can be undone.", font=font(13), text_color=MUTED, wraplength=440,
                     justify="left", anchor="w").pack(fill="x", padx=14)
        feels = ["Normal"] + [config.SITUATION_NAMES[n] for n in config.SITUATIONS[1:] + config.SITUATIONS[:1]
                              if getattr(self.current.situations, f"{n}_preset")]
        self.target_buttons = None
        if len(feels) > 1:
            ctk.CTkLabel(body, text="Which feel is wrong?", font=font(13, "bold"), text_color=TEXT,
                         anchor="w").pack(fill="x", padx=14, pady=(12, 0))
            self.target_buttons = segmented(body, feels, self._target_selected, height=36)
            self.target_buttons.pack(fill="x", padx=14, pady=(4, 0))
            last = self.engine.snapshot().situation
            self.target_buttons.set(config.SITUATION_NAMES[last] if last else "Normal")
            self.target = last
        self.axis_buttons = segmented(body, ["Left & right", "Up & down"], self._axis_selected, height=40)
        self.axis_buttons.pack(fill="x", padx=14, pady=(14, 4))
        self.axis_buttons.set("Left & right" if axis == "x" else "Up & down")
        self.mode_label = ctk.CTkLabel(body, text="", font=font(12), text_color=MUTED, anchor="w")
        self.mode_label.pack(fill="x", padx=14)
        self.fix_frame = ctk.CTkFrame(body, fg_color="transparent")
        self.fix_frame.pack(fill="x", padx=14, pady=(8, 0))
        self.result = ctk.CTkLabel(body, text="", font=font(13), text_color=TEXT, wraplength=440, justify="left",
                                   anchor="w")
        self.result.pack(fill="x", padx=14, pady=(4, 8), after=self.mode_label)
        self._show_fixes()

    def _target_selected(self, label):
        self.target = next((n for n in config.SITUATIONS if config.SITUATION_NAMES[n] == label), None)
        self.result.configure(text="")
        self._show_fixes()

    def _axis_selected(self, label):
        self.axis = "x" if label == "Left & right" else "y"
        self._show_fixes()

    def _feel(self):
        try:
            return quickfix.target_feel(self.engine.path, self.current, self.target)
        except config.SettingsError:
            return self.current, None

    def _show_fixes(self):
        for w in self.fix_frame.winfo_children():
            w.destroy()
        s, preset = self._feel()
        mode = config.axis_modes(s)[0 if self.axis == "x" else 1]
        where = f'the preset "{preset}"' if preset else "your normal feel"
        self.mode_label.configure(text=f"Uses {SettingsWindow.MODE_LABELS[mode]}. Changes go into {where}.",
                                  wraplength=440, justify="left")
        for fix in quickfix.available(s, self.axis):
            secondary_button(self.fix_frame, fix.label, lambda k=fix.key: self.apply(k), height=40,
                             anchor="w").pack(fill="x", pady=3)

    def apply(self, key):
        feel, preset = self._feel()
        new_feel, lines = quickfix.apply(feel, self.axis, key)
        if not lines:
            self.result.configure(text="That's already as far as it goes. Try another fix, or look at "
                                       "Settings > Feel.", text_color=MUTED)
            return
        try:
            new = quickfix.store(self.engine.path, self.current, self.target, preset, new_feel)
        except config.SettingsError as e:
            messagebox.showerror("HeadMouse", str(e), parent=self.top)
            return
        self.history.append((self.current, self.target, preset, feel))
        self.current = new
        self.engine.apply_settings(new, save=True)
        tip = quickfix.tip(feel, self.axis, key)
        self.result.configure(text="Changed:\n" + "\n".join(f"•  {line}" for line in lines)
                              + (f"\n\nTip: {tip}" if tip else ""), text_color=TEXT)
        self.undo_button.configure(state="normal")
        self._show_fixes()

    def undo(self):
        if not self.history:
            return
        self.current, situation, preset, feel = self.history.pop()
        if situation is not None and not config.is_builtin_preset(preset):
            config.save_preset(self.engine.path, preset, feel)   # the preset as it was
        self.engine.apply_settings(self.current, save=True)
        self.result.configure(text="Undone - back to how it was before that change.", text_color=MUTED)
        if not self.history:
            self.undo_button.configure(state="disabled")
        self._show_fixes()


class PracticeWindow(Child):
    """Practice check-up: short blocks of targets that measure your settings, try a few
    variations and keep only what clearly works better (see practice.py)."""

    SCENE = ("#0f172a", "#0b1120")
    GRID = ("#1e293b", "#172033")
    PX_PER_DEG = {"precision": 16.0, "steady": 16.0, "turns": 8.0}
    GET_READY = 2.5   # seconds between blocks

    def __init__(self, main):
        super().__init__(main, "HeadMouse practice", "780x760")
        self.original = self.engine.settings
        self.checkup = None
        self.block = None
        self.trial = None
        self.cam_start = (0.0, 0.0)
        self.next_at = None
        self.block_starts = None
        self.last_t = None
        self.playing = False
        self.done_blocks = 0
        self.engine.set_practice(True)

        buttons = ctk.CTkFrame(self.top, fg_color="transparent")
        buttons.pack(side="bottom", fill="x", padx=24, pady=(6, 18))
        self.secondary = secondary_button(buttons, "Cancel", self.close, width=200)
        self.secondary.pack(side="left")
        self.primary = primary_button(buttons, "Start", self.start, width=240)
        self.primary.pack(side="right")
        body = card(self.top)
        body.pack(fill="both", expand=True, padx=24, pady=(18, 6))
        self.heading = ctk.CTkLabel(body, text="Find my best settings", font=font(22, "bold"),
                                    text_color=TEXT, anchor="w")
        self.heading.pack(fill="x", padx=22, pady=(18, 2))
        self.text = ctk.CTkLabel(body, font=font(14), text_color=MUTED, wraplength=700, justify="left", anchor="w",
                                 text="Steer the crosshair onto each target with your head, just like in the game, "
                                      "and hold it there for a moment - it turns green. HeadMouse measures how well "
                                      "your settings work, tries a few small variations, and keeps only what "
                                      "clearly works better. Short breaks between parts come by themselves; "
                                      "nothing changes unless you choose to keep it at the end.")
        self.text.pack(fill="x", padx=22)
        self.choices = ctk.CTkFrame(body, fg_color="transparent")
        self.choices.pack(fill="x", padx=22, pady=(12, 0))
        self.focus = segmented(self.choices, list(practice.FOCUSES.values()), None, height=40)
        self.focus.set(practice.FOCUSES["all"])
        self.focus.pack(fill="x")
        feels = ["Normal feel"] + [f"{config.SITUATION_NAMES[n]} feel" for n in config.SITUATIONS[1:] +
                                   config.SITUATIONS[:1] if getattr(self.original.situations, f"{n}_preset")]
        self.target, self.target_preset = None, None
        self.feel_choice = None
        if len(feels) > 1:
            self.feel_choice = segmented(self.choices, feels, self._feel_chosen, height=34)
            self.feel_choice.set("Normal feel")
            self.feel_choice.pack(fill="x", pady=(8, 0))
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

    def _feel_chosen(self, label):
        self.target = next((n for n in config.SITUATIONS if f"{config.SITUATION_NAMES[n]} feel" == label), None)
        if self.target in ("aim", "build"):
            self.focus.set(practice.FOCUSES["aim"])

    def start(self):
        focus = next(k for k, v in practice.FOCUSES.items() if v == self.focus.get())
        self.engine.apply_settings(self.original, save=False)
        try:
            feel, self.target_preset = quickfix.target_feel(self.engine.path, self.original, self.target)
        except config.SettingsError as e:
            messagebox.showerror("HeadMouse", str(e), parent=self.top)
            return
        self.checkup = practice.Checkup(feel, focus=focus)
        self.done_blocks = 0
        self.choices.pack_forget()
        self.primary.configure(state="disabled", text="Playing...")
        self.secondary.configure(text="Stop", command=self.close)
        self._begin(self.checkup.next_block())

    def _begin(self, block):
        """Show the next block after a short get-ready pause."""
        self.block, self.trial = block, None
        if block is None:
            self._show_result()
            return
        self.engine.apply_settings(block.settings, save=False)   # this block's settings, tried live
        self.playing = True
        self.next_at = time.monotonic() + self.GET_READY
        self.heading.configure(text=block.title)
        what = {"precision": "Small targets: steer onto each one and hold still until it turns green.",
                "turns": "Far targets: turn to each one (follow the arrow) and hold it.",
                "steady": "Hold the crosshair as still as you can inside the circle."}[block.kind]
        trying = f"  Trying: {block.trying}." if block.trying and block.trying != "your settings" else ""
        self.text.configure(text=what + trying)
        self.status.configure(text="Get ready...")

    def _next_target(self, snap):
        if len(self.block.trials) == len(self.block.targets):
            self.playing = False
            self.done_blocks += 1
            self._begin(self.checkup.next_block(self.block))
            return
        self.trial = self.block.new_trial(self.block.targets[len(self.block.trials)])
        self.cam_start = snap.practice_camera
        n, total = len(self.block.trials) + 1, len(self.block.targets)
        self.status.configure(text=f"Target {n} of {total}" if self.block.kind != "steady" else
                              f"Hold steady {n} of {total}")

    def _show_result(self):
        c = self.checkup
        self.playing = False
        if not self.original.general.checkup_done:   # for the Getting started list
            self.original = replace(self.original, "general", checkup_done=True)
        self.engine.apply_settings(self.original, save=True)
        lines = []
        if "precision" in c.scores:
            before, after = c.scores["precision"]
            better = f" ({(after / before - 1) * 100:.0f}% better)" if before > 0 and after > before * 1.01 else ""
            lines.append(f"Small aiming score: {before:.2f} → {after:.2f}{better}")
        if "updown" in c.scores:
            before, after = c.scores["updown"]
            better = f" ({(after / before - 1) * 100:.0f}% better)" if before > 0 and after > before * 1.01 else ""
            lines.append(f"Up & down aiming score: {before:.2f} → {after:.2f}{better}")
        if "turns" in c.scores:
            before, after = c.scores["turns"]
            lines.append(f"Big turns: {before:.1f} s → {after:.1f} s per target")
        if "steady" in c.scores:
            lines.append(f"Holding still: wobble {c.scores['steady'][0]:.2f}° "
                         + ("(steady)" if c.scores["steady"][0] <= practice.WOBBLY else "(a bit shaky)"))
        changes = practice.changes(c.original, c.best)
        if self.target is not None:
            changes = [f'In "{self.target_preset}": {line}' for line in changes]
        self.canvas.delete("all")
        if c.changed and changes:
            self.heading.configure(text="Found settings that work better for you")
            text = "\n".join(lines) + "\n\nWhat would change:\n" + "\n".join(f"•  {line}" for line in changes)
            self.primary.configure(state="normal", text="Use the new settings", command=self._use_new)
            self.secondary.configure(text="Keep my old settings", command=self.close)
        else:
            self.heading.configure(text="Your settings already suit you")
            text = "\n".join(lines) + "\n\nNothing tried clearly worked better, so nothing changes."
            self.primary.configure(state="normal", text="Done", command=self.close)
            self.secondary.configure(text="Practice again", command=self._restart)
        self.text.configure(text=text)
        self.status.configure(text="")
        self._draw_notes(c.notes)
        self.progress.set(1)

    def _draw_notes(self, notes):
        c, k = self.canvas, self.k
        c.configure(bg=pick(SUBTLE))
        item = c.create_text(16 * k, 14 * k, text="What was tried:", anchor="nw", fill=pick(TEXT),
                             font=(FAMILY, 11, "bold"))
        for note in notes[:12]:
            y = c.bbox(item)[3] + 6 * k
            item = c.create_text(16 * k, y, text="•  " + note, anchor="nw", fill=pick(MUTED), font=(FAMILY, 10),
                                 width=int(c["width"]) - 32 * k)

    def _use_new(self):
        self.engine.set_practice(False)
        try:
            best = replace(self.checkup.best, "general", checkup_done=True)
            new = quickfix.store(self.engine.path, self.original, self.target, self.target_preset, best)
        except config.SettingsError as e:
            messagebox.showerror("HeadMouse", str(e), parent=self.top)
            return
        self.engine.apply_settings(new, save=True)      # saved (and the old settings backed up)
        self.engine.play_sound("done")
        self.top.destroy()

    def _restart(self):
        self.engine.apply_settings(self.original, save=False)
        self.choices.pack(fill="x", padx=22, pady=(12, 0), before=self.canvas)
        self.primary.configure(text="Start", command=self.start, state="normal")
        self.secondary.configure(text="Cancel", command=self.close)
        self.heading.configure(text="Find my best settings")
        self.text.configure(text="Choose what to practise and press Start.")

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
        kind = self.block.kind if self.block else "turns"
        ppd = self.PX_PER_DEG[kind] * k
        step = (5 if kind != "turns" else 10) * ppd
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
            r = self.trial.radius * ppd
            if 0 <= tx <= w and 0 <= ty <= h:
                color = "#22c55e" if on else "#3b82f6"
                c.create_oval(tx - r, ty - r, tx + r, ty + r, outline=color, width=3)
                c.create_oval(tx - 4 * k, ty - 4 * k, tx + 4 * k, ty + 4 * k, fill=color, outline="")
                if on and self.trial._on_since is not None:   # how long until it counts
                    share = min(1.0, (self.trial.samples[-1].t - self.trial._on_since) / self.trial.dwell)
                    c.create_arc(tx - r - 6 * k, ty - r - 6 * k, tx + r + 6 * k, ty + r + 6 * k, start=90,
                                 extent=-359.9 * share, style="arc", outline="#22c55e", width=4)
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
        elif self.playing and self.next_at is not None:
            left = max(0.0, self.next_at - time.monotonic())
            c.create_text(cx, cy - 40 * k, text=f"{left:.0f}" if left >= 0.5 else "Go", fill="white",
                          font=(FAMILY, 28, "bold"))
        a = 14 * k
        c.create_line(cx - a, cy, cx - a / 3, cy, fill="white", width=2)
        c.create_line(cx + a / 3, cy, cx + a, cy, fill="white", width=2)
        c.create_line(cx, cy - a, cx, cy - a / 3, fill="white", width=2)
        c.create_line(cx, cy + a / 3, cx, cy + a, fill="white", width=2)
        if snap.tracking != TrackingStatus.OK:
            c.create_text(cx, cy + 50 * k, text="Can't see you - face the camera", fill="#f87171",
                          font=(FAMILY, 14, "bold"))

    def _progress(self):
        if self.checkup is None or self.block is None:
            return
        planned = {"all": 13, "aim": 7, "updown": 4, "turns": 2}[self.checkup.focus]
        within = len(self.block.trials) / max(1, len(self.block.targets))
        self.progress.set(min(0.97, (self.done_blocks + within) / planned))

    def poll(self):
        if not self.alive():
            return
        snap = self.engine.snapshot()
        now = time.monotonic()
        dt = 0.0 if self.last_t is None else now - self.last_t
        self.last_t = now
        if self.playing and self.block is not None:
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
                        self.block.trials.append(self.trial)
                        self.trial = None
                        self.next_at = now + 0.4
            self._progress()
        if self.checkup is None or self.playing:
            self._draw(snap)
        self.top.after(16, self.poll)
