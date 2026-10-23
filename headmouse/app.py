"""HeadMouse: joystick-style head control of the mouse, fed by OpenTrack.

Run with no options for normal use. Other modes:
  --monitor    show what OpenTrack is sending; never moves the mouse
  --dry-run    run everything but never move the mouse (shows the speeds it would use)
  --curves     print the speed tables for the four directions and exit
  --calibrate  send exact 360-degree turns on a key press, to calibrate counts_per_360
"""

import argparse
import sys
import time
from pathlib import Path

from . import config
from .controller import MotionController, StepResult, orient
from .curves import DirectionCurve
from .safety import TrackingMonitor, TrackingStatus
from .tracking import OpenTrackUDPSource
from .winput import KeyReader, WindowsInput, high_resolution_timer

SETTINGS_FILE = "headmouse_settings.toml"
KEY_NAMES = ("pause_hold", "enable_toggle", "recenter", "precision_hold", "calibrate_turn")


def base_dir():
    """Folder holding the settings file: next to the .exe, or the project folder."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


class Console:
    """One self-updating status line, with event messages printed above it."""

    def __init__(self, enabled=True):
        self.enabled = enabled
        self._width = 0

    def status(self, text):
        if not self.enabled:
            return
        pad = max(0, self._width - len(text))
        sys.stdout.write("\r" + text + " " * pad)
        sys.stdout.flush()
        self._width = len(text)

    def event(self, text):
        if self._width:
            sys.stdout.write("\r" + " " * self._width + "\r")
            self._width = 0
        stamp = time.strftime("%H:%M:%S")
        print(f"[{stamp}] {text}", flush=True)


class SettingsFile:
    def __init__(self, path):
        self.path = Path(path)
        self._mtime = self._read_mtime()

    def _read_mtime(self):
        try:
            return self.path.stat().st_mtime
        except OSError:
            return None

    def changed(self):
        mtime = self._read_mtime()
        if mtime != self._mtime:
            self._mtime = mtime
            return True
        return False


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
    """One instance runs the whole joystick-style loop; call tick() repeatedly."""

    def __init__(self, settings, source, backend, send=True):
        self.source = source
        self.backend = backend
        self.keys = Keys(backend)
        self.send = send
        self.enabled = settings.general.start_enabled
        self.offset = (0.0, 0.0)
        self.state = "STARTING"
        self.result = StepResult()
        self.tracking = TrackingStatus.NO_DATA
        self._last_tick = None
        self._reported_tracking = None
        self._reported_failures = 0
        self.apply_settings(settings)

    def apply_settings(self, settings):
        self.settings = settings
        self.controller = MotionController(settings)
        self.monitor = TrackingMonitor(settings.safety)
        self.vk = {name: settings.key(name) for name in KEY_NAMES}

    def _window_ok(self):
        wanted = self.settings.general.only_when_window_title_contains.strip().lower()
        return not wanted or wanted in self.backend.foreground_window_title().lower()

    def tick(self, now):
        """Run one output tick. Returns a list of event messages to show."""
        events = []
        dt = 0.0 if self._last_tick is None else min(now - self._last_tick, 0.05)
        self._last_tick = now

        if self.keys.pressed(self.vk["enable_toggle"]):
            self.enabled = not self.enabled
            events.append("Head control ENABLED" if self.enabled else "Head control DISABLED")
        paused = self.keys.held(self.vk["pause_hold"])
        precision = self.keys.held(self.vk["precision_hold"])

        self.tracking, raw = self.monitor.check(self.source.latest(), now)
        if self.tracking != self._reported_tracking:
            if self.tracking == TrackingStatus.OK:
                events.append("Tracking OK")
            else:
                events.append(f"Movement stopped: {self.tracking.value}")
            self._reported_tracking = self.tracking

        if self.keys.pressed(self.vk["recenter"]):
            if raw is None:
                events.append("Cannot set neutral position: tracking not available")
            else:
                self.offset = orient(raw, self.settings)
                events.append(f"Neutral position set (yaw {self.offset[0]:+.1f}, "
                              f"pitch {self.offset[1]:+.1f})")

        angles = orient(raw, self.settings, self.offset) if raw is not None else None
        window_ok = self._window_ok()
        hold = paused or not self.enabled or not window_ok
        self.result = self.controller.step(angles, dt, hold=hold, precision=precision)

        if self.send and (self.result.dx or self.result.dy):
            self.backend.send_relative(self.result.dx, self.result.dy)
        if self.backend.failed_sends > self._reported_failures:
            if self._reported_failures == 0:
                events.append("Windows refused the mouse movement. If the game runs as "
                              "administrator, run this program as administrator too.")
            self._reported_failures = self.backend.failed_sends

        if not self.enabled:
            self.state = "DISABLED"
        elif not window_ok:
            self.state = "WAITING FOR GAME WINDOW"
        elif self.tracking != TrackingStatus.OK:
            self.state = "STOPPED: " + self.tracking.value
        elif paused:
            self.state = "PAUSED"
        elif self.result.waiting_for_center:
            self.state = "CENTER HEAD TO RESUME"
        else:
            self.state = "ACTIVE" + (" (precision)" if precision else "")
        return events

    def status_line(self):
        r = self.result
        horiz = "right" if r.yaw_speed > 0 else "left " if r.yaw_speed < 0 else "  -  "
        vert = "up  " if r.pitch_speed > 0 else "down" if r.pitch_speed < 0 else " -  "
        return (f"{self.state:<25} yaw{r.yaw:+6.1f} pitch{r.pitch:+6.1f} | "
                f"{horiz}{abs(r.yaw_speed):4.0f} {vert}{abs(r.pitch_speed):4.0f} deg/s")


def _key_help(settings):
    k = settings.keys
    return (f"  {k.enable_toggle:<6} turn head control on/off\n"
            f"  {k.pause_hold:<6} HOLD to freeze the camera (release to resume)\n"
            f"  {k.precision_hold:<6} HOLD for precision (slow) aiming\n"
            f"  {k.recenter:<6} set the current head position as neutral\n"
            f"  Ctrl+C (in this window) to quit")


def _load_or_exit(path, console):
    try:
        settings, warnings = config.load(path)
    except config.SettingsError as e:
        console.event(f"Settings error: {e}")
        raise SystemExit(1)
    for w in warnings:
        console.event(f"Settings warning: {w}")
    return settings


def _reload(settings_file, current, console):
    """Re-read the settings file after it was saved. Keeps the old settings on error."""
    try:
        settings, warnings = config.load(settings_file.path)
    except config.SettingsError as e:
        console.event(f"Settings NOT reloaded - {e}")
        return current
    for w in warnings:
        console.event(f"Settings warning: {w}")
    console.event("Settings reloaded")
    return settings


def _start_source(settings, console):
    source = OpenTrackUDPSource(settings.opentrack.listen_address, settings.opentrack.port)
    try:
        return source.start()
    except OSError as e:
        console.event(f"Error: {e}")
        raise SystemExit(1)


def _sleep_until(next_tick, period):
    delay = next_tick - time.perf_counter()
    if delay > 0:
        time.sleep(delay)
        return next_tick + period
    return time.perf_counter() + period  # fell behind; don't try to catch up


def run_tracking(path, dry_run):
    console = Console()
    settings = _load_or_exit(path, console)
    if sys.platform != "win32" and not dry_run:
        console.event("Moving the mouse only works on Windows. Use --dry-run to test elsewhere.")
        return 1
    backend = KeyReader() if dry_run else WindowsInput()
    source = _start_source(settings, console)
    app = HeadMouse(settings, source, backend, send=not dry_run)
    settings_file = SettingsFile(path)

    print(f"HeadMouse - listening for {source.describe()}"
          + ("  [DRY RUN: the mouse will not move]" if dry_run else ""))
    print(f"Settings: {path}  (saved changes are picked up automatically)")
    print(_key_help(settings))
    print("Head control starts " + ("ENABLED" if app.enabled else
                                    f"DISABLED - press {settings.keys.enable_toggle} to enable"))
    print()

    next_check = next_status = time.perf_counter()
    next_tick = time.perf_counter()
    try:
        with high_resolution_timer():
            while True:
                now = time.perf_counter()
                if now >= next_check:
                    next_check = now + 1.0
                    if settings_file.changed():
                        new = _reload(settings_file, settings, console)
                        if new is not settings:
                            if (new.opentrack.listen_address, new.opentrack.port) != \
                                    (settings.opentrack.listen_address, settings.opentrack.port):
                                source.stop()
                                source = _start_source(new, console)
                                app.source = source
                            settings = new
                            app.apply_settings(settings)
                for message in app.tick(now):
                    console.event(message)
                if settings.general.show_status and now >= next_status:
                    next_status = now + 0.1
                    console.status(app.status_line())
                next_tick = _sleep_until(next_tick, 1.0 / settings.general.output_rate_hz)
    except KeyboardInterrupt:
        console.event("Stopped.")
    finally:
        source.stop()
    return 0


def run_monitor(path):
    console = Console()
    settings = _load_or_exit(path, console)
    source = _start_source(settings, console)
    monitor = TrackingMonitor(settings.safety)
    print(f"Monitor mode - listening for {source.describe()}. The mouse will NOT move.")
    print("Turn your head right, left, up and down and check the words match. Ctrl+C to quit.\n")
    last_packets, last_time = 0, time.perf_counter()
    rate = 0.0
    try:
        while True:
            time.sleep(0.1)
            now = time.perf_counter()
            if now - last_time >= 1.0:
                rate = (source.packets - last_packets) / (now - last_time)
                last_packets, last_time = source.packets, now
            sample = source.latest()
            status, raw = monitor.check(sample, now)
            if sample is None:
                console.status(f"Waiting for data from OpenTrack on port {settings.opentrack.port}...")
                continue
            yaw, pitch = orient((sample.yaw, sample.pitch), settings)
            h = "RIGHT" if yaw > 0.5 else "LEFT" if yaw < -0.5 else "center"
            v = "UP" if pitch > 0.5 else "DOWN" if pitch < -0.5 else "center"
            console.status(f"{status.value:<22} {rate:5.0f} packets/s | yaw {yaw:+6.1f} ({h:<6}) "
                           f"pitch {pitch:+6.1f} ({v:<6}) | roll {sample.values[5]:+6.1f}")
    except KeyboardInterrupt:
        console.event("Stopped.")
    finally:
        source.stop()
    return 0


def print_curves(path):
    settings = _load_or_exit(path, Console())
    names = ("right", "left", "up", "down")
    curves = {n: DirectionCurve(getattr(settings, n)) for n in names}
    print("Camera speed in degrees/second for each head angle"
          + f" (precision mode multiplies by {settings.motion.precision_speed_factor:g})\n")
    print("angle " + "".join(f"{n:>9}" for n in names))
    for tenth in range(0, 201, 5):
        a = tenth / 10
        print(f"{a:5.1f} " + "".join(f"{curves[n].speed(a):9.1f}" for n in names))
    cpd = settings.mouse.counts_per_360 / 360
    print(f"\nMouse counts per degree: horizontal {cpd:.2f}, vertical "
          f"{cpd * settings.mouse.vertical_scale:.2f} (counts_per_360 = {settings.mouse.counts_per_360:g})")
    return 0


def run_calibrate(path):
    console = Console()
    settings = _load_or_exit(path, console)
    if sys.platform != "win32":
        console.event("Calibration sends real mouse movement and only works on Windows.")
        return 1
    backend = WindowsInput()
    keys = Keys(backend)
    print("Calibration mode - head tracking is OFF.")
    print(f"In Enshrouded, face a landmark and press {settings.keys.calibrate_turn}: the camera "
          f"should turn exactly once around ({settings.mouse.calibrate_turn_seconds:g} s).")
    print(f"Hold {settings.keys.pause_hold} to cancel a turn. Edit counts_per_360 in the settings "
          "file and save - it is re-read on every key press. Ctrl+C to quit.\n")
    remaining = 0.0
    rate = 0.0
    acc = 0.0
    period = 1.0 / settings.general.output_rate_hz
    next_tick = time.perf_counter()
    try:
        with high_resolution_timer():
            while True:
                if keys.pressed(settings.key("calibrate_turn")) and remaining <= 0:
                    try:
                        settings, _ = config.load(path)
                    except config.SettingsError as e:
                        console.event(f"Settings error, using previous values: {e}")
                    remaining = settings.mouse.counts_per_360
                    rate = remaining / settings.mouse.calibrate_turn_seconds
                    acc = 0.0
                    console.event(f"Turning 360 degrees with counts_per_360 = {remaining:g} ...")
                if remaining > 0:
                    if keys.held(settings.key("pause_hold")):
                        remaining = 0.0
                        console.event("Turn cancelled.")
                    else:
                        acc += min(rate * period, remaining)
                        step = int(acc)
                        acc -= step
                        remaining -= step
                        if step:
                            backend.send_relative(step, 0)
                        if remaining < 1:
                            remaining = 0.0
                            console.event("Done. Too far: lower counts_per_360. Not far enough: raise it. "
                                          "New value = old value x 360 / degrees actually turned.")
                next_tick = _sleep_until(next_tick, period)
    except KeyboardInterrupt:
        console.event("Stopped.")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="headmouse", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--settings", type=Path, default=base_dir() / SETTINGS_FILE,
                        help="settings file to use (default: %(default)s)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--monitor", action="store_true", help="show incoming tracking data only")
    mode.add_argument("--dry-run", action="store_true", help="run without moving the mouse")
    mode.add_argument("--curves", action="store_true", help="print the speed tables and exit")
    mode.add_argument("--calibrate", action="store_true", help="calibrate counts_per_360")
    args = parser.parse_args(argv)

    if args.monitor:
        return run_monitor(args.settings)
    if args.curves:
        return print_curves(args.settings)
    if args.calibrate:
        return run_calibrate(args.settings)
    return run_tracking(args.settings, args.dry_run)
