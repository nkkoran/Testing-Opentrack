"""Glance guard: glancing at the keyboard must not move the camera; steering still must."""

import unittest

from headmouse import config
from headmouse.controller import MotionController

DT = 1 / 125
EYE0 = -0.05          # eye score when looking straight at the screen
SCALE = 30.0          # eye score -> degrees


def settings(**sections):
    """Settings with the glance features switched ON (they are off by default)."""
    sections["glance"] = {"enabled": True, **sections.get("glance", {})}
    sections["down"] = {"start_delay": 0.2, **sections.get("down", {})}
    return config.from_dict(sections)[0]


def ramp(a, b, seconds):
    n = max(1, round(seconds / DT))
    return [a + (b - a) * (i + 1) / n for i in range(n)]


class Player:
    """Feeds a scripted head/eye movement through the controller and totals the mouse output."""

    def __init__(self, s=None):
        self.ctl = MotionController(s or settings())
        self.dx = self.dy = 0
        self.glanced = False

    def run(self, pitches, eyes=None, yaw=0.0, blinks=None):
        for i, p in enumerate(pitches):
            eye = eyes[i] if isinstance(eyes, list) else eyes
            blink = blinks[i] if blinks else 0.0
            r = self.ctl.step((yaw, p), DT, eye_pitch=eye, blink=blink)
            self.dx += r.dx
            self.dy += r.dy
            self.glanced |= r.glancing
        return self

    def hold(self, pitch, seconds, eye=None, yaw=0.0):
        return self.run([pitch] * round(seconds / DT), eye, yaw)


def watching(pitch):
    """Eye score while the head is tilted by `pitch` and the eyes stay on the screen."""
    return EYE0 - pitch / SCALE


class EyeCheckTests(unittest.TestCase):
    def test_glance_at_keyboard_does_not_move_camera(self):
        s = settings(glance={"eye_neutral": EYE0, "eye_scale": SCALE})
        p = Player(s)
        p.hold(0.0, 0.3, eye=EYE0)
        p.run(ramp(0, -25, 0.15), eyes=-0.75)       # eyes drop, head follows quickly
        p.hold(-25.0, 1.0, eye=-0.75)               # reading the keys
        p.run(ramp(-25, 0, 0.2), eyes=EYE0)         # back to the screen
        p.hold(0.0, 0.5, eye=EYE0)
        self.assertTrue(p.glanced)
        self.assertEqual((p.dx, p.dy), (0, 0))

    def test_steering_down_while_watching_screen_still_moves(self):
        s = settings(glance={"eye_neutral": EYE0, "eye_scale": SCALE})
        p = Player(s)
        pitches = ramp(0, -7, 0.4) + [-7.0] * 125
        p.run(pitches, eyes=[watching(x) for x in pitches])
        self.assertFalse(p.glanced)
        self.assertGreater(p.dy, 0)                 # + is down on screen

    def test_steering_up_while_watching_screen_still_moves(self):
        # Head up means eyes down relative to the head - must not look like a glance.
        s = settings(glance={"eye_neutral": EYE0, "eye_scale": SCALE})
        p = Player(s)
        pitches = ramp(0, 9, 0.4) + [9.0] * 125
        p.run(pitches, eyes=[watching(x) for x in pitches])
        self.assertFalse(p.glanced)
        self.assertLess(p.dy, 0)

    def test_blink_is_ignored(self):
        s = settings(glance={"eye_neutral": EYE0, "eye_scale": SCALE})
        p = Player(s)
        n = 125
        eyes = [watching(-6)] * n
        blinks = [0.0] * n
        for i in range(40, 60):                     # a blink reads as "eyes down"
            eyes[i], blinks[i] = -0.8, 0.9
        p.run([-6.0] * n, eyes=eyes, blinks=blinks)
        self.assertFalse(p.glanced)


