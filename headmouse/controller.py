"""Turns head angles into mouse movement (joystick-style).

Pure logic with no Windows calls, so it can be tested anywhere. Each call to
MotionController.step() is one tick of the output loop.
"""

import math
from dataclasses import dataclass

from .config import axis_modes
from .curves import DirectionCurve
from .glance import GlanceGuard

SPEED_RISE = 0.02        # seconds: the head speed estimate (slow-movement precision) catches up with a quick
SPEED_FALL = 0.15        # move fast, and settles slowly, so tracker jitter doesn't make it flicker
STEADY_SPEED = 10.0      # degrees/second: auto-center only learns while the head is this still
SETTLE_TIME = 0.2        # seconds: hybrid follows again after a turn once the head has been still this long
TURN_TRAVEL = 0.2        # camera degrees: once the joystick has turned this much, coming back won't swing back
CATCH_UP = 0.1           # seconds: after the mouse-like start delay, the camera catches up about this fast


def orient(raw, settings, offset=(0.0, 0.0)):
    """Convert tracker angles to (yaw, pitch) where right and up are positive."""
    yaw, pitch = raw
    source = settings.source_settings()
    if not source.yaw_right_is_positive:
        yaw = -yaw
    if not source.pitch_up_is_positive:
        pitch = -pitch
    return yaw - offset[0], pitch - offset[1]


class AxisMotion:
    """One axis (yaw or pitch). Positive angles use `positive`, negative use `negative`.

    Direction only reverses after the head has been back inside the dead zone
    (stopped) for at least `reverse_delay` seconds, so returning toward center can
    slow the camera but never turn it the other way. Movement in a direction only
    starts once the head has stayed past its dead zone for that direction's
    `start_delay` (so a quick glance doesn't move the camera).

    With `return_stop`, coming back to the middle after a turn locks the axis:
    it stays still until the head moves `release` degrees away from where it came
    to rest (and past the dead zone), so resting slightly off center can't creep.

    `blend` (hybrid mode) is how many degrees past the dead zone mouse-like
    following fades out while the joystick fades in.
    """

    def __init__(self, positive, negative, hysteresis, reverse_delay, return_stop=False, release=2.5,
                 blend=0.0):
        self.positive = positive
        self.negative = negative
        self.hysteresis = hysteresis
        self.reverse_delay = reverse_delay
        self.return_stop = return_stop
        self.release = release
        self.blend = blend
        self.reset()

    def reset(self):
        self.direction = 0        # -1, 0 or +1: what the axis is doing right now
        self.last_direction = 0   # last non-zero direction, for the reversal guard
        self.stopped_time = math.inf
        self.pending = 0.0        # time spent waiting out the start delay
        self.locked = False       # return_stop: back in the middle, waiting for a clear new turn
        self.anchor = 0.0         # where the head rests while locked

    def in_deadzone(self, angle):
        curve = self.positive if angle >= 0 else self.negative
        return abs(angle) <= curve.deadzone

    def _clamp_to_deadzone(self, angle):
        return max(-self.negative.deadzone, min(self.positive.deadzone, angle))

    def weight(self, angle):
        """Hybrid: how much head movement here is followed like a mouse (1 in the dead zone, fading to 0)."""
        over = abs(angle) - (self.positive if angle >= 0 else self.negative).deadzone
        if over <= 0:
            return 1.0
        if over >= self.blend:
            return 0.0
        return 1.0 - over / self.blend

    def follow_position(self, angle):
        """Hybrid: the weight added up from 0 to angle, i.e. where following puts the camera (per unit gain)."""
        dz = (self.positive if angle >= 0 else self.negative).deadzone
        over = abs(angle) - dz
        if over <= 0:
            return angle
        over = min(over, self.blend)
        fade = over * over / (2 * self.blend) if self.blend > 0 else 0.0
        return math.copysign(dz + over - fade, angle)

    def speed(self, angle, dt):
        """Signed camera speed in degrees/second for this tick."""
        sign = 1 if angle > 0 else -1 if angle < 0 else 0
        curve = self.positive if sign >= 0 else self.negative
        magnitude = abs(angle)
        hysteresis = min(self.hysteresis, curve.deadzone * 0.5)

        if self.locked:
            if magnitude <= curve.deadzone:
                self.anchor = angle                      # follow the resting position
            elif abs(angle - self.anchor) >= self.release:
                self.locked = False                      # a clear new turn
            if self.locked:
                self.direction = self.last_direction = 0
                self.pending = 0.0
                self.stopped_time += dt
                return 0.0

        if magnitude > curve.deadzone:
            wanted = sign
        elif sign != 0 and sign == self.direction and magnitude > curve.deadzone - hysteresis:
            wanted = sign  # still just past the edge: keep going at minimum speed
        else:
            wanted = 0

        if wanted != 0 and self.last_direction not in (0, wanted) \
                and self.stopped_time < self.reverse_delay:
            wanted = 0  # crossed center too quickly to count as a deliberate reversal

        if wanted != 0 and wanted != self.direction:
            self.pending += dt
            if self.pending < curve.start_delay:
                self.direction = 0
                self.stopped_time += dt
                return 0.0
        elif wanted == 0:
            self.pending = 0.0

        if wanted == 0:
            if self.return_stop and self.direction != 0:  # just came back from a turn
                self.locked = True
                self.anchor = self._clamp_to_deadzone(angle)
            self.direction = 0
            self.stopped_time += dt
            if self.stopped_time >= self.reverse_delay:
                self.last_direction = 0
            return 0.0

        self.pending = 0.0
        self.direction = self.last_direction = wanted
        self.stopped_time = 0.0
        return wanted * curve.speed_beyond_deadzone(magnitude)


