"""Practice game maths: measure how well the current settings work and suggest better ones.

The player steers a crosshair onto targets with head control (exactly the same
joystick logic as in the game, but no mouse movement). For each direction we look
at how they reached the targets:

* overshoot      - flew past the target and had to come back  -> slower near the middle
* too slow       - slow to reach targets, or long at full tilt -> faster overall
* slow approach  - crept up on the target                      -> a little quicker near the middle
* can't stop     - reached the target but drifted off again     -> bigger dead zone
* dead-zone push - head held just at the dead-zone edge        -> smaller dead zone

With mouse-like aiming (hybrid) on, small targets (within mouse-like reach) tune
its strength instead, and the dead zone - now the mouse-like area - is left alone:

* jumpy          - overshot or wobbled off small targets        -> gentler (lower strength)
* too weak       - had to turn past the area for small targets  -> stronger
* rough hand-over - overshot big turns                          -> wider blend

Changes are small and bounded; the player sees them and decides whether to keep them.
"""

import dataclasses
import math
import random
import statistics
from dataclasses import dataclass, field

RADIUS = 2.5      # degrees: the crosshair counts as on the target within this
DWELL = 0.35      # seconds the crosshair must stay on the target
TIMEOUT = 8.0     # seconds before a target counts as missed
DIRECTIONS = ("right", "left", "up", "down")
SMALL_MOVE = (10.0, 6.0)  # degrees (left/right, up/down): with mouse-like aiming, targets this close are small moves


def make_targets(seed=None, hybrid=False):
    """12 targets (relative to where the camera points when each appears): 3 per direction.
    With mouse-like aiming, one per direction is a small move (within SMALL_MOVE)."""
    rng = random.Random(seed)
    yaws, pitches = ((8, 25, 55), (5, 10, 16)) if hybrid else ((15, 35, 60), (6, 12, 18))
    targets = []
    for side in (1, -1):
        targets += [(side * d, rng.uniform(-3, 3)) for d in yaws]
        targets += [(rng.uniform(-5, 5), side * d) for d in pitches]
    rng.shuffle(targets)
    return targets


def direction_of(target):
    """(name, axis, sign): which direction's settings a target exercises."""
    yaw, pitch = target
    if abs(yaw) >= abs(pitch):
        return ("right" if yaw > 0 else "left"), 0, (1 if yaw > 0 else -1)
    return ("up" if pitch > 0 else "down"), 1, (1 if pitch > 0 else -1)


@dataclass
class Sample:
    t: float
    err: tuple        # (yaw, pitch) degrees from crosshair to target
    head: tuple       # (yaw, pitch) head angles relative to neutral
    speed: tuple      # (yaw, pitch) camera degrees/second


@dataclass
class Trial:
    target: tuple
    samples: list = field(default_factory=list)
    start: float = None
    entries: int = 0          # times the crosshair arrived on the target
    acquired: bool = False
    done: bool = False
    _inside: bool = False
    _on_since: float = None

    @property
    def time(self):
        return self.samples[-1].t - self.start if self.samples else 0.0

    def add(self, t, camera, head, speed):
        """Record one moment. camera: (yaw, pitch) turned since the target appeared. Returns done."""
        if self.start is None:
            self.start = t
        err = (self.target[0] - camera[0], self.target[1] - camera[1])
        self.samples.append(Sample(t, err, tuple(head), tuple(speed)))
        if math.hypot(*err) <= RADIUS:
            if not self._inside:
                self.entries += 1
                self._inside = True
                self._on_since = t
            if t - self._on_since >= DWELL:
                self.acquired = self.done = True
        else:
            self._inside = False
            self._on_since = None
        if t - self.start >= TIMEOUT:
            self.done = True
        return self.done


def hybrid_axes(settings):
    """Axes (0 = left/right, 1 = up/down) that use mouse-like aiming."""
    a = settings.assist
    if not a.hybrid:
        return ()
    return (0,) if a.vertical_follow else (0, 1)


def trial_metrics(trial, settings):
    name, axis, sign = direction_of(trial.target)
    d = getattr(settings, name)
    samples = trial.samples
    n = max(1, len(samples))
    dt = trial.time / n if samples else 0.0
    toward = [sign * s.head[axis] for s in samples]          # head angle toward the target
    err = [s.err[axis] for s in samples]
    overshoot = max([0.0] + [-sign * e for e in err])
    full = dt * sum(1 for h in toward if h >= d.full_speed_angle)   # seconds at full tilt
    approach = dt * sum(1 for s in samples if 1.5 * RADIUS < abs(s.err[axis]) < 8.0)
    stall = sum(1 for s, h in zip(samples, toward)
                if abs(s.err[axis]) > 2 * RADIUS and s.speed[axis] == 0
                and d.deadzone - 0.7 <= h <= d.deadzone + 0.2) / n
    joystick = dt * sum(1 for h in toward if h > d.deadzone)   # seconds past the mouse-like area
    small = axis in hybrid_axes(settings) and abs(trial.target[axis]) <= SMALL_MOVE[axis]
    return {"direction": name, "time": trial.time if trial.acquired else TIMEOUT + 2.0,
            "acquired": trial.acquired, "overshoot": overshoot, "full": full, "approach": approach,
            "exits": max(0, trial.entries - 1), "stall": stall, "joystick": joystick, "small": small}


def worth_keeping(old_score, new_score):
    """Keep new settings if they did better - or if the old ones missed most targets."""
    return new_score < old_score or old_score >= TIMEOUT


