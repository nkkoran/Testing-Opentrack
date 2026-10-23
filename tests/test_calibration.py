"""Tests for the setup-wizard maths."""

import random
import unittest

from headmouse import config
from headmouse.calibration import measure_movement, measure_neutral, propose


def samples(center, spread, n=60, seed=0):
    rnd = random.Random(seed)
    return [(center[0] + rnd.uniform(-spread, spread), center[1] + rnd.uniform(-spread, spread))
            for _ in range(n)]


def hold(target, n=60):
    """Ramp from center to the target, then hold - like a real turn."""
    ramp = [(target[0] * i / 20, target[1] * i / 20) for i in range(20)]
    return ramp + [target] * (n - 20)


class CalibrationTests(unittest.TestCase):
    def run_wizard(self, settings, kind, offset, right, left, up, down, noise=0.1):
        neutral = measure_neutral(samples(offset, noise))
        shift = lambda p: (p[0] + offset[0], p[1] + offset[1])
        moves = {name: measure_movement([shift(p) for p in hold(t)], neutral, axis)
                 for name, t, axis in (("right", right, 0), ("left", left, 0),
                                       ("up", up, 1), ("down", down, 1))}
        return propose(settings, kind, neutral, moves)

    def test_reproduces_original_defaults_for_matching_ranges(self):
        s = config.Settings()
        new, report, problems, _ = self.run_wizard(s, "webcam", (0, 0), (20, 0), (-20, 0), (0, 13.4), (0, -13.4))
        self.assertEqual(problems, [])
        self.assertAlmostEqual(new.right.full_speed_angle, 15.0, delta=0.2)
        self.assertAlmostEqual(new.right.deadzone, 3.0, delta=0.1)
        self.assertAlmostEqual(new.up.full_speed_angle, 10.0, delta=0.2)
        self.assertAlmostEqual(new.up.deadzone, 2.0, delta=0.1)
        self.assertEqual(new.right.max_speed, s.right.max_speed)    # speeds untouched

    def test_asymmetric_down_gets_its_own_settings(self):
        s = config.Settings()
        new, *_ = self.run_wizard(s, "webcam", (0, 0), (20, 0), (-20, 0), (0, 14), (0, -6))
        self.assertLess(new.down.full_speed_angle, new.up.full_speed_angle)
        self.assertLess(new.down.deadzone, new.up.deadzone)

    def test_neutral_saved_for_webcam(self):
        s = config.Settings()
        new, _, _, offset = self.run_wizard(s, "webcam", (4.0, -9.0), (20, 0), (-20, 0), (0, 12), (0, -12))
        self.assertAlmostEqual(new.webcam.neutral_yaw, 4.0, delta=0.2)
        self.assertAlmostEqual(new.webcam.neutral_pitch, -9.0, delta=0.2)
        self.assertEqual(new.opentrack, s.opentrack)

    def test_reversed_directions_are_fixed(self):
        s = config.Settings()
        # Tracker reports right as negative and up as negative.
        new, report, problems, offset = self.run_wizard(
            s, "opentrack", (2.0, 3.0), (-20, 0), (20, 0), (0, -12), (0, 12))
        self.assertEqual(problems, [])
        self.assertFalse(new.opentrack.yaw_right_is_positive)
        self.assertFalse(new.opentrack.pitch_up_is_positive)
        self.assertAlmostEqual(offset[0], -2.0, delta=0.2)    # neutral flipped with the axis
        self.assertAlmostEqual(new.right.full_speed_angle, 15.0, delta=0.2)

    def test_missing_movement_is_reported_and_left_alone(self):
        s = config.Settings()
        new, _, problems, _ = self.run_wizard(s, "webcam", (0, 0), (20, 0), (-20, 0), (0, 12), (0, -1))
        self.assertEqual(new.down, s.down)
        self.assertTrue(any("down" in p for p in problems))

    def test_noise_widens_deadzone(self):
        s = config.Settings()
        new, _, problems, _ = self.run_wizard(s, "webcam", (0, 0), (20, 0), (-20, 0), (0, 12), (0, -12),
                                              noise=2.0)
        self.assertGreater(new.right.deadzone, 3.0)
        self.assertTrue(any("jittery" in p for p in problems))

    def test_result_is_valid_settings(self):
        s = config.Settings()
        new, *_ = self.run_wizard(s, "webcam", (0, 0), (6, 0), (-50, 0), (0, 3.5), (0, -30))
        config.validate(new)


if __name__ == "__main__":
    unittest.main()
