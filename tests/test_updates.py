"""Tests for the update check (no network)."""

import io
import json
import unittest

from headmouse import updates


def fake_opener(payload=None, error=None):
    def opener(request, timeout):
        if error:
            raise error
        return io.BytesIO(json.dumps(payload).encode())
    return opener


class UpdateTests(unittest.TestCase):
    def test_versions(self):
        self.assertEqual(updates.parse_version("v1.2.3"), (1, 2, 3))
        self.assertIsNone(updates.parse_version("latest"))
        self.assertTrue(updates.is_newer("v1.0.10", "1.0.9"))
        self.assertFalse(updates.is_newer("v1.0.0", "1.0.0"))
        self.assertFalse(updates.is_newer("nonsense", "1.0.0"))

    def test_latest_release(self):
        payload = {"tag_name": "v9.0.0", "assets": [
            {"name": "notes.txt", "browser_download_url": "x"},
            {"name": "HeadMouse-Setup.exe", "browser_download_url": "https://example/HeadMouse-Setup.exe"}]}
        self.assertEqual(updates.latest_release(opener=fake_opener(payload)),
                         ("9.0.0", "https://example/HeadMouse-Setup.exe"))
        self.assertEqual(updates.available_update(opener=fake_opener(payload))[0], "9.0.0")

    def test_no_update_when_offline_or_missing(self):
        self.assertIsNone(updates.latest_release(opener=fake_opener(error=OSError("offline"))))
        self.assertIsNone(updates.latest_release(opener=fake_opener({"tag_name": "v9.0.0", "assets": []})))
        old = {"tag_name": "v0.1.0", "assets": [{"name": "HeadMouse-Setup.exe", "browser_download_url": "u"}]}
        self.assertIsNone(updates.available_update(opener=fake_opener(old)))


if __name__ == "__main__":
    unittest.main()
