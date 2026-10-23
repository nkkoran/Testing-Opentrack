"""Tests for creating the HeadMouse OpenTrack profile."""

import configparser
import tempfile
import unittest
from pathlib import Path

from headmouse.opentrack_setup import PROFILE_NAME, list_profiles, make_headmouse_profile, patch_profile_text

SAMPLE = (
    "[modules]\r\nfilter-dll=accela\r\nprotocol-dll=mouse\r\ntracker-dll=neuralnet\r\n\r\n"
    "[opentrack-mappings]\r\npitch-max-output-value=90\r\npitch-max-value=30\r\nyaw-alt-axis-sign=true\r\n"
    "yaw-max-output-value=180\r\nyaw-max-value=25\r\nx-max-value=30\r\n\r\n"
    "[spline-yaw]\r\npoints=@Variant(\\0\\0\\0\\x7f\\0\\0\\0\\x10)\r\n\r\n"
    "[spline-roll]\r\npoints=@Variant(\\0\\0\\0\\x7f\\0\\0\\0\\x11)\r\n\r\n"
    "[neuralnet-tracker]\r\ncamera-name=Logitech HD Webcam C270\r\n"
)


def parse(text):
    cp = configparser.ConfigParser(interpolation=None)
    cp.optionxform = str
    cp.read_string(text)
    return cp


class ProfileTests(unittest.TestCase):
    def test_patch(self):
        out = patch_profile_text(SAMPLE)
        cp = parse(out)
        self.assertEqual(cp["modules"]["protocol-dll"], "udp")
        self.assertEqual(cp["modules"]["tracker-dll"], "neuralnet")            # kept
        self.assertEqual(cp["neuralnet-tracker"]["camera-name"], "Logitech HD Webcam C270")
        self.assertEqual(dict(cp["udp-proto"]), {"ip1": "127", "ip2": "0", "ip3": "0", "ip4": "1",
                                                 "port": "4242"})
        self.assertNotIn("points", cp["spline-yaw"])                           # yaw -> 1:1
        self.assertIn("points", cp["spline-roll"])                             # roll untouched
        self.assertEqual(dict(cp["opentrack-mappings"]), {"x-max-value": "30"})
        self.assertIn("\r\n", out)

    def test_profile_file_backup_and_original_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            (folder / "default.ini").write_text(SAMPLE, newline="")
            dest, backup = make_headmouse_profile(folder, "default.ini")
            self.assertIsNone(backup)
            self.assertEqual((folder / "default.ini").read_text(newline=""), SAMPLE)
            dest, backup = make_headmouse_profile(folder, "default.ini", port=5000)
            self.assertTrue(backup.exists())
            self.assertEqual(parse(dest.read_text())["udp-proto"]["port"], "5000")
            self.assertIn(PROFILE_NAME, list_profiles(folder))

    def test_empty_source(self):
        cp = parse(patch_profile_text(""))
        self.assertEqual(cp["modules"]["protocol-dll"], "udp")


if __name__ == "__main__":
    unittest.main()
