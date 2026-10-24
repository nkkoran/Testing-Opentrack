"""Optional control helpers: stop when back in the middle, auto-center, vertical follow, hybrid, linking."""

import math
import random
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


class HybridTests(unittest.TestCase):
    """Mouse-like inside the dead zone (3 deg left/right, 2 deg up/down by default), joystick beyond."""

    def ctl(self, **assist):
        return MotionController(settings(assist={"hybrid": True, **assist}, motion={"smoothing_seconds": 0}))

    def test_off_by_default(self):
        self.assertFalse(config.Settings().assist.hybrid)

    def test_small_moves_follow_like_a_mouse(self):
        ctl = self.ctl(hybrid_gain_x=3.0, hybrid_gain_y=5.0)
        self.assertAlmostEqual(glide(ctl, 0, 2, 0.5), (2 - 0.25) * 3, delta=0.1)
        self.assertEqual(run(ctl, 2.0, yaw=2)[0], 0.0)                  # stays where you leave it
        self.assertAlmostEqual(glide(ctl, 2, -1, 0.5), -(3 - 0.5) * 3, delta=0.1)  # and back the other way
        self.assertAlmostEqual(glide(ctl, 0, 1.5, 0.5, axis=1), (1.5 - 0.25) * 5, delta=0.1)
        self.assertEqual(run(ctl, 2.0, pitch=1.5)[1], 0.0)

    def test_jitter_is_ignored(self):
        ctl = self.ctl()
        turned = sum(abs(ctl.step((0.2 if i % 2 else -0.2, 0.0), DT).yaw_speed) * DT for i in range(500))
        self.assertLess(turned, 1.0)

    def test_far_turns_are_the_joystick_as_before(self):
        on, off = self.ctl(hybrid_blend=0.0), MotionController(settings(motion={"smoothing_seconds": 0}))
        run(on, 0.5)
        run(off, 0.5)
        far_on, far_off = run(on, 1.0, yaw=12), run(off, 1.0, yaw=12)
        self.assertGreater(far_off[0], 50)
        self.assertAlmostEqual(far_on[0], far_off[0] + 3 * 3.0, delta=0.01)   # + following through the dead zone

    def test_blend_fades_from_mouse_to_joystick(self):
        sharp, smooth = self.ctl(hybrid_blend=0.0), self.ctl(hybrid_blend=4.0)
        # following stops at the dead zone (sharp) or fades over the blend band (smooth)
        self.assertAlmostEqual(sharp.yaw_axis.follow_position(10), 3.0)
        self.assertAlmostEqual(smooth.yaw_axis.follow_position(10), 3.0 + 2.0)
        self.assertAlmostEqual(smooth.yaw_axis.weight(5.0), 0.5)
        # just past the dead zone the joystick starts gently in the blend band
        self.assertLess(run(smooth, 1.0, yaw=4.0)[0], run(sharp, 1.0, yaw=4.0)[0] * 0.5)

    def test_coming_back_from_a_turn_does_not_swing_back(self):
        plain = MotionController(settings(motion={"smoothing_seconds": 0}))
        glide(plain, 0, 15, 0.3)
        run(plain, 1.0, yaw=15)
        slowing = glide(plain, 15, 0, 0.4)                           # the joystick winding down
        for blend in (0.0, 2.0):
            ctl = self.ctl(hybrid_blend=blend, hybrid_gain_x=4.0)
            glide(ctl, 0, 15, 0.3)
            run(ctl, 1.0, yaw=15)                                    # turning right
            back = glide(ctl, 15, 0, 0.4) + run(ctl, 1.0)[0]         # head back to the middle
            self.assertGreaterEqual(back, 0.0, blend)                # never turns back left
            self.assertLessEqual(back, slowing + 0.01, blend)        # and stops like the joystick does
            self.assertLess(glide(ctl, 0, -2, 0.5), -5.0, blend)     # then small moves follow again

    def test_small_moves_follow_again_with_real_tracking_noise(self):
        """Webcam-like input: new samples at 30 Hz with jitter, default smoothing, 125 Hz ticks."""
        ctl = MotionController(settings(assist={"hybrid": True}))
        rng = random.Random(4)
        head, sample, t = 0.0, 0.0, 0.0

        def tick(target, seconds, speed=60.0):
            nonlocal head, sample, t
            turned = 0.0
            for _ in range(round(seconds / DT)):
                head += max(-speed * DT, min(speed * DT, target - head))
                if int((t + DT) * 30) != int(t * 30):          # a new camera frame
                    sample = head + rng.uniform(-0.15, 0.15)
                t += DT
                turned += ctl.step((sample, 0.0), DT).yaw_speed * DT
            return turned
        tick(0, 1.0)
        tick(15, 1.0)                                              # turn right
        tick(0, 0.5)                                               # back to the middle
        tick(0, 1.0)                                               # rest a second
        self.assertEqual(ctl._turned[0], 0)
        self.assertLess(tick(-2, 1.0, speed=5.0), -4.0)            # small moves follow again

    def test_a_nudge_past_the_edge_does_not_stop_mouse_movement(self):
        ctl = self.ctl()
        glide(ctl, 0, 2, 0.3)
        glide(ctl, 2, 4.5, 0.3)                                      # just past the 3 deg area
        glide(ctl, 4.5, 0, 0.3)
        self.assertLess(glide(ctl, 0, -2, 0.3), -4.0)                # still follows to the left
        self.assertGreater(glide(ctl, -2, 1, 0.3), 6.0)              # and back right

    def test_after_a_turn_the_middle_ends_the_return_guard(self):
        ctl = self.ctl()
        run(ctl, 1.0, yaw=12)                                        # a real turn right
        glide(ctl, 12, 0, 0.3)                                       # back to the middle, no pause
        self.assertLess(glide(ctl, 0, -2, 0.3), -4.0)                # left follows straight away

    def test_per_axis_modes(self):
        ctl = self.ctl(hybrid_vertical=False)                        # left/right only
        self.assertEqual(ctl.modes, ("hybrid", "joystick"))
        self.assertAlmostEqual(glide(ctl, 0, 2, 0.5), (2 - 0.25) * 3, delta=0.1)
        self.assertEqual(glide(ctl, 0, 1.5, 0.5, axis=1), 0.0)       # up/down: joystick dead zone
        ctl = self.ctl(hybrid_horizontal=False)
        self.assertEqual(ctl.modes, ("joystick", "hybrid"))
        self.assertEqual(glide(ctl, 0, 2, 0.5), 0.0)

    def test_blend_per_axis(self):
        ctl = self.ctl(hybrid_blend=0.0, hybrid_blend_y=4.0)
        self.assertAlmostEqual(ctl.yaw_axis.follow_position(10), 3.0)
        self.assertAlmostEqual(ctl.pitch_axis.follow_position(10), 2.0 + 2.0)

    def test_overshooting_center_after_a_turn_stays_still(self):
        ctl = self.ctl()
        run(ctl, 1.0, yaw=-12)
        moved = glide(ctl, -12, 1.5, 0.3)
        self.assertLessEqual(moved, 0.0)

    def test_pause_and_recenter_do_not_jump(self):
        ctl = self.ctl()
        glide(ctl, 0, 2, 0.3)
        for i in range(40):
            ctl.step((2 - i / 20, 0.0), DT, hold=True)
        self.assertEqual(run(ctl, 0.5)[0], 0.0)
        s = settings(general={"start_enabled": True}, assist={"hybrid": True})
        src, backend = FakeSource(), NullInput()
        app = HeadMouse(s, src, backend)
        t = 0.0
        for i in range(round(1 / DT)):
            src.set(2.0 + 0.01 * (i % 3), 0.0, t)                    # a little noise so tracking isn't frozen
            app.tick(t)
            t += DT
        app.recenter()                                               # 2 deg becomes the middle
        src.set(2.0, 0.0, t)
        app.tick(t)
        self.assertEqual(app.controller.step((0.0, 0.0), DT).yaw_speed, 0.0)

    def test_with_auto_center_resting_does_not_creep(self):
        ctl = self.ctl(auto_center=True)
        glide(ctl, 0, 2, 0.3)
        self.assertAlmostEqual(run(ctl, 20, yaw=2.0)[0], 0.0)
        self.assertGreater(ctl.drift[0], 1.5)

    def test_vertical_follow_wins_for_up_down(self):
        ctl = self.ctl(vertical_follow=True, vertical_follow_gain=4.0)
        glide(ctl, 0, 2, 0.3, axis=1)
        self.assertGreater(glide(ctl, 2, 8, 0.5, axis=1), 20)       # still follows past the dead zone
        self.assertEqual(run(ctl, 1.0, pitch=8)[1], 0.0)

    def test_with_return_stop(self):
        ctl = self.ctl(return_stop=True)
        run(ctl, 1.0, yaw=-12)
        glide(ctl, -12, -1, 0.3)
        run(ctl, 0.5, yaw=-1)
        self.assertLess(run(ctl, 0.5, yaw=-8)[0], -1.0)             # a new turn still works

    def test_settings_round_trip(self):
        self.assertEqual(config.Settings().assist.hybrid_blend, 2.0)
        with self.assertRaises(config.SettingsError):
            settings(assist={"hybrid_gain_x": 50.0})
        with self.assertRaises(config.SettingsError):
            settings(assist={"hybrid_blend": -1.0})


