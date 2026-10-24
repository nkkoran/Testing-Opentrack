"""The running core of HeadMouse.

HeadMouse.tick() is one step of the joystick loop (keys, tracking safety,
motion, mouse output). Engine runs those ticks on a background thread and is
what the window (gui.py) and console mode talk to. All commands from other
threads are queued and executed on the engine thread.
"""

import collections
import dataclasses
import logging
import queue
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from . import config
from . import actions
from .config import SITUATION_NAMES, SITUATIONS
from .keys import key_code
from .controller import MotionController, StepResult, orient
from .safety import TrackingMonitor, TrackingStatus
from .sounds import SoundPlayer
from .tracking import OpenTrackUDPSource
from .winput import KeyReader, NullInput, WindowsInput, high_resolution_timer

KEY_NAMES = ("pause_hold", "enable_toggle", "recenter", "precision_hold", "calibrate_turn")
FOCUS_STABLE_SECONDS = 0.4   # the game window must stay (in)active this long before auto on/off
POINTER_STABLE_SECONDS = 0.2  # the game's mouse pointer must stay shown/hidden this long to switch feel
LOST_BEEP_SECONDS = 1.0      # only beep "tracking lost" when it lasts this long
log = logging.getLogger("headmouse")


@dataclass
class Event:
    kind: str       # enabled, disabled, pause, tracking_lost, tracking_ok, recentered, situation, info, warning
    text: str = ""
    data: object = None


class Keys:
    """Edge detection on top of a backend's is_key_down()."""

    def __init__(self, backend):
        self.backend = backend
        self._prev = {}

    def held(self, vk):
        return self.backend.is_key_down(vk)

    def pressed(self, vk):
        down = self.backend.is_key_down(vk)
        was = self._prev.get(vk, False)
        self._prev[vk] = down
        return down and not was


