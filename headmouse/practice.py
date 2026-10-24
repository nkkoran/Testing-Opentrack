"""Practice check-up: short blocks of targets that measure the current settings, try a
few variations, and keep only what clearly works better.

Three kinds of block, matching the game:

* precision - small targets a few degrees away, in a circle of directions (like
  the ISO 9241-411 pointing test). Scored by throughput in bits/second: how much
  "aiming difficulty" is handled per second, with the difficulty measured from
  where the crosshair actually ended up (effective width), so being fast but
  sloppy doesn't win. Comparisons also weigh how many targets were hit.
* turns     - far targets (the joystick part). Scored by time per target; the
  existing tuning rules (overshoot, slow approach...) propose changes.
* steady    - keep the crosshair on a target for a few seconds. Scored by how
  much it wobbles; too much wobble raises the wobble filter / steadiness.

Comparing settings uses blocks of 8 targets; the first 2 are practice and not
scored (people need a moment to adapt to a change). A variation must beat the
best so far by MARGIN, and the winner is measured once more at the end.
Everything here is plain logic; the practice window shows the blocks.
"""

import dataclasses
import math
import random
import statistics
from dataclasses import dataclass, field

from . import tuning
from .config import axis_modes

MARGIN = 1.08            # a variation must be 8% better to replace the best so far
CONFIRM_MARGIN = 1.04    # ...and still 4% better after measuring it again at the end
PRECISION_TARGETS = 8
WARMUP = 2
TURN_TARGETS = 8
STEADY_HOLDS = 2
STEADY_SECONDS = 3.0
WOBBLY = 0.35            # degrees RMS while holding still: more than this counts as shaky
FOCUSES = {
    "all": "Everything · 6 min",
    "aim": "Small aiming · 3 min",
    "updown": "Up & down · 1½ min",
    "turns": "Big turns · 1 min",
}


@dataclass
class Block:
    kind: str                 # "precision", "turns" or "steady"
    title: str                # e.g. "Small aiming - try 2 of 4"
    settings: object
    targets: list
    radius: float
    dwell: float
    warmup: int = 0
    trying: str = ""          # what this block tries, for the player ("sensitivity 2.1x")
    trials: list = field(default_factory=list)

    def new_trial(self, target):
        return tuning.Trial(target, radius=self.radius, dwell=self.dwell,
                            timeout=12.0 if self.kind == "turns" else 8.0)

    @property
    def scored(self):
        return self.trials[self.warmup:]


def precision_targets(rng, n=PRECISION_TARGETS):
    """Targets around a circle of directions, alternating across it, flatter vertically
    (looking up and down has less room). Each is relative to where the crosshair is."""
    out = []
    for i in range(n):
        angle = (i * 3 % n) / n * 2 * math.pi + rng.uniform(-0.15, 0.15)
        distance = rng.choice((5.0, 8.0, 11.0))
        out.append((round(distance * math.cos(angle), 2), round(distance * 0.6 * math.sin(angle), 2)))
    return out


def vertical_targets(rng, n=PRECISION_TARGETS):
    """Mostly up or down, a few degrees away, alternating."""
    return [(round(rng.uniform(-1.5, 1.5), 2), (1 if i % 2 else -1) * rng.choice((3.0, 5.0, 7.0))) for i in range(n)]


def turn_targets(rng, n=TURN_TARGETS):
    out = []
    for i in range(n):
        if i % 4 == 3:
            out.append((rng.uniform(-4, 4), (14 if i % 8 == 3 else -14)))
        else:
            out.append(((1 if i % 2 else -1) * rng.choice((30.0, 50.0, 70.0)), rng.uniform(-3, 3)))
    return out


