"""Tests for the engine, settings saving, sounds, filters and webcam maths."""

import dataclasses
import math
import os
import shutil
import tempfile
import time
import unittest
import wave
import io
from pathlib import Path

from headmouse import config
from headmouse.engine import Engine, HeadMouse
from headmouse.filters import OneEuroFilter
from headmouse.sounds import CUES, SoundPlayer, tone_wav
from headmouse.tracking import HeadSample
from headmouse.webcam import matrix_to_angles
from headmouse.winput import NullInput

ROOT = Path(__file__).resolve().parent.parent
DT = 1 / 125


class LiveSource:
    """Fake tracker that always has a fresh sample at the given angles."""

    def __init__(self, yaw=0.0, pitch=0.0):
        self.yaw, self.pitch = yaw, pitch
        self.seq = 0
        self.stopped = False
        self.packets = 0

    def start(self):
        return self

    def stop(self):
        self.stopped = True

    def describe(self):
        return "fake"

    def latest(self):
        self.seq += 1
        return HeadSample(self.yaw, self.pitch, (0, 0, 0, self.yaw, self.pitch, self.seq * 1e-6),
                          time.perf_counter(), self.seq)


def wait_for(condition, timeout=2.0):
    end = time.time() + timeout
    while time.time() < end:
        if condition():
            return True
        time.sleep(0.01)
    return False


