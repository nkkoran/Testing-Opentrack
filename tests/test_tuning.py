"""Practice-game tuning, checked with a simulated player using the real motion logic."""

import dataclasses
import math
import random
import unittest

from headmouse import config, tuning
from headmouse.controller import MotionController

DT = 1 / 125


def simulate_round(settings, targets, reaction=0.15, lag=0.12, gain=0.5, anticipate=0.35, reach=(20.0, 13.0),
                   belief=None, rate=2.5, make_trial=tuning.Trial, noise=0.0, seed=0):
    """A simple human model: aims the head in proportion to the error, after a reaction delay,
    easing off as the camera swings toward the target (anticipation).

    With mouse-like aiming, small errors (within what the player believes the mouse-like
    area reaches, from `belief` = the strength they think it has) are fixed by nudging the
    head by error / belief at `rate` per second, starting from the middle."""
    ctl = MotionController(settings)
    rng = random.Random(seed)
    a = settings.assist
    hybrid = tuning.hybrid_axes(settings)
    belief = belief or (a.hybrid_gain_x, a.hybrid_gain_y)
    dz = {"right": settings.right.deadzone, "left": settings.left.deadzone,
          "up": settings.up.deadzone, "down": settings.down.deadzone}
    head = [0.0, 0.0]
    trials = []
    t = 0.0
    for target in targets:
        for _ in range(int(0.4 / DT)):                     # relax back to the middle
            head = [h + (0 - h) * min(1, DT / lag) for h in head]
            ctl.step(tuple(head), DT)
            t += DT
        trial = make_trial(target)
        camera = [0.0, 0.0]
        speed = (0.0, 0.0)
        history = []
        nudge = [None, None]                               # hybrid: head aim while nudging
        while not trial.done:
            err = (target[0] - camera[0], target[1] - camera[1])
            history.append((err, speed))
            (seen_err, seen_speed) = history[max(0, len(history) - 1 - int(reaction / DT))]
            seen = [e - anticipate * v for e, v in zip(seen_err, seen_speed)]
            want = []
            for axis, e in enumerate(seen):
                name = (("right", "left"), ("up", "down"))[axis][0 if seen_err[axis] > 0 else 1]
                if axis in hybrid and abs(seen_err[axis]) <= belief[axis] * dz[name] * 0.9:
                    if nudge[axis] is None:
                        nudge[axis] = 0.0                  # back to the middle, then nudge
                    nudge[axis] += seen_err[axis] * rate * DT / belief[axis]
                    want.append(nudge[axis])
                    continue
                nudge[axis] = None
                if abs(e) <= trial.radius * 0.6:
                    want.append(0.0)
                    continue
                name = (("right", "left"), ("up", "down"))[axis][0 if e > 0 else 1]
                angle = min(reach[axis], dz[name] + 0.6 + gain * abs(e))
                want.append(math.copysign(angle, e))
            head = [h + (w - h) * min(1, DT / lag) for h, w in zip(head, want)]
            seen_head = tuple(h + rng.gauss(0, noise) for h in head) if noise else tuple(head)
            r = ctl.step(seen_head, DT)
            camera[0] += r.yaw_speed * DT
            camera[1] += r.pitch_speed * DT
            speed = (r.yaw_speed, r.pitch_speed)
            t += DT
            trial.add(t, tuple(camera), tuple(head), (r.yaw_speed, r.pitch_speed))
        trials.append(trial)
    return trials


def tune(settings, rounds=3, **player):
    """Practice + adjust a few times, keeping a change only if it scored better (like the window)."""
    targets = tuning.make_targets(seed=1, hybrid=settings.assist.hybrid)
    best = settings
    best_score = tuning.score(simulate_round(best, targets, **player), best)
    start = best_score
    for _ in range(rounds):
        proposal, _ = tuning.propose(best, simulate_round(best, targets, **player))
        s = tuning.score(simulate_round(proposal, targets, **player), proposal)
        if tuning.worth_keeping(best_score, s):
            best, best_score = proposal, s
    return start, best_score, best


def all_dirs(settings, **changes):
    for name in tuning.DIRECTIONS:
        settings = dataclasses.replace(settings, **{name: dataclasses.replace(getattr(settings, name), **changes)})
    return settings


class TrialTests(unittest.TestCase):
    def test_acquire_needs_dwell(self):
        trial = tuning.Trial((10.0, 0.0))
        trial.add(0.0, (0.0, 0.0), (0, 0), (0, 0))
        trial.add(0.1, (9.0, 0.0), (0, 0), (0, 0))       # on target...
        self.assertFalse(trial.done)
        trial.add(0.5, (9.5, 0.0), (0, 0), (0, 0))       # ...held for the dwell time
        self.assertTrue(trial.acquired)
        self.assertEqual(trial.entries, 1)

    def test_timeout(self):
        trial = tuning.Trial((40.0, 0.0))
        for i in range(int(tuning.TIMEOUT / 0.1) + 2):
            trial.add(i * 0.1, (0.0, 0.0), (0, 0), (0, 0))
        self.assertTrue(trial.done)
        self.assertFalse(trial.acquired)

    def test_targets_cover_every_direction(self):
        targets = tuning.make_targets(seed=3)
        self.assertEqual(len(targets), 12)
        self.assertEqual(sorted(tuning.direction_of(t)[0] for t in targets),
                         sorted(["right", "left", "up", "down"] * 3))


