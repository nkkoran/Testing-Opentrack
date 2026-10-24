"""Practice-game tuning, checked with a simulated player using the real motion logic."""

import dataclasses
import math
import unittest

from headmouse import config, tuning
from headmouse.controller import MotionController

DT = 1 / 125


def simulate_round(settings, targets, reaction=0.15, lag=0.12, gain=0.5, anticipate=0.35, reach=(20.0, 13.0)):
    """A simple human model: aims the head in proportion to the error, after a reaction delay,
    easing off as the camera swings toward the target (anticipation)."""
    ctl = MotionController(settings)
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
        trial = tuning.Trial(target)
        camera = [0.0, 0.0]
        speed = (0.0, 0.0)
        history = []
        while not trial.done:
            err = (target[0] - camera[0], target[1] - camera[1])
            history.append((err, speed))
            (seen_err, seen_speed) = history[max(0, len(history) - 1 - int(reaction / DT))]
            seen = [e - anticipate * v for e, v in zip(seen_err, seen_speed)]
            want = []
            for axis, e in enumerate(seen):
                if abs(e) <= tuning.RADIUS * 0.6:
                    want.append(0.0)
                    continue
                name = (("right", "left"), ("up", "down"))[axis][0 if e > 0 else 1]
                angle = min(reach[axis], dz[name] + 0.6 + gain * abs(e))
                want.append(math.copysign(angle, e))
            head = [h + (w - h) * min(1, DT / lag) for h, w in zip(head, want)]
            r = ctl.step(tuple(head), DT)
            camera[0] += r.yaw_speed * DT
            camera[1] += r.pitch_speed * DT
            speed = (r.yaw_speed, r.pitch_speed)
            t += DT
            trial.add(t, tuple(camera), tuple(head), (r.yaw_speed, r.pitch_speed))
        trials.append(trial)
    return trials


def tune(settings, rounds=3):
    """Practice + adjust a few times, keeping a change only if it scored better (like the window)."""
    targets = tuning.make_targets(seed=1)
    best = settings
    best_score = tuning.score(simulate_round(best, targets), best)
    start = best_score
    for _ in range(rounds):
        proposal, _ = tuning.propose(best, simulate_round(best, targets))
        s = tuning.score(simulate_round(proposal, targets), proposal)
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


if __name__ == "__main__":
    unittest.main()