class HeadMouse:
    """One step of the joystick-style loop per tick()."""

    def __init__(self, settings, source, backend, send=True):
        self.source = source
        self.backend = backend
        self.keys = Keys(backend)
        self.send = send
        self.enabled = settings.general.start_enabled
        self.offset = (0.0, 0.0)
        self.holds = set()           # extra reasons to stop, e.g. "wizard"
        self.practice = False        # practice game: steer a virtual camera, never the mouse
        self.practice_camera = [0.0, 0.0]
        self.state = "STARTING"
        self.result = StepResult()
        self.tracking = TrackingStatus.NO_DATA
        self.raw_angles = None       # oriented angles before offset and smoothing
        self.eye_pitch = None        # webcam eye direction score (+ up), None without eye data
        self.in_game = False
        self._focus_candidate = None
        self._focus_since = 0.0
        self.paused = False
        self.precision_on = False   # precision key in toggle mode
        self.situation = None       # "menu", "aim", "build" or None (normal feel)
        self._toggled = {}          # situations switched on with a tap
        self.actions = actions.Actions()      # click actions from keys and face gestures
        self.gestures = actions.GestureDetector()
        self.buttons_down = set()             # mouse buttons HeadMouse is holding down
        self.action_precision = False         # precision aim / freeze switched on by an action
        self.action_freeze = False
        self._pointer = False       # the game shows a mouse pointer (steady for POINTER_STABLE_SECONDS)
        self._pointer_seen, self._pointer_since = False, 0.0
        self.settings = None
        self._events = []
        self._last_tick = None
        self._reported_tracking = None
        self._reported_failures = 0
        self.apply_settings(settings)

    def apply_settings(self, settings, feels=None):
        """Use new settings. feels: {situation: Settings} - the feel (preset) for each situation in use."""
        previous = self.settings
        self.settings = settings
        old = getattr(self, "controller", None)
        self.controllers = {None: MotionController(settings)}
        for name, feel in (feels or {}).items():
            self.controllers[name] = MotionController(feel)
        if self.situation not in self.controllers:
            self.situation = None
        self.controller = self.controllers[self.situation]
        if old is not None and settings.assist.auto_center:
            self.controller.drift = list(old.drift)  # keep what auto-center has learned
        self._situation_keys = {name: key_code(getattr(settings.situations, f"{name}_key"))
                                for name in SITUATIONS}
        self._bindings = actions.bindings(settings)
        self._action_keys = {source: key_code(source[4:]) for source, _ in self._bindings if source.startswith("key:")}
        self.monitor = TrackingMonitor(settings.safety)
        self.vk = {name: settings.key(name) for name in KEY_NAMES}
        if settings.tracking.source == "webcam":
            self.offset = (settings.webcam.neutral_yaw, settings.webcam.neutral_pitch)
        elif previous is None or previous.tracking.source != settings.tracking.source:
            self.offset = (0.0, 0.0)

    def set_enabled(self, value):
        if value != self.enabled:
            self.enabled = value
            self.precision_on = False   # always start without precision aim
            self._toggled = {}          # ...and in the normal feel
            self.action_precision = self.action_freeze = False
            self._events.append(Event("enabled", "Head control ON") if value
                                else Event("disabled", "Head control OFF"))

    def recenter(self):
        if self.raw_angles is None:
            self._events.append(Event("warning", "Cannot re-center: no head tracking right now"))
            return
        self.offset = self.raw_angles
        self.controller.recentered()  # the head didn't move, so the camera mustn't either
        self._events.append(Event("recentered", f"Re-centered (yaw {self.offset[0]:+.1f}, "
                                                f"pitch {self.offset[1]:+.1f})", self.offset))

    def _update_actions(self, now, dt, focused, face):
        """Mouse buttons and commands from the click-action keys and face gestures."""
        a = self.settings.actions
        held = {source: self.keys.held(vk) for source, vk in self._action_keys.items()}
        for gesture in self.gestures.update(face, now, dt, actions.thresholds(self.settings), a.gesture_hold):
            held[f"face:{gesture}"] = True
        out = self.actions.update(self._bindings, held, now)
        if not (self.enabled and focused is not False and not self.practice and not self.holds):
            self.actions.reset()     # only in the game with head control on: never click elsewhere
            out = actions.Output(set(), [])
        for command in out.commands:
            if command == "recenter":
                self.recenter()
            elif command == "precision":
                self.action_precision = not self.action_precision
                self._events.append(Event("precision_on" if self.action_precision else "precision_off",
                                          "Precision aim " + ("ON" if self.action_precision else "OFF")))
            elif command == "freeze":
                self.action_freeze = not self.action_freeze
                self._events.append(Event("pause", "Camera frozen" if self.action_freeze else "Camera free"))
        self.set_buttons(out.buttons)

    def set_buttons(self, wanted):
        """Press and release mouse buttons so exactly `wanted` are down."""
        if not self.send:
            wanted = set()
        for button in sorted(self.buttons_down - wanted):
            self.backend.send_button(button, False)
        for button in sorted(wanted - self.buttons_down):
            self.backend.send_button(button, True)
        self.buttons_down = set(wanted)

    def _pointer_steady(self, now):
        """Pointer shown/hidden, ignoring flickers (loading screens, the moment between menus)."""
        seen = bool(self.backend.pointer_visible())
        if seen != self._pointer_seen:
            self._pointer_seen, self._pointer_since = seen, now
        if seen != self._pointer and now - self._pointer_since >= POINTER_STABLE_SECONDS:
            self._pointer = seen
        return self._pointer

    def _update_situation(self, focused, now):
        """Pick the feel for what the player is doing (aiming, building, a menu) and switch to it."""
        s = self.settings.situations
        wanted = None
        for name in SITUATIONS:
            vk = self._situation_keys[name]
            if getattr(s, f"{name}_toggle"):
                if self.keys.pressed(vk):
                    self._toggled[name] = not self._toggled.get(name, False)
                on = self._toggled.get(name, False)
            else:
                on = self.keys.held(vk)
            if name == "menu" and s.menu_pointer and focused is not False:
                on = self._pointer_steady(now) or on
            if on and wanted is None and name in self.controllers and not self.practice:
                wanted = name   # (the practice game always measures the normal feel)
        if wanted != self.situation:
            new = self.controllers[wanted]
            new.take_over(self.controller)
            self.controller, self.situation = new, wanted
            self._events.append(Event("situation", "Feel: " + (SITUATION_NAMES[wanted] if wanted else "normal"),
                                      wanted))

    def _game_focused(self):
        wanted = self.settings.general.game_window_title.strip().lower()
        if not wanted:
            return None
        return wanted in self.backend.foreground_window_title().lower()

    def tick(self, now):
        """Run one output tick. Returns the events that happened."""
        g = self.settings.general
        dt = 0.0 if self._last_tick is None else min(now - self._last_tick, 0.05)
        self._last_tick = now

        if self.keys.pressed(self.vk["enable_toggle"]):
            self.set_enabled(not self.enabled)

        focused = self._game_focused()
        if focused is None:
            self.in_game = False
        else:
            # Ignore quick focus flickers (overlays, pop-ups): act once it has settled.
            if focused != self._focus_candidate:
                self._focus_candidate, self._focus_since = focused, now
            if focused != self.in_game and now - self._focus_since >= FOCUS_STABLE_SECONDS:
                self.in_game = focused
                if g.auto_enable_in_game:
                    self.set_enabled(focused)
        window_ok = not (g.only_move_in_game_window and focused is False)

        paused = self.keys.held(self.vk["pause_hold"])
        if paused and not self.paused:
            self._events.append(Event("pause"))
        if self.settings.general.precision_toggle:
            if self.keys.pressed(self.vk["precision_hold"]):
                self.precision_on = not self.precision_on
                self._events.append(Event("precision_on", "Precision aim ON") if self.precision_on
                                    else Event("precision_off", "Precision aim OFF"))
            precision = self.precision_on
        else:
            precision = self.keys.held(self.vk["precision_hold"])

        self._update_situation(focused, now)

        sample = self.source.latest()
        self.tracking, raw = self.monitor.check(sample, now)
        self.raw_angles = orient(raw, self.settings) if raw is not None else None
        self.eye_pitch = sample.eye_pitch if raw is not None else None
        blink = sample.blink if raw is not None else 0.0
        self._update_actions(now, dt, focused, sample.face if raw is not None else None)
        precision = precision or self.action_precision
        paused = paused or self.action_freeze
        self.paused = paused
        if self.tracking != self._reported_tracking:
            if self.tracking == TrackingStatus.OK:
                self._events.append(Event("tracking_ok", "Tracking OK"))
            elif self._reported_tracking == TrackingStatus.OK:
                self._events.append(Event("tracking_lost", f"Movement stopped: {self.tracking.value}"))
            else:
                self._events.append(Event("info", f"Waiting for tracking: {self.tracking.value}"))
            self._reported_tracking = self.tracking

        if self.keys.pressed(self.vk["recenter"]):
            self.recenter()

        angles = None
        if self.raw_angles is not None:
            angles = (self.raw_angles[0] - self.offset[0], self.raw_angles[1] - self.offset[1])
        if self.practice:  # works whether head control is on or off, and outside the game
            hold = paused or bool(self.holds)
        else:
            hold = paused or not self.enabled or not window_ok or bool(self.holds)
        self.result = self.controller.step(angles, dt, hold=hold, precision=precision,
                                           eye_pitch=self.eye_pitch, blink=blink)
        if self.practice:
            self.practice_camera[0] += self.result.yaw_speed * dt
            self.practice_camera[1] += self.result.pitch_speed * dt

        if self.send and not self.practice and (self.result.dx or self.result.dy):
            self.backend.send_relative(self.result.dx, self.result.dy)
        if self.backend.failed_sends > self._reported_failures:
            if self._reported_failures == 0:
                self._events.append(Event("warning", "Windows refused to send the mouse movement."))
            self._reported_failures = self.backend.failed_sends

        if self.practice and not self.holds:
            self.state = "PRACTICE"
        elif self.holds:
            self.state = "BUSY: " + ", ".join(sorted(self.holds))
        elif not self.enabled:
            self.state = "OFF"
        elif not window_ok:
            self.state = "WAITING FOR GAME WINDOW"
        elif self.tracking != TrackingStatus.OK:
            self.state = "STOPPED: " + self.tracking.value
        elif paused:
            self.state = "PAUSED"
        elif self.result.glancing:
            self.state = "LOOKING AWAY"
        elif self.result.waiting_for_center:
            self.state = "CENTER HEAD TO RESUME"
        else:
            self.state = "ACTIVE" + (" (precision)" if precision else "")

        events, self._events = self._events, []
        return events


