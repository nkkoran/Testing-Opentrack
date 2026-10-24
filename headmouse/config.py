"""Loading and validating headmouse_settings.toml.

Every setting has a default here, so a missing or partial settings file still works.
The section and field names below match the settings file exactly.
"""

import dataclasses
import math
import os
import re
import shutil
import time
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
    smoothing_min_cutoff: float = 1.0           # steadiness, left/right (Hz: lower = steadier, laggier)
    vertical_smoothing_min_cutoff: float = 1.0  # steadiness, up/down (missing = same as left/right)
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
    theme: str = "system"
    check_for_updates: bool = True
    show_status: bool = True
    setup_done: bool = False
    link_left_right: bool = False   # Settings > Feel: changing one side changes the other too
    link_up_down: bool = False
    precision_toggle: bool = False  # True: tap the precision key to switch precision aim on/off
    checkup_done: bool = False      # the practice check-up has been played (Getting started)
    freeze_toggle: bool = False     # True: tap the freeze key to freeze, tap again to continue


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
    no_data_timeout: float = 0.5
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
    start_delay: float = 0.0
    points: list = field(default_factory=list)


def _horizontal():
    return DirectionSettings(deadzone=3.0, min_speed=7.5, max_speed=180.0,
                             full_speed_angle=15.0, curve=2.45)


def _vertical(start_delay=0.0):
    return DirectionSettings(deadzone=2.0, min_speed=4.0, max_speed=60.0,
                             full_speed_angle=10.0, curve=1.95, start_delay=start_delay)


@dataclass
class GlanceSettings:
    enabled: bool = False      # opt-in: new behaviour must never change existing setups
    eye_check: bool = True
    eye_threshold: float = 15.0
    eye_scale: float = 30.0
    eye_neutral: float = 0.0
    blink_limit: float = 0.5
    look_away: bool = True
    look_away_factor: float = 1.5
    look_away_speed: float = 150.0
    settle_time: float = 0.3
    settle_speed: float = 20.0


@dataclass
class AssistSettings:
    """Optional helpers. All off unless switched on (Settings > Feel)."""
    return_stop: bool = False         # after a turn, stay still once back in the middle...
    return_stop_release: float = 2.5  # ...until the head turns this many degrees again
    auto_center: bool = False         # slowly follow the resting head position
    auto_center_seconds: float = 8.0
    auto_center_limit: float = 6.0    # never shift the center more than this (degrees)
    vertical_follow: bool = False     # up/down follows the head like a mouse
    vertical_follow_gain: float = 4.0
    hybrid: bool = False              # mouse-like inside the dead zone, joystick beyond it...
    hybrid_horizontal: bool = True    # ...for left/right
    hybrid_vertical: bool = True      # ...for up/down (unless vertical_follow)
    hybrid_gain_x: float = 3.0        # camera degrees per head degree, left/right
    hybrid_gain_y: float = 3.0        # camera degrees per head degree, up/down
    hybrid_blend: float = 2.0         # left/right: degrees past the dead zone over which mouse fades into joystick
    hybrid_blend_y: float = 2.0       # up/down (missing = same as left/right)
    mouse_delay_x: float = 0.0        # mouse-like movement from rest waits this long (s); a quick glance is ignored
    mouse_delay_y: float = 0.0
    slow_precision_x: float = 1.0     # mouse-like: share of the sensitivity for slow head movement (1 = off)...
    slow_precision_y: float = 1.0
    fast_speed_x: float = 20.0        # ...rising to the full sensitivity at this head speed (degrees/second)
    fast_speed_y: float = 20.0
    wobble_x: float = 0.25            # mouse-like: head movement smaller than this (degrees) is ignored as jitter
    wobble_y: float = 0.25


SITUATIONS = ("menu", "aim", "build")   # checked in this order: the first one active wins
SITUATION_NAMES = {"menu": "Menus", "aim": "Aiming", "build": "Building"}


