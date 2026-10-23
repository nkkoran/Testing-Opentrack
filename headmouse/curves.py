"""Speed curves: how fast the camera turns for a given head angle in one direction."""

import bisect


class MonotoneSpline:
    """Smooth curve through (x, y) points that never overshoots between them.

    Uses Fritsch-Carlson monotone cubic interpolation: if the speeds in the table
    only ever increase, the curve between the points only ever increases too.
    Outside the table the end values are held.
    """

    def __init__(self, points):
        self.xs = [float(p[0]) for p in points]
        self.ys = [float(p[1]) for p in points]
        n = len(self.xs)
        h = [self.xs[i + 1] - self.xs[i] for i in range(n - 1)]
        delta = [(self.ys[i + 1] - self.ys[i]) / h[i] for i in range(n - 1)]
        m = [0.0] * n
        m[0], m[-1] = delta[0], delta[-1]
        for i in range(1, n - 1):
            if delta[i - 1] * delta[i] <= 0:
                m[i] = 0.0
            else:
                w1 = 2 * h[i] + h[i - 1]
                w2 = h[i] + 2 * h[i - 1]
                m[i] = (w1 + w2) / (w1 / delta[i - 1] + w2 / delta[i])
        for i in range(n - 1):
            if delta[i] == 0:
                m[i] = m[i + 1] = 0.0
        self.m = m

    def __call__(self, x):
        xs, ys, m = self.xs, self.ys, self.m
        if x <= xs[0]:
            return ys[0]
        if x >= xs[-1]:
            return ys[-1]
        i = bisect.bisect_right(xs, x) - 1
        h = xs[i + 1] - xs[i]
        t = (x - xs[i]) / h
        t2, t3 = t * t, t * t * t
        return ((2 * t3 - 3 * t2 + 1) * ys[i] + (t3 - 2 * t2 + t) * h * m[i]
                + (-2 * t3 + 3 * t2) * ys[i + 1] + (t3 - t2) * h * m[i + 1])


class DirectionCurve:
    """Camera speed (degrees/second) for head angles in one direction.

    Formula mode (default):
        angle <= deadzone          -> 0
        deadzone .. full_speed     -> min_speed + (max_speed - min_speed) * t ** curve
                                      where t goes 0 -> 1 across that range
        angle >= full_speed_angle  -> max_speed

    Table mode (when `points` is set): speeds are read from a smooth curve through
    the [angle, speed] points; the deadzone still applies.
    """

    def __init__(self, settings):
        self.deadzone = settings.deadzone
        self.start_delay = settings.start_delay
        self._settings = settings
        self._spline = MonotoneSpline(settings.points) if settings.points else None

    def speed(self, angle):
        """Speed for an absolute head angle; 0 inside the dead zone."""
        if angle <= self.deadzone:
            return 0.0
        return self.speed_beyond_deadzone(angle)

    def speed_beyond_deadzone(self, angle):
        """Speed as if the angle were at least at the dead-zone edge.

        Used while the head drifts back a fraction of a degree inside the dead
        zone (hysteresis) so movement does not flicker on and off at the edge.
        """
        angle = max(angle, self.deadzone)
        if self._spline is not None:
            return max(0.0, self._spline(angle))
        s = self._settings
        t = (angle - s.deadzone) / (s.full_speed_angle - s.deadzone)
        t = min(max(t, 0.0), 1.0)
        return s.min_speed + (s.max_speed - s.min_speed) * t ** s.curve
