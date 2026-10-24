"""Quick fixes: plain-language problems turned into small, valid setting changes."""

import unittest

from headmouse import config, quickfix
from tests.test_core import settings

MODES = {"joystick": {}, "hybrid": {"hybrid": True}, "follow": {"vertical_follow": True}}


class QuickFixTests(unittest.TestCase):
    def test_every_fix_stays_valid_and_runs_out_at_limits(self):
        for mode, assist in MODES.items():
            for axis in ("x", "y"):
                if mode == "follow" and axis == "x":
                    continue
                for fix in quickfix.available(settings(assist=assist), axis):
                    s = settings(assist=assist)
                    for _ in range(60):                      # pressing it again and again
                        s, lines = quickfix.apply(s, axis, fix.key)
                        config.validate(s)
                        if not lines:
                            break
                    else:
                        self.fail(f"{fix.key} on {mode}/{axis} never reaches a limit")

    def test_only_fixes_that_fit_the_mode(self):
        keys = lambda s, axis: {f.key for f in quickfix.available(s, axis)}
        self.assertNotIn("drifts", keys(settings(assist=MODES["follow"]), "y"))
        self.assertNotIn("glance", keys(settings(), "x"))
        self.assertIn("glance", keys(settings(), "y"))

    def test_changes_only_the_chosen_pair(self):
        s = settings(assist={"hybrid": True})
        new, lines = quickfix.apply(s, "x", "jumpy")
        self.assertLess(new.assist.hybrid_gain_x, s.assist.hybrid_gain_x)
        self.assertEqual(new.assist.hybrid_gain_y, s.assist.hybrid_gain_y)
        self.assertEqual(new.assist.slow_precision_x, 0.6)
        self.assertEqual(new.assist.slow_precision_y, 1.0)
        self.assertTrue(any("Left/right sensitivity 3 → 2.4x" in line for line in lines), lines)
        new, _ = quickfix.apply(s, "y", "too_slow")
        self.assertGreater(new.up.max_speed, s.up.max_speed)
        self.assertEqual(new.right, s.right)

    def test_drifts_switches_on_the_return_stop_first(self):
        s, lines = quickfix.apply(settings(), "x", "drifts")
        self.assertTrue(s.assist.return_stop)
        self.assertEqual(lines, ["Stop when I come back to the middle: on"])
        s2, lines = quickfix.apply(s, "x", "drifts")
        self.assertGreater(s2.right.deadzone, s.right.deadzone)

    def test_glance_turns_on_glance_pause_first(self):
        s, lines = quickfix.apply(settings(), "y", "glance")
        self.assertTrue(s.glance.enabled and s.glance.eye_check)
        s2, _ = quickfix.apply(s, "y", "glance")
        self.assertGreater(s2.down.start_delay, s.down.start_delay)

    def test_steadiness_only_with_the_webcam(self):
        s = settings(tracking={"source": "opentrack"}, assist={"hybrid": True})
        new, lines = quickfix.apply(s, "x", "shaky")
        self.assertEqual(new.webcam, s.webcam)
        self.assertGreater(new.assist.wobble_x, s.assist.wobble_x)


if __name__ == "__main__":
    unittest.main()
