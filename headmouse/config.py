"""Loading and validating headmouse_settings.toml.

Every setting has a default here, so a missing or partial settings file still works.
The section and field names below match the settings file exactly.
"""

import dataclasses
import math
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .keys import key_code


TRACKING_SOURCES = ("webcam", "opentrack")


@dataclass
class TrackingSettings:
    source: str = "webcam"


@dataclass
class WebcamSettings:
    camera_index: int = 0
    frame_width: int = 640
    frame_height: int = 480
    fps: int = 30
    smoothing_min_cutoff: float = 1.0
    smoothing_beta: float = 0.05
    neutral_yaw: float = 0.0
    neutral_pitch: float = 0.0
    yaw_right_is_positive: bool = True
    pitch_up_is_positive: bool = True
    model_path: str = ""


@dataclass
class OpenTrackSettings:
    listen_address: str = "127.0.0.1"
    port: int = 4242
    yaw_right_is_positive: bool = True
    pitch_up_is_positive: bool = True
    launch_opentrack: bool = True
    opentrack_exe: str = ""


@dataclass
class KeySettings:
    pause_hold: str = "F9"
    enable_toggle: str = "F10"
    recenter: str = "F8"
    precision_hold: str = "F7"
    calibrate_turn: str = "F6"


@dataclass
class GeneralSettings:
    start_enabled: bool = False
    output_rate_hz: float = 125.0
    game_window_title: str = "Enshrouded"
    auto_enable_in_game: bool = True
    only_move_in_game_window: bool = False
    always_on_top: bool = False
    show_status: bool = True
    setup_done: bool = False


@dataclass
class SoundSettings:
    enabled: bool = True
    volume: float = 0.5
    on_enable_disable: bool = True
    on_tracking_lost: bool = True
    on_pause: bool = False


@dataclass
class MouseSettings:
    counts_per_360: float = 4000.0
    vertical_scale: float = 1.0
    invert_vertical: bool = False
    max_counts_per_tick: int = 400
    calibrate_turn_seconds: float = 3.0


@dataclass
class MotionSettings:
    smoothing_seconds: float = 0.04
    deadzone_hysteresis: float = 0.3
    reverse_delay_seconds: float = 0.15
    require_center_to_resume: bool = False
    precision_speed_factor: float = 0.2


@dataclass
class SafetySettings:
    no_data_timeout: float = 0.25
    frozen_data_timeout: float = 1.0
    max_jump_degrees: float = 25.0
    jump_holdoff_seconds: float = 0.5
    max_valid_yaw: float = 120.0
    max_valid_pitch: float = 90.0


@dataclass
class DirectionSettings:
    deadzone: float = 3.0
    min_speed: float = 7.5
    max_speed: float = 180.0
    full_speed_angle: float = 15.0
    curve: float = 2.45
    points: list = field(default_factory=list)


def _horizontal():
    return DirectionSettings(deadzone=3.0, min_speed=7.5, max_speed=180.0,
                             full_speed_angle=15.0, curve=2.45)


def _vertical():
    return DirectionSettings(deadzone=2.0, min_speed=4.0, max_speed=60.0,
                             full_speed_angle=10.0, curve=1.95)


@dataclass
class Settings:
    tracking: TrackingSettings = field(default_factory=TrackingSettings)
    webcam: WebcamSettings = field(default_factory=WebcamSettings)
    opentrack: OpenTrackSettings = field(default_factory=OpenTrackSettings)
    keys: KeySettings = field(default_factory=KeySettings)
    general: GeneralSettings = field(default_factory=GeneralSettings)
    sounds: SoundSettings = field(default_factory=SoundSettings)
    mouse: MouseSettings = field(default_factory=MouseSettings)
    motion: MotionSettings = field(default_factory=MotionSettings)
    safety: SafetySettings = field(default_factory=SafetySettings)
    right: DirectionSettings = field(default_factory=_horizontal)
    left: DirectionSettings = field(default_factory=_horizontal)
    up: DirectionSettings = field(default_factory=_vertical)
    down: DirectionSettings = field(default_factory=_vertical)

    def source_settings(self):
        """The [webcam] or [opentrack] section for the tracker in use."""
        return getattr(self, self.tracking.source)

    def key(self, name):
        """Virtual-key code for one of the [keys] entries, or None if disabled."""
        return key_code(getattr(self.keys, name))


class SettingsError(Exception):
    pass