class MouseDelayTests(unittest.TestCase):
    """Mouse-like start delay: a quick glance doesn't move the camera, a real move catches up."""

    def ctl(self, delay, **assist):
        return MotionController(settings(assist={"hybrid": True, "hybrid_gain_y": 3.0, "mouse_delay_y": delay,
                                                 **assist}, motion={"smoothing_seconds": 0}))

    def nod(self, ctl, depth, seconds):
        """Glance down and straight back up."""
        return glide(ctl, 0, -depth, seconds / 2, axis=1) + glide(ctl, -depth, 0, seconds / 2, axis=1) \
            + run(ctl, 0.5)[1]

    def test_a_quick_glance_does_not_move_the_camera(self):
        self.assertAlmostEqual(self.nod(self.ctl(0.3), 1.8, 0.15), 0.0)
        self.assertLess(abs(self.nod(self.ctl(0.0), 1.8, 0.15)), 2.0)    # without: it moved and came back
        moved_without = glide(self.ctl(0.0), 0, -1.8, 0.075, axis=1)
        self.assertLess(moved_without, -3.0)

    def test_a_real_move_ends_up_the_same_and_catches_up_smoothly(self):
        a, b = self.ctl(0.2), self.ctl(0.0)
        peak = 0.0
        total_a = total_b = 0.0
        for i in range(1, round(0.5 / DT) + 1):
            p = min(2.0, 2.0 * i * DT / 0.3)
            r = a.step((0.0, p), DT)
            total_a += r.pitch_speed * DT
            peak = max(peak, abs(r.pitch_speed))
            total_b += b.step((0.0, p), DT).pitch_speed * DT
        total_a += run(a, 0.5, pitch=2.0)[1]
        self.assertGreater(total_b, 4.5)
        self.assertAlmostEqual(total_a, total_b, delta=0.02)              # same place in the end
        self.assertLess(peak, 80.0)                                       # no one-tick jump

    def test_slow_steady_moves_still_get_through(self):
        ctl = self.ctl(0.3)
        self.assertLess(glide(ctl, 0, -2, 2.0, axis=1) + run(ctl, 0.5, pitch=-2)[1], -4.0)

    def test_left_right_has_its_own_delay(self):
        ctl = self.ctl(0.3)
        self.assertLess(glide(ctl, 0, -1.8, 0.075), -3.0)                 # left/right: no delay

    def test_works_with_up_down_follow(self):
        ctl = self.ctl(0.3, vertical_follow=True)
        self.assertAlmostEqual(self.nod(ctl, 3.0, 0.15), 0.0)