def score(trials, settings):
    """Average seconds per target (missed targets count as 10 s). Lower is better."""
    if not trials:
        return float("inf")
    return statistics.fmean(trial_metrics(t, settings)["time"] for t in trials)


def _propose_hybrid(settings, small, big_overshoot):
    """Mouse-like aiming strength (per axis) and blend. Returns (assist settings, reasons)."""
    a = settings.assist
    changes, why = {}, []
    for axis in hybrid_axes(settings):
        field, label = (("hybrid_gain_x", "left/right"), ("hybrid_gain_y", "up/down"))[axis]
        ms = small[axis]
        gain = getattr(a, field)
        if len(ms) < 2:
            continue
        mean = lambda key: statistics.fmean(m[key] for m in ms)
        if mean("overshoot") >= 2.0 or mean("exits") >= 0.8:
            gain = max(0.5, gain * 0.8)
            why.append(f"small {label} moves were jumpy - gentler mouse-like aiming")
        elif mean("joystick") >= 0.3:
            gain = min(12.0, gain * 1.3)
            why.append(f"small {label} moves needed a turn - stronger mouse-like aiming")
        elif mean("approach") >= 1.2 or mean("time") >= 2.5:
            gain = min(12.0, gain * 1.15)
            why.append(f"slow on small {label} moves - a bit stronger mouse-like aiming")
        if round(gain, 1) != getattr(a, field):
            changes[field] = round(gain, 1)
    if big_overshoot and a.hybrid_blend < 4.0:
        changes["hybrid_blend"] = a.hybrid_blend + 1.0
        why.append("overshot bigger turns - smoother hand-over from mouse-like to turning")
    return dataclasses.replace(a, **changes), why


def propose(settings, trials):
    """New settings from one round of practice. Returns (new_settings, notes {direction or "aiming": [reasons]})."""
    by_dir = {name: [] for name in DIRECTIONS}
    small = ([], [])          # hybrid: small-move trials per axis
    for t in trials:
        m = trial_metrics(t, settings)
        if m["small"]:
            small[direction_of(t.target)[1]].append(m)
        else:
            by_dir[m["direction"]].append(m)
    hybrid = hybrid_axes(settings)
    big_overshoot_any = False
    g = settings.general
    groups = ([("right", "left")] if g.link_left_right else [("right",), ("left",)]) + \
             ([("up", "down")] if g.link_up_down else [("up",), ("down",)])
    new = settings
    notes = {}
    for group in groups:
        name = group[0]
        ms = [m for n in group for m in by_dir[n]]
        d = getattr(settings, name)
        if len(ms) < 2:
            continue
        if name in ("up", "down") and settings.assist.vertical_follow:
            for n in group:
                notes[n] = ["follows your head (Settings > Feel) - not changed"]
            continue
        if any(getattr(settings, n).points for n in group):
            for n in group:
                notes[n] = ["uses a custom points table - not changed"]
            continue
        mean = lambda key: statistics.fmean(m[key] for m in ms)
        over_rate = sum(1 for m in ms if m["overshoot"] > 3.0) / len(ms)
        dz, full, lo, hi, curve = d.deadzone, d.full_speed_angle, d.min_speed, d.max_speed, d.curve
        why = []
        overshoot = mean("overshoot")
        big_overshoot = overshoot >= 6.0 or over_rate >= 0.5
        mouse_area = DIRECTIONS.index(name) // 2 in hybrid   # the dead zone is the mouse-like area: leave it
        big_overshoot_any |= big_overshoot and mouse_area
        if big_overshoot:
            # The worse the overshoot, the bigger the correction.
            if overshoot >= 20.0:
                hi, lo, curve = hi * 0.6, lo * 0.5, curve + 0.6
            elif overshoot >= 12.0:
                hi, lo, curve = hi * 0.75, lo * 0.7, curve + 0.4
            else:
                lo, curve = lo * 0.8, curve + 0.3
            curve = min(4.0, curve)
            why.append("overshot the targets - slower near the middle")
        elif mean("full") >= 0.4 or (mean("time") >= 2.5 and overshoot < 2.0):
            if hi < 360:
                hi = min(360.0, hi * 1.3)
                lo = lo * 1.2
                why.append("slow to reach the targets - faster overall")
            else:
                full = max(dz + 3.0, full * 0.85)
                why.append("often at full tilt - full speed with less head turn")
        if not big_overshoot and mean("approach") >= 1.2:
            lo = min(30.0, max(1.0, lo * 1.35))
            curve = max(1.0, curve - 0.2)
            why.append("slow final approach - a little quicker near the middle")
        if mouse_area:
            pass
        elif not big_overshoot and mean("exits") >= 0.8:
            dz = min(6.0, dz + 0.5)
            lo *= 0.85
            why.append("hard to stop on the target - bigger dead zone")
        elif mean("stall") >= 0.25:
            dz = max(1.0, dz - 0.5)
            why.append("pushing at the edge of the dead zone - smaller dead zone")
        if not why:
            continue
        full = max(full, dz + 0.5)
        lo = min(lo, hi)
        for n in group:  # linked directions get the same values
            new = dataclasses.replace(new, **{n: dataclasses.replace(
                d, deadzone=round(dz, 1), full_speed_angle=round(full, 1), min_speed=round(lo, 1),
                max_speed=round(hi / 5) * 5, curve=round(curve, 2))})
            notes[n] = why
    if hybrid:
        assist, why = _propose_hybrid(settings, small, big_overshoot_any)
        if why:
            new = dataclasses.replace(new, assist=assist)
            notes["aiming"] = why
    return new, notes