def _convert(section, name, value, default):
    where = f"[{section}] {name}"
    if isinstance(default, bool):
        if not isinstance(value, bool):
            raise SettingsError(f"{where} must be true or false, got {value!r}")
        return value
    if isinstance(default, int):
        if isinstance(value, bool) or not isinstance(value, int):
            raise SettingsError(f"{where} must be a whole number, got {value!r}")
        return value
    if isinstance(default, float):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise SettingsError(f"{where} must be a number, got {value!r}")
        if not math.isfinite(value):
            raise SettingsError(f"{where} must be a finite number")
        return float(value)
    if isinstance(default, str):
        if not isinstance(value, str):
            raise SettingsError(f"{where} must be text in quotes, got {value!r}")
        return value
    if isinstance(default, list):
        if not isinstance(value, list):
            raise SettingsError(f"{where} must be a list")
        return value
    raise SettingsError(f"{where}: unsupported setting type")


def from_dict(data):
    """Build Settings from a parsed TOML dict. Returns (settings, warnings)."""
    settings = Settings()
    warnings = []
    sections = {f.name for f in dataclasses.fields(Settings)}
    for section_name, values in data.items():
        if section_name not in sections:
            warnings.append(f"unknown section [{section_name}] ignored")
            continue
        if not isinstance(values, dict):
            raise SettingsError(f"[{section_name}] must be a section")
        section = getattr(settings, section_name)
        known = {f.name: getattr(section, f.name) for f in dataclasses.fields(section)}
        for name, value in values.items():
            if name not in known:
                warnings.append(f"unknown setting [{section_name}] {name} ignored")
                continue
            setattr(section, name, _convert(section_name, name, value, known[name]))
    validate(settings)
    return settings, warnings


def _check(condition, message):
    if not condition:
        raise SettingsError(message)


def _validate_direction(name, d):
    _check(d.deadzone >= 0, f"[{name}] deadzone must be 0 or more")
    if d.points:
        pts = d.points
        _check(len(pts) >= 2, f"[{name}] points needs at least two [angle, speed] pairs")
        for p in pts:
            _check(isinstance(p, list) and len(p) == 2
                   and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in p),
                   f"[{name}] each entry in points must look like [angle, speed]")
            _check(p[1] >= 0, f"[{name}] point speeds must be 0 or more")
        angles = [p[0] for p in pts]
        _check(all(a < b for a, b in zip(angles, angles[1:])),
               f"[{name}] point angles must increase from one entry to the next")
        return
    _check(d.full_speed_angle > d.deadzone,
           f"[{name}] full_speed_angle must be larger than deadzone")
    _check(0 <= d.min_speed <= d.max_speed,
           f"[{name}] needs 0 <= min_speed <= max_speed")
    _check(d.curve > 0, f"[{name}] curve must be more than 0")


def validate(s):
    _check(s.tracking.source in TRACKING_SOURCES,
           f"[tracking] source must be one of: {', '.join(TRACKING_SOURCES)}")
    _check(s.webcam.camera_index >= 0, "[webcam] camera_index must be 0 or more")
    _check(s.webcam.frame_width > 0 and s.webcam.frame_height > 0 and s.webcam.fps > 0,
           "[webcam] frame_width, frame_height and fps must be more than 0")
    _check(s.webcam.smoothing_min_cutoff > 0, "[webcam] smoothing_min_cutoff must be more than 0")
    _check(s.webcam.smoothing_beta >= 0, "[webcam] smoothing_beta must be 0 or more")
    _check(0 < s.opentrack.port < 65536, "[opentrack] port must be between 1 and 65535")
    _check(0 <= s.sounds.volume <= 1, "[sounds] volume must be between 0 and 1")
    used = {}
    for f in dataclasses.fields(KeySettings):
        try:
            code = s.key(f.name)
        except ValueError as e:
            raise SettingsError(f"[keys] {f.name}: {e}") from None
        if code is not None:
            _check(code not in used, f"[keys] {f.name} uses the same key as {used.get(code)}")
            used[code] = f.name
    _check(20 <= s.general.output_rate_hz <= 1000, "[general] output_rate_hz must be 20-1000")
    _check(s.mouse.counts_per_360 > 0, "[mouse] counts_per_360 must be more than 0")
    _check(s.mouse.vertical_scale > 0, "[mouse] vertical_scale must be more than 0")
    _check(s.mouse.max_counts_per_tick > 0, "[mouse] max_counts_per_tick must be more than 0")
    _check(s.mouse.calibrate_turn_seconds > 0, "[mouse] calibrate_turn_seconds must be more than 0")
    _check(s.motion.smoothing_seconds >= 0, "[motion] smoothing_seconds must be 0 or more")
    _check(s.motion.deadzone_hysteresis >= 0, "[motion] deadzone_hysteresis must be 0 or more")
    _check(s.motion.reverse_delay_seconds >= 0, "[motion] reverse_delay_seconds must be 0 or more")
    _check(0 < s.motion.precision_speed_factor <= 1,
           "[motion] precision_speed_factor must be more than 0 and at most 1")
    _check(s.safety.no_data_timeout > 0, "[safety] no_data_timeout must be more than 0")
    _check(s.safety.frozen_data_timeout >= 0, "[safety] frozen_data_timeout must be 0 or more")
    _check(s.safety.max_jump_degrees > 0, "[safety] max_jump_degrees must be more than 0")
    _check(s.safety.jump_holdoff_seconds >= 0, "[safety] jump_holdoff_seconds must be 0 or more")
    for name in ("right", "left", "up", "down"):
        _validate_direction(name, getattr(s, name))


