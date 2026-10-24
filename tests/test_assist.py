"""Optional control helpers: stop when back in the middle, auto-center, vertical follow, linking."""

import unittest

from headmouse import calibration, config, tuning
from headmouse.controller import MotionController
from headmouse.engine import HeadMouse
from headmouse.winput import NullInput
from tests.test_core import DT, FakeSource, settings
from tests.test_tuning import simulate_round


def run(ctl, seconds, yaw=0.0, pitch=0.0, **kw):
    """Hold the head at (yaw, pitch); returns total camera degrees turned (yaw, pitch)."""
    turned = [0.0, 0.0]
    for _ in range(round(seconds / DT)):
        r = ctl.step((yaw, pitch), DT, **kw)
        turned[0] += r.yaw_speed * DT
        turned[1] += r.pitch_speed * DT
    return turned


def glide(ctl, start, end, seconds, axis=0):
    """Move the head smoothly from start to end on one axis; returns camera degrees turned."""
    n = round(seconds / DT)
    turned = 0.0
    for i in range(1, n + 1):
        a = start + (end - start) * i / n
        r = ctl.step((a, 0.0) if axis == 0 else (0.0, a), DT)
        turned += (r.yaw_speed if axis == 0 else r.pitch_speed) * DT
    return turned


class ReturnStopTests(unittest.TestCase):
    def ctl(self, on):
        return MotionController(settings(assist={"return_stop": on}, motion={"smoothing_seconds": 0}))

    def test_off_by_default(self):
        self.assertFalse(config.Settings().assist.return_stop)

    def test_overshoot_past_center_stays_still(self):
        for on, expect_move in ((False, True), (True, False)):
            ctl = self.ctl(on)
            run(ctl, 1.0, yaw=-12)                       # turning left
            glide(ctl, -12, 4.5, 0.3)                    # back past center, ending a bit right
            turned = run(ctl, 1.5, yaw=4.5)
            self.assertEqual(turned[0] > 1.0, expect_move, (on, turned))

    def test_creeping_off_center_after_a_turn_stays_still(self):
        for on, expect_move in ((False, True), (True, False)):
            ctl = self.ctl(on)
            run(ctl, 1.0, yaw=-12)
            glide(ctl, -12, -2, 0.3)                     # rests just inside the dead zone
            run(ctl, 0.5, yaw=-2)
            turned = glide(ctl, -2, -4, 2.0) + run(ctl, 1.0, yaw=-4)[0]   # slowly creeps out
            self.assertEqual(turned < -1.0, expect_move, (on, turned))

    def test_a_clear_new_turn_moves_again(self):
        ctl = self.ctl(True)
        run(ctl, 1.0, yaw=-12)
        glide(ctl, -12, -1, 0.3)
        run(ctl, 0.5, yaw=-1)
        self.assertLess(run(ctl, 0.5, yaw=-8)[0], -1.0)        # left again
        glide(ctl, -8, 0, 0.3)
        run(ctl, 0.5)
        self.assertGreater(run(ctl, 0.5, yaw=8)[0], 1.0)       # and right

    def test_first_turn_from_rest_is_unchanged(self):
        on, off = self.ctl(True), self.ctl(False)
        self.assertEqual(run(on, 1.0, yaw=4.0), run(off, 1.0, yaw=4.0))

    def test_works_vertically(self):
        ctl = self.ctl(True)
        run(ctl, 1.0, pitch=8)
        glide(ctl, 8, -3.5, 0.3, axis=1)                       # overshoot below center
        self.assertEqual(run(ctl, 1.0, pitch=-3.5)[1], 0.0)


