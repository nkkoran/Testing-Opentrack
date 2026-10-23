"""The HeadMouse window: big status light, head-position view and large buttons,
plus the setup wizard, sensitivity sliders, game calibration and tracker setup.

Everything here talks to the Engine, which does the real work on its own thread.
"""

import base64
import dataclasses
import sys
import time
import tkinter as tk
from tkinter import messagebox, ttk

from . import calibration, config, opentrack_setup
from .curves import DirectionCurve
from .engine import Engine
from .keys import key_code
from .safety import TrackingStatus

FONT = "Segoe UI" if sys.platform == "win32" else "DejaVu Sans"
COLORS = {"ACTIVE": "#2e7d32", "PAUSED": "#e0a000", "OFF": "#616161", "STOPPED": "#c62828",
          "BUSY": "#1565c0", "WAITING": "#5c6bc0", "CENTER": "#5c6bc0", "STARTING": "#616161"}
DIRECTION_NAMES = ("right", "left", "up", "down")


def _font(size, bold=False):
    return (FONT, size, "bold") if bold else (FONT, size)


def _replace(settings, section, **changes):
    return dataclasses.replace(settings, **{section: dataclasses.replace(getattr(settings, section), **changes)})


def _big_button(parent, text, command, **kw):
    return tk.Button(parent, text=text, command=command, font=_font(13, True), height=2,
                     relief="raised", bd=2, **kw)


def _png_photo(data):
    return tk.PhotoImage(data=base64.b64encode(data).decode("ascii"))


