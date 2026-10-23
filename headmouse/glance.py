"""Glance guard: stop the camera while the player looks away from the screen.

Two signals, either of which pauses movement:

* Gaze below the screen (built-in webcam only). Gaze = head pitch + eye pitch.
  While steering, the eyes counter-rotate to stay on the screen (head down, eyes
  up), so gaze stays near the screen. Glancing at the keyboard moves head AND eyes
  down, so gaze drops far below it. The eyes usually move first, so this fires
  before the head has turned the camera.
* Head far beyond the normal steering range (any tracker), e.g. turning to look
  at someone in the room.

Once triggered, movement only resumes after the gaze is back on the screen, the
head is within range again and has been steady for settle_time - so returning
from the keyboard doesn't turn the camera on the way back.
"""

import math


class GlanceGuard:
    def __init__(self, settings):
        self.s = settings.glance
        self.full = {name: getattr(settings, name).full_speed_angle for name in ("right", "left", "up", "down")}
        self.limits = {name: settings.glance.look_away_factor * full for name, full in self.full.items()}
        self.active = False
        self.reason = ""
        self._eyes_off = False
        self._prev = None
        self._speed = 0.0
        self._velocity = (0.0, 0.0)  # smoothed (yaw, pitch) degrees/second
        self._steady_for = 0.0
        self.gaze = None  # degrees relative to the screen centre, + is up (for display/wizard)

    def gaze_pitch(self, head_pitch, eye_pitch):
        """Where the player is looking vertically, in degrees (+ up, - down)."""
        return head_pitch + self.s.eye_scale * (eye_pitch - self.s.eye_neutral)

    def _beyond_range(self, yaw, pitch):
        lim = self.limits
        return yaw > lim["right"] or -yaw > lim["left"] or pitch > lim["up"] or -pitch > lim["down"]

    def _flinging_out(self, yaw, pitch):
        """Past full speed and still turning outward very fast: looking away, not steering."""
        fast = self.s.look_away_speed
        if fast <= 0:
            return False
        vy, vp = self._velocity
        full = self.full
        return ((yaw > full["right"] and vy > fast) or (-yaw > full["left"] and -vy > fast)
                or (pitch > full["up"] and vp > fast) or (-pitch > full["down"] and -vp > fast))

    def update(self, angles, dt, eye_pitch=None, blink=0.0):
        """angles: (yaw, pitch) relative to neutral. Returns True while movement must stop."""
        if not self.s.enabled or angles is None:
            self.active = False
            self._prev = None
            return False
        yaw, pitch = angles
        if self._prev is not None and dt > 0:
            a = min(1.0, dt / 0.05)
            vy = (yaw - self._prev[0]) / dt
            vp = (pitch - self._prev[1]) / dt
            self._velocity = (self._velocity[0] + a * (vy - self._velocity[0]),
                              self._velocity[1] + a * (vp - self._velocity[1]))
            self._speed = math.hypot(*self._velocity)  # smoothed head speed
        self._prev = (yaw, pitch)

        if self.s.eye_check and eye_pitch is not None:
            if blink < self.s.blink_limit:  # while blinking, keep the previous decision
                self.gaze = self.gaze_pitch(pitch, eye_pitch)
                if self._eyes_off:
                    self._eyes_off = self.gaze < -0.7 * self.s.eye_threshold  # hysteresis
                else:
                    self._eyes_off = self.gaze < -self.s.eye_threshold
        else:
            self._eyes_off = False
            self.gaze = None
        far = self.s.look_away and (self._beyond_range(yaw, pitch) or self._flinging_out(yaw, pitch))

        if self._eyes_off or far:
            self.active = True
            self.reason = "eyes" if self._eyes_off else "far"
            self._steady_for = 0.0
        elif self.active:
            self._steady_for = self._steady_for + dt if self._speed < self.s.settle_speed else 0.0
            if self._steady_for >= self.s.settle_time:
                self.active = False
                self.reason = ""
        return self.active
