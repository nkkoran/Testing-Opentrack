"""Setup-wizard maths: turn measured head movements into settings.

The wizard records head angles while the player (1) looks straight ahead and
then turns comfortably (2) right, (3) left, (4) up and (5) down. From that:

* neutral position = median of the straight-ahead samples
* direction signs  = fixed automatically if e.g. "right" was measured as negative
* full_speed_angle = 75% of the comfortable range, so top speed never needs a strain
* deadzone         = 20% of full_speed_angle (the ratio of the original defaults),
                     but at least 4x the tracking noise and at least 1 degree

Speeds and curve shapes are left as they are - those are taste, not range.
"""

import dataclasses
import statistics
from dataclasses import dataclass

DIRECTIONS = (("right", 0, +1), ("left", 0, -1), ("up", 1, +1), ("down", 1, -1))
MIN_RANGE = 3.0           # degrees; less than this means the movement wasn't seen
FULL_SPEED_SHARE = 0.75
DEADZONE_SHARE = 0.2


@dataclass
class Neutral:
    yaw: float
    pitch: float
    noise_yaw: float
    noise_pitch: float


@dataclass
class Movement:
    extent: float   # comfortable range in degrees
    sign: int       # +1 or -1: which way the angle actually went


def _percentile(values, share):
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(share * len(ordered)))]


def measure_neutral(samples):
    """samples: list of (yaw, pitch) while looking straight ahead."""
    yaws = [s[0] for s in samples]
    pitches = [s[1] for s in samples]
    noise = (lambda v: statistics.pstdev(v) if len(v) > 1 else 0.0)
    return Neutral(statistics.median(yaws), statistics.median(pitches), noise(yaws), noise(pitches))


def measure_movement(samples, neutral, axis):
    """How far, and which way, the head went on one axis (0 = yaw, 1 = pitch)."""
    center = neutral.yaw if axis == 0 else neutral.pitch
    d = [s[axis] - center for s in samples]
    pos = _percentile([max(v, 0.0) for v in d], 0.9)
    neg = _percentile([max(-v, 0.0) for v in d], 0.9)
    return Movement(extent=max(pos, neg), sign=+1 if pos >= neg else -1)


def propose(settings, source_kind, neutral, movements):
    """Build new settings from the measurements.

    movements: {"right": Movement, "left": ..., "up": ..., "down": ...}
    Returns (new_settings, report_lines, problems, new_offset). new_offset is the
    neutral position in the new orientation (for OpenTrack it is applied in memory).
    """
    report, problems = [], []
    flips = {0: False, 1: False}
    for axis, (pos_name, neg_name) in ((0, ("right", "left")), (1, ("up", "down"))):
        pos, neg = movements[pos_name], movements[neg_name]
        if pos.extent < MIN_RANGE or neg.extent < MIN_RANGE:
            continue
        if pos.sign == neg.sign:
            problems.append(f"{pos_name.title()} and {neg_name} looked the same to the tracker - "
                            f"direction left unchanged. Try the wizard again.")
        elif pos.sign < 0:
            flips[axis] = True
            report.append(f"{pos_name.title()}/{neg_name} were reversed - fixed automatically.")

    source = getattr(settings, source_kind)
    source = dataclasses.replace(
        source,
        yaw_right_is_positive=source.yaw_right_is_positive ^ flips[0],
        pitch_up_is_positive=source.pitch_up_is_positive ^ flips[1])
    offset = (-neutral.yaw if flips[0] else neutral.yaw,
              -neutral.pitch if flips[1] else neutral.pitch)
    if source_kind == "webcam":
        source = dataclasses.replace(source, neutral_yaw=round(offset[0], 2),
                                     neutral_pitch=round(offset[1], 2))
    new = dataclasses.replace(settings, **{source_kind: source})

    for name, axis, _ in DIRECTIONS:
        m = movements[name]
        d = getattr(settings, name)
        noise = neutral.noise_yaw if axis == 0 else neutral.noise_pitch
        if m.extent < MIN_RANGE:
            problems.append(f"Could not see enough movement {name} ({m.extent:.1f} deg) - "
                            f"{name} settings unchanged.")
            continue
        if d.points:
            report.append(f"{name.title()}: uses a custom points table - left unchanged.")
            continue
        full = min(45.0, max(5.0, round(FULL_SPEED_SHARE * m.extent, 1)))
        dead = max(DEADZONE_SHARE * full, 4 * noise, 1.0)
        dead = round(min(dead, full - 2.0), 1)
        new = dataclasses.replace(new, **{name: dataclasses.replace(d, deadzone=dead, full_speed_angle=full)})
        report.append(f"{name.title()}: comfortable range {m.extent:.0f}°  ->  dead zone {dead:g}°, "
                      f"full speed at {full:g}°")
    if max(neutral.noise_yaw, neutral.noise_pitch) > 1.0:
        problems.append("Tracking was jittery while you held still - check lighting and that your "
                        "face is clearly visible.")
    return new, report, problems, offset
