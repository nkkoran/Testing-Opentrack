"""Click actions: mouse buttons (and a few HeadMouse commands) from keys or face gestures.

For a player who can't use the mouse buttons. A key (or foot pedal) can act as a
mouse button, and so can a facial gesture seen by the webcam - like Google's
Project Gameface. Gestures are smoothed, must pass a threshold for a moment (so
talking doesn't click) and are released a little below it (so they don't
flicker). Everything here is plain logic; the engine sends the buttons.
"""

import math
from dataclasses import dataclass

# Gesture -> MediaPipe face blendshapes it is read from (the score is their average,
# or the biggest group for eyebrows, which some people raise in the middle only).
GESTURES = {"mouth": "Open mouth", "brows": "Raise eyebrows", "smile": "Smile", "pucker": "Pucker lips"}

ACTIONS = {
    "": "Nothing",
    "left": "Left mouse button (held while held)",
    "right": "Right mouse button (held while held)",
    "middle": "Middle mouse button (held while held)",
    "left_click": "Left click",
    "right_click": "Right click",
    "left_toggle": "Left button on/off",
    "right_toggle": "Right button on/off",
    "recenter": "Re-center",
    "precision": "Precision aim on/off",
    "freeze": "Freeze camera on/off",
}
BUTTONS = ("left", "right", "middle")
CLICK_SECONDS = 0.06     # a click holds the button this long, so every game notices it
SMOOTHING = 0.08         # seconds: gesture scores are averaged over about this long
RELEASE = 0.75           # a gesture ends when it falls below this share of its threshold
STEADY_FROM = 0.3        # steady camera: from this share of the threshold on the way up...
STEADY_AFTER = 0.25      # ...until this long after the gesture starts or ends
STEADY_MAX_RISE = 0.3    # but never longer than this for a gesture that may be starting (talking moves the mouth too)


def face_scores(blendshapes):
    """{gesture: 0..1} from MediaPipe face blendshapes (objects with category_name and score)."""
    s = {c.category_name: c.score for c in blendshapes}
    g = lambda *names: sum(s.get(n, 0.0) for n in names) / len(names)
    return {"mouth": g("jawOpen"),
            "brows": max(g("browInnerUp"), g("browOuterUpLeft", "browOuterUpRight")),
            "smile": g("mouthSmileLeft", "mouthSmileRight"),
            "pucker": g("mouthPucker")}


class GestureDetector:
    """Turns noisy gesture scores into on/off, with a hold time and hysteresis."""

    def __init__(self):
        self.level = {}       # smoothed scores
        self.active = set()
        self._above = {}      # since when each gesture has been above its threshold
        self._changed = {}    # when each gesture last started or ended
        self.raw = {}         # latest unsmoothed scores (to notice a gesture starting as early as possible)
        self._rising = {}     # since when each gesture may be starting

    def update(self, scores, now, dt, thresholds, hold):
        """scores: {gesture: 0..1} or None (no face). Returns the set of active gestures."""
        if scores is None:
            self.level.clear()
            self._above.clear()
            self._changed.clear()
            self.active = set()
            return self.active
        a = 1.0 - math.exp(-dt / SMOOTHING) if dt > 0 else 1.0
        self.raw = dict(scores)
        for name, value in scores.items():
            level = self.level.get(name, value)
            level += (value - level) * a
            self.level[name] = level
            threshold = thresholds.get(name, 1.1)
            if name in self.active:
                if level < threshold * RELEASE:
                    self.active.discard(name)
                    self._above.pop(name, None)
                    self._changed[name] = now
            elif level >= threshold:
                since = self._above.setdefault(name, now)
                if now - since >= hold:
                    self.active.add(name)
                    self._changed[name] = now
            else:
                self._above.pop(name, None)
        return self.active

    def changing(self, now, thresholds, gestures):
        """True while one of `gestures` is starting or ending - the face is moving, so the head
        angle may jump a little (opening the mouth tilts the face)."""
        for name in gestures:
            level = max(self.level.get(name, 0.0), self.raw.get(name, 0.0))
            threshold = thresholds.get(name, 1.1)
            if name not in self.active and level >= threshold * STEADY_FROM:
                if now - self._rising.setdefault(name, now) < STEADY_MAX_RISE:
                    return True                   # on the way up
                continue
            self._rising.pop(name, None)
            if now - self._changed.get(name, -1e9) < STEADY_AFTER:
                return True                       # just started or ended
        return False


@dataclass
class Output:
    buttons: set           # mouse buttons that should be down
    commands: list         # HeadMouse commands to run now: "recenter", "precision", "freeze"


class Actions:
    """Combines bindings (source -> action) into button states and commands.
    A source is anything that can be held: a key or a gesture."""

    def __init__(self):
        self.toggled = set()      # "left_toggle", "right_toggle" currently on
        self._was = {}            # source -> held last time
        self._click_until = {}    # button -> time a click ends

    def reset(self):
        """Forget toggles and clicks (head control off, game not in front...)."""
        self.toggled.clear()
        self._click_until.clear()

    def update(self, bindings, held, now):
        """bindings: [(source, action)]; held: {source: bool}. Returns Output."""
        buttons, commands = set(), []
        for source, action in bindings:
            down = bool(held.get(source))
            pressed = down and not self._was.get(source, False)
            self._was[source] = down
            if not action:
                continue
            if action in BUTTONS:
                if down:
                    buttons.add(action)
            elif action.endswith("_click"):
                if pressed:
                    self._click_until[action[:-6]] = now + CLICK_SECONDS
            elif action.endswith("_toggle"):
                if pressed:
                    self.toggled ^= {action}
            elif pressed:
                commands.append(action)
        for toggle in self.toggled:
            buttons.add(toggle[:-7])
        for button, until in list(self._click_until.items()):
            if now < until:
                buttons.add(button)
            else:
                del self._click_until[button]
        return Output(buttons, commands)


def bindings(settings):
    """[(source, action)] from the [actions] settings: ("key:<name>", action) and ("face:<gesture>", action)."""
    a = settings.actions
    if not a.enabled:
        return []
    out = [(f"key:{getattr(a, f'key{i}')}", getattr(a, f"key{i}_action")) for i in (1, 2, 3)
           if getattr(a, f"key{i}") and getattr(a, f"key{i}_action")]
    out += [(f"face:{g}", getattr(a, f"{g}_action")) for g in GESTURES if getattr(a, f"{g}_action")]
    return out


def uses_gestures(settings):
    return any(source.startswith("face:") for source, _ in bindings(settings))


def thresholds(settings):
    return {g: getattr(settings.actions, f"{g}_threshold") for g in GESTURES}


def suggest_threshold(rest, peak):
    """From levels seen while relaxed and while making a gesture: (threshold or None, verdict).
    The threshold sits between the relaxed level (its 95th percentile) and the gesture level
    (its median), so a clear gesture counts and an ordinary face doesn't."""
    if not rest or not peak:
        return None, "not measured"
    rest_level = sorted(rest)[min(len(rest) - 1, int(len(rest) * 0.95))]
    peak_level = sorted(peak)[len(peak) // 2]
    gap = peak_level - rest_level
    if gap < 0.12:
        return None, "hard to see - try another gesture"
    threshold = round(min(0.95, max(0.1, rest_level + gap * 0.5)) * 20) / 20
    return threshold, "clear" if gap >= 0.3 else "weak - make it bigger, or try another"
