"""Tests for the platform-independent parts. Run with:  py -m unittest -v"""

import ctypes
import socket
import time
import unittest
from pathlib import Path

from headmouse import config
from headmouse.engine import HeadMouse
from headmouse.controller import AxisMotion, MotionController, orient
from headmouse.curves import DirectionCurve, MonotoneSpline
from headmouse.keys import key_code
from headmouse.safety import TrackingMonitor, TrackingStatus
from headmouse.tracking import OPENTRACK_PACKET, HeadSample, OpenTrackUDPSource, parse_opentrack_packet
from headmouse.winput import INPUT, NullInput

ROOT = Path(__file__).resolve().parent.parent
DT = 1 / 125


def settings(**sections):
    return config.from_dict(sections)[0]


class FakeSource:
    def __init__(self):
        self.sample = None
        self.seq = 0

    def set(self, yaw, pitch, now, values=None):
        self.seq += 1
        self.sample = HeadSample(yaw, pitch, values or (0, 0, 0, yaw, pitch, self.seq * 1e-6),
                                 now, self.seq)

    def latest(self):
        return self.sample


class SettingsFileTests(unittest.TestCase):
    def test_shipped_settings_file_matches_defaults(self):
        loaded, warnings = config.load(ROOT / "headmouse_settings.toml")
        self.assertEqual(warnings, [])
        self.assertEqual(loaded, config.Settings())

    def test_bad_values_are_rejected(self):
        with self.assertRaises(config.SettingsError):
            settings(right={"deadzone": 20.0})          # beyond full_speed_angle
        with self.assertRaises(config.SettingsError):
            settings(keys={"pause_hold": "F99"})
        with self.assertRaises(config.SettingsError):
            settings(keys={"recenter": "F9"})           # same as pause_hold
        with self.assertRaises(config.SettingsError):
            settings(mouse={"counts_per_360": "lots"})

    def test_unknown_names_warn(self):
        _, warnings = config.from_dict({"mouse": {"speeeed": 1}, "extra": {}})
        self.assertEqual(len(warnings), 2)

    def test_key_names(self):
        self.assertEqual(key_code("F9"), 0x78)
        self.assertEqual(key_code("f10"), 0x79)
        self.assertEqual(key_code("Caps Lock"), 0x14)
        self.assertEqual(key_code("0x7A"), 0x7A)
        self.assertIsNone(key_code(""))


class CurveTests(unittest.TestCase):
    def test_horizontal_defaults_near_requested_targets(self):
        c = DirectionCurve(config.Settings().right)
        for angle, target in [(5, 10), (8, 25), (10, 60), (12, 100), (15, 180)]:
            self.assertAlmostEqual(c.speed(angle), target, delta=target * 0.15 + 1)
        self.assertEqual(c.speed(3.0), 0)
        self.assertEqual(c.speed(40), 180)

    def test_vertical_defaults_near_requested_targets(self):
        c = DirectionCurve(config.Settings().up)
        for angle, target in [(3, 5), (5, 12), (7, 25), (8, 40), (10, 60)]:
            self.assertAlmostEqual(c.speed(angle), target, delta=target * 0.15 + 1)
        self.assertEqual(c.speed(2.0), 0)

    def test_speed_never_decreases_with_angle(self):
        s = config.Settings()
        tables = [s.right, s.up, config.DirectionSettings(
            deadzone=3, points=[[3, 0], [5, 10], [8, 25], [10, 60], [12, 100], [15, 180]])]
        for d in tables:
            c = DirectionCurve(d)
            speeds = [c.speed(a / 20) for a in range(0, 600)]
            self.assertEqual(speeds, sorted(speeds))

    def test_table_mode_hits_points_exactly(self):
        pts = [[3, 0], [5, 10], [8, 25], [10, 60], [12, 100], [15, 180]]
        spline = MonotoneSpline(pts)
        for a, v in pts:
            self.assertAlmostEqual(spline(a), v)


