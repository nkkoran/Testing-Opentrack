"""Settings backups and restore."""

import shutil
import tempfile
import unittest
from pathlib import Path

from headmouse import config

ROOT = Path(__file__).resolve().parent.parent


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "headmouse_settings.toml"
        shutil.copy(ROOT / "headmouse_settings.toml", self.path)

    def tearDown(self):
        self.dir.cleanup()

    def test_every_save_keeps_the_previous_file(self):
        config.save_values(self.path, {"right": {"deadzone": 4.0}})
        config.save_values(self.path, {"right": {"deadzone": 5.0}})
        backups = config.list_backups(self.path)
        self.assertEqual(len(backups), 2)
        self.assertEqual(config.load(backups[0])[0].right.deadzone, 4.0)   # newest first
        self.assertEqual(config.load(backups[1])[0].right.deadzone, 3.0)

    def test_restore_brings_back_old_values_and_is_itself_undoable(self):
        config.save_values(self.path, {"left": {"max_speed": 100.0}})
        before_change = config.list_backups(self.path)[0]
        config.restore_backup(self.path, before_change)
        self.assertEqual(config.load(self.path)[0].left.max_speed, 180.0)
        self.assertEqual(config.load(config.list_backups(self.path)[0])[0].left.max_speed, 100.0)

    def test_no_backup_when_nothing_changes(self):
        config.save_values(self.path, {"right": {"deadzone": 3.0}})
        self.assertEqual(config.list_backups(self.path), [])

    def test_old_backups_are_pruned(self):
        for i in range(config.BACKUPS_KEPT + 5):
            config.save_values(self.path, {"right": {"max_speed": 100.0 + i}})
        self.assertEqual(len(config.list_backups(self.path)), config.BACKUPS_KEPT)

    def test_invalid_backup_is_refused(self):
        bad = Path(self.dir.name) / "bad.toml"
        bad.write_text("[right]\ndeadzone = 99.0\n")
        with self.assertRaises(config.SettingsError):
            config.restore_backup(self.path, bad)

    def test_finds_settings_from_an_earlier_source_install(self):
        import os
        from unittest import mock
        old = Path(self.dir.name) / "HeadMouse"
        old.mkdir()
        (old / "headmouse_settings.toml").write_text("[right]\ndeadzone = 4.5\n")
        with mock.patch.dict(os.environ, {"LOCALAPPDATA": self.dir.name}):
            self.assertEqual(config.earlier_install_settings(), old / "headmouse_settings.toml")
        with mock.patch.dict(os.environ, {"LOCALAPPDATA": str(Path(self.dir.name) / "none")}):
            self.assertIsNone(config.earlier_install_settings())


if __name__ == "__main__":
    unittest.main()
