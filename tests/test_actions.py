"""Click actions: mouse buttons and commands from keys and face gestures."""

import unittest

from headmouse import actions, config
from headmouse.engine import HeadMouse
from headmouse.tracking import HeadSample
from headmouse.winput import NullInput
from tests.test_core import DT, settings


class Blend:
    def __init__(self, name, score):
        self.category_name, self.score = name, score


class GestureTests(unittest.TestCase):
    def test_scores_from_blendshapes(self):
        s = actions.face_scores([Blend("jawOpen", 0.8), Blend("mouthSmileLeft", 0.4), Blend("mouthSmileRight", 0.6),
                                 Blend("browOuterUpLeft", 0.7), Blend("browOuterUpRight", 0.5)])
        self.assertAlmostEqual(s["mouth"], 0.8)
        self.assertAlmostEqual(s["smile"], 0.5)
        self.assertAlmostEqual(s["brows"], 0.6)
        self.assertEqual(s["pucker"], 0.0)

    def run_scores(self, d, values, hold=0.15):
        t, active = 0.0, []
        for v in values:
            t += DT
            active.append("mouth" in d.update({"mouth": v}, t, DT, {"mouth": 0.5}, hold))
        return active

    def test_needs_a_moment_and_a_clear_gesture(self):
        d = actions.GestureDetector()
        self.assertFalse(any(self.run_scores(d, [0.9] * 10)))           # 0.08 s: talking, not a gesture
        d = actions.GestureDetector()
        self.assertTrue(self.run_scores(d, [0.9] * 40)[-1])             # 0.32 s: counts

    def test_lets_go_below_the_threshold_without_flicker(self):
        d = actions.GestureDetector()
        self.run_scores(d, [0.9] * 40)
        flicker = self.run_scores(d, [0.45, 0.55] * 20, hold=0.15)      # hovering around the threshold
        self.assertTrue(all(flicker))
        self.assertFalse(self.run_scores(d, [0.1] * 40)[-1])

    def test_no_face_clears(self):
        d = actions.GestureDetector()
        self.run_scores(d, [0.9] * 40)
        self.assertEqual(d.update(None, 1.0, DT, {}, 0.1), set())


class ActionTests(unittest.TestCase):
    def test_hold_click_toggle_and_commands(self):
        a = actions.Actions()
        b = [("k1", "left"), ("k2", "right_click"), ("k3", "right_toggle"), ("k4", "recenter")]
        self.assertEqual(a.update(b, {"k1": True}, 0.0).buttons, {"left"})
        out = a.update(b, {"k2": True}, 0.01)
        self.assertEqual(out.buttons, {"right"})                        # a click: down...
        self.assertEqual(a.update(b, {"k2": True}, 0.2).buttons, set())  # ...and up again, even if still held
        a.update(b, {"k3": True}, 0.3)
        self.assertEqual(a.update(b, {}, 0.4).buttons, {"right"})        # toggled on, stays on
        a.update(b, {"k3": True}, 0.5)
        self.assertEqual(a.update(b, {}, 0.6).buttons, set())            # and off
        self.assertEqual(a.update(b, {"k4": True}, 0.7).commands, ["recenter"])
        self.assertEqual(a.update(b, {"k4": True}, 0.8).commands, [])    # once per press

    def test_bindings_from_settings(self):
        s = settings(actions={"enabled": True, "key1": "CAPSLOCK", "key1_action": "left",
                              "mouth_action": "right", "smile_action": ""})
        self.assertEqual(actions.bindings(s), [("key:CAPSLOCK", "left"), ("face:mouth", "right")])
        self.assertTrue(actions.uses_gestures(s))
        off = settings(actions={"enabled": False, "key1": "CAPSLOCK", "key1_action": "left"})
        self.assertEqual(actions.bindings(off), [])

    def test_face_reading_starts_with_the_master_switch(self):
        from headmouse.engine import needs_face
        self.assertFalse(needs_face(settings()))
        self.assertTrue(needs_face(settings(actions={"enabled": True})))   # meters work before binding

    def test_suggested_thresholds(self):
        threshold, verdict = actions.suggest_threshold([0.05, 0.1, 0.08] * 10, [0.7, 0.8, 0.75] * 10)
        self.assertEqual(verdict, "clear")
        self.assertTrue(0.1 < threshold < 0.75)
        self.assertEqual(actions.suggest_threshold([0.1] * 10, [0.15] * 10)[0], None)
        self.assertEqual(actions.suggest_threshold([], [0.5])[1], "not measured")
        self.assertTrue(actions.suggest_threshold([0.1] * 10, [0.35] * 10)[1].startswith("weak"))

    def test_validation(self):
        with self.assertRaises(config.SettingsError):
            settings(actions={"key1_action": "explode"})
        with self.assertRaises(config.SettingsError):
            settings(actions={"mouth_threshold": 0.0})


