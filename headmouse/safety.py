"""Decides whether the latest head-tracking data can be trusted.

If anything looks wrong the program stops moving the camera instead of guessing.
"""

import math
from enum import Enum


class TrackingStatus(Enum):
    OK = "ok"
    NO_DATA = "no tracking data"
    FROZEN = "tracking frozen"
    INVALID = "bad tracking data"
    UNSTABLE = "tracking jumped"


class TrackingMonitor:
    def __init__(self, safety):
        self.s = safety
        self._last_sequence = None
        self._last_values = None
        self._last_change = None
        self._last_valid = None      # (yaw, pitch) of the previous valid sample
        self._unstable_until = -math.inf
        self.last_status = TrackingStatus.NO_DATA

    def check(self, sample, now):
        """Return (status, (yaw, pitch) or None) for the most recent sample."""
        status, angles = self._check(sample, now)
        self.last_status = status
        return status, angles

    def _check(self, sample, now):
        s = self.s
        if sample is None or now - sample.received_at > s.no_data_timeout:
            return TrackingStatus.NO_DATA, None

        if sample.sequence != self._last_sequence:
            self._last_sequence = sample.sequence
            if not self._is_valid(sample):
                self._last_valid = None
                return TrackingStatus.INVALID, None
            if sample.values != self._last_values:
                self._last_values = sample.values
                self._last_change = now
            if self._last_valid is not None:
                jump = max(abs(sample.yaw - self._last_valid[0]),
                           abs(sample.pitch - self._last_valid[1]))
                if jump > s.max_jump_degrees:
                    self._unstable_until = now + s.jump_holdoff_seconds
            self._last_valid = (sample.yaw, sample.pitch)
        elif self._last_valid is None:
            return TrackingStatus.INVALID, None

        if s.frozen_data_timeout > 0 and now - self._last_change > s.frozen_data_timeout:
            return TrackingStatus.FROZEN, None
        if now < self._unstable_until:
            return TrackingStatus.UNSTABLE, None
        return TrackingStatus.OK, (sample.yaw, sample.pitch)

    def _is_valid(self, sample):
        if not all(math.isfinite(v) for v in sample.values):
            return False
        return (abs(sample.yaw) <= self.s.max_valid_yaw
                and abs(sample.pitch) <= self.s.max_valid_pitch)