class _NoSource:
    """Used when the tracker could not start, so the loop keeps running safely."""

    def __init__(self, error):
        self.error = error
        self.status = error
        self.packets = 0

    def latest(self):
        return None

    def describe(self):
        return "no tracker"

    def stop(self):
        pass


def make_source(settings, base_dir):
    if settings.tracking.source == "webcam":
        from .webcam import WebcamSource
        return WebcamSource(settings.webcam, base_dir, eyes=needs_face(settings))
    return OpenTrackUDPSource(settings.opentrack.listen_address, settings.opentrack.port)


def uses_eyes(settings):
    """True when the glance eye check needs eye data from the webcam."""
    return settings.glance.enabled and settings.glance.eye_check


def needs_face(settings):
    """True when the webcam must read the face's expressions (eyes for glances, or gestures - as soon
    as click actions are on, so the gesture meters work before anything is assigned)."""
    return uses_eyes(settings) or settings.actions.enabled


def _restart_needed(old, new):
    if old.tracking.source != new.tracking.source:
        return True
    if new.tracking.source == "webcam" and needs_face(old) != needs_face(new):
        return True
    if new.tracking.source == "opentrack":
        return (old.opentrack.listen_address, old.opentrack.port) != \
               (new.opentrack.listen_address, new.opentrack.port)
    keys = ("camera_index", "frame_width", "frame_height", "fps", "model_path")
    return any(getattr(old.webcam, k) != getattr(new.webcam, k) for k in keys)