class AxisTests(unittest.TestCase):
    def make_axis(self, **kw):
        s = config.Settings()
        return AxisMotion(DirectionCurve(s.right), DirectionCurve(s.left),
                          kw.get("hysteresis", 0.3), kw.get("reverse_delay", 0.15))

    def test_returning_to_center_slows_but_never_reverses(self):
        axis = self.make_axis()
        speeds = [axis.speed(a / 10, DT) for a in range(150, -1, -1)]   # 15 deg back to 0
        self.assertTrue(all(v >= 0 for v in speeds))
        moving = [v for v in speeds if v > 0]
        self.assertEqual(moving, sorted(moving, reverse=True))
        self.assertEqual(speeds[-1], 0)

    def test_overshoot_past_center_does_not_reverse(self):
        axis = self.make_axis()
        axis.speed(12, DT)
        # Filter overshoot: jumps straight to 5 deg left for a few ticks.
        self.assertEqual([axis.speed(-5, DT) for _ in range(5)], [0.0] * 5)
        # Held left long enough -> deliberate reversal is allowed.
        later = [axis.speed(-5, DT) for _ in range(30)]
        self.assertLess(later[-1], 0)

    def test_reverses_after_resting_in_center(self):
        axis = self.make_axis()
        axis.speed(12, DT)
        for _ in range(25):                  # 0.2 s in the dead zone
            axis.speed(0.5, DT)
        self.assertLess(axis.speed(-6, DT), 0)

    def test_hysteresis_keeps_moving_just_inside_deadzone(self):
        axis = self.make_axis()
        self.assertGreater(axis.speed(3.5, DT), 0)
        self.assertGreater(axis.speed(2.9, DT), 0)       # within 0.3 of the edge
        self.assertEqual(axis.speed(2.6, DT), 0)
        self.assertEqual(axis.speed(2.9, DT), 0)         # not restarted from below the edge


class ControllerTests(unittest.TestCase):
    def run_for(self, ctl, seconds, angles, **kw):
        dx = dy = 0
        for _ in range(round(seconds / DT)):
            r = ctl.step(angles, DT, **kw)
            dx += r.dx
            dy += r.dy
        return dx, dy

    def test_held_angle_gives_steady_speed_in_counts(self):
        s = settings(motion={"smoothing_seconds": 0.0})
        ctl = MotionController(s)
        speed = DirectionCurve(s.right).speed(10)
        dx, dy = self.run_for(ctl, 2.0, (10.0, 0.0))
        expected = speed * 2.0 * s.mouse.counts_per_360 / 360
        self.assertAlmostEqual(dx, expected, delta=2)
        self.assertEqual(dy, 0)

    def test_direction_signs(self):
        s = settings(motion={"smoothing_seconds": 0.0})
        self.assertLess(self.run_for(MotionController(s), 0.5, (-8.0, 0.0))[0], 0)
        self.assertLess(self.run_for(MotionController(s), 0.5, (0.0, 6.0))[1], 0)   # up = -y
        self.assertGreater(self.run_for(MotionController(s), 0.5, (0.0, -6.0))[1], 0)
        inv = settings(motion={"smoothing_seconds": 0.0}, mouse={"invert_vertical": True})
        self.assertGreater(self.run_for(MotionController(inv), 0.5, (0.0, 6.0))[1], 0)

    def test_slow_speeds_still_move_thanks_to_fractions(self):
        s = settings(motion={"smoothing_seconds": 0.0}, mouse={"counts_per_360": 360.0})
        ctl = MotionController(s)   # 1 count per degree, ~7.5 deg/s => 0.06 counts per tick
        dx, _ = self.run_for(ctl, 2.0, (3.2, 0.0))
        self.assertGreaterEqual(dx, 14)

    def test_pause_stops_immediately_and_discards_fractions(self):
        s = settings(motion={"smoothing_seconds": 0.0}, mouse={"counts_per_360": 360.0})
        ctl = MotionController(s)
        self.run_for(ctl, 0.13, (3.5, 0.0))
        self.assertNotEqual(ctl._acc_x, 0)
        r = ctl.step((15.0, 9.0), DT, hold=True)
        self.assertEqual((r.dx, r.dy, r.yaw_speed, r.pitch_speed), (0, 0, 0, 0))
        self.assertEqual(ctl._acc_x, 0)
        # Head goes back to center while paused, then released: no movement at all.
        self.assertEqual(self.run_for(ctl, 1.0, (0.0, 0.0), hold=True), (0, 0))
        self.assertEqual(self.run_for(ctl, 1.0, (0.0, 0.0)), (0, 0))

    def test_tracking_loss_stops(self):
        ctl = MotionController(settings())
        self.run_for(ctl, 0.5, (15.0, 0.0))
        r = ctl.step(None, DT)
        self.assertEqual((r.dx, r.dy), (0, 0))

    def test_precision_mode_scales_speed(self):
        s = settings(motion={"smoothing_seconds": 0.0})
        normal = self.run_for(MotionController(s), 1.0, (12.0, 0.0))[0]
        slow = self.run_for(MotionController(s), 1.0, (12.0, 0.0), precision=True)[0]
        self.assertAlmostEqual(slow / normal, s.motion.precision_speed_factor, delta=0.01)

    def test_require_center_to_resume(self):
        s = settings(motion={"smoothing_seconds": 0.0, "require_center_to_resume": True})
        ctl = MotionController(s)
        ctl.step((10.0, 0.0), DT, hold=True)
        self.assertEqual(self.run_for(ctl, 0.5, (10.0, 0.0)), (0, 0))
        ctl.step((0.0, 0.0), DT)
        self.assertGreater(self.run_for(ctl, 0.5, (10.0, 0.0))[0], 0)

    def test_up_and_down_are_independent(self):
        s = settings(motion={"smoothing_seconds": 0.0},
                     down={"deadzone": 1.0, "min_speed": 4.0, "max_speed": 120.0,
                           "full_speed_angle": 6.0, "curve": 1.5})
        up = self.run_for(MotionController(s), 1.0, (0.0, 5.0))[1]
        down = self.run_for(MotionController(s), 1.0, (0.0, -5.0))[1]
        self.assertGreater(abs(down), 3 * abs(up))
        self.assertEqual(MotionController(s).pitch_axis.positive.speed(5.0),
                         DirectionCurve(config.Settings().up).speed(5.0))

    def test_orient_and_offset(self):
        s = settings(tracking={"source": "opentrack"}, opentrack={"yaw_right_is_positive": False})
        self.assertEqual(orient((5.0, 2.0), s, (1.0, 1.0)), (-6.0, 1.0))
        s = settings(webcam={"pitch_up_is_positive": False})       # webcam is the default source
        self.assertEqual(orient((5.0, 2.0), s), (5.0, -2.0))


