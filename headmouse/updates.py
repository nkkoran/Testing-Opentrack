"""Checks GitHub for a newer HeadMouse release and installs it.

Only used by the installed app (HeadMouse.exe). The installer keeps the player's
settings and starts HeadMouse again when it finishes.
"""

import json
import re
import subprocess
import tempfile
import urllib.request
from pathlib import Path

from . import __version__

REPO = "nkkoran/Testing-Opentrack"
LATEST_API = f"https://api.github.com/repos/{REPO}/releases/latest"
INSTALLER_NAME = "HeadMouse-Setup.exe"


def parse_version(text):
    """(1, 2, 3) from 'v1.2.3' or '1.2.3'; None if it isn't a version."""
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", str(text).strip())
    return tuple(int(x) for x in m.groups()) if m else None


def is_newer(latest, current=__version__):
    a, b = parse_version(latest), parse_version(current)
    return a is not None and b is not None and a > b


def latest_release(timeout=6, opener=urllib.request.urlopen):
    """(version, installer_url) of the newest release, or None (offline, none published...)."""
    request = urllib.request.Request(LATEST_API, headers={"Accept": "application/vnd.github+json",
                                                          "User-Agent": "HeadMouse"})
    try:
        with opener(request, timeout=timeout) as response:
            data = json.load(response)
    except (OSError, ValueError):
        return None
    version = data.get("tag_name", "")
    for asset in data.get("assets", []):
        if asset.get("name") == INSTALLER_NAME and parse_version(version):
            return version.lstrip("v"), asset["browser_download_url"]
    return None


def available_update(**kw):
    """(version, installer_url) if a newer release exists, else None."""
    release = latest_release(**kw)
    return release if release and is_newer(release[0]) else None


def download_and_install(url):
    """Download the installer and start it (with a progress window). The caller should then exit."""
    path = Path(tempfile.gettempdir()) / INSTALLER_NAME
    with urllib.request.urlopen(url, timeout=120) as response, path.open("wb") as f:
        while chunk := response.read(1 << 16):
            f.write(chunk)
    subprocess.Popen([str(path), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART"])