@dataclass
class Snapshot:
    """Read-only picture of the engine's state, for the window and console."""
    state: str = "STARTING"
    enabled: bool = False
    paused: bool = False
    tracking: TrackingStatus = TrackingStatus.NO_DATA
    yaw: float = 0.0
    pitch: float = 0.0
    raw_angles: tuple = None
    yaw_speed: float = 0.0
    pitch_speed: float = 0.0
    source_kind: str = ""
    source_status: str = ""
    source_error: str = None
    face_visible: bool = None
    packets: int = 0
    in_game: bool = False
    test_turn_active: bool = False
    glancing: bool = False
    gaze: float = None
    eye_pitch: float = None
    rate: float = 0.0
    practice_camera: tuple = (0.0, 0.0)
    situation: str = None
    face: dict = None              # smoothed face gesture scores (click actions)
    gestures: tuple = ()           # gestures active now
    buttons: tuple = ()            # mouse buttons HeadMouse holds down now
    frozen_by_action: bool = False # frozen by a click action (not the freeze key)
    dry_run: bool = False
    settings: object = None


def status_line(snap):
    horiz = "right" if snap.yaw_speed > 0 else "left " if snap.yaw_speed < 0 else "  -  "
    vert = "up  " if snap.pitch_speed > 0 else "down" if snap.pitch_speed < 0 else " -  "
    return (f"{snap.state:<25} yaw{snap.yaw:+6.1f} pitch{snap.pitch:+6.1f} | "
            f"{horiz}{abs(snap.yaw_speed):4.0f} {vert}{abs(snap.pitch_speed):4.0f} deg/s")