class PrecisionTests(unittest.TestCase):
    """Slow-movement precision (speed-dependent sensitivity) and the wobble filter."""

    def ctl(self, **assist):
        return MotionController(settings(assist={"hybrid": True, "hybrid_gain_x": 2.0, **assist}))

    def webcam_glide(self, ctl, start, end, seconds, jitter=0.15, seed=1):
        """Webcam-like: new samples at 30 Hz with jitter, default smoothing, 125 Hz ticks."""
        rng = random.Random(seed)
        turned, sample, gains = 0.0, start, []
        n = round(seconds / DT)
        for i in range(1, n + 1):
            if int(i * DT * 30) != int((i - 1) * DT * 30):
                sample = start + (end - start) * i / n + rng.uniform(-jitter, jitter)
            turned += ctl.step((sample, 0.0), DT).yaw_speed * DT
            gains.append(ctl._precision(0))
        return turned, gains

    def test_off_by_default(self):
        a = config.Settings().assist
        self.assertEqual((a.slow_precision_x, a.slow_precision_y, a.wobble_x), (1.0, 1.0, 0.25))

    def test_slow_moves_get_finer_fast_moves_full(self):
        on, off = self.ctl(slow_precision_x=0.3), self.ctl()
        slow_on, gains = self.webcam_glide(on, 0, 2.0, 2.0)          # 1 deg/s, a fine correction
        slow_off, _ = self.webcam_glide(off, 0, 2.0, 2.0)
        self.assertLess(slow_on, slow_off * 0.55)
        self.assertLess(max(gains[40:]), 0.6)                          # steadily low, no flicker to full
        totals = []
        for ctl in (self.ctl(slow_precision_x=0.3), self.ctl()):                   # a quick flick
            totals.append(self.webcam_glide(ctl, 0, 2.0, 0.06, jitter=0)[0] + run(ctl, 0.3, yaw=2.0)[0])
        self.assertGreater(totals[0], totals[1] * 0.75, totals)

    def test_does_not_touch_the_joystick(self):
        on, off = self.ctl(slow_precision_x=0.2, hybrid_blend=0.0), self.ctl(hybrid_blend=0.0)
        run(on, 0.5, yaw=12)
        run(off, 0.5, yaw=12)
        self.assertAlmostEqual(run(on, 1.0, yaw=12)[0], run(off, 1.0, yaw=12)[0], places=6)

    def test_wobble_filter_sets_how_soon_a_reversal_responds(self):
        for wobble, expect in ((0.1, 0.2), (0.25, 0.5)):
            ctl = MotionController(settings(assist={"hybrid": True, "wobble_x": wobble},
                                            motion={"smoothing_seconds": 0}))
            glide(ctl, 0, 2, 0.3)
            back = 0.0
            for i in range(1, 101):                                    # reverse 0.01 deg at a time
                if ctl.step((2 - i * 0.01, 0.0), DT).yaw_speed < 0:
                    back = i * 0.01
                    break
            self.assertAlmostEqual(back, expect, delta=0.02)

    def test_lower_sensitivity_values_are_allowed(self):
        s = settings(assist={"hybrid_gain_x": 0.1, "vertical_follow_gain": 0.2})
        self.assertEqual(s.assist.hybrid_gain_x, 0.1)
        with self.assertRaises(config.SettingsError):
            settings(assist={"wobble_x": 0.0})                         # 0 would never count as still

    def test_precision_key_toggle(self):
        s = settings(general={"start_enabled": True, "precision_toggle": True})
        src, backend = FakeSource(), NullInput()
        app = HeadMouse(s, src, backend)
        key = s.key("precision_hold")
        t = 0.0

        def ticks(seconds):
            nonlocal t
            for i in range(round(seconds / DT)):
                src.set(12.0 + 0.01 * (i % 3), 0.0, t)
                app.tick(t)
                t += DT
        ticks(0.5)
        self.assertFalse(app.precision_on)
        backend.keys_down.add(key)
        ticks(0.1)
        backend.keys_down.discard(key)
        ticks(0.3)
        self.assertTrue(app.precision_on)                              # stays on after letting go
        self.assertIn("precision", app.state)
        backend.keys_down.add(key)
        ticks(0.1)
        backend.keys_down.discard(key)
        ticks(0.1)
        self.assertFalse(app.precision_on)
        hold = settings(general={"start_enabled": True})
        self.assertFalse(hold.general.precision_toggle)


