"""Named settings presets."""

import dataclasses
import tempfile
import unittest
from pathlib import Path

from headmouse import config


class PresetTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "headmouse_settings.toml"

    def tearDown(self):
        self.dir.cleanup()

    def tuned(self):
        s = config.Settings()
        s = dataclasses.replace(s, right=dataclasses.replace(s.right, max_speed=240.0, deadzone=4.5),
                                down=dataclasses.replace(s.down, points=[[2.0, 0.0], [10.0, 60.0]]),
                                motion=dataclasses.replace(s.motion, precision_speed_factor=0.35))
        return s

    def test_save_and_load_round_trip(self):
        config.save_preset(self.path, "Dad's evening", self.tuned())
        self.assertIn("Dads evening", config.list_presets(self.path))
        loaded = config.load_preset(self.path, "Dads evening", config.Settings())
        self.assertEqual(config.preset_values(loaded), config.preset_values(self.tuned()))

    def test_preset_leaves_other_settings_alone(self):
        config.save_preset(self.path, "Mine", self.tuned())
        base = config.Settings()
        base = dataclasses.replace(base, keys=dataclasses.replace(base.keys, pause_hold="F4"),
                                   glance=dataclasses.replace(base.glance, enabled=True))
        loaded = config.load_preset(self.path, "Mine", base)
        self.assertEqual(loaded.keys.pause_hold, "F4")
        self.assertTrue(loaded.glance.enabled)
        self.assertEqual(loaded.right.max_speed, 240.0)

    def test_builtins_are_valid_and_protected(self):
        names = config.list_presets(self.path)
        self.assertEqual(names[0], config.DEFAULT_PRESET)
        for name in names:
            config.validate(config.load_preset(self.path, name, config.Settings()))
        with self.assertRaises(config.SettingsError):
            config.save_preset(self.path, config.DEFAULT_PRESET, self.tuned())
        with self.assertRaises(config.SettingsError):
            config.delete_preset(self.path, config.DEFAULT_PRESET)
        gentle = config.load_preset(self.path, names[1], config.Settings())
        self.assertLess(gentle.right.max_speed, config.Settings().right.max_speed)

    def test_matching_and_delete(self):
        self.assertEqual(config.matching_preset(self.path, config.Settings()), config.DEFAULT_PRESET)
        config.save_preset(self.path, "Mine", self.tuned())
        self.assertEqual(config.matching_preset(self.path, self.tuned()), "Mine")
        config.delete_preset(self.path, "Mine")
        self.assertNotIn("Mine", config.list_presets(self.path))
        self.assertIsNone(config.matching_preset(self.path, self.tuned()))

    def test_bad_names_and_files(self):
        with self.assertRaises(config.SettingsError):
            config.save_preset(self.path, "///", self.tuned())
        config.preset_folder(self.path).mkdir()
        (config.preset_folder(self.path) / "Broken.toml").write_text("[right]\nmax_speed = -5\n", encoding="utf-8")
        with self.assertRaises(config.SettingsError):
            config.load_preset(self.path, "Broken", config.Settings())
        self.assertEqual(config.matching_preset(self.path, config.Settings()), config.DEFAULT_PRESET)


if __name__ == "__main__":
    unittest.main()
