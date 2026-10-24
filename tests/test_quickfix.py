"""Quick fixes: plain-language problems turned into small, valid setting changes."""

import tempfile
import unittest
from pathlib import Path

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


class SituationFeelTests(unittest.TestCase):
    def setUp(self):
        self.path = Path(tempfile.mkdtemp()) / "headmouse_settings.toml"

    def test_fixing_the_aiming_feel_changes_its_preset_only(self):
        aim = settings(assist={"hybrid": True, "hybrid_gain_x": 1.0})
        config.save_preset(self.path, "Aiming", aim)
        base = settings(situations={"aim_preset": "Aiming"}, assist={"hybrid_gain_x": 3.0})
        feel, preset = quickfix.target_feel(self.path, base, "aim")
        self.assertEqual((preset, feel.assist.hybrid_gain_x), ("Aiming", 1.0))
        fixed, lines = quickfix.apply(feel, "x", "jumpy")
        new_base = quickfix.store(self.path, base, "aim", preset, fixed)
        self.assertEqual(new_base.assist.hybrid_gain_x, 3.0)                       # normal feel untouched
        self.assertEqual(config.load_preset(self.path, "Aiming", new_base).assist.hybrid_gain_x, 0.8)

    def test_helpers_still_go_to_the_normal_settings(self):
        config.save_preset(self.path, "Aiming", settings(assist={"hybrid": True}))
        base = settings(situations={"aim_preset": "Aiming"})
        feel, preset = quickfix.target_feel(self.path, base, "aim")
        fixed, _ = quickfix.apply(feel, "x", "drifts")                          # switches on return_stop
        new_base = quickfix.store(self.path, base, "aim", preset, fixed)
        self.assertTrue(new_base.assist.return_stop)
        self.assertFalse(new_base.assist.hybrid)                                   # the preset's mode stays there

    def test_built_in_preset_gets_an_adjusted_copy(self):
        base = settings(situations={"aim_preset": config.DEFAULT_PRESET})
        feel, preset = quickfix.target_feel(self.path, base, "aim")
        fixed, _ = quickfix.apply(feel, "x", "too_fast")
        new_base = quickfix.store(self.path, base, "aim", preset, fixed)
        self.assertEqual(new_base.situations.aim_preset, "Aiming (adjusted)")
        self.assertLess(config.load_preset(self.path, "Aiming (adjusted)", new_base).right.max_speed,
                        base.right.max_speed)

    def test_normal_feel_is_unchanged_behaviour(self):
        base = settings()
        feel, preset = quickfix.target_feel(self.path, base, None)
        self.assertIs(feel, base)
        fixed, _ = quickfix.apply(feel, "x", "too_fast")
        self.assertIs(quickfix.store(self.path, base, None, None, fixed), fixed)


if __name__ == "__main__":
    unittest.main()