class CompatibilityTests(unittest.TestCase):
    """Settings saved by 1.4 must behave exactly as before."""

    OLD = {"assist": {"hybrid": True, "hybrid_gain_x": 2.5, "hybrid_blend": 3.0, "return_stop": True},
           "webcam": {"smoothing_min_cutoff": 0.6}, "down": {"start_delay": 0.2},
           "general": {"link_left_right": True}}

    def test_old_file_keeps_its_meaning(self):
        old = settings(**self.OLD)
        self.assertEqual(config.axis_modes(old), ("hybrid", "hybrid"))
        self.assertEqual(old.assist.hybrid_blend_y, 3.0)                          # inherited
        self.assertEqual(old.webcam.vertical_smoothing_min_cutoff, 0.6)           # inherited
        explicit = settings(**{**self.OLD, "assist": {**self.OLD["assist"], "hybrid_blend_y": 3.0,
                                                       "hybrid_horizontal": True, "hybrid_vertical": True}})
        a, b = MotionController(old), MotionController(explicit)
        path = [(8 * math.sin(i / 40), 5 * math.sin(i / 23)) for i in range(800)]
        self.assertEqual([a.step(p, DT) for p in path], [b.step(p, DT) for p in path])

    def test_follow_wins_like_before(self):
        s = settings(assist={"hybrid": True, "vertical_follow": True})
        self.assertEqual(config.axis_modes(s), ("hybrid", "follow"))
        self.assertEqual(config.axis_modes(settings(assist={"vertical_follow": True})), ("joystick", "follow"))
        self.assertEqual(config.axis_modes(config.Settings()), ("joystick", "joystick"))

    def test_mode_values_round_trip(self):
        for x in config.AXIS_MODES[0]:
            for y in config.AXIS_MODES[1]:
                s = settings(assist=config.mode_values(x, y))
                self.assertEqual(config.axis_modes(s), (x, y))

    def test_saving_writes_down_inherited_values(self):
        import tempfile
        from pathlib import Path
        d = Path(tempfile.mkdtemp())
        path = d / "headmouse_settings.toml"
        path.write_text("[webcam]\nsmoothing_min_cutoff = 0.6\n[assist]\nhybrid_blend = 3.0\n")
        config.save_values(path, {"webcam": {"smoothing_min_cutoff": 2.0}, "assist": {"hybrid_blend": 1.0}})
        s = config.load(path)[0]
        self.assertEqual((s.webcam.smoothing_min_cutoff, s.webcam.vertical_smoothing_min_cutoff), (2.0, 0.6))
        self.assertEqual((s.assist.hybrid_blend, s.assist.hybrid_blend_y), (1.0, 3.0))


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

    def test_wizard_keeps_the_mouse_like_area(self):
        s = settings(assist={"hybrid": True}, right={"deadzone": 5.0}, up={"deadzone": 4.0})
        neutral = calibration.Neutral(0, 0, 0.1, 0.1)
        moves = {"right": calibration.Movement(30, 1), "left": calibration.Movement(20, -1),
                 "up": calibration.Movement(15, 1), "down": calibration.Movement(10, -1)}
        new = calibration.propose(s, "webcam", neutral, moves)[0]
        self.assertEqual((new.right.deadzone, new.up.deadzone), (5.0, 4.0))
        self.assertGreater(new.right.full_speed_angle, new.right.deadzone)
        plain = calibration.propose(settings(right={"deadzone": 5.0}), "webcam", neutral, moves)[0]
        self.assertLess(plain.right.deadzone, 5.0)                 # unchanged behaviour without it

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