@dataclass
class SituationSettings:
    """A different feel (a preset) for parts of the game. All off unless a preset is chosen."""
    aim_preset: str = ""        # preset used while aiming ("" = off)
    aim_key: str = ""           # the key or mouse button the game uses to aim
    aim_toggle: bool = False    # False: while the key is held; True: tap on, tap off
    build_preset: str = ""
    build_key: str = ""
    build_toggle: bool = True
    menu_preset: str = ""
    menu_key: str = ""
    menu_toggle: bool = True
    menu_pointer: bool = False  # also whenever the game shows a mouse pointer
    sound: bool = True          # a short blip when the feel changes


@dataclass
class ActionSettings:
    """Mouse buttons from keys or face gestures (for a player who can't use the mouse buttons)."""
    enabled: bool = False
    key1: str = ""               # a key (or foot pedal)...
    key1_action: str = ""        # ...and what it does: see actions.ACTIONS
    key2: str = ""
    key2_action: str = ""
    key3: str = ""
    key3_action: str = ""
    mouth_action: str = ""       # face gestures (built-in webcam): open mouth...
    mouth_threshold: float = 0.5
    brows_action: str = ""       # ...raise eyebrows...
    brows_threshold: float = 0.5
    smile_action: str = ""       # ...smile...
    smile_threshold: float = 0.6
    pucker_action: str = ""      # ...pucker lips
    pucker_threshold: float = 0.6
    gesture_hold: float = 0.15   # seconds a gesture must be held before it counts
    steady_gestures: bool = True  # hold the camera still for a moment while a gesture starts or ends


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
    glance: GlanceSettings = field(default_factory=GlanceSettings)
    assist: AssistSettings = field(default_factory=AssistSettings)
    situations: SituationSettings = field(default_factory=SituationSettings)
    actions: ActionSettings = field(default_factory=ActionSettings)

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


# Settings added as an up/down copy of an existing one. A file without the new key
# (saved by an older version) keeps using the old key's value for it.
INHERITED = (("webcam", "vertical_smoothing_min_cutoff", "smoothing_min_cutoff"),
             ("assist", "hybrid_blend_y", "hybrid_blend"))

AXIS_MODES = (("joystick", "hybrid"), ("joystick", "hybrid", "follow"))


def axis_modes(settings):
    """How the head moves the camera: (left/right, up/down), each "joystick", "hybrid"
    (mouse-like near the middle, joystick further out) or, up/down only, "follow" (mouse-like)."""
    a = settings.assist
    x = "hybrid" if a.hybrid and a.hybrid_horizontal else "joystick"
    y = "follow" if a.vertical_follow else "hybrid" if a.hybrid and a.hybrid_vertical else "joystick"
    return x, y


def mode_values(x, y):
    """[assist] values that give these axis modes."""
    return {"hybrid": x == "hybrid" or y == "hybrid", "hybrid_horizontal": x == "hybrid",
            "hybrid_vertical": y == "hybrid", "vertical_follow": y == "follow"}


def _inherit(data):
    """Fill in up/down copies missing from an older file (see INHERITED)."""
    for section, new, old in INHERITED:
        values = data.get(section)
        if isinstance(values, dict) and old in values and new not in values:
            data = {**data, section: {**values, new: values[old]}}
    return data