class SaveTests(unittest.TestCase):
    def test_round_trip_keeps_comments(self):
        text = (ROOT / "headmouse_settings.toml").read_text(encoding="utf-8")
        new = config.update_text(text, {"down": {"deadzone": 1.5}, "mouse": {"counts_per_360": 2667.0},
                                        "keys": {"pause_hold": "PAUSE"}})
        self.assertEqual(text.count("#"), new.count("#"))
        s, warnings = config.from_dict(__import__("tomllib").loads(new))
        self.assertEqual(warnings, [])
        self.assertEqual((s.down.deadzone, s.up.deadzone), (1.5, 2.0))
        self.assertEqual(s.mouse.counts_per_360, 2667.0)
        self.assertEqual(s.keys.pause_hold, "PAUSE")

    def test_save_refuses_invalid_result(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.toml"
            shutil.copy(ROOT / "headmouse_settings.toml", p)
            before = p.read_text()
            with self.assertRaises(config.SettingsError):
                config.save_values(p, {"right": {"deadzone": 99.0}})
            self.assertEqual(p.read_text(), before)

    def test_diff(self):
        a = config.Settings()
        b = dataclasses.replace(a, left=dataclasses.replace(a.left, max_speed=150.0))
        self.assertEqual(config.diff(a, b), {"left": {"max_speed": 150.0}})


class SoundTests(unittest.TestCase):
    def test_wav_is_valid(self):
        for name, parts in CUES.items():
            with wave.open(io.BytesIO(tone_wav(parts, 0.5))) as w:
                self.assertEqual(w.getframerate(), 22050)
                self.assertGreater(w.getnframes(), 100, name)

    def test_cue_switches(self):
        s = config.SoundSettings(on_pause=False)
        player = SoundPlayer(s)
        player.play("pause")
        player.play("enabled")
        self.assertEqual(player.played, ["enabled"])
        player.update(dataclasses.replace(s, enabled=False))
        player.play("enabled")
        self.assertEqual(player.played, ["enabled"])


class FilterAndMathTests(unittest.TestCase):
    def test_one_euro_reduces_jitter_but_follows_moves(self):
        import random
        rnd = random.Random(1)
        f = OneEuroFilter(1.0, 0.05)
        out = [f(10 + rnd.uniform(-0.5, 0.5), i / 30) for i in range(120)]
        self.assertLess(max(out[60:]) - min(out[60:]), 0.4)
        out = [f(20.0, 4 + i / 30) for i in range(30)]
        self.assertAlmostEqual(out[-1], 20.0, delta=0.5)

    def rot(self, yaw, pitch, roll):
        y, p, r = (math.radians(v) for v in (yaw, pitch, roll))
        ry = [[math.cos(y), 0, math.sin(y)], [0, 1, 0], [-math.sin(y), 0, math.cos(y)]]
        rx = [[1, 0, 0], [0, math.cos(p), -math.sin(p)], [0, math.sin(p), math.cos(p)]]
        rz = [[math.cos(r), -math.sin(r), 0], [math.sin(r), math.cos(r), 0], [0, 0, 1]]
        mul = lambda a, b: [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
        m = mul(mul(ry, rx), rz)
        return [row + [0.0] for row in m] + [[0, 0, 0, 1]]

    def test_matrix_to_angles(self):
        # MediaPipe yaw/pitch signs are flipped so right and up come out positive.
        yaw, pitch, roll = matrix_to_angles(self.rot(12, -7, 4))
        self.assertAlmostEqual(yaw, -12, places=6)
        self.assertAlmostEqual(pitch, 7, places=6)
        self.assertAlmostEqual(roll, 4, places=6)


class ModelDownloadTests(unittest.TestCase):
    def fake_download(self, payload):
        import urllib.request
        from unittest import mock
        return mock.patch.object(urllib.request, "urlopen", lambda url, timeout: io.BytesIO(payload))

    def test_valid_model_with_leading_zero_bytes(self):
        import os as _os
        import zipfile
        from headmouse.webcam import download_model
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
            z.writestr("model.tflite", _os.urandom(1_200_000))
        with tempfile.TemporaryDirectory() as d, self.fake_download(b"\0\0" + buf.getvalue()):
            dest = download_model(Path(d) / "face_landmarker.task")
            self.assertTrue(dest.exists())
            self.assertFalse((Path(d) / "face_landmarker.part").exists())

    def test_damaged_download_is_removed(self):
        from headmouse.webcam import download_model
        with tempfile.TemporaryDirectory() as d, self.fake_download(b"<html>error</html>" * 100000):
            with self.assertRaises(OSError):
                download_model(Path(d) / "face_landmarker.task")
            self.assertEqual(list(Path(d).iterdir()), [])


class AutoEnableTests(unittest.TestCase):
    def test_turns_on_in_game_and_off_outside(self):
        s = config.Settings()
        backend = NullInput()
        app = HeadMouse(s, LiveSource(10.0), backend)
        t = 0.0
        for title, expected in [("Desktop", False), ("Enshrouded", True), ("Discord", False)]:
            backend.window_title = title
            events = []
            for _ in range(10):
                events += app.tick(t)
                t += DT
            self.assertEqual(app.enabled, expected, title)
        kinds = [e.kind for e in events]
        self.assertIn("disabled", kinds)


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "headmouse_settings.toml"
        shutil.copy(ROOT / "headmouse_settings.toml", self.path)
        config.save_values(self.path, {"general": {"start_enabled": True, "game_window_title": ""},
                                       "sounds": {"on_pause": True}})
        self.sources = []
        self.backend = NullInput()
        self.sounds = SoundPlayer(config.SoundSettings())

    def factory(self, settings, base):
        src = LiveSource(12.0, 0.0)
        src.kind = settings.tracking.source
        self.sources.append(src)
        return src

    def start(self):
        self.engine = Engine(self.path, self.dir.name, backend=self.backend, sound_player=self.sounds,
                             source_factory=self.factory, launch_opentrack=False).start()
        self.engine.app.send = True  # NullInput records instead of moving the mouse
        return self.engine

    def tearDown(self):
        self.engine.stop()
        self.dir.cleanup()

    def test_moves_and_toggles(self):
        e = self.start()
        self.assertTrue(wait_for(lambda: sum(dx for dx, _ in self.backend.sent) > 20))
        e.toggle_enabled()
        self.assertTrue(wait_for(lambda: e.snapshot().state == "OFF"))
        n = len(self.backend.sent)
        time.sleep(0.1)
        self.assertEqual(len(self.backend.sent), n)
        self.assertIn("disabled", self.sounds.played)

    def test_webcam_recenter_is_saved(self):
        e = self.start()
        self.assertTrue(wait_for(lambda: e.snapshot().state == "ACTIVE"))
        e.recenter()
        self.assertTrue(wait_for(lambda: e.snapshot().state == "ACTIVE" and e.snapshot().yaw_speed == 0))
        self.assertTrue(wait_for(lambda: config.load(self.path)[0].webcam.neutral_yaw == 12.0))

    def test_test_turn_sends_exact_counts(self):
        config.save_values(self.path, {"mouse": {"counts_per_360": 300.0, "calibrate_turn_seconds": 0.3}})
        e = self.start()
        e.set_enabled(False)
        self.assertTrue(wait_for(lambda: e.snapshot().state == "OFF"))
        self.backend.sent.clear()
        e.start_test_turn()
        self.assertTrue(wait_for(lambda: e.snapshot().test_turn_active))
        self.assertTrue(wait_for(lambda: not e.snapshot().test_turn_active))
        self.assertEqual(sum(dx for dx, _ in self.backend.sent), 300)
        self.assertIn("done", self.sounds.played)

    def test_apply_settings_saves_and_switches_source(self):
        e = self.start()
        new = dataclasses.replace(e.settings, tracking=config.TrackingSettings(source="opentrack"),
                                  right=dataclasses.replace(e.settings.right, max_speed=120.0))
        e.apply_settings(new)
        self.assertTrue(wait_for(lambda: len(self.sources) == 2))
        self.assertTrue(self.sources[0].stopped)
        saved = config.load(self.path)[0]
        self.assertEqual((saved.tracking.source, saved.right.max_speed), ("opentrack", 120.0))
        text = self.path.read_text()
        self.assertIn("#  Where head angles come from", text)

    def test_save_after_live_preview_writes_file(self):
        e = self.start()
        new = dataclasses.replace(e.settings, up=dataclasses.replace(e.settings.up, max_speed=90.0))
        e.apply_settings(new, save=False)                       # slider preview
        self.assertTrue(wait_for(lambda: e.snapshot().settings.up.max_speed == 90.0))
        self.assertEqual(config.load(self.path)[0].up.max_speed, 60.0)
        e.apply_settings(new, save=True)                        # then Save
        self.assertTrue(wait_for(lambda: config.load(self.path)[0].up.max_speed == 90.0))

    def test_webcam_smoothing_change_does_not_restart_camera(self):
        e = self.start()
        new = dataclasses.replace(e.settings, webcam=dataclasses.replace(e.settings.webcam,
                                                                        smoothing_min_cutoff=2.0))
        e.apply_settings(new, save=False)
        self.assertTrue(wait_for(lambda: e.snapshot().settings.webcam.smoothing_min_cutoff == 2.0))
        self.assertEqual(len(self.sources), 1)

    def test_external_edit_is_reloaded(self):
        e = self.start()
        time.sleep(0.05)
        config.save_values(self.path, {"left": {"deadzone": 5.0}})
        os.utime(self.path, (time.time() + 5, time.time() + 5))
        self.assertTrue(wait_for(lambda: e.snapshot().settings.left.deadzone == 5.0, timeout=3))

    def test_wizard_hold_stops_movement(self):
        e = self.start()
        e.set_hold("wizard", True)
        self.assertTrue(wait_for(lambda: e.snapshot().state.startswith("BUSY")))
        n = len(self.backend.sent)
        time.sleep(0.1)
        self.assertEqual(len(self.backend.sent), n)
        self.assertIsNotNone(e.snapshot().raw_angles)


@unittest.skipUnless(os.environ.get("HEADMOUSE_TEST_ASSETS"), "set HEADMOUSE_TEST_ASSETS to a folder "
                     "with face_landmarker.task and portrait.jpg to run the real MediaPipe test")
class WebcamIntegrationTest(unittest.TestCase):
    def test_real_face_from_video(self):
        import cv2
        from headmouse.webcam import WebcamSource
        assets = Path(os.environ["HEADMOUSE_TEST_ASSETS"])
        img = cv2.imread(str(assets / "portrait.jpg"))
        with tempfile.TemporaryDirectory() as d:
            video = str(Path(d) / "face.avi")
            h, w = img.shape[:2]
            out = cv2.VideoWriter(video, cv2.VideoWriter_fourcc(*"MJPG"), 30, (w, h))
            for i in range(90):
                out.write(img if i < 45 else cv2.flip(img, 1))
            out.release()
            ws = dataclasses.replace(config.WebcamSettings(),
                                     model_path=str(assets / "face_landmarker.task"))
            src = WebcamSource(ws, d, open_camera=lambda: cv2.VideoCapture(video), eyes=True)
            src.preview_wanted = True
            yaws = []
            src._handle_orig = src._handle

            def record(result, now):
                src._handle_orig(result, now)
                if result.facial_transformation_matrixes:
                    yaws.append(matrix_to_angles(result.facial_transformation_matrixes[0])[0])
            src._handle = record
            src.start()
            wait_for(lambda: src.status != "running" and src.status != "starting"
                     and not src.status.startswith(("loading", "opening")), timeout=60)
            src.stop()
        self.assertGreater(len(yaws), 60, src.status)
        first, second = sum(yaws[:30]) / 30, sum(yaws[-30:]) / 30
        self.assertLess(first * second, 0)          # mirroring flips the yaw sign
        self.assertIsNotNone(src.preview_png())
        self.assertGreater(src.packets, 60)
        self.assertIsNotNone(src.latest().eye_pitch)       # eye data for the glance guard


if __name__ == "__main__":
    unittest.main()