def load(path):
    """Load settings from a TOML file. Returns (settings, warnings)."""
    path = Path(path)
    if not path.exists():
        return Settings(), [f"settings file {path} not found - using built-in defaults"]
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise SettingsError(f"{path.name}: {e}") from None
    return from_dict(data)


# --- Saving -----------------------------------------------------------------
# tomllib can only read, so values are written by editing the existing file text
# in place. Comments, ordering and layout stay exactly as they were.

_SECTION_RE = re.compile(r"^\s*\[([A-Za-z0-9_.-]+)\]\s*(#.*)?$")
_VALUE_RE = r'(?:"(?:[^"\\]|\\.)*"|\[.*\]|[^#\n]*?)'


def format_value(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        text = f"{value:.4f}".rstrip("0")
        return text + "0" if text.endswith(".") else text
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, list):
        return "[" + ", ".join(format_value(v) for v in value) + "]"
    raise TypeError(f"cannot write {value!r} to the settings file")


def update_text(text, updates):
    """Return settings-file text with `updates` ({section: {key: value}}) applied."""
    lines = text.splitlines()
    pending = {sec: dict(vals) for sec, vals in updates.items()}
    section = None
    section_end = {}  # section -> index after its last non-blank line
    for i, line in enumerate(lines):
        m = _SECTION_RE.match(line)
        if m:
            section = m.group(1)
            section_end.setdefault(section, i + 1)
            continue
        if section is None:
            continue
        if line.strip():
            section_end[section] = i + 1
        todo = pending.get(section)
        if not todo:
            continue
        for key in list(todo):
            km = re.match(rf"^(\s*{re.escape(key)}\s*=\s*)({_VALUE_RE})(\s*(#.*)?)$", line)
            if km:
                lines[i] = km.group(1) + format_value(todo.pop(key)) + km.group(3)
                break
    # Keys not found: add them at the end of their section (or a new section).
    inserts = []
    for sec, todo in pending.items():
        if not todo:
            continue
        new_lines = [f"{k} = {format_value(v)}" for k, v in todo.items()]
        if sec in section_end:
            inserts.append((section_end[sec], new_lines))
        else:
            lines.extend(["", f"[{sec}]"] + new_lines)
    for index, new_lines in sorted(inserts, reverse=True):
        lines[index:index] = new_lines
    return "\n".join(lines) + "\n"


def save_values(path, updates):
    """Write {section: {key: value}} into the settings file, keeping comments."""
    path = Path(path)
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    new_text = update_text(text, updates)
    from_dict(tomllib.loads(new_text))  # never write a file that would not load
    tmp = path.with_suffix(".tmp")
    tmp.write_text(new_text, encoding="utf-8")
    tmp.replace(path)


def diff(old, new):
    """{section: {key: value}} for every setting that differs between two Settings."""
    out = {}
    for f in dataclasses.fields(Settings):
        a, b = getattr(old, f.name), getattr(new, f.name)
        for g in dataclasses.fields(a):
            va, vb = getattr(a, g.name), getattr(b, g.name)
            if va != vb:
                out.setdefault(f.name, {})[g.name] = vb
    return out
