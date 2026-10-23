"""Head-tracking input.

This module is the only part of the program that knows where head angles come
from. Anything that provides `start()`, `stop()` and `latest()` returning a
HeadSample can replace OpenTrackUDPSource (for example a different tracker later).
"""

import socket
import struct
import threading
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class HeadSample:
    yaw: float          # degrees
    pitch: float        # degrees
    values: tuple       # every number the tracker sent, used to spot frozen data
    received_at: float  # time.perf_counter() when it arrived
    sequence: int       # increases by one for each sample received


# OpenTrack's "UDP over network" output sends six little-endian doubles per packet,
# in its axis order: X, Y, Z (centimetres), Yaw, Pitch, Roll (degrees).
OPENTRACK_PACKET = struct.Struct("<6d")
_YAW, _PITCH = 3, 4


def parse_opentrack_packet(data):
    """Return the six values from an OpenTrack UDP packet, or None if it is malformed."""
    if len(data) != OPENTRACK_PACKET.size:
        return None
    return OPENTRACK_PACKET.unpack(data)


class OpenTrackUDPSource:
    """Receives OpenTrack's UDP output on a background thread."""

    def __init__(self, address="127.0.0.1", port=4242, clock=time.perf_counter):
        self.address = address
        self.port = port
        self._clock = clock
        self._lock = threading.Lock()
        self._latest = None
        self._sequence = 0
        self._sock = None
        self._thread = None
        self._running = False
        self.packets = 0
        self.bad_packets = 0

    def describe(self):
        return f"OpenTrack UDP on {self.address}:{self.port}"

    def start(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.bind((self.address, self.port))
        except OSError as e:
            sock.close()
            raise OSError(
                f"cannot listen on {self.address}:{self.port} ({e}). Is another copy "
                f"of this program already running, or another app using that port?"
            ) from None
        sock.settimeout(0.1)
        self._sock = sock
        self._running = True
        self._thread = threading.Thread(target=self._run, name="opentrack-udp", daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        if self._sock is not None:
            self._sock.close()
        self._thread = self._sock = None

    def latest(self):
        with self._lock:
            return self._latest

    def _run(self):
        while self._running:
            try:
                data, _ = self._sock.recvfrom(1024)
            except socket.timeout:
                continue
            except OSError:
                if self._running:
                    time.sleep(0.05)
                continue
            values = parse_opentrack_packet(data)
            if values is None:
                self.bad_packets += 1
                continue
            now = self._clock()
            with self._lock:
                self._sequence += 1
                self._latest = HeadSample(
                    yaw=values[_YAW], pitch=values[_PITCH], values=values,
                    received_at=now, sequence=self._sequence)
            self.packets += 1