def from_dict(data):
    """Build Settings from a parsed TOML dict. Returns (settings, warnings)."""
    settings = Settings()
    warnings = []
    sections = {f.name for f in dataclasses.fields(Settings)}
    data = _inherit(data)
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
    _check(0 <= d.start_delay <= 2, f"[{name}] start_delay must be between 0 and 2 seconds")
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
    _check(s.general.theme in ("system", "light", "dark"),
           "[general] theme must be \"system\", \"light\" or \"dark\"")
    _check(s.webcam.camera_index >= 0, "[webcam] camera_index must be 0 or more")
    _check(s.webcam.frame_width > 0 and s.webcam.frame_height > 0 and s.webcam.fps > 0,
           "[webcam] frame_width, frame_height and fps must be more than 0")
    _check(s.webcam.smoothing_min_cutoff > 0 and s.webcam.vertical_smoothing_min_cutoff > 0,
           "[webcam] smoothing_min_cutoff and vertical_smoothing_min_cutoff must be more than 0")
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
    g = s.glance
    _check(g.eye_threshold > 0, "[glance] eye_threshold must be more than 0")
    _check(g.eye_scale > 0, "[glance] eye_scale must be more than 0")
    _check(0 < g.blink_limit <= 1, "[glance] blink_limit must be more than 0 and at most 1")
    _check(g.look_away_factor > 1, "[glance] look_away_factor must be more than 1")
    _check(g.look_away_speed >= 0, "[glance] look_away_speed must be 0 or more")
    _check(g.settle_time >= 0 and g.settle_speed > 0, "[glance] settle_time >= 0 and settle_speed > 0")
    a = s.assist
    _check(0.5 <= a.return_stop_release <= 10, "[assist] return_stop_release must be 0.5-10 degrees")
    _check(2 <= a.auto_center_seconds <= 60, "[assist] auto_center_seconds must be 2-60")
    _check(0 <= a.auto_center_limit <= 20, "[assist] auto_center_limit must be 0-20 degrees")
    _check(0.1 <= a.vertical_follow_gain <= 20, "[assist] vertical_follow_gain must be 0.1-20")
    _check(0.1 <= a.hybrid_gain_x <= 20 and 0.1 <= a.hybrid_gain_y <= 20,
           "[assist] hybrid_gain_x and hybrid_gain_y must be 0.1-20")
    _check(0.1 <= a.slow_precision_x <= 1 and 0.1 <= a.slow_precision_y <= 1,
           "[assist] slow_precision_x and slow_precision_y must be 0.1-1")
    _check(2 <= a.fast_speed_x <= 90 and 2 <= a.fast_speed_y <= 90,
           "[assist] fast_speed_x and fast_speed_y must be 2-90 degrees/second")
    _check(0.05 <= a.wobble_x <= 1.5 and 0.05 <= a.wobble_y <= 1.5,
           "[assist] wobble_x and wobble_y must be 0.05-1.5 degrees")
    for name in SITUATIONS:
        try:
            key_code(getattr(s.situations, f"{name}_key"))
        except ValueError as e:
            raise SettingsError(f"[situations] {name}_key: {e}") from None
    from .actions import ACTIONS, GESTURES
    act = s.actions
    for i in (1, 2, 3):
        try:
            key_code(getattr(act, f"key{i}"))
        except ValueError as e:
            raise SettingsError(f"[actions] key{i}: {e}") from None
        _check(getattr(act, f"key{i}_action") in ACTIONS, f"[actions] key{i}_action must be one of: "
               + ", ".join(repr(k) for k in ACTIONS))
    for g in GESTURES:
        _check(getattr(act, f"{g}_action") in ACTIONS, f"[actions] {g}_action must be one of: "
               + ", ".join(repr(k) for k in ACTIONS))
        _check(0.05 <= getattr(act, f"{g}_threshold") <= 1, f"[actions] {g}_threshold must be 0.05-1")
    _check(0 <= act.gesture_hold <= 1, "[actions] gesture_hold must be 0-1 seconds")
    _check(0 <= a.hybrid_blend <= 10 and 0 <= a.hybrid_blend_y <= 10,
           "[assist] hybrid_blend and hybrid_blend_y must be 0-10 degrees")
    _check(0 <= a.mouse_delay_x <= 2 and 0 <= a.mouse_delay_y <= 2,
           "[assist] mouse_delay_x and mouse_delay_y must be 0-2 seconds")


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
            start = re.match(rf"^(\s*{re.escape(key)}\s*=\s*)\[", line)
            if start and line.split("#")[0].count("[") > line.split("#")[0].count("]"):   # array over several lines
                end, depth = i, line.split("#")[0].count("[") - line.split("#")[0].count("]")
                while depth > 0 and end + 1 < len(lines):
                    end += 1
                    code = lines[end].split("#")[0]
                    depth += code.count("[") - code.count("]")
                lines[i] = start.group(1) + format_value(todo.pop(key))
                del lines[i + 1:end + 1]
                break
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


BACKUPS_KEPT = 20


def backup_folder(path):
    return Path(path).parent / "backups"


