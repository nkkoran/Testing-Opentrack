"""Settings files written by older versions keep working, and new settings can be saved into them."""

import shutil
import tempfile
import unittest
from pathlib import Path

from headmouse import config

FIXTURE = Path(__file__).parent / "fixtures" / "settings_v1_0_0.toml"


class OldFileTests(unittest.TestCase):
    def test_v1_0_file_loads_without_warnings(self):
        s, warnings = config.load(FIXTURE)
        self.assertEqual(warnings, [])
        self.assertEqual(config.axis_modes(s), ("joystick", "joystick"))
        self.assertFalse(s.actions.enabled or s.situations.aim_preset)

    def test_new_settings_can_be_saved_into_it(self):
        path = Path(tempfile.mkdtemp()) / "headmouse_settings.toml"
        shutil.copy(FIXTURE, path)
        config.save_values(path, {"assist": {"hybrid": True, "slow_precision_x": 0.5},
                                  "situations": {"aim_preset": "Aiming", "aim_key": "RIGHTMOUSE"},
                                  "actions": {"enabled": True, "mouth_action": "right"},
                                  "webcam": {"smoothing_min_cutoff": 2.0}})
        s, warnings = config.load(path)
        self.assertEqual(warnings, [])
        self.assertEqual(config.axis_modes(s), ("hybrid", "hybrid"))
        self.assertEqual((s.situations.aim_key, s.actions.mouth_action), ("RIGHTMOUSE", "right"))
        self.assertEqual(s.webcam.vertical_smoothing_min_cutoff, 1.0)    # written down before the change
        self.assertIn("# ", path.read_text(encoding="utf-8"))           # comments kept


class SaveRobustnessTests(unittest.TestCase):
    def setUp(self):
        self.path = Path(tempfile.mkdtemp()) / "headmouse_settings.toml"

    def test_a_multi_line_array_is_replaced_whole(self):
        self.path.write_text("[right]\npoints = [\n  [3, 0],\n  [15, 180],\n]\ndeadzone = 3.0\n", encoding="utf-8")
        config.save_values(self.path, {"right": {"points": []}})
        s = config.load(self.path)[0]
        self.assertEqual((s.right.points, s.right.deadzone), ([], 3.0))

    def test_a_broken_file_gives_a_settings_error(self):
        self.path.write_text("[right]\ndeadzone = 3.0\nthis is not toml\n", encoding="utf-8")
        with self.assertRaises(config.SettingsError):
            config.save_values(self.path, {"right": {"deadzone": 4.0}})

    def test_inherited_key_missing_together_with_its_source(self):
        self.path.write_text("[assist]\nhybrid = true\n", encoding="utf-8")   # neither blend key
        config.save_values(self.path, {"assist": {"hybrid_blend": 5.0}})
        s = config.load(self.path)[0]
        self.assertEqual((s.assist.hybrid_blend, s.assist.hybrid_blend_y), (5.0, 2.0))


if __name__ == "__main__":
    unittest.main()