class MainWindow:
    def __init__(self, root, engine):
        self.root = root
        self.engine = engine
        self.messages = []
        self.preview_photo = None
        self.children = {}
        s = engine.settings
        title = "HeadMouse" + ("  [DRY RUN - mouse will not move]" if engine.dry_run else "")
        root.title(title)
        root.configure(padx=12, pady=10)
        root.attributes("-topmost", s.general.always_on_top)

        self.banner = tk.Label(root, text="STARTING", font=_font(26, True), fg="white", bg=COLORS["OFF"],
                               pady=10)
        self.banner.pack(fill="x")
        self.hint = tk.Label(root, text="", font=_font(12), wraplength=440, justify="center", pady=4)
        self.hint.pack(fill="x")

        self.canvas = tk.Canvas(root, width=300, height=190, bg="#fafafa", highlightthickness=1,
                                highlightbackground="#bbb")
        self.canvas.pack(pady=(6, 2))
        self.speed_label = tk.Label(root, text="", font=_font(12))
        self.speed_label.pack()

        grid = tk.Frame(root)
        grid.pack(fill="x", pady=8)
        grid.columnconfigure((0, 1), weight=1, uniform="b")
        self.toggle_btn = _big_button(grid, "Turn ON", engine.toggle_enabled)
        self.toggle_btn.grid(row=0, column=0, sticky="ew", padx=3, pady=3)
        _big_button(grid, "Re-center", engine.recenter).grid(row=0, column=1, sticky="ew", padx=3, pady=3)
        _big_button(grid, "Setup wizard", self.open_wizard).grid(row=1, column=0, sticky="ew", padx=3, pady=3)
        _big_button(grid, "Sensitivity", self.open_sensitivity).grid(row=1, column=1, sticky="ew", padx=3,
                                                                     pady=3)
        tk.Button(grid, text="Game calibration", font=_font(11), command=self.open_calibration).grid(
            row=2, column=0, sticky="ew", padx=3, pady=3)
        tk.Button(grid, text="Tracker / OpenTrack", font=_font(11), command=self.open_tracker).grid(
            row=2, column=1, sticky="ew", padx=3, pady=3)

        opts = tk.Frame(root)
        opts.pack(fill="x")
        self.show_camera = tk.BooleanVar(value=False)
        self.camera_check = tk.Checkbutton(opts, text="Show camera", variable=self.show_camera,
                                           font=_font(10), command=self._camera_toggled)
        self.camera_check.pack(side="left")
        self.on_top = tk.BooleanVar(value=s.general.always_on_top)
        tk.Checkbutton(opts, text="Keep on top", variable=self.on_top, font=_font(10),
                       command=self._on_top_toggled).pack(side="right")
        self.preview = tk.Label(root)
        self.preview.pack()

        k = s.keys
        self.keys_label = tk.Label(root, font=_font(10), fg="#444", justify="left")
        self.keys_label.pack(fill="x", pady=(6, 0))
        self._update_keys_label(k)
        self.log = tk.Label(root, text="", font=_font(9), fg="#555", justify="left", anchor="w",
                            wraplength=440)
        self.log.pack(fill="x", pady=(4, 0))

        root.protocol("WM_DELETE_WINDOW", self.close)
        self.refresh()
        if not s.general.setup_done:
            root.after(600, self.open_wizard)

    def _update_keys_label(self, k):
        self.keys_label.config(text=f"{k.enable_toggle}: on/off     {k.pause_hold} (hold): freeze camera\n"
                                    f"{k.precision_hold} (hold): precision aim     {k.recenter}: re-center")

    # --- child windows ---------------------------------------------------------

    def _open(self, name, cls):
        win = self.children.get(name)
        if win is not None and win.top.winfo_exists():
            win.top.lift()
            return
        self.children[name] = cls(self)

    def open_wizard(self):
        self._open("wizard", WizardWindow)

    def open_sensitivity(self):
        self._open("sensitivity", SensitivityWindow)

    def open_calibration(self):
        self._open("calibration", CalibrationWindow)

    def open_tracker(self):
        self._open("tracker", TrackerWindow)

    def _camera_toggled(self):
        self.engine.set_preview(self.show_camera.get())
        if not self.show_camera.get():
            self.preview.config(image="")
            self.preview_photo = None

    def _on_top_toggled(self):
        value = self.on_top.get()
        self.root.attributes("-topmost", value)
        self.engine.apply_settings(_replace(self.engine.settings, "general", always_on_top=value))

    def close(self):
        self.engine.stop()
        self.root.destroy()

    # --- live updates ----------------------------------------------------------

    def _hint(self, snap):
        s = snap.settings
        if snap.source_error:
            return snap.source_error, "#c62828"
        if snap.state.startswith("BUSY"):
            return "Head control is paused while this runs.", "#1565c0"
        if snap.tracking != TrackingStatus.OK:
            if snap.source_kind == "webcam":
                if snap.source_status != "running":
                    return snap.source_status.capitalize(), "#444"
                return "Looking for your face - sit facing the camera, with light on your face.", "#c62828"
            if snap.tracking == TrackingStatus.FROZEN:
                return "OpenTrack's tracking froze - it may have lost your face.", "#c62828"
            return ("No data from OpenTrack - is it running with the HeadMouse profile, and Started?",
                    "#c62828")
        if not snap.enabled:
            if s.general.auto_enable_in_game and s.general.game_window_title:
                return (f"Turns ON automatically in {s.general.game_window_title}, or press "
                        f"{s.keys.enable_toggle}.", "#444")
            return f"Press {s.keys.enable_toggle} or 'Turn ON' to start.", "#444"
        if snap.paused:
            return "Frozen while the pause key is held.", "#444"
        if snap.state.startswith("CENTER"):
            return "Bring your head back to center to continue.", "#444"
        return f"Hold {s.keys.pause_hold} to freeze the camera.", "#2e7d32"

    def _draw_head(self, snap):
        c = self.canvas
        c.delete("all")
        s = snap.settings
        w, h = int(c["width"]), int(c["height"])
        cx, cy = w / 2, h / 2
        xr = max(s.right.full_speed_angle, s.left.full_speed_angle) * 1.25
        yr = max(s.up.full_speed_angle, s.down.full_speed_angle) * 1.25
        sx, sy = (w / 2 - 10) / xr, (h / 2 - 10) / yr
        # full-speed box and dead-zone box (each side can differ)
        c.create_rectangle(cx - s.left.full_speed_angle * sx, cy - s.up.full_speed_angle * sy,
                           cx + s.right.full_speed_angle * sx, cy + s.down.full_speed_angle * sy,
                           outline="#ef9a9a", dash=(4, 3))
        c.create_rectangle(cx - s.left.deadzone * sx, cy - s.up.deadzone * sy,
                           cx + s.right.deadzone * sx, cy + s.down.deadzone * sy,
                           fill="#e8f5e9", outline="#81c784")
        c.create_line(cx, 4, cx, h - 4, fill="#ddd")
        c.create_line(4, cy, w - 4, cy, fill="#ddd")
        for text, x, y, anchor in (("LEFT", 6, cy - 2, "sw"), ("RIGHT", w - 6, cy - 2, "se"),
                                   ("UP", cx + 4, 4, "nw"), ("DOWN", cx + 4, h - 4, "sw")):
            c.create_text(x, y, text=text, anchor=anchor, fill="#999", font=_font(8))
        if snap.tracking == TrackingStatus.OK:
            x = cx + max(-xr, min(xr, snap.yaw)) * sx
            y = cy - max(-yr, min(yr, snap.pitch)) * sy
            moving = snap.yaw_speed or snap.pitch_speed
            color = "#1565c0" if moving else "#43a047"
            c.create_oval(x - 9, y - 9, x + 9, y + 9, fill=color, outline="white", width=2)
        else:
            c.create_text(cx, cy, text="no tracking", fill="#c62828", font=_font(12, True))

    def refresh(self):
        if not self.root.winfo_exists():
            return
        snap = self.engine.snapshot()
        state = snap.state
        key = state.split(":")[0].split(" ")[0]
        label = {"STOPPED": "NO TRACKING", "BUSY": "BUSY", "WAITING": "NOT IN GAME",
                 "CENTER": "CENTER HEAD"}.get(key, state)
        if key == "ACTIVE" and "precision" in state:
            label = "ACTIVE - PRECISION"
        self.banner.config(text=label, bg=COLORS.get(key, COLORS["OFF"]))
        text, color = self._hint(snap)
        self.hint.config(text=text, fg=color)
        self.toggle_btn.config(text="Turn OFF" if snap.enabled else "Turn ON")
        self._draw_head(snap)
        if snap.yaw_speed or snap.pitch_speed:
            parts = []
            if snap.yaw_speed:
                parts.append(f"turning {'right' if snap.yaw_speed > 0 else 'left'} {abs(snap.yaw_speed):.0f}°/s")
            if snap.pitch_speed:
                parts.append(f"looking {'up' if snap.pitch_speed > 0 else 'down'} {abs(snap.pitch_speed):.0f}°/s")
            self.speed_label.config(text=",  ".join(parts))
        else:
            self.speed_label.config(text="camera still")
        self.camera_check.config(state="normal" if snap.source_kind == "webcam" else "disabled")
        if self.show_camera.get():
            png = self.engine.preview_png()
            if png:
                self.preview_photo = _png_photo(png)
                self.preview.config(image=self.preview_photo)
        for _, text in self.engine.drain_messages():
            self.messages = (self.messages + [f"{time.strftime('%H:%M:%S')}  {text}"])[-3:]
            self.log.config(text="\n".join(self.messages))
        self._update_keys_label(snap.settings.keys)
        self.root.after(40, self.refresh)


