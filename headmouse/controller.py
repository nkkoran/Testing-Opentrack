"""Turns head angles into mouse movement (joystick-style).

Pure logic with no Windows calls, so it can be tested anywhere. Each call to
MotionController.step() is one tick of the output loop.
"""

import math
from dataclasses import dataclass

from .curves import DirectionCurve
from .glance import GlanceGuard

FOLLOW_BACKLASH = 0.25   # degrees: head jitter smaller than this doesn't move the camera (vertical follow)
STEADY_SPEED = 10.0      # degrees/second: auto-center only learns while the head is this still
SETTLE_TIME = 0.2        # seconds: hybrid follows again after a turn once the head has been still this long


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
                                     a.return_stop, a.return_stop_release, a.hybrid_blend)
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
        self._turned = [0, 0]          # hybrid: direction of the last joystick turn, until the head settles
        self._still = [0.0, 0.0]       # hybrid: how long the head has been still (within the jitter filter)

    def _stop(self, result):
        """Stop all movement and throw away leftover fractions of a count."""
        self._acc_x = self._acc_y = 0.0
        self.reset_follow()  # follow modes pick up from wherever the head is next
        self.yaw_axis.reset()
        self.pitch_axis.reset()
        if self.s.motion.require_center_to_resume:
            self._need_center = True
        result.waiting_for_center = self._need_center
        return result

    def recentered(self):
        """The neutral position changed: start over from wherever the head is now."""
        self.drift = [0.0, 0.0]
        self._smoothed = None   # the old smoothed angle would look like the head moving
        self.reset_follow()

    def reset_follow(self):
        """Forget where the head was, so the next tick can't jump (after pause, re-center...)."""
        self._follow_ref = [None, None]
        self._turned = [0, 0]
        self._still = [0.0, 0.0]

    def step(self, angles, dt, hold=False, precision=False, eye_pitch=None, blink=0.0):
        """Advance one tick.

        angles    -- (yaw, pitch) from orient(), or None when tracking is not usable
        dt        -- seconds since the previous tick
        hold      -- True while paused, disabled or otherwise not allowed to move
        precision -- True while precision (slow) mode is held
        eye_pitch -- eye direction score from the webcam (+ up), None if unknown
        blink     -- how closed the eyes are (0-1)
        """
        if angles is None:
            self._smoothed = None
            self.glance.update(None, dt)
            return self._stop(StepResult())

        tau = self.s.motion.smoothing_seconds
        if self._smoothed is None or tau <= 0:
            self._smoothed = tuple(angles)
        else:
            a = 1.0 - math.exp(-dt / tau)
            self._smoothed = tuple(p + a * (n - p) for p, n in zip(self._smoothed, angles))
        yaw, pitch = self._smoothed[0] - self.drift[0], self._smoothed[1] - self.drift[1]
        result = StepResult(yaw=yaw, pitch=pitch)
        result.glancing = self.glance.update((yaw, pitch), dt, eye_pitch, blink)
        result.gaze = self.glance.gaze

        if hold or result.glancing:
            return self._stop(result)

        if self._need_center:
            if self.yaw_axis.in_deadzone(yaw) and self.pitch_axis.in_deadzone(pitch):
                self._need_center = False
            else:
                result.waiting_for_center = True
                return result

        a = self.s.assist
        follow = a.vertical_follow
        if a.hybrid:
            yaw_speed = self._hybrid(0, yaw, dt, a.hybrid_gain_x, self.yaw_axis)
        else:
            yaw_speed = self.yaw_axis.speed(yaw, dt)
        if follow:
            pitch_speed = self._follow(1, pitch, dt, a.vertical_follow_gain)
        elif a.hybrid:
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

    def _follow(self, i, angle, dt, gain, axis=None):
        """Camera speed that turns the camera gain x the head's movement (like a mouse).

        With an axis (hybrid), only movement inside its dead zone counts, fading out
        over the blend band, and coming back from a joystick turn doesn't count.
        """
        ref = self._follow_ref[i]
        if ref is None or dt <= 0:
            self._follow_ref[i] = angle
            return 0.0
        new = min(max(ref, angle - FOLLOW_BACKLASH), angle + FOLLOW_BACKLASH)  # ignores tiny jitter
        self._follow_ref[i] = new
        if axis is None:
            return (new - ref) * gain / dt
        if self._turned[i] and (new - ref) * self._turned[i] < 0:
            return 0.0  # heading back after a turn: don't swing the camera back
        return (axis.follow_position(new) - axis.follow_position(ref)) * gain / dt

    def _hybrid(self, i, angle, dt, gain, axis):
        """Mouse-like inside the dead zone, joystick beyond it, blended in between."""
        stick = axis.speed(angle, dt) * (1.0 - axis.weight(angle))
        if axis.direction:
            self._turned[i] = axis.direction
        before = self._follow_ref[i]
        follow = self._follow(i, angle, dt, gain, axis)
        # still = jitter too small to move the follower (the same filter that keeps the camera still)
        self._still[i] = self._still[i] + dt if self._follow_ref[i] == before else 0.0
        if self._turned[i] and not axis.direction and axis.stopped_time >= axis.reverse_delay \
                and self._still[i] >= SETTLE_TIME:
            self._turned[i] = 0  # the turn is over: small movements follow again
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
