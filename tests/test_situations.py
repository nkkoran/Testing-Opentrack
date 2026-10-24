"""Situations: a different feel (preset) while aiming, building or in a menu."""

import dataclasses
import tempfile
import unittest
from pathlib import Path

from headmouse import config
from headmouse.engine import Engine, HeadMouse
from headmouse.sounds import SoundPlayer
from headmouse.winput import NullInput
from tests.test_core import DT, FakeSource, settings
from tests.test_engine import LiveSource


def aim_feel(base):
    """Slow, mouse-like aiming."""
    return dataclasses.replace(base, assist=dataclasses.replace(base.assist, hybrid=True, hybrid_gain_x=0.5))


class SituationTests(unittest.TestCase):
    def make(self, **situations):
        s = settings(general={"start_enabled": True}, situations=situations)
        src, backend = FakeSource(), NullInput()
        backend.window_title = "Enshrouded"
        app = HeadMouse(s, src, backend)
        feels = {name: aim_feel(s) for name in config.SITUATIONS if getattr(s.situations, f"{name}_preset")}
        app.apply_settings(s, feels)
        return app, src, backend, s

    def ticks(self, app, src, seconds, yaw=0.0):
        events = []
        for i in range(round(seconds / DT)):
            self.t = getattr(self, "t", 0.0) + DT
            src.set(yaw + 0.01 * (i % 3), 0.0, self.t)
            events += app.tick(self.t)
        return events

    def test_off_by_default(self):
        app, src, backend, s = self.make()
        backend.keys_down.add(config.key_code("RIGHTMOUSE"))
        self.ticks(app, src, 0.3)
        self.assertIsNone(app.situation)

    def test_aim_while_held(self):
        app, src, backend, s = self.make(aim_preset="Aiming", aim_key="RIGHTMOUSE")
        normal = app.controller
        backend.keys_down.add(config.key_code("RIGHTMOUSE"))
        events = self.ticks(app, src, 0.1)
        self.assertEqual(app.situation, "aim")
        self.assertEqual(app.controller.s.assist.hybrid_gain_x, 0.5)
        self.assertTrue(any(e.kind == "situation" and e.data == "aim" for e in events))
        backend.keys_down.clear()
        self.ticks(app, src, 0.1)
        self.assertIsNone(app.situation)
        self.assertIs(app.controller, normal)

    def test_toggle_and_reset_when_head_control_turns_off(self):
        app, src, backend, s = self.make(build_preset="Building", build_key="B")
        key = config.key_code("B")
        backend.keys_down.add(key)
        self.ticks(app, src, 0.05)
        backend.keys_down.clear()
        self.ticks(app, src, 0.3)
        self.assertEqual(app.situation, "build")                 # stays on after letting go
        app.set_enabled(False)
        app.set_enabled(True)
        self.ticks(app, src, 0.1)
        self.assertIsNone(app.situation)

    def test_menu_wins_and_pointer_detection(self):
        app, src, backend, s = self.make(aim_preset="Aiming", aim_key="RIGHTMOUSE",
                                         menu_preset="Menus", menu_pointer=True)
        backend.keys_down.add(config.key_code("RIGHTMOUSE"))
        self.ticks(app, src, 0.05)
        self.assertEqual(app.situation, "aim")
        backend.pointer = True                                   # the game shows a pointer
        self.ticks(app, src, 0.05)
        self.assertEqual(app.situation, "menu")
        backend.pointer = False
        self.ticks(app, src, 0.05)
        self.assertEqual(app.situation, "aim")

    def test_pointer_only_counts_in_the_game_window(self):
        s_extra = {"game_window_title": "Enshrouded"}
        s = settings(general={"start_enabled": True, **s_extra}, situations={"menu_preset": "M", "menu_pointer": True})
        src, backend = FakeSource(), NullInput()
        app = HeadMouse(s, src, backend)
        app.apply_settings(s, {"menu": aim_feel(s)})
        backend.pointer = True
        backend.window_title = "Desktop"
        self.ticks(app, src, 0.1)
        self.assertIsNone(app.situation)
        backend.window_title = "Enshrouded"
        self.ticks(app, src, 0.1)
        self.assertEqual(app.situation, "menu")

    def test_switching_does_not_jump(self):
        app, src, backend, s = self.make(aim_preset="Aiming", aim_key="RIGHTMOUSE")
        self.ticks(app, src, 0.5, yaw=2.0)
        backend.keys_down.add(config.key_code("RIGHTMOUSE"))
        backend.sent.clear()
        self.ticks(app, src, 0.5, yaw=2.0)                         # head held still while switching
        self.assertLess(sum(abs(dx) for dx, _ in backend.sent), 3)

    def test_engine_loads_feels_from_presets(self):
        d = Path(tempfile.mkdtemp())
        path = d / "headmouse_settings.toml"
        path.write_text('[situations]\naim_preset = "Aiming"\naim_key = "RIGHTMOUSE"\n'
                        '[general]\nsetup_done = true\n', encoding="utf-8")
        config.save_preset(path, "Aiming", aim_feel(config.Settings()))
        engine = Engine(path, d, backend=NullInput(), sound_player=SoundPlayer(config.SoundSettings()),
                        source_factory=lambda s, b: LiveSource(), launch_opentrack=False)
        engine.start()
        try:
            self.assertEqual(engine.app.controllers["aim"].s.assist.hybrid_gain_x, 0.5)
        finally:
            engine.stop()

    def test_missing_preset_is_skipped(self):
        d = Path(tempfile.mkdtemp())
        path = d / "headmouse_settings.toml"
        path.write_text('[situations]\naim_preset = "Nope"\n', encoding="utf-8")
        engine = Engine(path, d, backend=NullInput(), sound_player=SoundPlayer(config.SoundSettings()),
                        source_factory=lambda s, b: LiveSource(), launch_opentrack=False)
        engine.start()
        try:
            self.assertNotIn("aim", engine.app.controllers)
            self.assertTrue(any("Aiming feel not used" in text for _, text in engine.drain_messages()))
        finally:
            engine.stop()

    def test_bad_key_is_rejected(self):
        with self.assertRaises(config.SettingsError):
            settings(situations={"aim_key": "NOTAKEY"})


if __name__ == "__main__":
    unittest.main()
