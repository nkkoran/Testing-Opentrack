"""Random settings and random head/keys/face input: nothing crashes, movement stays bounded, and no
mouse button is ever held outside the game, with head control off, or in the practice game."""

import math
import random
import unittest

from headmouse import actions, config
from headmouse.controller import MotionController
from headmouse.engine import HeadMouse
from headmouse.tracking import HeadSample
from headmouse.winput import NullInput


def random_settings(rng):
    data = {}
    for name in ("right", "left", "up", "down"):
        dz = rng.choice([0.0, 0.5, 3.0, 8.0, 20.0])
        data[name] = {"deadzone": dz, "full_speed_angle": dz + rng.uniform(0.6, 40), "min_speed": rng.uniform(0, 60),
                      "max_speed": rng.uniform(60, 720), "curve": rng.uniform(0.5, 6),
                      "start_delay": rng.choice([0, 0.1, 1.0])}
    data["assist"] = {**config.mode_values(rng.choice(["joystick", "hybrid"]), rng.choice(["joystick", "hybrid", "follow"])),
                      "hybrid_gain_x": rng.uniform(0.1, 20), "hybrid_gain_y": rng.uniform(0.1, 20),
                      "hybrid_blend": rng.choice([0, 2, 10]), "mouse_delay_x": rng.choice([0, 0.3, 2]),
                      "slow_precision_x": rng.uniform(0.1, 1), "fast_speed_x": rng.uniform(2, 90),
                      "wobble_x": rng.uniform(0.05, 1.5), "return_stop": rng.random() < 0.5,
                      "auto_center": rng.random() < 0.5}
    data["motion"] = {"smoothing_seconds": rng.choice([0, 0.04, 0.3])}
    return config.from_dict(data)[0]


class FuzzTests(unittest.TestCase):
    def test_controller_stays_finite_and_bounded(self):
        rng = random.Random(11)
        for _ in range(40):
            s = random_settings(rng)
            ctl = MotionController(s)
            yaw = pitch = 0.0
            for _ in range(600):
                yaw = max(-60, min(60, yaw + rng.gauss(0, 1.5)))
                pitch = max(-40, min(40, pitch + rng.gauss(0, 1.0)))
                angles = None if rng.random() < 0.01 else (yaw, pitch)
                r = ctl.step(angles, rng.choice([0.008, 0.016, 0.05, 0.0]), hold=rng.random() < 0.02,
                             precision=rng.random() < 0.1, steady=rng.random() < 0.02)
                self.assertTrue(math.isfinite(r.yaw_speed) and math.isfinite(r.pitch_speed))
                self.assertLessEqual(max(abs(r.dx), abs(r.dy)), s.mouse.max_counts_per_tick)

    def test_buttons_only_where_allowed(self):
        rng = random.Random(12)
        keys = [config.key_code(k) for k in ("CAPSLOCK", "Q", "RIGHTMOUSE", "B", "F7", "F9", "F10")]
        for _ in range(25):
            s = config.from_dict({"general": {"start_enabled": True, "freeze_toggle": rng.random() < .5},
                                  "situations": {"aim_key": "RIGHTMOUSE", "build_key": "B", "menu_pointer": True},
                                  "actions": {"enabled": True, "key1": "CAPSLOCK", "key1_action": rng.choice(list(actions.ACTIONS)),
                                              "key2": "Q", "key2_action": rng.choice(list(actions.ACTIONS)),
                                              "mouth_action": rng.choice(list(actions.ACTIONS)),
                                              "brows_action": rng.choice(list(actions.ACTIONS))}})[0]
            backend = NullInput()
            backend.window_title = "Enshrouded"
            src = type("Src", (), {"sample": None, "latest": lambda self: self.sample})()
            app = HeadMouse(s, src, backend)
            app.apply_settings(s, {"aim": s, "build": s})
            t = 0.0
            for i in range(800):
                t += 0.008
                if rng.random() < 0.05:
                    backend.keys_down.symmetric_difference_update({rng.choice(keys)})
                if rng.random() < 0.01:
                    backend.window_title = rng.choice(["Enshrouded", "Desktop"])
                if rng.random() < 0.01:
                    app.set_enabled(not app.enabled)
                if rng.random() < 0.004:
                    app.practice = not app.practice
                face = None if rng.random() < 0.02 else {g: rng.random() for g in actions.GESTURES}
                src.sample = HeadSample(rng.gauss(0, 6), rng.gauss(0, 4), (0, 0, 0, 0, 0, i), t, i, face=face)
                app.tick(t)
                if app.buttons_down:
                    self.assertTrue(app.enabled and backend.window_title == "Enshrouded" and not app.practice)
            sent = {}
            for button, down in backend.buttons:
                sent[button] = down
            self.assertEqual({b for b, d in sent.items() if d}, app.buttons_down)


if __name__ == "__main__":
    unittest.main()