def make_backup(path):
    """Copy the settings file into backups/ (newest BACKUPS_KEPT are kept). Returns the copy."""
    path = Path(path)
    if not path.exists():
        return None
    folder = backup_folder(path)
    folder.mkdir(exist_ok=True)
    stamp = time.strftime("%Y-%m-%d_%H-%M-%S")
    dest = folder / f"{path.stem}_{stamp}{path.suffix}"
    n = 1
    while dest.exists():
        n += 1
        dest = folder / f"{path.stem}_{stamp}_{n}{path.suffix}"
    shutil.copy2(path, dest)
    for old in list_backups(path)[BACKUPS_KEPT:]:
        old.unlink(missing_ok=True)
    return dest


def list_backups(path):
    """Backups of the settings file, newest first."""
    folder = backup_folder(path)
    stem = Path(path).stem
    found = folder.glob(f"{stem}_*.toml") if folder.is_dir() else []
    return sorted(found, key=lambda p: p.stat().st_mtime, reverse=True)


def restore_backup(path, backup):
    """Replace the settings file with `backup` (after backing up the current one)."""
    from_dict(tomllib.loads(Path(backup).read_text(encoding="utf-8")))  # must be valid
    make_backup(path)
    tmp = Path(path).with_suffix(".tmp")
    shutil.copyfile(backup, tmp)
    os.replace(tmp, path)


def earlier_install_settings():
    """Settings left by a HeadMouse installed from source (before the installer existed), if any."""
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        return None
    old = Path(local) / "HeadMouse" / "headmouse_settings.toml"
    return old if old.is_file() else None


# --- presets -----------------------------------------------------------------
# A preset is a named "feel": the four direction curves and the motion settings.
# Keys, camera, game and glance settings are never touched by a preset.

PRESET_SECTIONS = ("right", "left", "up", "down", "motion", "assist")
# From [assist], a preset keeps only how the head moves the camera (modes and the
# mouse-like settings) - not the helpers like "stop in the middle".
PRESET_ASSIST = ("hybrid", "hybrid_horizontal", "hybrid_vertical", "vertical_follow", "vertical_follow_gain",
                 "hybrid_gain_x", "hybrid_gain_y", "hybrid_blend", "hybrid_blend_y", "mouse_delay_x",
                 "mouse_delay_y", "slow_precision_x", "slow_precision_y", "fast_speed_x", "fast_speed_y",
                 "wobble_x", "wobble_y")
DEFAULT_PRESET = "Normal (default)"


def _scaled(settings, speed, curve=0.0):
    out = settings
    for name in ("right", "left", "up", "down"):
        d = getattr(out, name)
        out = dataclasses.replace(out, **{name: dataclasses.replace(
            d, min_speed=round(d.min_speed * speed, 1), max_speed=min(360.0, round(d.max_speed * speed / 5) * 5),
            curve=round(min(4.0, max(0.5, d.curve + curve)), 2))})
    return out


def builtin_presets():
    """{name: Settings} for the presets that come with HeadMouse (they cannot be deleted)."""
    normal = Settings()
    return {DEFAULT_PRESET: normal,
            "Gentle (slower, smoother)": _scaled(normal, 0.6, 0.3),
            "Fast (quicker turns)": _scaled(normal, 1.4, -0.2)}


def preset_folder(path):
    return Path(path).parent / "presets"


def preset_filename(name):
    """A safe file name for a preset name, or None if nothing usable is left."""
    clean = re.sub(r"[^A-Za-z0-9 _()+-]", "", name).strip(" .")[:60]
    return f"{clean}.toml" if clean else None


def list_presets(path):
    """Preset names: the built-in ones first, then the player's own (alphabetical)."""
    names = list(builtin_presets())
    folder = preset_folder(path)
    if folder.is_dir():
        names += sorted((p.stem for p in folder.glob("*.toml") if p.stem not in names), key=str.lower)
    return names


def is_builtin_preset(name):
    return name in builtin_presets()


def preset_values(settings):
    """{section: {key: value}} for the parts of `settings` a preset stores."""
    values = {name: dataclasses.asdict(getattr(settings, name)) for name in PRESET_SECTIONS}
    values["assist"] = {key: values["assist"][key] for key in PRESET_ASSIST}
    return values