class SafetyTests(unittest.TestCase):
    def setUp(self):
        self.mon = TrackingMonitor(config.Settings().safety)

    def sample(self, yaw, t, seq, values=None):
        return HeadSample(yaw, 0.0, values or (0, 0, 0, yaw, 0, seq * 1e-6), t, seq)

    def test_no_data(self):
        self.assertEqual(self.mon.check(None, 0)[0], TrackingStatus.NO_DATA)
        self.assertEqual(self.mon.check(self.sample(1, 0.0, 1), 0.0)[0], TrackingStatus.OK)
        self.assertEqual(self.mon.check(self.sample(1, 0.0, 1), 0.3)[0], TrackingStatus.NO_DATA)

    def test_frozen_values(self):
        same = (0, 0, 0, 12.0, 0, 0)
        t, seq = 0.0, 0
        while t < 0.9:
            seq += 1
            self.assertEqual(self.mon.check(self.sample(12, t, seq, same), t)[0], TrackingStatus.OK)
            t += 0.01
        while t < 1.2:
            seq += 1
            status = self.mon.check(self.sample(12, t, seq, same), t)[0]
            t += 0.01
        self.assertEqual(status, TrackingStatus.FROZEN)
        seq += 1
        self.assertEqual(self.mon.check(self.sample(12.1, t, seq), t)[0], TrackingStatus.OK)

    def test_jump_and_invalid(self):
        self.mon.check(self.sample(0, 0.0, 1), 0.0)
        self.assertEqual(self.mon.check(self.sample(40, 0.01, 2), 0.01)[0], TrackingStatus.UNSTABLE)
        self.assertEqual(self.mon.check(self.sample(40.1, 0.3, 3), 0.3)[0], TrackingStatus.UNSTABLE)
        self.assertEqual(self.mon.check(self.sample(40.2, 0.6, 4), 0.6)[0], TrackingStatus.OK)
        nan = float("nan")
        self.assertEqual(self.mon.check(self.sample(nan, 0.61, 5, (0, 0, 0, nan, 0, 0)), 0.61)[0],
                         TrackingStatus.INVALID)
        self.assertEqual(self.mon.check(self.sample(150, 0.62, 6), 0.62)[0], TrackingStatus.INVALID)


