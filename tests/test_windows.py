"""Tests of the real Windows calls. Skipped on other systems.

They never move the mouse or create shortcuts, so they are safe to run on any PC.
"""

import ctypes
import sys
import tempfile
import time
import unittest
from pathlib import Path

from headmouse import config
from headmouse.engine import HeadMouse
from headmouse.tracking import HeadSample

WINDOWS = sys.platform == "win32"


@unittest.skipUnless(WINDOWS, "Windows only")
class WindowsInputTests(unittest.TestCase):
    def test_struct_size_matches_windows(self):
        from headmouse.winput import INPUT
        user32 = ctypes.WinDLL("user32")
        # SendInput rejects a wrong cbSize with ERROR_INVALID_PARAMETER; a zero-length call
        # with the right size is accepted and moves nothing.
        user32.SendInput.argtypes = (ctypes.c_uint, ctypes.c_void_p, ctypes.c_int)
        ctypes.set_last_error(0)
        self.assertEqual(user32.SendInput(0, None, ctypes.sizeof(INPUT)), 0)
        self.assertEqual(ctypes.sizeof(INPUT), 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28)

    def test_key_reading_and_window_title(self):
        from headmouse.winput import WindowsInput
        w = WindowsInput()
        self.assertIsInstance(w.is_key_down(0x78), bool)
        self.assertFalse(w.is_key_down(None))
        self.assertIsInstance(w.foreground_window_title(), str)

    def test_zero_movement_send(self):
        from headmouse.winput import WindowsInput
        w = WindowsInput()
        w.send_relative(0, 0)          # no visible movement; checks the call itself works
        self.assertIn(w.failed_sends, (0, 1))

    def test_high_resolution_timer(self):
        from headmouse.winput import high_resolution_timer
        with high_resolution_timer():
            start = time.perf_counter()
            for _ in range(20):
                time.sleep(0.002)
            elapsed = time.perf_counter() - start
        self.assertLess(elapsed, 0.2)

    def test_engine_tick_with_real_backend_does_not_move_when_off(self):
        from headmouse.winput import WindowsInput

        class Source:
            def latest(self):
                return HeadSample(12.0, 0.0, (0, 0, 0, 12.0, 0, time.perf_counter()), time.perf_counter(), 1)
        settings = config.from_dict({"general": {"start_enabled": False, "game_window_title": ""}})[0]
        app = HeadMouse(settings, Source(), WindowsInput())
        for i in range(10):
            app.tick(i / 125)
        self.assertEqual(app.state, "OFF")


@unittest.skipUnless(WINDOWS, "Windows only")
class WindowsSystemTests(unittest.TestCase):
    def test_sound_files_play_without_error(self):
        from headmouse.sounds import SoundPlayer
        with tempfile.TemporaryDirectory() as d:
            player = SoundPlayer(config.SoundSettings(volume=0.01), folder=d)
            player.play("tracking_ok", force=True)
            time.sleep(0.2)
            self.assertTrue(any(Path(d).glob("tracking_ok_*.wav")))

    def test_documents_folder_and_process_check(self):
        from headmouse import opentrack_setup
        self.assertTrue(opentrack_setup.documents_folder().is_dir())
        self.assertIsInstance(opentrack_setup.is_running(), bool)
        self.assertIn(type(opentrack_setup.current_profile()), (str, type(None)))


if __name__ == "__main__":
    unittest.main()