class _Child:
    """Base for secondary windows."""

    title = ""

    def __init__(self, main):
        self.main = main
        self.engine = main.engine
        self.top = tk.Toplevel(main.root)
        self.top.title(self.title)
        self.top.configure(padx=14, pady=12)
        self.top.transient(main.root)
        self.top.protocol("WM_DELETE_WINDOW", self.close)

    def close(self):
        self.top.destroy()

    def alive(self):
        return self.top.winfo_exists()


class WizardWindow(_Child):
    title = "HeadMouse setup wizard"
    STEPS = [
        ("right", 0, "Turn your head to the RIGHT", "as far as is comfortable - no straining - and hold it."),
        ("left", 0, "Turn your head to the LEFT", "as far as is comfortable, and hold it."),
        ("up", 1, "Tilt your head UP", "as far as is comfortable, and hold it."),
        ("down", 1, "Tilt your head DOWN", "as far as is comfortable, and hold it."),
    ]

    def __init__(self, main):
        super().__init__(main)
        self.engine.set_hold("wizard", True)
        self.samples = []
        self.capturing = None
        self.neutral = None
        self.movements = {}
        self.step = -1
        self.top.geometry("560x520")
        self.heading = tk.Label(self.top, font=_font(18, True), wraplength=520, justify="center")
        self.heading.pack(pady=(4, 6))
        self.body = tk.Label(self.top, font=_font(12), wraplength=520, justify="left")
        self.body.pack(fill="x")
        self.extra = tk.Frame(self.top)
        self.extra.pack(fill="both", expand=True, pady=6)
        self.meter = tk.Canvas(self.top, width=520, height=34, bg="#fafafa", highlightthickness=0)
        self.meter.pack(pady=4)
        self.status = tk.Label(self.top, font=_font(11), fg="#444")
        self.status.pack()
        buttons = tk.Frame(self.top)
        buttons.pack(fill="x", pady=(8, 0))
        self.back_btn = tk.Button(buttons, text="Cancel", font=_font(12), command=self.close, width=10)
        self.back_btn.pack(side="left")
        self.next_btn = tk.Button(buttons, text="Next", font=_font(13, True), command=self.next, width=14)
        self.next_btn.pack(side="right")
        self.show_intro()
        self.poll()

    def close(self):
        self.engine.set_hold("wizard", False)
        self.engine.set_preview(self.main.show_camera.get())
        super().close()

    def _clear_extra(self):
        for w in self.extra.winfo_children():
            w.destroy()

    def show_intro(self):
        self.step = -1
        self.heading.config(text="Welcome! Let's set up head control")
        self.body.config(text="This takes about a minute. HeadMouse will measure how far you can "
                              "comfortably move your head in each direction and set itself up to suit you.\n\n"
                              "First, choose how your head is tracked:")
        self._clear_extra()
        self.source = tk.StringVar(value=self.engine.settings.tracking.source)
        for value, text in (("webcam", "Built-in webcam tracking (recommended - nothing else to run)"),
                            ("opentrack", "OpenTrack (must be running, with the HeadMouse profile)")):
            tk.Radiobutton(self.extra, text=text, value=value, variable=self.source, font=_font(12),
                           command=self._source_changed).pack(anchor="w", pady=2)
        self.preview = tk.Label(self.extra)
        self.preview.pack(pady=4)
        self.photo = None
        self.engine.set_preview(True)
        self.next_btn.config(text="Next", state="disabled")

    def _source_changed(self):
        value = self.source.get()
        if value != self.engine.settings.tracking.source:
            self.engine.apply_settings(_replace(self.engine.settings, "tracking", source=value))
            self.main.root.after(500, lambda: self.engine.set_preview(True))

    def show_neutral(self):
        self.step = 0
        self._clear_extra()
        self.heading.config(text="Look straight at the middle of the screen")
        self.body.config(text="Sit the way you normally play, relax, and look at the center of the screen.\n"
                              "Press Start, then hold still until you hear the beep (3 seconds).")
        self.next_btn.config(text="Start", state="normal")

    def show_direction(self, index):
        self.step = index + 1
        name, axis, head, rest = self.STEPS[index]
        self.heading.config(text=head)
        self.body.config(text=f"Press Start, then {head.lower()} {rest}\nKeep holding until you hear the beep "
                              f"(4 seconds).")
        self.next_btn.config(text="Start", state="normal")

    def show_results(self):
        self.step = 99
        new, report, problems, offset = calibration.propose(
            self.engine.settings, self.engine.settings.tracking.source, self.neutral, self.movements)
        self.result = (new, offset)
        self.heading.config(text="All done!" if not problems else "Done - with some notes")
        lines = report + ([""] if problems else []) + [f"! {p}" for p in problems]
        self.body.config(text="\n".join(lines))
        self._clear_extra()
        tk.Button(self.extra, text="Try again", font=_font(11), command=self.show_neutral).pack(anchor="w")
        self.next_btn.config(text="Save and finish", state="normal")

    def next(self):
        if self.capturing:
            return
        if self.step == -1:
            self.engine.set_preview(False)
            self.show_neutral()
        elif self.step == 0:
            self._capture(3.0, 0.5, self._neutral_done)
        elif 1 <= self.step <= 4:
            self._capture(4.0, 1.5, self._direction_done)
        elif self.step == 99:
            new, offset = self.result
            new = _replace(new, "general", setup_done=True)
            self.engine.apply_settings(new)
            if new.tracking.source == "opentrack":
                self.engine.set_offset(offset)
            self.engine.play_sound("done")
            self.close()

    def _capture(self, seconds, settle, done):
        self.samples = []
        self.capturing = (time.monotonic() + settle, time.monotonic() + seconds, done)
        self.next_btn.config(state="disabled")

    def _neutral_done(self):
        if len(self.samples) < 10:
            self.status.config(text="Not enough tracking data - check that your face is tracked, then retry.")
            self.show_neutral()
            return
        self.neutral = calibration.measure_neutral(self.samples)
        self.show_direction(0)

    def _direction_done(self):
        name, axis, *_ = self.STEPS[self.step - 1]
        self.movements[name] = calibration.measure_movement(self.samples, self.neutral, axis)
        index = self.step
        if index < len(self.STEPS):
            self.show_direction(index)
        else:
            self.show_results()

    def _draw_meter(self, snap):
        m = self.meter
        m.delete("all")
        if snap.raw_angles is None or self.neutral is None or not (1 <= self.step <= 4):
            return
        name, axis, *_ = self.STEPS[self.step - 1]
        center = self.neutral.yaw if axis == 0 else self.neutral.pitch
        value = abs(snap.raw_angles[axis] - center)
        width = min(1.0, value / 30.0) * 500
        m.create_rectangle(10, 8, 510, 26, outline="#bbb")
        m.create_rectangle(10, 8, 10 + width, 26, fill="#64b5f6", outline="")
        m.create_text(260, 17, text=f"{value:.1f}°", font=_font(10, True))

    def poll(self):
        if not self.alive():
            return
        snap = self.engine.snapshot()
        ok = snap.tracking == TrackingStatus.OK
        if self.step == -1:
            if snap.source_error:
                self.status.config(text=snap.source_error, fg="#c62828")
            elif ok:
                self.status.config(text="Tracking is working.", fg="#2e7d32")
            else:
                self.status.config(text=f"Waiting for tracking... ({snap.source_status})", fg="#c62828")
            self.next_btn.config(state="normal" if ok else "disabled")
            png = self.engine.preview_png() if snap.source_kind == "webcam" else None
            if png:
                self.photo = _png_photo(png)
                self.preview.config(image=self.photo)
        if self.capturing:
            settle_until, end, done = self.capturing
            now = time.monotonic()
            if now >= settle_until and snap.raw_angles is not None:
                self.samples.append(snap.raw_angles)
            remaining = end - now
            self.status.config(text=f"Hold... {max(0, remaining):.0f}" if ok else
                               "Tracking lost - keep your face visible", fg="#1565c0" if ok else "#c62828")
            if remaining <= 0:
                self.capturing = None
                self.engine.play_sound("tracking_ok")
                self.status.config(text="")
                done()
        self._draw_meter(snap)
        self.top.after(30, self.poll)