class Engine:
    def __init__(self, settings_path, base_dir, dry_run=False, backend=None,
                 sound_player=None, source_factory=make_source, clock=time.perf_counter,
                 launch_opentrack=True):
        self.path = Path(settings_path)
        self.base_dir = Path(base_dir)
        self.dry_run = dry_run
        self._backend = backend
        self._sounds = sound_player
        self._source_factory = source_factory
        self._clock = clock
        self._launch_opentrack = launch_opentrack
        self._commands = queue.Queue()
        self._messages = collections.deque(maxlen=200)
        self._lock = threading.Lock()
        self._snapshot = Snapshot()
        self._running = False
        self._thread = None
        self._mtime = None
        self._turn_remaining = 0.0
        self._turn_rate = 0.0
        self._turn_acc = 0.0
        self._lost_since = None
        self._lost_beeped = False
        self._rate_at = None
        self._rate_packets = 0
        self._next_rate_log = 0.0
        self.rate = 0.0
        self.calibration_mode = False
        self.settings = None
        self.source = None
        self._feel_problems = set()
        self.app = None

    # --- lifecycle ---------------------------------------------------------

    def start(self):
        """Load settings and start the loop. Raises config.SettingsError on a bad file."""
        settings, warnings = config.load(self.path)
        for w in warnings:
            self._message("warning", f"Settings: {w}")
        self.settings = settings
        self._mtime = self._read_mtime()
        windows = sys.platform == "win32"
        if self._backend is None:
            self._backend = WindowsInput() if windows and not self.dry_run else \
                KeyReader() if windows else NullInput()
        if self._sounds is None:
            self._sounds = SoundPlayer(settings.sounds)
        self.source = self._start_source(settings)
        self.app = HeadMouse(settings, self.source, self._backend,
                             send=not self.dry_run and windows)
        self._preset_mtime = self._read_preset_mtime()
        self.app.apply_settings(settings, self._feels(settings))
        self._maybe_launch_opentrack(settings)
        from . import __version__
        log.info("HeadMouse %s started (tracker %s, settings %s)", __version__, settings.tracking.source, self.path)
        self._update_snapshot()
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="headmouse-engine", daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        if self.app is not None:
            self.app.set_buttons(set())   # never leave a mouse button held down
        if self.source is not None:
            self.source.stop()

    # --- commands (safe to call from any thread) ---------------------------

    def call(self, fn):
        self._commands.put(fn)

    def toggle_enabled(self):
        self.call(lambda: self.app.set_enabled(not self.app.enabled))

    def set_enabled(self, value):
        self.call(lambda: self.app.set_enabled(value))

    def recenter(self):
        self.call(self.app.recenter)

    def pointer_visible(self):
        """Whether Windows shows a mouse pointer right now (for the Situations tab)."""
        try:
            return bool(self._backend.pointer_visible())
        except (AttributeError, OSError):
            return False

    def set_practice(self, on):
        """Practice game: head control turns a virtual camera instead of the mouse."""
        def do():
            self.app.practice = on
            self.app.practice_camera = [0.0, 0.0]
        self.call(do)

    def set_offset(self, offset):
        """Set the neutral head position directly (used by the setup wizard)."""
        def do():
            self.app.offset = tuple(offset)
            self.app.controller.recentered()
        self.call(do)

    def set_hold(self, reason, on):
        self.call(lambda: (self.app.holds.add if on else self.app.holds.discard)(reason))

    def start_test_turn(self):
        self.call(self._begin_turn)

    def apply_settings(self, new_settings, save=True):
        """Use new settings now; with save=True also write the changes to the file."""
        self.call(lambda: self._apply(new_settings, save))

    def play_sound(self, name):
        self.call(lambda: self._sounds.play(name, force=True))

    def set_preview(self, wanted):
        def do():
            if hasattr(self.source, "preview_wanted"):
                self.source.preview_wanted = wanted
        self.call(do)

    def preview_png(self):
        get = getattr(self.source, "preview_png", None)
        return get() if get else None

    def snapshot(self):
        with self._lock:
            return self._snapshot

    def drain_messages(self):
        out = []
        while self._messages:
            out.append(self._messages.popleft())
        return out

    # --- engine thread -----------------------------------------------------

    def _message(self, kind, text):
        if text:
            self._messages.append((kind, text))
            log.info("%s: %s", kind, text)

    def _read_mtime(self):
        try:
            return self.path.stat().st_mtime
        except OSError:
            return None

    def _start_source(self, settings):
        try:
            return self._source_factory(settings, self.base_dir).start()
        except OSError as e:
            self._message("warning", f"Tracker could not start: {e}")
            return _NoSource(str(e))

    def _maybe_launch_opentrack(self, settings):
        if not (self._launch_opentrack and settings.tracking.source == "opentrack"
                and settings.opentrack.launch_opentrack and sys.platform == "win32"):
            return
        from . import opentrack_setup
        self._message("info", opentrack_setup.launch_if_needed(settings.opentrack.opentrack_exe))

    def _apply(self, new, save):
        old = self.settings
        if save:
            # Compare with the file, not the running settings: values tried live
            # (save=False) are already running but not yet written.
            try:
                on_disk = config.load(self.path)[0]
            except config.SettingsError:
                on_disk = old
            changes = config.diff(on_disk, new)
            if changes:
                try:
                    config.save_values(self.path, changes)
                    self._mtime = self._read_mtime()
                except (OSError, config.SettingsError) as e:
                    self._message("warning", f"Could not save settings: {e}")
        self.settings = new
        if _restart_needed(old, new):
            self.source.stop()
            self.source = self._start_source(new)
            self.app.source = self.source
            if old.tracking.source != new.tracking.source:
                self._maybe_launch_opentrack(new)
        elif hasattr(self.source, "update_settings"):
            self.source.update_settings(new.webcam)
        self.app.apply_settings(new, self._feels(new))
        self._sounds.update(new.sounds)

    def _feels(self, settings):
        """{situation: Settings} for each situation with a preset chosen."""
        feels, problems = {}, set()
        for name in SITUATIONS:
            preset = getattr(settings.situations, f"{name}_preset")
            if not preset:
                continue
            try:
                feels[name] = config.load_preset(self.path, preset, settings)
            except config.SettingsError as e:
                problems.add(f"{SITUATION_NAMES[name]} feel not used: {e}")
        for text in problems - self._feel_problems:   # say it once, not on every slider move
            self._message("warning", text)
        self._feel_problems = problems
        return feels

    def _read_preset_mtime(self):
        folder = config.preset_folder(self.path)
        try:
            return max([folder.stat().st_mtime] + [p.stat().st_mtime for p in folder.glob("*.toml")])
        except OSError:
            return None

    def _check_file(self):
        presets = self._read_preset_mtime()
        if presets != self._preset_mtime:   # a preset used for a situation may have changed
            self._preset_mtime = presets
            self.app.apply_settings(self.settings, self._feels(self.settings))
        mtime = self._read_mtime()
        if mtime == self._mtime:
            return
        self._mtime = mtime
        try:
            new, warnings = config.load(self.path)
        except config.SettingsError as e:
            self._message("warning", f"Settings NOT reloaded - {e}")
            return
        for w in warnings:
            self._message("warning", f"Settings: {w}")
        self._apply(new, save=False)
        self._message("info", "Settings reloaded from file")

    def _begin_turn(self):
        if self._turn_remaining > 0:
            return
        m = self.settings.mouse
        self._turn_remaining = m.counts_per_360
        self._turn_rate = m.counts_per_360 / m.calibrate_turn_seconds
        self._turn_acc = 0.0
        self.app.holds.add("test turn")
        self._message("info", f"Test turn: sending {m.counts_per_360:g} counts (one full turn)")

    def _turn_tick(self, dt):
        if self.app.keys.held(self.app.vk["pause_hold"]):
            self._turn_remaining = 0.0
            self.app.holds.discard("test turn")
            self._message("info", "Test turn cancelled")
            return
        self._turn_acc += min(self._turn_rate * dt, self._turn_remaining)
        step = int(self._turn_acc)
        self._turn_acc -= step
        self._turn_remaining -= step
        if step and self.app.send:
            self._backend.send_relative(step, 0)
        if self._turn_remaining < 1:
            self._turn_remaining = 0.0
            self.app.holds.discard("test turn")
            self._sounds.play("done", force=True)
            self._message("info", "Test turn finished")

    def _handle(self, event):
        self._message(event.kind, event.text)
        if event.kind in ("enabled", "disabled", "pause", "precision_on", "precision_off"):
            self._sounds.play(event.kind)
        elif event.kind == "situation" and self.settings.situations.sound:
            self._sounds.play("situation_on" if event.data else "situation_off")
        elif event.kind == "tracking_lost":
            # Movement stops at once, but only beep if it lasts (games can briefly starve the camera).
            self._lost_since = self._clock()
        elif event.kind == "tracking_ok":
            if self._lost_beeped and self.app.enabled:
                self._sounds.play("tracking_ok")
            self._lost_since = None
            self._lost_beeped = False
        elif event.kind == "recentered" and self.settings.tracking.source == "webcam":
            new = dataclasses.replace(self.settings, webcam=dataclasses.replace(
                self.settings.webcam, neutral_yaw=round(event.data[0], 2),
                neutral_pitch=round(event.data[1], 2)))
            self._apply(new, save=True)

    def _update_snapshot(self):
        app, src = self.app, self.source
        r = app.result
        error = getattr(src, "error", None)
        snap = Snapshot(
            state=app.state, enabled=app.enabled, paused=app.paused, tracking=app.tracking,
            yaw=r.yaw, pitch=r.pitch, raw_angles=app.raw_angles,
            yaw_speed=r.yaw_speed, pitch_speed=r.pitch_speed,
            source_kind=self.settings.tracking.source,
            source_status=error or getattr(src, "status", "listening on port "
                                           f"{self.settings.opentrack.port}"),
            source_error=error, face_visible=getattr(src, "face_visible", None),
            packets=getattr(src, "packets", 0), in_game=app.in_game,
            test_turn_active=self._turn_remaining > 0, dry_run=self.dry_run,
            glancing=r.glancing, gaze=r.gaze, eye_pitch=app.eye_pitch, rate=self.rate,
            practice_camera=tuple(app.practice_camera), situation=app.situation,
            face=dict(app.gestures.level), gestures=tuple(sorted(app.gestures.active)),
            buttons=tuple(sorted(app.buttons_down)), frozen_by_action=app.action_freeze,
            settings=self.settings)
        with self._lock:
            self._snapshot = snap

    def _beep_if_still_lost(self, now):
        if (self._lost_since is not None and not self._lost_beeped and self.app.enabled
                and now - self._lost_since >= LOST_BEEP_SECONDS):
            self._sounds.play("tracking_lost")
            self._lost_beeped = True

    def _measure_rate(self, now):
        packets = getattr(self.source, "packets", 0)
        if self._rate_at is not None:
            self.rate = (packets - self._rate_packets) / max(1e-6, now - self._rate_at)
        self._rate_at, self._rate_packets = now, packets
        if now >= self._next_rate_log:
            self._next_rate_log = now + 60
            log.info("tracking rate %.0f/s, state %s", self.rate, self.app.state)

    def _loop(self):
        next_check = 0.0
        last = self._clock()
        next_tick = self._clock()
        with high_resolution_timer():
            while self._running:
                now = self._clock()
                dt = min(now - last, 0.05)
                last = now
                while True:
                    try:
                        self._commands.get_nowait()()
                    except queue.Empty:
                        break
                if now >= next_check:
                    next_check = now + 1.0
                    self._check_file()
                    self._measure_rate(now)
                self._beep_if_still_lost(now)
                for event in self.app.tick(now):
                    self._handle(event)
                if self.calibration_mode and self.app.keys.pressed(self.app.vk["calibrate_turn"]):
                    self._begin_turn()
                if self._turn_remaining > 0:
                    self._turn_tick(dt)
                self._update_snapshot()
                period = 1.0 / self.settings.general.output_rate_hz
                next_tick += period
                delay = next_tick - self._clock()
                if delay > 0:
                    time.sleep(delay)
                else:
                    next_tick = self._clock()