def throughput(trials):
    """Effective throughput (bits/s) of a block of pointing trials, ISO 9241-411 style:
    We = 4.133 x SD of the endpoints along the movement, IDe = log2(Ae / We + 1), TP = IDe / MT."""
    if len(trials) < 2:
        return 0.0
    along, travelled, times = [], [], []
    for t in trials:
        tx, ty = t.target
        d = math.hypot(tx, ty) or 1.0
        ux, uy = tx / d, ty / d
        ex, ey = t.endpoint
        reached = ex * ux + ey * uy                  # how far along the line to the target it ended
        along.append(reached - d)
        travelled.append(max(0.1, reached))
        times.append(max(0.2, t.movement_time if t.acquired else t.timeout + 2.0))
    we = max(0.3, 4.133 * statistics.stdev(along))   # degrees (floor: tracking noise)
    ide = math.log2(statistics.fmean(travelled) / we + 1)
    return ide / statistics.fmean(times)


def hit_rate(trials):
    return sum(1 for t in trials if t.acquired) / len(trials) if trials else 0.0


def precision_score(trials):
    """What the comparisons use: throughput, scaled down hard when targets were missed
    (a block of mostly misses says little about speed and must never win)."""
    return throughput(trials) * hit_rate(trials) ** 2


def wobble(trials):
    """RMS distance (degrees) of the crosshair from where it rested, while holding still
    (None if it never stayed in the circle long enough to tell)."""
    values = []
    for t in trials:
        pts = [(t.target[0] - s.err[0], t.target[1] - s.err[1]) for s in t.hold_samples()]
        pts = pts[len(pts) // 4:]                      # the settling moment isn't wobble
        if len(pts) < 5:
            continue
        mx, my = statistics.fmean(p[0] for p in pts), statistics.fmean(p[1] for p in pts)
        values.append(math.sqrt(statistics.fmean((p[0] - mx) ** 2 + (p[1] - my) ** 2 for p in pts)))
    return statistics.fmean(values) if values else None


def _replace(settings, section, **values):
    return dataclasses.replace(settings, **{section: dataclasses.replace(getattr(settings, section), **values)})


def _clamp(v, lo, hi):
    return min(hi, max(lo, v))


def scale_precision(settings, factor, axes=(0, 1)):
    """Small-aiming responsiveness x factor, for each pair (0 = left/right, 1 = up/down) in its mode:
    the mouse-like sensitivity, or (joystick) the slowest speed near the middle."""
    out = settings
    a = settings.assist
    for i, mode in enumerate(axis_modes(settings)):
        if i not in axes:
            continue
        if mode == "follow":
            out = _replace(out, "assist", vertical_follow_gain=round(_clamp(a.vertical_follow_gain * factor, 0.1, 10), 2))
        elif mode == "hybrid":
            field_name = "hybrid_gain_x" if i == 0 else "hybrid_gain_y"
            out = _replace(out, "assist", **{field_name: round(_clamp(getattr(a, field_name) * factor, 0.1, 10), 2)})
        else:
            for name in (("right", "left"), ("up", "down"))[i]:
                d = getattr(out, name)
                if not d.points:
                    out = _replace(out, name, min_speed=round(_clamp(d.min_speed * factor, 0.5, d.max_speed), 1))
    return out


def set_slow_precision(settings, value):
    out = settings
    for i, mode in enumerate(axis_modes(settings)):
        if mode in ("hybrid", "follow"):
            out = _replace(out, "assist", **{"slow_precision_x" if i == 0 else "slow_precision_y": value})
    return out


def describe(settings):
    """A short description of what drives small aiming in these settings."""
    a = settings.assist
    parts = []
    for i, mode in enumerate(axis_modes(settings)):
        pair = "left/right" if i == 0 else "up/down"
        if mode == "follow":
            parts.append(f"{pair} sensitivity {a.vertical_follow_gain:g}x")
        elif mode == "hybrid":
            parts.append(f"{pair} sensitivity {(a.hybrid_gain_x, a.hybrid_gain_y)[i]:g}x")
        else:
            d = settings.right if i == 0 else settings.up
            parts.append(f"{pair} slowest speed {d.min_speed:g}°/s")
    return ", ".join(parts)


class Checkup:
    """Plans the blocks. next_block(finished) gives the next Block (or None at the end);
    the window fills block.trials and passes the block back."""

    def __init__(self, settings, focus="all", seed=None):
        self.original = settings
        self.focus = focus
        self.rng = random.Random(seed)
        self.best = settings
        self.scores = {}          # what was measured: {"precision": (before, after), ...}
        self.notes = []           # what was tried and why it was kept or not
        self.blocks = []
        self._plan = self._steps()
        self._started = False

    def next_block(self, finished=None):
        try:
            block = next(self._plan) if not self._started else self._plan.send(finished)
        except StopIteration:
            return None
        self._started = True
        self.blocks.append(block)
        return block

    @property
    def changed(self):
        return self.best != self.original

    # --- the plan --------------------------------------------------------------

    def _precision(self, settings, title, trying, targets=None):
        return Block("precision", title, settings, targets or precision_targets(self.rng), radius=1.2, dwell=0.4,
                     warmup=WARMUP, trying=trying)

    def _steps(self):
        if self.focus in ("all", "aim"):
            yield from self._precision_steps()
        if self.focus in ("all", "updown"):
            yield from self._vertical_steps()
        if self.focus in ("all", "turns"):
            yield from self._turn_steps()
        if self.focus in ("all", "aim"):
            yield from self._steady_steps()

    def _compare(self, key, label, variations, targets):
        """Measure the current best, then each variation (functions returning settings), keep one only
        if it clearly scores better, and measure the winner once more. Scores go in self.scores[key]."""
        start = self.best
        total = len(variations) + 2
        block = yield self._precision(start, f"{label} - 1 of {total}", "your settings", targets())
        start_score = best_score = precision_score(block.scored)
        best_block = block
        if hit_rate(block.scored) < 0.5:   # mostly missed: try a much calmer setting first
            variations = [lambda: scale_precision(start, 0.45, self._axes(key))] + list(variations)
            total += 1
        for i, make in enumerate(variations, start=2):
            candidate = make()
            if candidate == self.best:
                continue
            trying = changes(self.best, candidate)
            block = yield self._precision(candidate, f"{label} - {i} of {total}", "; ".join(trying), targets())
            score = precision_score(block.scored)
            if score > best_score * MARGIN and hit_rate(block.scored) >= 0.5:
                self.notes.append(f"{label}: {block.trying} - better (score {score:.2f} vs {best_score:.2f})")
                self.best, best_score, best_block = candidate, score, block
            else:
                self.notes.append(f"{label}: tried {block.trying} - not better (score {score:.2f})")
        if self.best != start:   # measure the winner again: one lucky block shouldn't decide
            block = yield self._precision(self.best, f"{label} - {total} of {total} (check)", "the best one again",
                                          targets())
            confirmed = precision_score(best_block.scored + block.scored)
            if confirmed < start_score * CONFIRM_MARGIN:
                self.notes.append(f"{label}: the improvement didn't hold up when checked - kept the settings before")
                self.best, confirmed = start, start_score
            best_score = confirmed
        self.scores[key] = (start_score, best_score)

    @staticmethod
    def _axes(key):
        return (1,) if key == "updown" else (0, 1)

    def _precision_steps(self):
        """Your settings; then smaller and bigger sensitivity (both from yours); then slow-movement
        precision switched on or off on the best of those; then the winner once more."""
        start = self.best
        variations = [lambda: scale_precision(start, 0.7), lambda: scale_precision(start, 1.4)]
        if any(m in ("hybrid", "follow") for m in axis_modes(start)):
            on = start.assist.slow_precision_x >= 1.0
            variations.append(lambda: set_slow_precision(self.best, 0.5 if on else 1.0))
        yield from self._compare("precision", "Small aiming", variations, lambda: precision_targets(self.rng))

    def _vertical_steps(self):
        """Up & down on its own (it has less room than left & right): smaller and bigger up/down only."""
        start = self.best
        variations = [lambda: scale_precision(start, 0.7, (1,)), lambda: scale_precision(start, 1.4, (1,))]
        yield from self._compare("updown", "Up & down", variations, lambda: vertical_targets(self.rng))

    def _turn_steps(self):
        targets = turn_targets(self.rng)
        block = yield Block("turns", "Big turns - 1 of 2", self.best, targets, radius=2.5, dwell=0.35,
                            warmup=1, trying="your settings")
        before = tuning.score(block.scored, self.best)
        proposal, notes = tuning.propose(self.best, block.scored)
        if proposal == self.best:
            self.scores["turns"] = (before, before)
            return
        block = yield Block("turns", "Big turns - 2 of 2", proposal, turn_targets(self.rng), radius=2.5,
                            dwell=0.35, warmup=1, trying="adjusted turning")
        after = tuning.score(block.scored, proposal)
        if tuning.worth_keeping(before, after):
            self.best = proposal
            for name, why in notes.items():
                self.notes.append(f"Big turns ({name}): {'; '.join(why)}")
        else:
            self.notes.append("Big turns: tried an adjustment - your settings did better")
            after = before
        self.scores["turns"] = (before, after)

    def _steady_steps(self):
        holds = [(self.rng.uniform(-3, 3), self.rng.uniform(-1.5, 1.5)) for _ in range(STEADY_HOLDS)]
        block = yield Block("steady", "Hold steady", self.best, holds, radius=2.0, dwell=STEADY_SECONDS)
        shake = wobble(block.trials)
        self.scores["steady"] = (shake, shake)
        if shake is None:
            self.notes.append("Holding still: couldn't be measured (the crosshair didn't stay in the circle)")
            return
        if shake <= WOBBLY:
            return
        out = self.best
        a = out.assist
        for i, mode in enumerate(axis_modes(out)):
            if mode in ("hybrid", "follow"):
                f = "wobble_x" if i == 0 else "wobble_y"
                out = _replace(out, "assist", **{f: round(min(1.0, getattr(a, f) + 0.1), 2)})
        if out.tracking.source == "webcam":
            w = out.webcam
            out = _replace(out, "webcam", smoothing_min_cutoff=round(max(0.1, w.smoothing_min_cutoff * 0.8), 2),
                           vertical_smoothing_min_cutoff=round(max(0.1, w.vertical_smoothing_min_cutoff * 0.8), 2))
        if out != self.best:
            self.notes.append(f"Holding still wobbled {shake:.2f}° - a bit steadier")
            self.best = out


# --- describing the result ---------------------------------------------------------

LABELS = {
    ("assist", "hybrid_gain_x"): ("Left/right sensitivity", "x"), ("assist", "hybrid_gain_y"): ("Up/down sensitivity", "x"),
    ("assist", "vertical_follow_gain"): ("Up/down sensitivity (mouse only)", "x"),
    ("assist", "slow_precision_x"): ("Left/right slow-movement precision", ""),
    ("assist", "slow_precision_y"): ("Up/down slow-movement precision", ""),
    ("assist", "wobble_x"): ("Left/right wobble filter", "°"), ("assist", "wobble_y"): ("Up/down wobble filter", "°"),
    ("assist", "hybrid_blend"): ("Left/right blend", "°"), ("assist", "hybrid_blend_y"): ("Up/down blend", "°"),
    ("webcam", "smoothing_min_cutoff"): ("Left/right steadiness", ""),
    ("webcam", "vertical_smoothing_min_cutoff"): ("Up/down steadiness", ""),
}
DIRECTION_LABELS = {"deadzone": ("dead zone", "°"), "full_speed_angle": ("full speed at", "°"),
                    "min_speed": ("slowest speed", "°/s"), "max_speed": ("top speed", "°/s"), "curve": ("curve", "")}


def changes(old, new):
    """Human-readable lines for what differs between two settings (the parts a check-up changes)."""
    lines = []
    for (section, name), (label, unit) in LABELS.items():
        a, b = getattr(getattr(old, section), name), getattr(getattr(new, section), name)
        if a != b:
            lines.append(f"{label} {a:g} → {b:g}{unit}")
    for direction in ("right", "left", "up", "down"):
        for name, (label, unit) in DIRECTION_LABELS.items():
            a, b = getattr(getattr(old, direction), name), getattr(getattr(new, direction), name)
            if a != b:
                lines.append(f"{direction.title()} {label} {a:g} → {b:g}{unit}")
    return lines