class FaceSource:
    def __init__(self):
        self.seq, self.face = 0, None

    def set(self, now, face=None):
        self.seq += 1
        self.sample = HeadSample(0.01 * (self.seq % 3), 0.0, (0, 0, 0, 0.01 * (self.seq % 3), 0, self.seq),
                                 now, self.seq, face=face)

    def latest(self):
        return self.sample


class EngineActionTests(unittest.TestCase):
    def make(self, **act):
        s = settings(general={"start_enabled": True}, actions={"enabled": True, **act})
        src, backend = FaceSource(), NullInput()
        backend.window_title = "Enshrouded"
        return HeadMouse(s, src, backend), src, backend, s

    def ticks(self, app, src, seconds, face=None):
        for _ in range(round(seconds / DT)):
            self.t = getattr(self, "t", 0.0) + DT
            src.set(self.t, face)
            app.tick(self.t)

    def test_key_holds_a_button(self):
        app, src, backend, s = self.make(key1="CAPSLOCK", key1_action="left")
        backend.keys_down.add(config.key_code("CAPSLOCK"))
        self.ticks(app, src, 0.1)
        self.assertEqual(backend.buttons, [("left", True)])
        backend.keys_down.clear()
        self.ticks(app, src, 0.1)
        self.assertEqual(backend.buttons, [("left", True), ("left", False)])

    def test_gesture_holds_the_right_button_for_aiming(self):
        app, src, backend, s = self.make(mouth_action="right")
        self.ticks(app, src, 0.5, face={"mouth": 0.9, "brows": 0, "smile": 0, "pucker": 0})
        self.assertIn("right", app.buttons_down)
        self.ticks(app, src, 0.5, face={"mouth": 0.0, "brows": 0, "smile": 0, "pucker": 0})
        self.assertEqual(app.buttons_down, set())

    def test_never_outside_the_game_and_released_when_off(self):
        app, src, backend, s = self.make(key1="CAPSLOCK", key1_action="left_toggle")
        backend.window_title = "Desktop"
        backend.keys_down.add(config.key_code("CAPSLOCK"))
        self.ticks(app, src, 0.6)
        self.assertEqual(backend.buttons, [])
        backend.keys_down.clear()
        backend.window_title = "Enshrouded"
        self.ticks(app, src, 0.6)
        backend.keys_down.add(config.key_code("CAPSLOCK"))
        self.ticks(app, src, 0.05)
        backend.keys_down.clear()
        self.ticks(app, src, 0.2)
        self.assertEqual(app.buttons_down, {"left"})                    # toggled on
        app.set_enabled(False)
        self.ticks(app, src, 0.05)
        self.assertEqual(app.buttons_down, set())                       # head control off: let go
        self.assertEqual(backend.buttons[-1], ("left", False))

    def test_commands(self):
        app, src, backend, s = self.make(brows_action="freeze", smile_action="precision")
        face = {"mouth": 0, "brows": 0.9, "smile": 0, "pucker": 0}
        self.ticks(app, src, 0.4, face=face)
        self.assertTrue(app.action_freeze)
        self.assertEqual(app.state, "PAUSED")
        self.assertTrue(app.paused)
        self.ticks(app, src, 0.4, face={**face, "brows": 0.0})
        self.ticks(app, src, 0.4, face={**face, "brows": 0.9})
        self.assertFalse(app.action_freeze)
        self.ticks(app, src, 0.4, face={**face, "brows": 0.0, "smile": 0.9})
        self.assertTrue(app.action_precision)
        self.assertIn("precision", app.state)

    def test_camera_keeps_still_while_a_gesture_starts(self):
        free, steady = self.check_gesture_onset(False), self.check_gesture_onset(True)
        self.assertGreater(free, 3.0)
        self.assertLess(steady, free * 0.5)                     # most of the nudge is gone

    def check_gesture_onset(self, steady):
        s = settings(general={"start_enabled": True}, assist={"hybrid": True},
                     actions={"enabled": True, "mouth_action": "right", "steady_gestures": steady})
        src, backend = FaceSource(), NullInput()
        backend.window_title = "Enshrouded"
        app = HeadMouse(s, src, backend)
        rest = {"mouth": 0.0, "brows": 0, "smile": 0, "pucker": 0}
        self.ticks(app, src, 0.3, face=rest)
        src.yaw = 0
        moved = []
        for i in range(round(0.6 / DT)):                     # mouth opening: the head angle jumps 3 deg
            self.t += DT
            mouth = min(0.9, i * DT * 3)
            src.set(self.t, {**rest, "mouth": mouth})
            src.sample = src.sample.__class__(3.0 * mouth, 0.0, (0, 0, 0, 3.0 * mouth, 0, src.seq), self.t, src.seq,
                                              face={**rest, "mouth": mouth})
            app.tick(self.t)
            moved.append(app.result.yaw_speed)
        self.assertIn("right", app.buttons_down)
        return sum(abs(v) for v in moved) * DT

    def test_talking_does_not_keep_the_camera_paused(self):
        d = actions.GestureDetector()
        t, steady = 0.0, 0
        for i in range(round(2.0 / DT)):                       # jaw moving while talking, below the threshold
            t += DT
            d.update({"mouth": 0.25 + 0.1 * ((i // 10) % 2)}, t, DT, {"mouth": 0.5}, 0.15)
            steady += d.changing(t, {"mouth": 0.5}, ["mouth"])
        self.assertLess(steady * DT, 0.4)

    def test_freeze_key_tap_mode(self):
        s = settings(general={"start_enabled": True, "freeze_toggle": True})
        src, backend = FaceSource(), NullInput()
        backend.window_title = "Enshrouded"
        app = HeadMouse(s, src, backend)
        key = s.key("pause_hold")
        backend.keys_down.add(key)
        self.ticks(app, src, 0.05)
        backend.keys_down.clear()
        self.ticks(app, src, 0.3)
        self.assertEqual(app.state, "PAUSED")                         # stays frozen after letting go
        backend.keys_down.add(key)
        self.ticks(app, src, 0.05)
        backend.keys_down.clear()
        self.ticks(app, src, 0.1)
        self.assertNotEqual(app.state, "PAUSED")

    def test_dry_run_sends_no_buttons(self):
        s = settings(general={"start_enabled": True}, actions={"enabled": True, "key1": "CAPSLOCK",
                                                               "key1_action": "left"})
        src, backend = FaceSource(), NullInput()
        backend.window_title = "Enshrouded"
        app = HeadMouse(s, src, backend, send=False)
        backend.keys_down.add(config.key_code("CAPSLOCK"))
        self.ticks(app, src, 0.1)
        self.assertEqual(backend.buttons, [])


if __name__ == "__main__":
    unittest.main()