class ProposalTests(unittest.TestCase):
    def test_overshooting_player_gets_slower_near_center(self):
        fast = all_dirs(config.Settings(), min_speed=30.0, curve=1.0)
        fast = dataclasses.replace(fast, right=dataclasses.replace(fast.right, max_speed=360.0),
                                   left=dataclasses.replace(fast.left, max_speed=360.0))
        trials = simulate_round(fast, tuning.make_targets(seed=1))
        new, notes = tuning.propose(fast, trials)
        self.assertTrue(any("overshot" in n for ns in notes.values() for n in ns), notes)
        self.assertGreater(new.right.curve, fast.right.curve)
        self.assertLess(new.right.min_speed, fast.right.min_speed)
        config.validate(new)

    def test_too_slow_gets_faster(self):
        slow = all_dirs(config.Settings(), max_speed=40.0)
        trials = simulate_round(slow, tuning.make_targets(seed=1))
        new, notes = tuning.propose(slow, trials)
        self.assertGreater(new.right.max_speed, slow.right.max_speed, notes)
        config.validate(new)

    def test_points_table_is_left_alone(self):
        s = dataclasses.replace(config.Settings(), right=dataclasses.replace(
            config.Settings().right, min_speed=30.0, curve=1.0, points=[[3, 0], [15, 180]]))
        new, notes = tuning.propose(s, simulate_round(s, tuning.make_targets(seed=1)))
        self.assertEqual(new.right, s.right)


class ImprovementTests(unittest.TestCase):
    """The whole loop should make badly tuned settings measurably better."""

    def test_far_too_fast_improves(self):
        bad = all_dirs(config.Settings(), min_speed=30.0, curve=1.0, max_speed=360.0)
        start, end, best = tune(bad)
        self.assertLess(end, start * 0.9, (start, end))

    def test_far_too_slow_improves(self):
        bad = all_dirs(config.Settings(), max_speed=35.0, min_speed=2.0)
        start, end, best = tune(bad)
        self.assertLess(end, start * 0.9, (start, end))

    def test_good_settings_are_not_made_worse(self):
        start, end, best = tune(config.Settings())
        self.assertLessEqual(end, start)
        config.validate(best)


class HybridTuningTests(unittest.TestCase):
    """Mouse-like aiming: small targets tune its strength, the dead zone (its area) is left alone."""

    def hybrid(self, **assist):
        return dataclasses.replace(config.Settings(), assist=dataclasses.replace(
            config.Settings().assist, hybrid=True, **assist))

    def test_small_targets_with_hybrid(self):
        targets = tuning.make_targets(seed=2, hybrid=True)
        s = self.hybrid()
        small = [t for t in targets if tuning.trial_metrics(tuning.Trial(t), s)["small"]]
        self.assertEqual(sorted(tuning.direction_of(t)[0] for t in small), ["down", "left", "right", "up"])

    def test_jumpy_gets_gentler(self):
        s = self.hybrid(hybrid_gain_x=6.0, hybrid_gain_y=6.0)
        trials = simulate_round(s, tuning.make_targets(seed=1, hybrid=True), belief=(1.5, 1.5))
        new, notes = tuning.propose(s, trials)
        self.assertIn("aiming", notes)
        self.assertLess(new.assist.hybrid_gain_x, 6.0, notes)
        self.assertEqual((new.right.deadzone, new.up.deadzone), (s.right.deadzone, s.up.deadzone))
        config.validate(new)

    def test_too_weak_gets_stronger(self):
        s = self.hybrid(hybrid_gain_x=1.5, hybrid_gain_y=1.0)
        trials = simulate_round(s, tuning.make_targets(seed=1, hybrid=True))
        new, notes = tuning.propose(s, trials)
        self.assertGreater(new.assist.hybrid_gain_x, 1.5, notes)
        config.validate(new)

    def test_good_player_keeps_default_strength(self):
        s = self.hybrid()
        new, notes = tuning.propose(s, simulate_round(s, tuning.make_targets(seed=1, hybrid=True)))
        self.assertEqual((new.assist.hybrid_gain_x, new.assist.hybrid_gain_y), (3.0, 3.0), notes)

    def test_no_change_at_the_limit_is_not_reported(self):
        s = self.hybrid(hybrid_gain_x=tuning.GAIN_LIMITS[0], hybrid_gain_y=tuning.GAIN_LIMITS[0])
        jumpy = [tuning.Trial(t) for t in tuning.make_targets(seed=1, hybrid=True)]
        for trial in jumpy:                                       # flew far past every target
            trial.add(0.0, (0, 0), (0, 0), (0, 0))
            trial.add(1.0, (trial.target[0] * 2, trial.target[1] * 2), (0, 0), (0, 0))
        new, notes = tuning.propose(s, jumpy)
        self.assertEqual(new.assist.hybrid_gain_x, tuning.GAIN_LIMITS[0])
        self.assertFalse(any("gentler" in n for n in notes.get("aiming", [])), notes)

    def test_off_leaves_aiming_alone(self):
        s = all_dirs(config.Settings(), min_speed=30.0, curve=1.0)
        new, notes = tuning.propose(s, simulate_round(s, tuning.make_targets(seed=1)))
        self.assertNotIn("aiming", notes)
        self.assertEqual(new.assist, s.assist)

    def test_jumpy_improves(self):
        start, end, best = tune(self.hybrid(hybrid_gain_x=6.0, hybrid_gain_y=6.0), belief=(1.5, 1.5))
        self.assertLess(end, start * 0.95, (start, end))
        self.assertLess(best.assist.hybrid_gain_x, 6.0)

    def test_good_hybrid_settings_are_not_made_worse(self):
        start, end, best = tune(self.hybrid())
        self.assertLessEqual(end, start)
        config.validate(best)


if __name__ == "__main__":
    unittest.main()