def save_preset(path, name, settings):
    """Save the feel part of `settings` as preset `name`. Returns the file written."""
    if is_builtin_preset(name):
        raise SettingsError(f'"{name}" is a built-in preset - choose another name')
    filename = preset_filename(name)
    if filename is None:
        raise SettingsError("give the preset a name using letters or numbers")
    validate(settings)
    lines = [f"# HeadMouse preset: {name}", ""]
    for section, values in preset_values(settings).items():
        lines.append(f"[{section}]")
        lines += [f"{key} = {format_value(value)}" for key, value in values.items()]
        lines.append("")
    folder = preset_folder(path)
    folder.mkdir(exist_ok=True)
    dest = folder / filename
    tmp = dest.with_suffix(".tmp")
    tmp.write_text("\n".join(lines), encoding="utf-8")
    tmp.replace(dest)
    return dest


def load_preset(path, name, base):
    """`base` with the preset's feel (direction curves, motion and mouse-like settings) in place.
    Built-in presets and presets saved before mouse-like settings existed keep base's."""
    builtins = builtin_presets()
    if name in builtins:
        values = preset_values(builtins[name])
        values["assist"] = preset_values(base)["assist"]
    else:
        filename = preset_filename(name)
        file = preset_folder(path) / filename if filename else None
        if file is None or not file.is_file():
            raise SettingsError(f'preset "{name}" was not found')
        try:
            data = tomllib.loads(file.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
            raise SettingsError(f'preset "{name}" could not be read: {e}') from e
        values = preset_values(base)
        for section in PRESET_SECTIONS:
            if isinstance(data.get(section), dict):
                values[section].update({k: v for k, v in data[section].items()
                                        if section != "assist" or k in PRESET_ASSIST})
    merged = {f.name: dataclasses.asdict(getattr(base, f.name)) for f in dataclasses.fields(Settings)}
    for section, section_values in values.items():
        merged[section].update(section_values)
    return from_dict(merged)[0]


def delete_preset(path, name):
    if is_builtin_preset(name):
        raise SettingsError(f'"{name}" is built in and cannot be deleted')
    filename = preset_filename(name)
    if filename:
        (preset_folder(path) / filename).unlink(missing_ok=True)


def matching_preset(path, settings):
    """The name of the preset `settings` currently matches, or None."""
    current = preset_values(settings)
    for name in list_presets(path):
        try:
            if preset_values(load_preset(path, name, settings)) == current:
                return name
        except SettingsError:
            continue
    return None


def save_values(path, updates, backup=True):
    """Write {section: {key: value}} into the settings file, keeping comments.

    The previous file is kept in backups/ first, so any change can be undone
    (backup=False for small automatic saves like a re-center, so they don't push
    older backups out).
    """
    path = Path(path)
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    try:
        before = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        before = {}
    updates = {sec: dict(vals) for sec, vals in updates.items()}
    for section, new, old in INHERITED:
        # The file relies on the old key for the new one: write it down before the old key changes.
        values = before.get(section) if isinstance(before.get(section), dict) else {}
        if new not in values and old in updates.get(section, {}) and new not in updates[section]:
            if old in values:
                updates[section][new] = values[old]
            else:   # neither is in the file: both are the default
                defaults = {f.name: f.default for f in dataclasses.fields(type(getattr(Settings(), section)))}
                updates[section][new] = defaults[new]
    new_text = update_text(text, updates)
    try:
        from_dict(tomllib.loads(new_text))  # never write a file that would not load
    except tomllib.TOMLDecodeError as e:
        raise SettingsError(f"the settings file could not be updated ({e}) - check it in Notepad") from None
    if new_text != text and backup:
        make_backup(path)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(new_text, encoding="utf-8")
    tmp.replace(path)


def overlay(base, changes):
    """`base` with {section: {key: value}} applied on top."""
    for section, values in changes.items():
        base = dataclasses.replace(base, **{section: dataclasses.replace(getattr(base, section), **values)})
    return base


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