class SensitivityWindow(_Child):
    title = "HeadMouse sensitivity"
    SLIDERS = [  # field, label, from, to, resolution
        ("deadzone", "Dead zone (degrees with no movement)", 0.0, 10.0, 0.1),
        ("full_speed_angle", "Head angle for full speed (degrees)", 3.0, 45.0, 0.5),
        ("min_speed", "Slowest speed (°/s, just past the dead zone)", 0.0, 60.0, 0.5),
        ("max_speed", "Top speed (°/s)", 10.0, 360.0, 5.0),
        ("curve", "Curve (1 = even, higher = finer control near center)", 0.5, 4.0, 0.05),
    ]
    PAIRS = {"right": "left", "left": "right", "up": "down", "down": "up"}

    def __init__(self, main):
        super().__init__(main)
        self.original = self.engine.settings
        self.work = self.engine.settings
        self.vars = {}
        self.canvases = {}
        self._pending = None
        nb = ttk.Notebook(self.top)
        nb.pack(fill="both", expand=True)
        for name in DIRECTION_NAMES:
            frame = tk.Frame(nb, padx=8, pady=8)
            nb.add(frame, text=f"  {name.title()}  ")
            self._direction_tab(frame, name)
        other = tk.Frame(nb, padx=8, pady=8)
        nb.add(other, text="  Other  ")
        self._other_tab(other)
        buttons = tk.Frame(self.top)
        buttons.pack(fill="x", pady=(10, 0))
        tk.Button(buttons, text="Cancel changes", font=_font(11), command=self.cancel).pack(side="left")
        tk.Button(buttons, text="Save", font=_font(13, True), width=12, command=self.save).pack(side="right")
        self.poll()

    def _direction_tab(self, frame, name):
        d = getattr(self.work, name)
        if d.points:
            tk.Label(frame, text="This direction uses a custom table of points from the settings file.",
                     font=_font(11), wraplength=420).pack(anchor="w")
            tk.Button(frame, text="Use sliders instead", font=_font(11),
                      command=lambda: self._drop_points(name, frame)).pack(anchor="w", pady=6)
            return
        for field, label, lo, hi, res in self.SLIDERS:
            var = tk.DoubleVar(value=getattr(d, field))
            self.vars[(name, field)] = var
            tk.Label(frame, text=label, font=_font(10)).pack(anchor="w")
            tk.Scale(frame, variable=var, from_=lo, to=hi, resolution=res, orient="horizontal", length=420,
                     font=_font(9), command=lambda _v, n=name: self._changed(n)).pack(anchor="w")
        canvas = tk.Canvas(frame, width=420, height=170, bg="#fafafa", highlightthickness=1,
                           highlightbackground="#ccc")
        canvas.pack(pady=(6, 4))
        self.canvases[name] = canvas
        pair = self.PAIRS[name]
        tk.Button(frame, text=f"Copy these settings to {pair.title()}", font=_font(10),
                  command=lambda: self._copy(name, pair)).pack(anchor="w")

    def _drop_points(self, name, frame):
        self.work = _replace(self.work, name, points=[])
        for w in frame.winfo_children():
            w.destroy()
        self._direction_tab(frame, name)
        self._schedule()

    def _other_tab(self, frame):
        w = self.work
        self.other = {}

        def row(label, var, widget_factory):
            tk.Label(frame, text=label, font=_font(10)).pack(anchor="w", pady=(6, 0))
            widget_factory(var).pack(anchor="w")

        def scale(lo, hi, res):
            return lambda var: tk.Scale(frame, variable=var, from_=lo, to=hi, resolution=res,
                                        orient="horizontal", length=420, font=_font(9),
                                        command=lambda _v: self._other_changed())

        self.other["precision"] = tk.DoubleVar(value=w.motion.precision_speed_factor)
        row("Precision mode speed (0.2 = 80% slower)", self.other["precision"], scale(0.05, 1.0, 0.05))
        self.other["webcam_smooth"] = tk.DoubleVar(value=w.webcam.smoothing_min_cutoff)
        row("Webcam steadiness (lower = steadier, higher = quicker)", self.other["webcam_smooth"],
            scale(0.2, 4.0, 0.1))
        self.other["volume"] = tk.DoubleVar(value=w.sounds.volume)
        row("Sound volume (0 = off)", self.other["volume"], scale(0.0, 1.0, 0.05))
        tk.Button(frame, text="Test sound", font=_font(10),
                  command=lambda: self.engine.play_sound("enabled")).pack(anchor="w")
        self.other["invert"] = tk.BooleanVar(value=w.mouse.invert_vertical)
        tk.Checkbutton(frame, text="Reverse up/down (look up = camera down)", variable=self.other["invert"],
                       font=_font(10), command=self._other_changed).pack(anchor="w", pady=(8, 0))
        self.other["auto"] = tk.BooleanVar(value=w.general.auto_enable_in_game)
        tk.Checkbutton(frame, text="Turn on automatically when the game window is active",
                       variable=self.other["auto"], font=_font(10),
                       command=self._other_changed).pack(anchor="w")
        keys = tk.LabelFrame(frame, text="Keys (e.g. F9, PAUSE, SCROLLLOCK, NUMPAD0)", font=_font(10),
                             padx=6, pady=4)
        keys.pack(fill="x", pady=(8, 0))
        for i, (field, label) in enumerate((("pause_hold", "Freeze (hold)"), ("enable_toggle", "On/off"),
                                            ("precision_hold", "Precision (hold)"), ("recenter", "Re-center"))):
            var = tk.StringVar(value=getattr(w.keys, field))
            self.other[f"key_{field}"] = var
            tk.Label(keys, text=label, font=_font(10)).grid(row=i // 2, column=(i % 2) * 2, sticky="w", padx=4)
            tk.Entry(keys, textvariable=var, width=10, font=_font(10)).grid(row=i // 2, column=(i % 2) * 2 + 1,
                                                                           padx=4, pady=2)

    def _copy(self, src, dst):
        for field, *_ in self.SLIDERS:
            if (dst, field) in self.vars:
                self.vars[(dst, field)].set(self.vars[(src, field)].get())
        self._changed(dst)

    def _collect_direction(self, name):
        d = getattr(self.work, name)
        if any((name, f) not in self.vars for f, *_ in self.SLIDERS):
            return d  # tab still being built
        values = {f: round(self.vars[(name, f)].get(), 3) for f, *_ in self.SLIDERS}
        if values["full_speed_angle"] <= values["deadzone"]:
            values["full_speed_angle"] = values["deadzone"] + 0.5
            self.vars[(name, "full_speed_angle")].set(values["full_speed_angle"])
        if values["min_speed"] > values["max_speed"]:
            values["min_speed"] = values["max_speed"]
            self.vars[(name, "min_speed")].set(values["min_speed"])
        return dataclasses.replace(d, **values)

    def _changed(self, name):
        self.work = dataclasses.replace(self.work, **{name: self._collect_direction(name)})
        self._schedule()

    def _other_changed(self):
        o = self.other
        w = self.work
        w = _replace(w, "motion", precision_speed_factor=round(o["precision"].get(), 3))
        w = _replace(w, "webcam", smoothing_min_cutoff=round(o["webcam_smooth"].get(), 3))
        w = _replace(w, "sounds", volume=round(o["volume"].get(), 3))
        w = _replace(w, "mouse", invert_vertical=o["invert"].get())
        w = _replace(w, "general", auto_enable_in_game=o["auto"].get())
        self.work = w
        self._schedule()

    def _schedule(self):
        """Try the new values live (not saved) shortly after the last slider move."""
        if self._pending:
            self.top.after_cancel(self._pending)
        self._pending = self.top.after(250, lambda: self.engine.apply_settings(self.work, save=False))

    def _keys_ok(self):
        changes = {}
        for field in ("pause_hold", "enable_toggle", "precision_hold", "recenter"):
            value = self.other[f"key_{field}"].get().strip().upper()
            try:
                key_code(value)
            except ValueError:
                messagebox.showerror("HeadMouse", f"'{value}' is not a key name I know.", parent=self.top)
                return None
            changes[field] = value
        candidate = _replace(self.work, "keys", **changes)
        try:
            config.validate(candidate)
        except config.SettingsError as e:
            messagebox.showerror("HeadMouse", str(e), parent=self.top)
            return None
        return candidate

    def save(self):
        candidate = self._keys_ok()
        if candidate is None:
            return
        if self._pending:
            self.top.after_cancel(self._pending)
        self.engine.apply_settings(candidate, save=True)
        self.top.destroy()

    def cancel(self):
        if self._pending:
            self.top.after_cancel(self._pending)
        self.engine.apply_settings(self.original, save=False)
        self.top.destroy()

    close = cancel

    def _plot(self, name, canvas, snap):
        d = getattr(self.work, name)
        curve = DirectionCurve(d)
        c = canvas
        c.delete("all")
        w, h = int(c["width"]), int(c["height"])
        x_max = max(20.0, d.full_speed_angle * 1.4) if not d.points else max(p[0] for p in d.points) * 1.4
        y_max = max(10.0, max(curve.speed(a / 10) for a in range(int(x_max * 10) + 1)) * 1.1)
        left, bottom = 40, h - 22
        px = lambda a: left + a / x_max * (w - left - 10)
        py = lambda v: bottom - v / y_max * (bottom - 10)
        c.create_line(left, bottom, w - 10, bottom, fill="#999")
        c.create_line(left, bottom, left, 8, fill="#999")
        for a in range(0, int(x_max) + 1, 5):
            c.create_text(px(a), bottom + 10, text=f"{a}°", font=_font(8), fill="#666")
        for v in (0, y_max / 2, y_max):
            c.create_text(left - 4, py(v), text=f"{v:.0f}", anchor="e", font=_font(8), fill="#666")
        c.create_text(left + 4, 10, text="°/s", anchor="nw", font=_font(8), fill="#666")
        pts = []
        for i in range(0, 201):
            a = x_max * i / 200
            pts += [px(a), py(curve.speed(a))]
        c.create_line(*pts, fill="#1565c0", width=2)
        c.create_line(px(d.deadzone), bottom, px(d.deadzone), 8, fill="#81c784", dash=(3, 3))
        if snap.tracking == TrackingStatus.OK:
            value = {"right": snap.yaw, "left": -snap.yaw, "up": snap.pitch, "down": -snap.pitch}[name]
            if value > 0:
                a = min(value, x_max)
                c.create_oval(px(a) - 5, py(curve.speed(a)) - 5, px(a) + 5, py(curve.speed(a)) + 5,
                              fill="#e53935", outline="white")

    def poll(self):
        if not self.alive():
            return
        snap = self.engine.snapshot()
        for name, canvas in self.canvases.items():
            if canvas.winfo_exists():
                self._plot(name, canvas, snap)
        self.top.after(80, self.poll)


class CalibrationWindow(_Child):
    title = "Game calibration"

    def __init__(self, main):
        super().__init__(main)
        self.engine.calibration_mode = True
        self.engine.set_hold("calibration", True)  # head must not move the camera meanwhile
        s = self.engine.settings
        k = s.keys
        tk.Label(self.top, text="Make HeadMouse's speeds match the game", font=_font(15, True)).pack(anchor="w")
        tk.Label(self.top, font=_font(11), justify="left", wraplength=480, text=(
            "1. Start Enshrouded and set its mouse sensitivity the way you like it.\n"
            f"2. In the game, face something easy to recognise and press {k.calibrate_turn}\n"
            f"    (or use the button below - you get 5 seconds to click into the game).\n"
            "3. The camera should turn exactly ONE full circle and stop facing the same thing.\n"
            "4. If it didn't, type how far it actually turned and press 'Correct it'. Repeat.")).pack(
            anchor="w", pady=6)
        row = tk.Frame(self.top)
        row.pack(fill="x", pady=4)
        tk.Label(row, text="Mouse counts for one full turn:", font=_font(11)).pack(side="left")
        self.counts = tk.StringVar(value=f"{s.mouse.counts_per_360:g}")
        tk.Label(row, textvariable=self.counts, font=_font(11, True)).pack(side="left", padx=6)
        self.turn_btn = tk.Button(self.top, text="Test turn in 5 seconds", font=_font(12, True),
                                  command=self.countdown)
        self.turn_btn.pack(anchor="w", pady=6)
        row2 = tk.Frame(self.top)
        row2.pack(fill="x", pady=4)
        tk.Label(row2, text="It actually turned about", font=_font(11)).pack(side="left")
        self.degrees = tk.StringVar(value="360")
        tk.Entry(row2, textvariable=self.degrees, width=6, font=_font(11)).pack(side="left", padx=4)
        tk.Label(row2, text="degrees", font=_font(11)).pack(side="left")
        tk.Button(row2, text="Correct it", font=_font(11), command=self.correct).pack(side="left", padx=8)
        tk.Label(self.top, font=_font(9), fg="#555", justify="left", wraplength=480, text=(
            "Tip: one and a half turns = 540 degrees, three quarters = 270. "
            f"Hold {k.pause_hold} to stop a test turn.")).pack(anchor="w", pady=(6, 0))
        tk.Button(self.top, text="Done", font=_font(12), width=10, command=self.close).pack(anchor="e", pady=(8, 0))

    def countdown(self, n=5):
        if not self.alive():
            return
        if n == 0:
            self.turn_btn.config(text="Test turn in 5 seconds", state="normal")
            self.engine.start_test_turn()
            return
        self.turn_btn.config(text=f"Turning in {n}...", state="disabled")
        self.top.after(1000, lambda: self.countdown(n - 1))

    def correct(self):
        try:
            turned = float(self.degrees.get())
            if not 10 <= turned <= 3600:
                raise ValueError
        except ValueError:
            messagebox.showerror("HeadMouse", "Type the number of degrees it turned, e.g. 400.", parent=self.top)
            return
        s = self.engine.settings
        new_counts = round(s.mouse.counts_per_360 * 360.0 / turned, 1)
        self.engine.apply_settings(_replace(s, "mouse", counts_per_360=new_counts))
        self.counts.set(f"{new_counts:g}")
        self.degrees.set("360")

    def close(self):
        self.engine.calibration_mode = False
        self.engine.set_hold("calibration", False)
        super().close()


class TrackerWindow(_Child):
    title = "Tracker and OpenTrack"

    def __init__(self, main):
        super().__init__(main)
        s = self.engine.settings
        tk.Label(self.top, text="How is your head tracked?", font=_font(15, True)).pack(anchor="w")
        self.source = tk.StringVar(value=s.tracking.source)
        for value, text in (("webcam", "Built-in webcam tracking (recommended)"),
                            ("opentrack", "OpenTrack")):
            tk.Radiobutton(self.top, text=text, value=value, variable=self.source, font=_font(12),
                           command=self._apply_source).pack(anchor="w")
        self.status = tk.Label(self.top, font=_font(10), fg="#444", wraplength=480, justify="left")
        self.status.pack(anchor="w", pady=(4, 8))

        cam = tk.LabelFrame(self.top, text="Webcam", font=_font(11), padx=8, pady=6)
        cam.pack(fill="x")
        tk.Label(cam, text="Camera number (try 1, 2 if the wrong camera is used):", font=_font(10)).pack(
            side="left")
        self.camera = tk.Spinbox(cam, from_=0, to=9, width=4, font=_font(11), command=self._apply_camera)
        self.camera.delete(0, "end")
        self.camera.insert(0, str(s.webcam.camera_index))
        self.camera.pack(side="left", padx=6)

        ot = tk.LabelFrame(self.top, text="OpenTrack", font=_font(11), padx=8, pady=6)
        ot.pack(fill="x", pady=(8, 0))
        self.folder = None
        for folder in opentrack_setup.profile_folders(s.opentrack.opentrack_exe):
            if folder.is_dir():
                self.folder = folder
                break
        profiles = opentrack_setup.list_profiles(self.folder) if self.folder else []
        profiles = [p for p in profiles if p != opentrack_setup.PROFILE_NAME] or profiles
        tk.Label(ot, font=_font(10), justify="left", wraplength=470, text=(
            "Creates a profile called 'HeadMouse' as a copy of one of your profiles (your camera and "
            "tracker settings are kept), with the output set to HeadMouse and the yaw/pitch curves "
            "set to 1:1. Your existing profiles are not changed.")).pack(anchor="w")
        row = tk.Frame(ot)
        row.pack(fill="x", pady=4)
        tk.Label(row, text="Copy from:", font=_font(10)).pack(side="left")
        current = opentrack_setup.current_profile()
        self.profile = tk.StringVar(value=current if current in profiles else (profiles[0] if profiles else ""))
        ttk.Combobox(row, textvariable=self.profile, values=profiles, state="readonly", width=24).pack(
            side="left", padx=6)
        tk.Button(ot, text="Create HeadMouse profile", font=_font(11, True), command=self.make_profile).pack(
            anchor="w", pady=4)
        if self.folder is None:
            tk.Label(ot, text="No OpenTrack profiles found (is OpenTrack installed and run once?).",
                     font=_font(10), fg="#c62828").pack(anchor="w")
        row2 = tk.Frame(ot)
        row2.pack(fill="x", pady=(4, 0))
        tk.Button(row2, text="Start OpenTrack now", font=_font(10), command=self.launch).pack(side="left")
        self.autolaunch = tk.BooleanVar(value=s.opentrack.launch_opentrack)
        tk.Checkbutton(row2, text="Start OpenTrack with HeadMouse", variable=self.autolaunch, font=_font(10),
                       command=self._apply_autolaunch).pack(side="left", padx=8)
        tk.Button(self.top, text="Close", font=_font(12), width=10, command=self.close).pack(anchor="e", pady=(10, 0))
        self.poll()

    def _apply_source(self):
        self.engine.apply_settings(_replace(self.engine.settings, "tracking", source=self.source.get()))

    def _apply_camera(self):
        try:
            index = int(self.camera.get())
        except ValueError:
            return
        self.engine.apply_settings(_replace(self.engine.settings, "webcam", camera_index=index))

    def _apply_autolaunch(self):
        self.engine.apply_settings(_replace(self.engine.settings, "opentrack",
                                            launch_opentrack=self.autolaunch.get()))

    def make_profile(self):
        if self.folder is None:
            messagebox.showerror("HeadMouse", "No OpenTrack profile folder was found.", parent=self.top)
            return
        try:
            dest, backup = opentrack_setup.make_headmouse_profile(
                self.folder, self.profile.get(), self.engine.settings.opentrack.port)
        except OSError as e:
            messagebox.showerror("HeadMouse", f"Could not create the profile: {e}", parent=self.top)
            return
        note = f"\n\nThe previous HeadMouse profile was backed up as {backup.name}." if backup else ""
        messagebox.showinfo("HeadMouse", f"Created {dest}.{note}\n\nIn OpenTrack, choose 'HeadMouse' in the "
                                         "profile list, then press Start.", parent=self.top)

    def launch(self):
        messagebox.showinfo("HeadMouse", opentrack_setup.launch_if_needed(
            self.engine.settings.opentrack.opentrack_exe), parent=self.top)

    def poll(self):
        if not self.alive():
            return
        snap = self.engine.snapshot()
        ok = snap.tracking == TrackingStatus.OK
        self.status.config(text=f"Status: {'tracking OK' if ok else snap.source_status}",
                           fg="#2e7d32" if ok else "#c62828")
        self.top.after(250, self.poll)


def _dpi_aware():
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass


def run_gui(settings_path, base_dir, dry_run=False, engine=None):
    _dpi_aware()
    root = tk.Tk()
    engine = engine or Engine(settings_path, base_dir, dry_run=dry_run)
    try:
        engine.start()
    except config.SettingsError as e:
        root.withdraw()
        messagebox.showerror("HeadMouse", f"There is a problem in the settings file:\n\n{e}\n\n"
                                          f"{settings_path}")
        root.destroy()
        return 1
    MainWindow(root, engine)
    root.mainloop()
    return 0
