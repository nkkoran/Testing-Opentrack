"""Short sound cues, so the player knows HeadMouse's state without looking.

Tones are generated as small WAV files (so volume can be set) and played
asynchronously with the Windows `winsound` module.
"""

import io
import math
import struct
import sys
import tempfile
import wave
from pathlib import Path

RATE = 22050

# name -> list of (frequency Hz or 0 for silence, seconds)
CUES = {
    "enabled": [(660, 0.07), (880, 0.11)],
    "disabled": [(880, 0.07), (587, 0.13)],
    "tracking_lost": [(330, 0.12), (0, 0.06), (330, 0.12)],
    "tracking_ok": [(988, 0.07)],
    "pause": [(1400, 0.025)],
    "done": [(784, 0.08), (1047, 0.14)],
    "target": [(1175, 0.05)],
}


def tone_wav(parts, volume):
    """WAV file bytes for a sequence of tones, with short fades to avoid clicks."""
    samples = bytearray()
    amplitude = 32767 * max(0.0, min(1.0, volume)) * 0.8
    fade = int(RATE * 0.006)
    for freq, seconds in parts:
        n = int(RATE * seconds)
        for i in range(n):
            env = min(1.0, i / fade, (n - 1 - i) / fade) if fade else 1.0
            value = amplitude * env * math.sin(2 * math.pi * freq * i / RATE) if freq else 0.0
            samples += struct.pack("<h", int(value))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(bytes(samples))
    return buf.getvalue()


class SoundPlayer:
    def __init__(self, sound_settings, folder=None):
        self.s = sound_settings
        self.folder = Path(folder or Path(tempfile.gettempdir()) / "headmouse_sounds")
        self.played = []  # for tests and non-Windows systems
        try:
            import winsound
            self._winsound = winsound if sys.platform == "win32" else None
        except ImportError:
            self._winsound = None

    def update(self, sound_settings):
        self.s = sound_settings

    def wanted(self, name):
        s = self.s
        if not s.enabled or s.volume <= 0:
            return False
        if name in ("enabled", "disabled"):
            return s.on_enable_disable
        if name in ("tracking_lost", "tracking_ok"):
            return s.on_tracking_lost
        if name == "pause":
            return s.on_pause
        return True

    def play(self, name, force=False):
        if name not in CUES or not (force or self.wanted(name)):
            return
        self.played.append(name)
        if self._winsound is None:
            return
        path = self.folder / f"{name}_{int(self.s.volume * 100)}.wav"
        try:
            if not path.exists():
                self.folder.mkdir(parents=True, exist_ok=True)
                path.write_bytes(tone_wav(CUES[name], self.s.volume))
            ws = self._winsound
            ws.PlaySound(str(path), ws.SND_FILENAME | ws.SND_ASYNC | ws.SND_NODEFAULT)
        except (OSError, RuntimeError):
            pass  # a missing sound must never stop head control
