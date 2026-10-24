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


if __name__ == "__main__":
    unittest.main()