class WithoutEyeDataTests(unittest.TestCase):
    """OpenTrack gives no eye data: the look-away limit and the start delay do the work."""

    def test_fast_steering_within_range_is_not_a_glance(self):
        p = Player()
        for yaw in ramp(0, 16, 0.2):                # snappy turn to full speed (80 deg/s)
            p.run([0.0], yaw=yaw)
        p.hold(0.0, 0.5, yaw=16.0)
        self.assertFalse(p.glanced)
        self.assertGreater(p.dx, 0)

    def test_quick_glance_is_ignored(self):
        p = Player()
        p.run(ramp(0, -25, 0.15))
        p.hold(-25.0, 1.0)
        p.run(ramp(-25, 0, 0.2))
        p.hold(0.0, 0.5)
        self.assertTrue(p.glanced)
        self.assertEqual((p.dx, p.dy), (0, 0))

    def test_turning_far_away_stops_and_settles_before_resuming(self):
        p = Player()
        p.hold(0.0, 0.5, yaw=12.0)
        moved = p.dx
        self.assertGreater(moved, 0)
        for yaw in ramp(12, 45, 0.15):              # quick turn to talk to someone (220 deg/s)
            p.run([0.0], yaw=yaw)
        # The camera was already turning at ~90 deg/s at 12 degrees; the guard must cut in
        # within about 0.1 s of the turn starting (at most ~12 degrees of camera turn).
        counts_per_degree = 4000 / 360
        self.assertTrue(p.glanced)
        self.assertLess(p.dx - moved, 12 * counts_per_degree)
        moved = p.dx
        p.hold(0.0, 1.0, yaw=45.0)
        self.assertEqual(p.dx, moved)
        p.hold(0.0, 0.2, yaw=10.0)                  # back, but not yet settled
        self.assertEqual(p.dx, moved)
        p.hold(0.0, 0.6, yaw=10.0)                  # steady: steering resumes
        self.assertGreater(p.dx, moved)

    def test_start_delay_only_for_down(self):
        p = Player()
        p.hold(-5.0, 0.15)                          # down: still waiting out 0.2 s
        self.assertEqual(p.dy, 0)
        p.hold(-5.0, 0.5)
        self.assertGreater(p.dy, 0)
        q = Player()
        q.hold(5.0, 0.15)                           # up: no delay by default
        self.assertLess(q.dy, 0)

    def test_guard_can_be_switched_off(self):
        s = settings(glance={"enabled": False}, down={"start_delay": 0.0})
        p = Player(s)
        p.run(ramp(0, -25, 0.15))
        p.hold(-25.0, 0.5)
        self.assertGreater(p.dy, 0)


class DefaultsTests(unittest.TestCase):
    def test_defaults_behave_exactly_like_version_1_0(self):
        # New features are opt-in: with default settings nothing pauses or delays movement.
        defaults = config.Settings()
        self.assertFalse(defaults.glance.enabled)
        self.assertEqual([getattr(defaults, d).start_delay for d in ("right", "left", "up", "down")], [0.0] * 4)
        p = Player(defaults)
        p.run(ramp(0, -25, 0.15), eyes=-0.75)
        p.hold(-25.0, 0.5, eye=-0.75)
        self.assertFalse(p.glanced)
        self.assertGreater(p.dy, 0)
        q = Player(defaults)
        q.hold(-5.0, 0.1)
        self.assertGreater(q.dy, 0)                 # no start delay

    def test_eye_processing_only_when_needed(self):
        from headmouse.engine import uses_eyes, _restart_needed
        off = config.Settings()
        on = config.from_dict({"glance": {"enabled": True}})[0]
        self.assertFalse(uses_eyes(off))
        self.assertTrue(uses_eyes(on))
        self.assertTrue(_restart_needed(off, on))


class EngineAndWebcamTests(unittest.TestCase):
    def test_engine_reports_looking_away(self):
        import time
        from headmouse.engine import HeadMouse
        from headmouse.tracking import HeadSample
        from headmouse.winput import NullInput

        class Source:
            pitch, eye, seq = 0.0, EYE0, 0

            def latest(self):
                self.seq += 1
                v = (0, 0, 0, 0.0, self.pitch, self.seq * 1e-6)
                return HeadSample(0.0, self.pitch, v, time.perf_counter(), self.seq, eye_pitch=self.eye)
        src, backend = Source(), NullInput()
        s = settings(general={"start_enabled": True, "game_window_title": ""},
                     glance={"eye_neutral": EYE0, "eye_scale": SCALE})
        app = HeadMouse(s, src, backend)
        t = 0.0
        for _ in range(30):
            app.tick(t)
            t += DT
        self.assertEqual(app.state, "ACTIVE")
        src.pitch, src.eye = -20.0, -0.7
        for _ in range(30):
            app.tick(t)
            t += DT
        self.assertEqual(app.state, "LOOKING AWAY")
        self.assertEqual(backend.sent, [])

    def test_eye_signals_from_blendshapes(self):
        from types import SimpleNamespace as C
        from headmouse.webcam import eye_signals
        shapes = [C(category_name="eyeLookUpLeft", score=0.1), C(category_name="eyeLookUpRight", score=0.3),
                  C(category_name="eyeLookDownLeft", score=0.6), C(category_name="eyeLookDownRight", score=0.4),
                  C(category_name="eyeBlinkLeft", score=0.2), C(category_name="eyeBlinkRight", score=0.4),
                  C(category_name="jawOpen", score=0.9)]
        eye, blink = eye_signals(shapes)
        self.assertAlmostEqual(eye, 0.2 - 0.5)
        self.assertAlmostEqual(blink, 0.3)


if __name__ == "__main__":
    unittest.main()
