"""The practice check-up: blocks, throughput, and keeping only what works better."""

import dataclasses
import unittest

from headmouse import config, practice
from tests.test_tuning import simulate_round


def play(block, seed=0, **player):
    """A simulated player does one block; returns it with trials filled in."""
    block.trials = simulate_round(block.settings, block.targets, make_trial=block.new_trial, seed=seed, **player)
    return block


def run(checkup, **player):
    block, n = checkup.next_block(), 0
    while block is not None:
        n += 1
        block = checkup.next_block(play(block, seed=n, **player))
    return checkup


def hybrid(**assist):
    return dataclasses.replace(config.Settings(), assist=dataclasses.replace(config.Settings().assist,
                                                                             hybrid=True, **assist))


class FakeTrial:
    def __init__(self, target, endpoint, mt):
        self.target, self.endpoint, self.movement_time, self.acquired, self.timeout = target, endpoint, mt, True, 8


class MeasureTests(unittest.TestCase):
    def test_throughput_rewards_fast_and_accurate(self):
        tight = [FakeTrial((8, 0), (8 + e, 0), 1.0) for e in (-0.2, 0.1, 0.0, 0.2, -0.1)]
        sloppy = [FakeTrial((8, 0), (8 + e, 0), 1.0) for e in (-1.0, 0.8, 0.1, 1.1, -0.9)]
        slow = [FakeTrial((8, 0), (8 + e, 0), 2.0) for e in (-0.2, 0.1, 0.0, 0.2, -0.1)]
        self.assertGreater(practice.throughput(tight), practice.throughput(sloppy))
        self.assertAlmostEqual(practice.throughput(tight), 2 * practice.throughput(slow), places=6)

    def test_targets(self):
        import random
        targets = practice.precision_targets(random.Random(1))
        self.assertEqual(len(targets), practice.PRECISION_TARGETS)
        self.assertTrue(all(3 <= (x * x + (y / 0.6) ** 2) ** 0.5 <= 12 for x, y in targets))
        self.assertTrue(any(x > 0 for x, _ in targets) and any(x < 0 for x, _ in targets))

    def test_wobble_measures_holding_still(self):
        quiet = practice.Block("steady", "", hybrid(), [(1.0, 0.0)], radius=2.0, dwell=3.0)
        shaky = practice.Block("steady", "", hybrid(), [(1.0, 0.0)], radius=2.0, dwell=3.0)
        play(quiet)
        play(shaky, noise=0.6)
        self.assertLess(practice.wobble(quiet.trials), practice.wobble(shaky.trials))

    def test_scaling_follows_each_pairs_mode(self):
        s = hybrid(vertical_follow=True, hybrid_gain_x=2.0, vertical_follow_gain=4.0)
        out = practice.scale_precision(s, 0.5)
        self.assertEqual((out.assist.hybrid_gain_x, out.assist.vertical_follow_gain), (1.0, 2.0))
        joy = practice.scale_precision(config.Settings(), 2.0)
        self.assertEqual(joy.right.min_speed, config.Settings().right.min_speed * 2)
        config.validate(out)
        config.validate(joy)


class CheckupTests(unittest.TestCase):
    def test_jumpy_mouse_like_gets_gentler(self):
        c = run(practice.Checkup(hybrid(hybrid_gain_x=6.0, hybrid_gain_y=6.0), focus="aim", seed=1),
                belief=(2.0, 2.0))
        before, after = c.scores["precision"]
        self.assertTrue(c.changed, c.notes)
        self.assertLess(c.best.assist.hybrid_gain_x, 6.0, c.notes)
        self.assertGreater(after, before)
        config.validate(c.best)

    def test_good_settings_are_kept(self):
        c = run(practice.Checkup(hybrid(), focus="aim", seed=2))
        before, after = c.scores["precision"]
        self.assertGreaterEqual(after, before * 0.999)
        config.validate(c.best)

    def test_blocks_and_focus(self):
        c = practice.Checkup(hybrid(), focus="turns", seed=3)
        first = c.next_block()
        self.assertEqual(first.kind, "turns")
        c = practice.Checkup(hybrid(), focus="aim", seed=3)
        first = c.next_block()
        self.assertEqual((first.kind, first.warmup, len(first.targets)), ("precision", 2, 8))

    def test_full_checkup_runs_and_stays_valid(self):
        c = run(practice.Checkup(hybrid(), focus="all", seed=4), noise=0.05)
        kinds = [b.kind for b in c.blocks]
        self.assertEqual(kinds[0], "precision")
        self.assertIn("turns", kinds)
        self.assertEqual(kinds[-1], "steady")
        config.validate(c.best)
        for line in practice.changes(c.original, c.best):
            self.assertIn("→", line)

    def test_shaky_holding_gets_steadier(self):
        c = practice.Checkup(hybrid(), focus="aim", seed=5)
        steps = c._steady_steps()   # only the steady part
        block = next(steps)
        play(block, noise=0.8)
        with self.assertRaises(StopIteration):
            steps.send(block)
        self.assertGreater(c.best.assist.wobble_x, 0.25)

    def test_joystick_player_checkup(self):
        c = run(practice.Checkup(config.Settings(), focus="aim", seed=6))
        config.validate(c.best)
        self.assertIn("precision", c.scores)


if __name__ == "__main__":
    unittest.main()
