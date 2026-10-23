"""Turns head angles into mouse movement (joystick-style).

Pure logic with no Windows calls, so it can be tested anywhere. Each call to
MotionController.step() is one tick of the output loop.
"""

import math
from dataclasses import dataclass

from .curves import DirectionCurve
from .glance import GlanceGuard


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
    """

    def __init__(self, positive, negative, hysteresis, reverse_delay):
        self.positive = positive
        self.negative = negative
        self.hysteresis = hysteresis
        self.reverse_delay = reverse_delay
        self.reset()

    def reset(self):
        self.direction = 0        # -1, 0 or +1: what the axis is doing right now
        self.last_direction = 0   # last non-zero direction, for the reversal guard
        self.stopped_time = math.inf
        self.pending = 0.0        # time spent waiting out the start delay

    def in_deadzone(self, angle):
        curve = self.positive if angle >= 0 else self.negative
        return abs(angle) <= curve.deadzone

    def speed(self, angle, dt):
        """Signed camera speed in degrees/second for this tick."""
        sign = 1 if angle > 0 else -1 if angle < 0 else 0
        curve = self.positive if sign >= 0 else self.negative
        magnitude = abs(angle)
        hysteresis = min(self.hysteresis, curve.deadzone * 0.5)

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
        m = settings.motion
        self.yaw_axis = AxisMotion(DirectionCurve(settings.right), DirectionCurve(settings.left),
                                   m.deadzone_hysteresis, m.reverse_delay_seconds)
        self.pitch_axis = AxisMotion(DirectionCurve(settings.up), DirectionCurve(settings.down),
                                     m.deadzone_hysteresis, m.reverse_delay_seconds)
        self.counts_per_degree_x = settings.mouse.counts_per_360 / 360.0
        self.counts_per_degree_y = self.counts_per_degree_x * settings.mouse.vertical_scale
        self.glance = GlanceGuard(settings)
        self._smoothed = None
        self._acc_x = 0.0
        self._acc_y = 0.0
        self._need_center = False

    def _stop(self, result):
        """Stop all movement and throw away leftover fractions of a count."""
        self._acc_x = self._acc_y = 0.0
        self.yaw_axis.reset()
        self.pitch_axis.reset()
        if self.s.motion.require_center_to_resume:
            self._need_center = True
        result.waiting_for_center = self._need_center
        return result

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
        yaw, pitch = self._smoothed
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

        yaw_speed = self.yaw_axis.speed(yaw, dt)
        pitch_speed = self.pitch_axis.speed(pitch, dt)
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
