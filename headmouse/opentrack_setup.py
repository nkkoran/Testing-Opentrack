"""Helpers for using OpenTrack with HeadMouse.

* Creates a "HeadMouse" OpenTrack profile as a COPY of an existing one (camera and
  tracker settings are kept) with the output set to UDP 127.0.0.1:4242 and the
  yaw/pitch mapping curves reset to 1:1. The original profile is never changed;
  an existing HeadMouse.ini is backed up before being replaced.
* Finds and starts opentrack.exe.

Profile keys were taken from the OpenTrack 2026.1.0 source code:
  [modules] protocol-dll          output plugin ("udp" = UDP over network)
  [udp-proto] ip1..ip4, port      UDP destination
  [spline-yaw] points (etc.)      mapping curve points; none = straight 1:1 line
  [opentrack-mappings] yaw-max-value / yaw-max-output-value / yaw-alt-axis-sign
                                  curve range; defaults (180/180, 90/90) = 1:1
"""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

PROFILE_NAME = "HeadMouse.ini"
ORG = "opentrack-2.3"

UDP_SETTINGS = {
    ("modules", "protocol-dll"): "udp",
    ("udp-proto", "ip1"): "127",
    ("udp-proto", "ip2"): "0",
    ("udp-proto", "ip3"): "0",
    ("udp-proto", "ip4"): "1",
}
REMOVE_FOR_1_TO_1 = [
    (section, "points") for section in ("spline-yaw", "alt-spline-yaw", "spline-pitch", "alt-spline-pitch")
] + [
    ("opentrack-mappings", f"{axis}-{key}")
    for axis in ("yaw", "pitch") for key in ("max-value", "max-output-value", "alt-axis-sign")
]


# --- INI editing (Qt QSettings format: [section] then key=value lines) ---------

def _find_section(lines, section):
    header = f"[{section}]"
    for i, line in enumerate(lines):
        if line.strip() == header:
            end = i + 1
            while end < len(lines) and not lines[end].strip().startswith("["):
                end += 1
            return i, end
    return None


def ini_set(lines, section, key, value):
    found = _find_section(lines, section)
    if found is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend([f"[{section}]", f"{key}={value}"])
        return
    start, end = found
    for i in range(start + 1, end):
        if lines[i].split("=", 1)[0].strip() == key:
            lines[i] = f"{key}={value}"
            return
    insert = end
    while insert > start + 1 and not lines[insert - 1].strip():
        insert -= 1
    lines.insert(insert, f"{key}={value}")


def ini_remove(lines, section, key):
    found = _find_section(lines, section)
    if found is None:
        return
    start, end = found
    for i in range(start + 1, end):
        if lines[i].split("=", 1)[0].strip() == key:
            del lines[i]
            return


def patch_profile_text(text, port=4242):
    """Return profile text set up for HeadMouse (UDP output, 1:1 yaw and pitch)."""
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines()
    for (section, key), value in UDP_SETTINGS.items():
        ini_set(lines, section, key, value)
    ini_set(lines, "udp-proto", "port", str(port))
    for section, key in REMOVE_FOR_1_TO_1:
        ini_remove(lines, section, key)
    return newline.join(lines) + newline


# --- Finding things ----------------------------------------------------------

def documents_folder():
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [("a", wintypes.DWORD), ("b", wintypes.WORD), ("c", wintypes.WORD),
                        ("d", ctypes.c_ubyte * 8)]
        documents = GUID(0xFDD39AD0, 0x238F, 0x46AF,
                         (ctypes.c_ubyte * 8)(0xAD, 0xB4, 0x6C, 0x85, 0x48, 0x03, 0x69, 0xC7))
        out = ctypes.c_wchar_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(documents), 0, None,
                                                      ctypes.byref(out)) == 0:
            path = out.value
            ctypes.windll.ole32.CoTaskMemFree(out)
            return Path(path)
    return Path.home() / "Documents"


def profile_folders(opentrack_exe=""):
    """Where OpenTrack keeps profiles: Documents\\opentrack-2.3, or 'ini' next to a portable install."""
    folders = []
    exe = find_opentrack_exe(opentrack_exe)
    if exe and (exe.parent / "portable.txt").exists():
        folders.append(exe.parent / "ini")
    folders.append(documents_folder() / ORG)
    return folders


def list_profiles(folder):
    folder = Path(folder)
    return sorted(p.name for p in folder.glob("*.ini")) if folder.is_dir() else []


def current_profile():
    """Name of the profile OpenTrack last used (from the registry), or None."""
    if sys.platform != "win32":
        return None
    import winreg
    for sub in (rf"Software\{ORG}\OrganizationDefaults", rf"Software\{ORG}\{ORG}", rf"Software\{ORG}"):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, sub) as k:
                value, _ = winreg.QueryValueEx(k, "settings-filename")
                return Path(str(value)).name
        except OSError:
            continue
    return None


def make_headmouse_profile(folder, source_name, port=4242):
    """Create HeadMouse.ini from `source_name`. Returns (path, backup_path or None)."""
    folder = Path(folder)
    source = folder / source_name
    dest = folder / PROFILE_NAME
    text = source.read_text(encoding="utf-8", errors="surrogateescape") if source.exists() else ""
    backup = None
    if dest.exists():
        backup = folder / f"{PROFILE_NAME}.backup-{time.strftime('%Y%m%d-%H%M%S')}"
        shutil.copy2(dest, backup)
    folder.mkdir(parents=True, exist_ok=True)
    dest.write_text(patch_profile_text(text, port), encoding="utf-8", errors="surrogateescape")
    return dest, backup


def find_opentrack_exe(configured=""):
    candidates = [Path(configured)] if configured else []
    for env in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        base = os.environ.get(env)
        if base:
            candidates += [Path(base) / "opentrack" / "opentrack.exe",
                           Path(base) / "Programs" / "opentrack" / "opentrack.exe"]
    for c in candidates:
        if c.is_file():
            return c
    return None


def is_running():
    if sys.platform != "win32":
        return False
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq opentrack.exe", "/NH"],
                             capture_output=True, timeout=5,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return b"opentrack.exe" in out.lower()


def launch_if_needed(configured=""):
    """Start OpenTrack if it isn't running. Returns a message for the user."""
    if is_running():
        return "OpenTrack is already running - make sure tracking is started."
    exe = find_opentrack_exe(configured)
    if exe is None:
        return ("OpenTrack not found. Start it yourself, or set opentrack_exe in the settings.")
    try:
        subprocess.Popen([str(exe)], cwd=str(exe.parent))
    except OSError as e:
        return f"Could not start OpenTrack: {e}"
    return "Started OpenTrack - select the HeadMouse profile and press Start."
