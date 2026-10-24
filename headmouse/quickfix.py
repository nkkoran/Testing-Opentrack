"""Quick fixes: describe what feels wrong in plain words, get a small, bounded change.

Each fix works on one pair of directions (left & right, or up & down) and knows
which mode that pair uses, so it only touches settings that matter there. It
returns the new settings plus a line per change ("Left/right top speed 180 ->
225°/s"), so the player can see what happened and undo it.
"""

import dataclasses
from dataclasses import dataclass

from .config import axis_modes

AXES = {"x": ("right", "left", "Left/right"), "y": ("up", "down", "Up/down")}


@dataclass(frozen=True)
class Fix:
    key: str
    label: str            # what the player says is wrong
    modes: tuple          # modes it applies to
    axes: tuple = ("x", "y")


FIXES = (
    Fix("too_slow", "Big turns are too slow", ("joystick", "hybrid", "follow")),
    Fix("too_fast", "Big turns are too fast / overshoot", ("joystick", "hybrid", "follow")),
    Fix("jumpy", "Small aiming is jumpy", ("joystick", "hybrid", "follow")),
    Fix("sticky", "Small aiming is sticky or sluggish", ("joystick", "hybrid", "follow")),
    Fix("shaky", "Shaky when I hold still", ("joystick", "hybrid", "follow")),
    Fix("laggy", "Feels laggy or floaty", ("joystick", "hybrid", "follow")),
    Fix("drifts", "Keeps moving after I stop", ("joystick", "hybrid")),
    Fix("early", "Turning starts during small aiming", ("joystick", "hybrid")),
    Fix("glance", "Glancing at the keyboard moves the camera", ("joystick", "hybrid", "follow"), ("y",)),
)


class _Edit:
    """Collects changes to a Settings object and describes them."""

    def __init__(self, settings, axis):
        self.s = settings
        self.axis = axis
        self.lines = []

    def _set(self, section, field, value, label, unit="", fmt="{:g}"):
        old = getattr(getattr(self.s, section), field)
        if isinstance(old, float):
            value = round(value, 2)
        if value == old:
            return False
        self.s = dataclasses.replace(self.s, **{section: dataclasses.replace(getattr(self.s, section),
                                                                             **{field: value})})
        if isinstance(value, bool):
            self.lines.append(f"{label}: {'on' if value else 'off'}")
        else:
            self.lines.append(f"{label} {fmt.format(old)} → {fmt.format(value)}{unit}")
        return True

    def both(self, field, change, label, unit="", lo=None, hi=None):
        """Change a per-direction field on both directions of the axis.
        lo/hi are limits: numbers, or functions of the direction's settings."""
        pos, neg, name = AXES[self.axis]
        changed = False
        for direction in (pos, neg):
            d = getattr(self.s, direction)
            if d.points:
                continue
            value = change(getattr(d, field))
            if hi is not None:
                value = min(hi(d) if callable(hi) else hi, value)
            if lo is not None:
                value = max(lo(d) if callable(lo) else lo, value)
            changed |= self._set(direction, field, value, f"{direction.title()} {label}", unit)
        self._keep_valid()
        return changed

    def axis_value(self, section, field_x, field_y, change, label, unit="", lo=None, hi=None):
        field = field_x if self.axis == "x" else field_y
        value = change(getattr(getattr(self.s, section), field))
        value = min(hi, value) if hi is not None else value
        value = max(lo, value) if lo is not None else value
        return self._set(section, field, value, f"{AXES[self.axis][2]} {label}", unit)

    def flag(self, section, field, value, label):
        return self._set(section, field, value, label)

    def _keep_valid(self):
        for direction in AXES[self.axis][:2]:
            d = getattr(self.s, direction)
            values = {}
            if d.full_speed_angle <= d.deadzone:
                values["full_speed_angle"] = round(d.deadzone + 1.0, 2)
            if d.min_speed > d.max_speed:
                values["min_speed"] = d.max_speed
            if values:
                self.s = dataclasses.replace(self.s, **{direction: dataclasses.replace(d, **values)})


def available(settings, axis):
    """The fixes that make sense for this pair of directions in its current mode."""
    mode = axis_modes(settings)[0 if axis == "x" else 1]
    return [f for f in FIXES if mode in f.modes and axis in f.axes]


