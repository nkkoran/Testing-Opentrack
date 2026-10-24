"""Getting started list."""

import unittest

from headmouse import guide
from tests.test_core import settings


class GuideTests(unittest.TestCase):
    def test_fresh_and_finished(self):
        fresh = settings()
        self.assertEqual(guide.progress(fresh), (0, 4))
        self.assertEqual(guide.next_step(fresh).key, "wizard")
        done = settings(general={"setup_done": True, "checkup_done": True}, mouse={"counts_per_360": 3600.0},
                        assist={"hybrid": True})
        self.assertEqual(guide.progress(done), (4, 4))
        self.assertIsNone(guide.next_step(done))
        optional = [s for s in guide.steps(done) if s.optional]
        self.assertTrue(optional and not any(s.done for s in optional))

    def test_optional_steps_tick(self):
        s = settings(situations={"aim_preset": "Aiming"}, actions={"enabled": True}, glance={"enabled": True})
        self.assertTrue(all(st.done for st in guide.steps(s) if st.optional))


if __name__ == "__main__":
    unittest.main()
