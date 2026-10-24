"""Situations: what each one is for, and a suggested feel to start from.

The suggestions are presets made from the player's current settings, changed
only where that part of the game needs something different: precise aiming,
steady building, or moving a menu pointer.
"""

import dataclasses

from .config import SITUATION_NAMES, SITUATIONS, axis_modes, mode_values

DESCRIPTIONS = {
    "aim": ("While you aim", "Slow, exact mouse-like movement while you aim a bow. In Enshrouded you aim by "
                             "holding the right mouse button (or Q) - choose that key below, and Hold."),
    "build": ("While you build", "Steady, precise placement with the construction hammer. Choose a free key to "
                                 "tap when you start and stop building."),
    "menu": ("In menus", "Mouse-like movement for moving the pointer in the inventory, map and crafting. "
                         "Switch on \"when the game shows a mouse pointer\", or choose a key to tap."),
}

SUGGESTED_KEYS = {"aim": ("RIGHTMOUSE", False), "build": ("", True), "menu": ("", True)}


def suggested_name(situation):
    return f"{SITUATION_NAMES[situation]} (suggested)"


def suggested_feel(settings, situation):
    """A starting feel for a situation, based on `settings`."""
    if situation not in SITUATIONS:
        raise ValueError(situation)
    a = settings.assist
    scaled = lambda gain, factor: max(0.3, round(gain * factor, 2))
    if situation == "aim":
        factor, area = 0.5, (4.0, 3.0)
        values = dict(slow_precision_x=0.5, slow_precision_y=0.5, wobble_x=0.15, wobble_y=0.15)
    elif situation == "build":
        factor, area = 0.6, (5.0, 4.0)
        values = dict(slow_precision_x=0.4, slow_precision_y=0.4, wobble_x=0.2, wobble_y=0.2)
    else:
        factor, area = None, (10.0, 6.0)   # up/down has less room
        values = dict(hybrid_gain_x=2.5, hybrid_gain_y=2.5, slow_precision_x=0.5, slow_precision_y=0.5,
                      mouse_delay_x=0.0, mouse_delay_y=0.0)
    if factor:
        values.update(hybrid_gain_x=scaled(a.hybrid_gain_x, factor), hybrid_gain_y=scaled(a.hybrid_gain_y, factor),
                      vertical_follow_gain=scaled(a.vertical_follow_gain, factor))
    # mouse-like for both; up/down keeps "Mouse only" if that's what the player uses
    values.update(mode_values("hybrid", "follow" if axis_modes(settings)[1] == "follow" else "hybrid"))
    out = dataclasses.replace(settings, assist=dataclasses.replace(a, **values))
    for name in ("right", "left", "up", "down"):
        d = getattr(out, name)
        if d.points:
            continue
        dz = max(d.deadzone, area[0] if name in ("right", "left") else area[1])
        out = dataclasses.replace(out, **{name: dataclasses.replace(
            d, deadzone=dz, full_speed_angle=max(d.full_speed_angle, dz + 6.0))})
    return out