def apply(settings, axis, key):
    """(new settings, [what changed]) for fix `key` on axis "x" or "y".
    An empty list means nothing more can be done that way (a limit was reached)."""
    mode = axis_modes(settings)[0 if axis == "x" else 1]
    e = _Edit(settings, axis)
    gain = ("assist", "vertical_follow_gain", "vertical_follow_gain") if mode == "follow" \
        else ("assist", "hybrid_gain_x", "hybrid_gain_y")
    mouse = mode in ("hybrid", "follow")
    stick = mode in ("joystick", "hybrid")
    area = "mouse-like area" if mode == "hybrid" else "dead zone"
    webcam = settings.tracking.source == "webcam"   # steadiness is the webcam's filter

    if key == "too_slow":
        if stick:
            e.both("max_speed", lambda v: v * 1.25, "top speed", "°/s", hi=720)
            e.both("full_speed_angle", lambda v: v * 0.9, "head turn for full speed", "°",
                   lo=lambda d: max(4.0, d.deadzone + 1.0))
        else:
            e.axis_value(*gain, lambda v: v * 1.25, "sensitivity", "x", hi=10)
    elif key == "too_fast":
        if stick:
            e.both("max_speed", lambda v: v * 0.8, "top speed", "°/s", lo=10)
            e.both("curve", lambda v: v + 0.25, "curve", hi=6)
        else:
            e.axis_value(*gain, lambda v: v * 0.8, "sensitivity", "x", lo=0.1)
    elif key == "jumpy":
        if mouse:
            e.axis_value(*gain, lambda v: v * 0.8, "sensitivity", "x", lo=0.1)
            e.axis_value("assist", "slow_precision_x", "slow_precision_y",
                         lambda v: 0.6 if v >= 1.0 else v - 0.1, "slow-movement precision", lo=0.2)
        else:
            e.both("min_speed", lambda v: v * 0.7, "slowest speed", "°/s", lo=0)
            e.both("curve", lambda v: v + 0.3, "curve", hi=6)
    elif key == "sticky":
        if mouse:
            e.axis_value("assist", "wobble_x", "wobble_y", lambda v: v - 0.05, "wobble filter", "°", lo=0.1)
            a = settings.assist
            slow = a.slow_precision_x if axis == "x" else a.slow_precision_y
            if slow < 1.0:
                e.axis_value("assist", "slow_precision_x", "slow_precision_y", lambda v: v + 0.1,
                             "slow-movement precision", hi=1.0)
            else:
                e.axis_value(*gain, lambda v: v * 1.2, "sensitivity", "x", hi=10)
        else:
            e.both("min_speed", lambda v: v * 1.3 + 0.5, "slowest speed", "°/s", hi=lambda d: d.max_speed)
            e.both("deadzone", lambda v: v - 0.5, area, "°", lo=0.5)
    elif key == "shaky":
        if webcam:
            e.axis_value("webcam", "smoothing_min_cutoff", "vertical_smoothing_min_cutoff",
                         lambda v: v * 0.7, "steadiness", lo=0.1)
        if mouse:
            e.axis_value("assist", "wobble_x", "wobble_y", lambda v: v + 0.1, "wobble filter", "°", hi=1.0)
        else:
            e.both("deadzone", lambda v: v + 0.5, area, "°", hi=20)
    elif key == "laggy":
        if webcam:
            e.axis_value("webcam", "smoothing_min_cutoff", "vertical_smoothing_min_cutoff",
                         lambda v: v * 1.4, "steadiness", hi=8)
        if mode == "hybrid":
            e.axis_value("assist", "hybrid_blend", "hybrid_blend_y", lambda v: v - 1.0, "blend", "°", lo=0)
    elif key == "drifts":
        if not e.flag("assist", "return_stop", True, "Stop when I come back to the middle"):
            e.both("deadzone", lambda v: v + 0.5, area, "°", hi=20)
    elif key == "early":
        e.both("deadzone", lambda v: v + 1.0, area, "°", hi=20)
        if mode == "joystick":
            e.both("start_delay", lambda v: v + 0.1, "start delay", " s", hi=2)
    elif key == "glance":
        if not settings.glance.enabled:
            e.flag("glance", "enabled", True, "Pause the camera when I look away")
            if webcam:
                e.flag("glance", "eye_check", True, "Use my eyes to spot glances")
        elif mouse:
            e.axis_value("assist", "mouse_delay_x", "mouse_delay_y", lambda v: v + 0.1,
                         "mouse-like start delay", " s", hi=1)
        else:
            e.both("start_delay", lambda v: v + 0.1, "start delay", " s", hi=2)
    else:
        raise ValueError(f"unknown fix {key!r}")
    return e.s, e.lines


def tip(settings, axis, key):
    """A suggestion beyond the change itself, or None."""
    mode = axis_modes(settings)[0 if axis == "x" else 1]
    if key in ("jumpy", "sticky") and mode == "joystick":
        return "for small, exact aiming, Mouse + joystick (Settings > Feel) usually works much better."
    if key == "glance" and not settings.glance.enabled:
        return "run the setup wizard once (Settings > Tracking) so HeadMouse learns your glances."
    if key == "shaky" and settings.tracking.source == "webcam":
        return "even light on your face makes the webcam steadier than any setting."
    return None


# --- fixing a situation's feel (its preset) ------------------------------------------

def target_feel(path, base, situation):
    """(feel, preset name) to fix: the normal settings (situation None), or a situation's preset."""
    from .config import load_preset
    if situation is None:
        return base, None
    preset = getattr(base.situations, f"{situation}_preset")
    return load_preset(path, preset, base), preset


def store(path, base, situation, preset, new_feel):
    """Keep a fixed feel. For a situation, the preset part goes into its preset (a copy named
    "<Situation> (adjusted)" if it is built in) and anything else into the normal settings.
    Returns the new normal settings."""
    from .config import PRESET_ASSIST, PRESET_SECTIONS, SITUATION_NAMES, SettingsError, is_builtin_preset, save_preset
    if situation is None:
        return new_feel
    if not preset:
        raise SettingsError(f"the {SITUATION_NAMES[situation]} feel has no preset")
    name = f"{SITUATION_NAMES[situation]} (adjusted)" if is_builtin_preset(preset) else preset
    save_preset(path, name, new_feel)
    out = base
    for f in dataclasses.fields(base):
        if f.name in PRESET_SECTIONS and f.name != "assist":
            continue
        section = getattr(new_feel, f.name)
        if f.name == "assist":   # only the helpers, not the preset's own mouse-like settings
            section = dataclasses.replace(base.assist, **{k: getattr(section, k)
                                                          for k in vars(section) if k not in PRESET_ASSIST})
        out = dataclasses.replace(out, **{f.name: section})
    if name != preset:
        out = dataclasses.replace(out, situations=dataclasses.replace(out.situations,
                                                                      **{f"{situation}_preset": name}))
    return out