@dataclass
class StepResult:
    dx: int = 0                  # mouse counts to send, + is right
    dy: int = 0                  # mouse counts to send, + is down (Windows convention)
    yaw: float = 0.0             # smoothed angles used this tick, + is right / up
    pitch: float = 0.0
    yaw_speed: float = 0.0       # camera degrees/second, + is right
    pitch_speed: float = 0.0     # camera degrees/second, + is up
    waiting_for_center: bool = False
    glancing: bool = False       # paused because the player is looking away
    gaze: float = None           # vertical gaze in degrees (+ up), when eye data is available


class MotionController:
    def __init__(self, settings):
        self.s = settings
        m, a = settings.motion, settings.assist
        self.yaw_axis = AxisMotion(DirectionCurve(settings.right), DirectionCurve(settings.left),
                                   m.deadzone_hysteresis, m.reverse_delay_seconds,
                                   a.return_stop, a.return_stop_release, a.hybrid_blend)
        self.pitch_axis = AxisMotion(DirectionCurve(settings.up), DirectionCurve(settings.down),
                                     m.deadzone_hysteresis, m.reverse_delay_seconds,
                                     a.return_stop, a.return_stop_release, a.hybrid_blend_y)
        self.modes = axis_modes(settings)
        self.counts_per_degree_x = settings.mouse.counts_per_360 / 360.0
        self.counts_per_degree_y = self.counts_per_degree_x * settings.mouse.vertical_scale
        self.glance = GlanceGuard(settings)
        self._smoothed = None
        self._acc_x = 0.0
        self._acc_y = 0.0
        self._need_center = False
        self.drift = [0.0, 0.0]        # auto-center: learned shift of the resting position
        self._previous = None          # last corrected angles, to tell resting from moving
        self._follow_ref = [None, None]  # follow modes: head angle the camera last followed (yaw, pitch)
        self.head_speed = 0.0          # smoothed head speed, degrees/second (slow-movement precision)
        self._speed_from = None        # previous smoothed angles, for head_speed
        self._turned = [0, 0]          # hybrid: direction of the last joystick turn, until the head settles
        self._travel = [0.0, 0.0]      # hybrid: camera degrees the joystick has turned in this turn
        self._still = [0.0, 0.0]       # hybrid: how long the head has been still (within the jitter filter)
        self._held = [None, None]      # mouse delay: camera movement waiting out the delay (None = not waiting)
        self._held_time = [0.0, 0.0]
        self._held_peak = [0.0, 0.0]   # mouse delay: furthest the held movement got from where it started
        self._catch_up = [0.0, 0.0]    # mouse delay: released movement still to send
        self._active = [False, False]  # mouse delay: moving already (no delay until the head rests again)
        self._rest = [0.0, 0.0]        # mouse delay: how long the mouse-like movement has been still

    def _stop(self, result, brief=False):
        """Stop all movement and throw away leftover fractions of a count. brief: only a moment
        (e.g. while a face gesture starts), so no need to come back to the middle afterwards."""
        self._acc_x = self._acc_y = 0.0
        self.reset_follow()  # follow modes pick up from wherever the head is next
        self.yaw_axis.reset()
        self.pitch_axis.reset()
        if self.s.motion.require_center_to_resume and not brief:
            self._need_center = True
        result.waiting_for_center = self._need_center
        return result

    def take_over(self, other):
        """Continue from another controller (a different feel for a situation in the game)
        without a jump: same head position, smoothing, learned center and glance state."""
        self._smoothed, self._speed_from, self.head_speed = other._smoothed, other._speed_from, other.head_speed
        self.drift = list(other.drift)
        self.glance = other.glance
        self._need_center = other._need_center
        self.reset_follow()
        self.yaw_axis.reset()
        self.pitch_axis.reset()

    def recentered(self):
        """The neutral position changed: start over from wherever the head is now."""
        self.drift = [0.0, 0.0]
        self._smoothed = self._speed_from = None   # the old angles would look like the head moving
        self.reset_follow()

    def reset_follow(self):
        """Forget where the head was, so the next tick can't jump (after pause, re-center...)."""
        self._follow_ref = [None, None]
        self._turned = [0, 0]
        self._travel = [0.0, 0.0]
        self._still = [0.0, 0.0]
        self._held = [None, None]
        self._held_time = [0.0, 0.0]
        self._held_peak = [0.0, 0.0]
        self._catch_up = [0.0, 0.0]
        self._active = [False, False]
        self._rest = [0.0, 0.0]

    def step(self, angles, dt, hold=False, precision=False, eye_pitch=None, blink=0.0, steady=False):
        """Advance one tick.

        angles    -- (yaw, pitch) from orient(), or None when tracking is not usable
        dt        -- seconds since the previous tick
        hold      -- True while paused, disabled or otherwise not allowed to move
        steady    -- True to keep still for a moment (a face gesture is starting or ending)
        precision -- True while precision (slow) mode is held
        eye_pitch -- eye direction score from the webcam (+ up), None if unknown
        blink     -- how closed the eyes are (0-1)
        """
        if angles is None:
            self._smoothed = self._speed_from = None
            self.glance.update(None, dt)
            return self._stop(StepResult())

        tau = self.s.motion.smoothing_seconds
        if self._smoothed is None or tau <= 0:
            self._smoothed = tuple(angles)
        else:
            a = 1.0 - math.exp(-dt / tau)
            self._smoothed = tuple(p + a * (n - p) for p, n in zip(self._smoothed, angles))
        yaw, pitch = self._smoothed[0] - self.drift[0], self._smoothed[1] - self.drift[1]
        self._measure_speed(dt)
        result = StepResult(yaw=yaw, pitch=pitch)
        result.glancing = self.glance.update((yaw, pitch), dt, eye_pitch, blink)
        result.gaze = self.glance.gaze

        if hold or result.glancing:
            return self._stop(result)
        if steady:
            return self._stop(result, brief=True)

        if self._need_center:
            if self.yaw_axis.in_deadzone(yaw) and self.pitch_axis.in_deadzone(pitch):
                self._need_center = False
            else:
                result.waiting_for_center = True
                return result

        a = self.s.assist
        x_mode, y_mode = self.modes
        follow = y_mode == "follow"
        if x_mode == "hybrid":
            yaw_speed = self._hybrid(0, yaw, dt, a.hybrid_gain_x, self.yaw_axis)
        else:
            yaw_speed = self.yaw_axis.speed(yaw, dt)
        if follow:
            pitch_speed = self._follow(1, pitch, dt, a.vertical_follow_gain)
        elif y_mode == "hybrid":
            pitch_speed = self._hybrid(1, pitch, dt, a.hybrid_gain_y, self.pitch_axis)
        else:
            pitch_speed = self.pitch_axis.speed(pitch, dt)
        if a.auto_center:
            self._learn_center(yaw, pitch, yaw_speed, 0.0 if follow else pitch_speed, dt, follow)
        if precision:
            yaw_speed *= self.s.motion.precision_speed_factor
            pitch_speed *= self.s.motion.precision_speed_factor
        result.yaw_speed, result.pitch_speed = yaw_speed, pitch_speed

        vertical = 1.0 if self.s.mouse.invert_vertical else -1.0  # screen y grows downward
        result.dx, self._acc_x = self._counts(self._acc_x, yaw_speed,
                                              yaw_speed * self.counts_per_degree_x * dt)
        result.dy, self._acc_y = self._counts(self._acc_y, pitch_speed,
                                              vertical * pitch_speed * self.counts_per_degree_y * dt)
        return result

    def _measure_speed(self, dt):
        """Head speed in any direction, averaged so 30 Hz tracker steps don't make it flicker."""
        last, self._speed_from = self._speed_from, self._smoothed
        if last is None or dt <= 0:
            return
        now = math.hypot(self._smoothed[0] - last[0], self._smoothed[1] - last[1]) / dt
        tau = SPEED_RISE if now > self.head_speed else SPEED_FALL
        self.head_speed += (now - self.head_speed) * (1.0 - math.exp(-dt / tau))

    def _precision(self, i):
        """Slow-movement precision: share of the sensitivity at the current head speed."""
        a = self.s.assist
        slow, fast = (a.slow_precision_x, a.fast_speed_x) if i == 0 else (a.slow_precision_y, a.fast_speed_y)
        return slow + (1.0 - slow) * min(1.0, self.head_speed / fast)

    def _follow(self, i, angle, dt, gain, axis=None):
        """Camera speed that turns the camera gain x the head's movement (like a mouse).

        With an axis (hybrid), only movement inside its dead zone counts, fading out
        over the blend band, and coming back from a joystick turn doesn't count.
        """
        ref = self._follow_ref[i]
        if ref is None or dt <= 0:
            self._follow_ref[i] = angle
            return 0.0
        wobble = self.s.assist.wobble_x if i == 0 else self.s.assist.wobble_y
        new = min(max(ref, angle - wobble), angle + wobble)  # ignores tiny jitter
        self._follow_ref[i] = new
        gain *= self._precision(i)
        if axis is None:
            moved = (new - ref) * gain
        elif self._turned[i] and (new - ref) * self._turned[i] < 0:
            moved = 0.0  # heading back after a turn: don't swing the camera back
        else:
            moved = (axis.follow_position(new) - axis.follow_position(ref)) * gain
        return self._delayed(i, moved, dt) / dt

    def _delayed(self, i, moved, dt):
        """Mouse-like start delay. Movement from rest is held until it has lasted the delay,
        then released over CATCH_UP; if the head went away and came back most of the way
        (a glance), it is dropped. Returns camera degrees to turn this tick."""
        delay = (self.s.assist.mouse_delay_x, self.s.assist.mouse_delay_y)[i]
        if delay <= 0:
            return moved
        out = 0.0
        if self._held[i] is None and not self._active[i] and moved:
            self._held[i], self._held_time[i], self._held_peak[i] = 0.0, 0.0, 0.0  # moving from rest: wait
        if self._held[i] is not None:
            self._held[i] += moved
            self._held_time[i] += dt
            self._held_peak[i] = max(self._held_peak[i], abs(self._held[i]))
            if self._held_time[i] >= delay:
                if abs(self._held[i]) >= 0.5 * self._held_peak[i]:   # still away: a real move
                    self._catch_up[i] += self._held[i]
                    self._active[i] = True
                self._held[i] = None
        else:
            out = moved
        if self._active[i]:
            self._rest[i] = self._rest[i] + dt if moved == 0 else 0.0
            if self._rest[i] >= SETTLE_TIME and not self._catch_up[i]:
                self._active[i] = False                   # resting again: the next move waits
        if self._catch_up[i]:
            step = self._catch_up[i] * min(1.0, dt / CATCH_UP)
            if abs(self._catch_up[i] - step) < 0.01:
                step = self._catch_up[i]
            self._catch_up[i] -= step
            out += step
        return out

    def _hybrid(self, i, angle, dt, gain, axis):
        """Mouse-like inside the dead zone, joystick beyond it, blended in between."""
        stick = axis.speed(angle, dt) * (1.0 - axis.weight(angle))
        if axis.direction:
            self._travel[i] += abs(stick) * dt
            if self._travel[i] >= TURN_TRAVEL:
                self._turned[i] = axis.direction          # a real turn, not a nudge past the edge
        else:
            self._travel[i] = 0.0
        before = self._follow_ref[i]
        follow = self._follow(i, angle, dt, gain, axis)
        # still = jitter too small to move the follower (the same filter that keeps the camera still)
        self._still[i] = self._still[i] + dt if self._follow_ref[i] == before else 0.0
        settled = not axis.direction and axis.stopped_time >= axis.reverse_delay and self._still[i] >= SETTLE_TIME
        if self._turned[i] and (settled or angle * self._turned[i] <= 0):
            self._turned[i] = 0  # the turn is over (or the head is back in the middle): small moves follow again
        return stick + follow

    def _learn_center(self, yaw, pitch, yaw_speed, pitch_speed, dt, skip_pitch):
        """Auto-center: while resting in the dead zone, slowly move the center to the head."""
        previous, self._previous = self._previous, (yaw, pitch)
        if previous is None or dt <= 0:
            return
        a = self.s.assist
        rate = min(1.0, dt / a.auto_center_seconds)
        for i, (angle, speed, axis) in enumerate(((yaw, yaw_speed, self.yaw_axis),
                                                   (pitch, pitch_speed, self.pitch_axis))):
            if i == 1 and skip_pitch:
                continue
            steady = abs(angle - previous[i]) / dt < STEADY_SPEED
            if speed == 0 and steady and axis.in_deadzone(angle):
                old = self.drift[i]
                self.drift[i] = max(-a.auto_center_limit, min(a.auto_center_limit, old + angle * rate))
                if self._follow_ref[i] is not None:
                    self._follow_ref[i] -= self.drift[i] - old  # the center moved, not the head

    def _counts(self, acc, speed, amount):
        """Whole counts to send now, plus the fraction carried to the next tick."""
        if speed == 0:
            return 0, 0.0
        acc += amount
        whole = int(acc)  # rounds toward zero, so the remainder keeps the same sign
        limit = self.s.mouse.max_counts_per_tick
        if abs(whole) > limit:
            return int(math.copysign(limit, whole)), 0.0
        return whole, acc - whole
