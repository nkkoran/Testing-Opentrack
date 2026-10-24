"""Quick health check of a HeadMouse installation.

Run with `HeadMouse.exe --selfcheck report.txt` (or `py run_headmouse.py --selfcheck`).
The build pipeline runs it on the packaged app; it never moves the mouse.
Exit code 0 = everything works.
"""

import ctypes
import sys
import time
from pathlib import Path


def run(base_dir, settings_path, report_path=""):
    lines = []
    failures = 0

    def check(name, fn):
        nonlocal failures
        try:
            detail = fn()
            lines.append(f"PASS  {name}: {detail or 'ok'}")
        except Exception as e:  # report every kind of failure
            failures += 1
            lines.append(f"FAIL  {name}: {type(e).__name__}: {e}")

    def version():
        from . import __version__
        return f"HeadMouse {__version__}, Python {sys.version.split()[0]}, frozen={getattr(sys, 'frozen', False)}"

    def settings():
        from . import config
        s, warnings = config.load(settings_path)
        return f"{settings_path} ({len(warnings)} warnings, tracker={s.tracking.source})"

    def window():
        import customtkinter as ctk
        root = ctk.CTk()
        root.withdraw()
        root.update()
        root.destroy()
        return f"customtkinter {ctk.__version__}"

    def program_parts():
        from . import actions, config, gui, guide, practice, quickfix, situations
        parts = (actions, gui, guide, practice, quickfix, situations)   # all must be in the program
        block = practice.Checkup(config.Settings(), focus="aim", seed=1).next_block()
        fixes = quickfix.available(config.Settings(), "x")
        return f"{len(parts)} parts, practice block of {len(block.targets)} targets, {len(fixes)} quick fixes"

    def face_tracking():
        import numpy as np
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions, vision
        from .webcam import find_model
        model = find_model(base_dir)
        if model is None:
            raise FileNotFoundError("face_landmarker.task not found")
        landmarker = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_buffer=model.read_bytes()),
            output_facial_transformation_matrixes=True))
        start = time.perf_counter()
        landmarker.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.zeros((240, 320, 3), np.uint8)))
        landmarker.close()
        return f"mediapipe {mp.__version__}, model {model}, detect {1000 * (time.perf_counter() - start):.0f} ms"

    def camera_library():
        import cv2
        return f"opencv {cv2.__version__}"

    def mouse_and_keys():
        from .winput import INPUT, WindowsInput
        size = ctypes.sizeof(INPUT)
        expected = 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28
        if size != expected:
            raise AssertionError(f"INPUT is {size} bytes, Windows expects {expected}")
        if sys.platform != "win32":
            return f"INPUT {size} bytes (Windows calls skipped on {sys.platform})"
        w = WindowsInput()
        w.is_key_down(0x78)
        title = w.foreground_window_title()
        return f"INPUT {size} bytes, key reading ok, foreground window {title[:40]!r}"

    def sounds():
        from .sounds import CUES, tone_wav
        return f"{sum(len(tone_wav(parts, 0.5)) for parts in CUES.values())} bytes of tones"

    for name, fn in (("version", version), ("settings", settings), ("window", window), ("program parts", program_parts),
                     ("face tracking", face_tracking), ("camera library", camera_library),
                     ("mouse and keys", mouse_and_keys), ("sounds", sounds)):
        check(name, fn)
    lines.append("RESULT: " + ("all checks passed" if not failures else f"{failures} check(s) failed"))
    text = "\n".join(lines) + "\n"
    if report_path:
        Path(report_path).write_text(text, encoding="utf-8")
    if sys.stdout is not None:  # None inside the windowed .exe
        print(text, end="")
    return 0 if not failures else 1
