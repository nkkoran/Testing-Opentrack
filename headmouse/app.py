"""HeadMouse: joystick-style head control of the mouse.

Run with no options to open the HeadMouse window. Other modes:
  --console    run without the window (status line in the console)
  --monitor    show the tracking data only; never moves the mouse
  --dry-run    run everything but never move the mouse (with the window or --console)
  --curves     print the speed tables for the four directions and exit
  --calibrate  console calibration: F6 sends one exact 360-degree turn
  --selfcheck  check the installation works (optionally write a report file)
"""

import argparse
import sys
import time
from pathlib import Path

from . import config
from .controller import orient
from .curves import DirectionCurve
from .engine import Engine, make_source, status_line
from .safety import TrackingMonitor

SETTINGS_FILE = "headmouse_settings.toml"


def base_dir():
    """Folder holding the settings file: next to the .exe, or the project folder."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


class Console:
    """One self-updating status line, with event messages printed above it."""

    def __init__(self):
        self._width = 0

    def status(self, text):
        pad = max(0, self._width - len(text))
        sys.stdout.write("\r" + text + " " * pad)
        sys.stdout.flush()
        self._width = len(text)

    def event(self, text):
        if self._width:
            sys.stdout.write("\r" + " " * self._width + "\r")
            self._width = 0
        print(f"[{time.strftime('%H:%M:%S')}] {text}", flush=True)


def _load_or_exit(path, console):
    try:
        settings, warnings = config.load(path)
    except config.SettingsError as e:
        console.event(f"Settings error: {e}")
        raise SystemExit(1)
    for w in warnings:
        console.event(f"Settings warning: {w}")
    return settings


def _key_help(settings):
    k = settings.keys
    return (f"  {k.enable_toggle:<6} turn head control on/off\n"
            f"  {k.pause_hold:<6} HOLD to freeze the camera (release to resume)\n"
            f"  {k.precision_hold:<6} HOLD for precision (slow) aiming\n"
            f"  {k.recenter:<6} re-center (look straight at the screen first)\n"
            f"  Ctrl+C (in this window) to quit")


def _start_engine(path, console, dry_run=False):
    engine = Engine(path, base_dir(), dry_run=dry_run)
    try:
        return engine.start()
    except config.SettingsError as e:
        console.event(f"Settings error: {e}")
        raise SystemExit(1)


def run_console(path, dry_run):
    console = Console()
    if sys.platform != "win32" and not dry_run:
        console.event("Moving the mouse only works on Windows. Use --dry-run to test elsewhere.")
        return 1
    engine = _start_engine(path, console, dry_run)
    s = engine.settings
    print(f"HeadMouse - tracking with {engine.source.describe()}"
          + ("  [DRY RUN: the mouse will not move]" if dry_run else ""))
    print(f"Settings: {path}  (saved changes are picked up automatically)")
    print(_key_help(s))
    print("Head control starts " + ("ON" if s.general.start_enabled else
                                    f"OFF - press {s.keys.enable_toggle} to turn it on"))
    print()
    try:
        while True:
            time.sleep(0.1)
            for _, text in engine.drain_messages():
                console.event(text)
            if engine.settings.general.show_status:
                console.status(status_line(engine.snapshot()))
    except KeyboardInterrupt:
        console.event("Stopped.")
    finally:
        engine.stop()
    return 0


def run_monitor(path):
    console = Console()
    settings = _load_or_exit(path, console)
    try:
        source = make_source(settings, base_dir()).start()
    except OSError as e:
        console.event(f"Error: {e}")
        return 1
    monitor = TrackingMonitor(settings.safety)
    print(f"Monitor mode - reading {source.describe()}. The mouse will NOT move.")
    print("Turn your head right, left, up and down and check the words match. Ctrl+C to quit.\n")
    last_packets, last_time, rate = 0, time.perf_counter(), 0.0
    try:
        while True:
            time.sleep(0.1)
            now = time.perf_counter()
            if now - last_time >= 1.0:
                rate = (source.packets - last_packets) / (now - last_time)
                last_packets, last_time = source.packets, now
            sample = source.latest()
            status, _ = monitor.check(sample, now)
            if sample is None:
                console.status(f"Waiting for tracking data... ({getattr(source, 'status', 'listening')})")
                continue
            yaw, pitch = orient((sample.yaw, sample.pitch), settings)
            h = "RIGHT" if yaw > 0.5 else "LEFT" if yaw < -0.5 else "center"
            v = "UP" if pitch > 0.5 else "DOWN" if pitch < -0.5 else "center"
            console.status(f"{status.value:<18} {rate:4.0f}/s | yaw {yaw:+6.1f} ({h:<6}) "
                           f"pitch {pitch:+6.1f} ({v:<6})")
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
    if sys.platform != "win32":
        console.event("Calibration sends real mouse movement and only works on Windows.")
        return 1
    engine = _start_engine(path, console)
    engine.calibration_mode = True
    engine.set_enabled(False)
    s = engine.settings
    print("Calibration mode - head control is OFF.")
    print(f"In Enshrouded, face a landmark and press {s.keys.calibrate_turn}: the camera should turn "
          f"exactly once around ({s.mouse.calibrate_turn_seconds:g} s).")
    print(f"Hold {s.keys.pause_hold} to cancel. Edit counts_per_360 in the settings file and save; "
          "it is picked up automatically.")
    print("Too far: lower counts_per_360. Not far enough: raise it. "
          "New value = old value x 360 / degrees actually turned.  Ctrl+C to quit.\n")
    try:
        while True:
            time.sleep(0.1)
            for _, text in engine.drain_messages():
                console.event(text)
    except KeyboardInterrupt:
        console.event("Stopped.")
    finally:
        engine.stop()
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="headmouse", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--settings", type=Path, default=base_dir() / SETTINGS_FILE,
                        help="settings file to use (default: %(default)s)")
    parser.add_argument("--dry-run", action="store_true", help="run without moving the mouse")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--console", action="store_true", help="run without the window")
    mode.add_argument("--monitor", action="store_true", help="show incoming tracking data only")
    mode.add_argument("--curves", action="store_true", help="print the speed tables and exit")
    mode.add_argument("--calibrate", action="store_true", help="console calibration of counts_per_360")
    mode.add_argument("--selfcheck", nargs="?", const="", metavar="REPORT",
                      help="check the installation works; optionally write the report to a file")
    args = parser.parse_args(argv)

    if args.selfcheck is not None:
        from .selfcheck import run
        return run(base_dir(), args.settings, args.selfcheck)
    if args.monitor:
        return run_monitor(args.settings)
    if args.curves:
        return print_curves(args.settings)
    if args.calibrate:
        return run_calibrate(args.settings)
    if args.console:
        return run_console(args.settings, args.dry_run)
    try:
        from .gui import run_gui
    except ModuleNotFoundError as e:  # customtkinter not installed yet
        import tkinter
        from tkinter import messagebox
        tkinter.Tk().withdraw()
        messagebox.showerror("HeadMouse", f"Part of HeadMouse is not installed yet ({e.name}).\n\n"
                                          "Please run Setup.bat in the HeadMouse folder.")
        return 1
    return run_gui(args.settings, base_dir(), args.dry_run)