class AppTests(unittest.TestCase):
    """HeadMouse.tick() end to end with a fake tracker and fake keyboard."""

    def make(self, **sections):
        sections["general"] = {"start_enabled": True, **sections.get("general", {})}
        s = settings(**sections)
        src, backend = FakeSource(), NullInput()
        return HeadMouse(s, src, backend), src, backend, s

    def run_ticks(self, app, src, t, seconds, yaw, pitch=0.0):
        for _ in range(round(seconds / DT)):
            src.set(yaw, pitch, t)
            app.tick(t)
            t += DT
        return t

    def test_pause_key_sequence_from_requirements(self):
        app, src, backend, s = self.make()
        t = self.run_ticks(app, src, 0.0, 1.0, 15.0)            # turning right
        self.assertGreater(sum(dx for dx, _ in backend.sent), 0)
        backend.keys_down.add(s.key("pause_hold"))               # hold F9
        backend.sent.clear()
        t = self.run_ticks(app, src, t, 0.5, 15.0)
        t = self.run_ticks(app, src, t, 0.5, 0.0)                # head back to center
        self.assertEqual(backend.sent, [])
        self.assertEqual(app.state, "PAUSED")
        backend.keys_down.clear()                                # release F9
        self.run_ticks(app, src, t, 1.0, 0.0)
        self.assertEqual(backend.sent, [])
        self.assertEqual(app.state, "ACTIVE")

    def test_enable_toggle_and_recenter(self):
        app, src, backend, s = self.make()
        toggle = s.key("enable_toggle")
        backend.keys_down.add(toggle)
        t = self.run_ticks(app, src, 0.0, 0.1, 10.0)
        backend.keys_down.discard(toggle)
        t = self.run_ticks(app, src, t, 0.5, 10.0)
        self.assertEqual(app.state, "OFF")
        self.assertEqual(backend.sent, [])
        backend.keys_down.add(s.key("recenter"))                 # 10 deg is now "center"
        t = self.run_ticks(app, src, t, 0.1, 10.0)
        backend.keys_down.clear()
        backend.keys_down.add(toggle)
        t = self.run_ticks(app, src, t, 0.1, 10.0)
        backend.keys_down.clear()
        self.run_ticks(app, src, t, 0.5, 10.0)
        self.assertTrue(app.enabled)
        self.assertEqual(backend.sent, [])

    def test_stops_when_data_stops(self):
        app, src, backend, _ = self.make()
        t = self.run_ticks(app, src, 0.0, 0.5, 12.0)
        backend.sent.clear()
        for _ in range(100):                                     # no new packets
            app.tick(t)
            t += DT
        moved_after_timeout = backend.sent[round(0.3 / DT):]
        self.assertEqual(moved_after_timeout, [])
        self.assertTrue(app.state.startswith("STOPPED"))

    def test_window_filter(self):
        app, src, backend, _ = self.make(general={"only_move_in_game_window": True,
                                                  "auto_enable_in_game": False})
        backend.window_title = "Desktop"
        t = self.run_ticks(app, src, 0.0, 0.5, 12.0)
        self.assertEqual(backend.sent, [])
        backend.window_title = "Enshrouded"
        self.run_ticks(app, src, t, 0.5, 12.0)
        self.assertNotEqual(backend.sent, [])


class TransportTests(unittest.TestCase):
    def test_packet_parsing(self):
        data = OPENTRACK_PACKET.pack(1, 2, 3, 10.5, -4.25, 7)
        self.assertEqual(parse_opentrack_packet(data), (1, 2, 3, 10.5, -4.25, 7))
        self.assertIsNone(parse_opentrack_packet(data[:-1]))

    def test_udp_round_trip(self):
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()
        src = OpenTrackUDPSource("127.0.0.1", port).start()
        try:
            out = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            out.sendto(b"junk", ("127.0.0.1", port))
            out.sendto(OPENTRACK_PACKET.pack(0, 0, 0, 12.0, -3.0, 0), ("127.0.0.1", port))
            deadline = time.time() + 2
            while src.latest() is None and time.time() < deadline:
                time.sleep(0.01)
            sample = src.latest()
            self.assertIsNotNone(sample)
            self.assertEqual((sample.yaw, sample.pitch), (12.0, -3.0))
            self.assertEqual(src.bad_packets, 1)
            out.close()
        finally:
            src.stop()

    @unittest.skipUnless(ctypes.sizeof(ctypes.c_void_p) == 8, "64-bit only")
    def test_input_struct_matches_windows_x64_size(self):
        self.assertEqual(ctypes.sizeof(INPUT), 40)


if __name__ == "__main__":
    unittest.main()