class AutoCenterTests(unittest.TestCase):
    def ctl(self, **assist):
        return MotionController(settings(assist={"auto_center": True, **assist},
                                         motion={"smoothing_seconds": 0}))

    def test_learns_resting_position(self):
        ctl = self.ctl()
        run(ctl, 30, yaw=2.0, pitch=-1.0)
        self.assertAlmostEqual(ctl.drift[0], 2.0, delta=0.1)
        self.assertAlmostEqual(ctl.drift[1], -1.0, delta=0.1)
        r = ctl.step((2.0, -1.0), DT)
        self.assertAlmostEqual(r.yaw, 0.0, delta=0.1)

    def test_off_learns_nothing(self):
        ctl = MotionController(settings())
        run(ctl, 30, yaw=2.0)
        self.assertEqual(ctl.drift, [0.0, 0.0])

    def test_not_while_turning_and_capped(self):
        ctl = self.ctl()
        run(ctl, 10, yaw=10.0)
        self.assertEqual(ctl.drift[0], 0.0)
        ctl = self.ctl(auto_center_limit=1.0)
        run(ctl, 30, yaw=2.5)
        self.assertAlmostEqual(ctl.drift[0], 1.0)

    def test_engine_keeps_it_across_settings_changes_and_recenter_resets(self):
        s = settings(general={"start_enabled": True}, assist={"auto_center": True})
        src, backend = FakeSource(), NullInput()
        app = HeadMouse(s, src, backend)
        t = 0.0
        for _ in range(round(20 / DT)):
            src.set(2.0, 0.0, t)
            app.tick(t)
            t += DT
        self.assertGreater(app.controller.drift[0], 1.5)
        app.apply_settings(s)
        self.assertGreater(app.controller.drift[0], 1.5)
        app.recenter()
        self.assertEqual(app.controller.drift, [0.0, 0.0])


class VerticalFollowTests(unittest.TestCase):
    def ctl(self, gain=4.0):
        return MotionController(settings(assist={"vertical_follow": True, "vertical_follow_gain": gain},
                                         motion={"smoothing_seconds": 0}))

    def test_camera_follows_head_tilt(self):
        ctl = self.ctl()
        up = glide(ctl, 0, 3, 0.5, axis=1)
        self.assertAlmostEqual(up, (3 - 0.25) * 4, delta=0.2)
        self.assertEqual(run(ctl, 1.0, pitch=3)[1], 0.0)      # stays where you leave it
        down = glide(ctl, 3, 0, 0.5, axis=1)
        self.assertAlmostEqual(up + down, 0.25 * 4, delta=0.3)       # back where it started, give or take the jitter filter

    def test_up_moves_the_mouse_up(self):
        ctl = self.ctl()
        dy = sum(ctl.step((0.0, p / 10), DT).dy for p in range(0, 31))
        self.assertLess(dy, 0)                                # screen y grows downward

    def test_jitter_is_ignored(self):
        ctl = self.ctl()
        turned = 0.0
        for i in range(500):
            turned += abs(ctl.step((0.0, 0.2 if i % 2 else -0.2), DT).pitch_speed) * DT
        self.assertLess(turned, 1.0)

    def test_pause_lets_you_reposition_without_moving(self):
        ctl = self.ctl()
        glide(ctl, 0, 3, 0.3, axis=1)
        for i in range(60):                                   # head back down while paused
            ctl.step((0.0, 3 - i / 20), DT, hold=True)
        self.assertEqual(run(ctl, 0.5, pitch=0.0)[1], 0.0)    # no jump on release

    def test_left_right_still_joystick(self):
        ctl = self.ctl()
        self.assertGreater(run(ctl, 1.0, yaw=12)[0], 50)


class LinkTests(unittest.TestCase):
    def test_practice_tuning_keeps_linked_sides_equal(self):
        fast = {n: {"min_speed": 30.0, "curve": 1.0, "max_speed": 360.0} for n in ("right", "left")}
        s = settings(general={"link_left_right": True}, **fast)
        new, notes = tuning.propose(s, simulate_round(s, tuning.make_targets(seed=1)))
        self.assertIn("right", notes)
        self.assertEqual(new.right, new.left)
        self.assertNotEqual(new.right, s.right)

    def test_practice_leaves_vertical_follow_alone(self):
        s = settings(assist={"vertical_follow": True})
        new, notes = tuning.propose(s, simulate_round(s, tuning.make_targets(seed=1)))
        self.assertEqual((new.up, new.down), (s.up, s.down))

    def test_wizard_keeps_linked_sides_equal(self):
        s = settings(general={"link_left_right": True})
        neutral = calibration.Neutral(0, 0, 0.1, 0.1)
        moves = {"right": calibration.Movement(30, 1), "left": calibration.Movement(20, -1),
                 "up": calibration.Movement(15, 1), "down": calibration.Movement(10, -1)}
        new = calibration.propose(s, "webcam", neutral, moves)[0]
        self.assertEqual(new.right.full_speed_angle, new.left.full_speed_angle)
        self.assertNotEqual(new.up.full_speed_angle, new.down.full_speed_angle)


if __name__ == "__main__":
    unittest.main()
