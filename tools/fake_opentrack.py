"""Pretend to be OpenTrack: send head angles over UDP for testing without a camera.

Examples (run in a second window while HeadMouse runs in the first):
  py tools/fake_opentrack.py --yaw 10                 hold head 10 deg right
  py tools/fake_opentrack.py --yaw -6 --pitch 4       left and up
  py tools/fake_opentrack.py --sweep                  slowly swing left and right
  py tools/fake_opentrack.py --yaw 15 --freeze-after 3   simulate OpenTrack losing the face
Stop with Ctrl+C - HeadMouse should then stop moving within a quarter second.
"""

import argparse
import math
import random
import socket
import struct
import time

PACKET = struct.Struct("<6d")  # X, Y, Z, Yaw, Pitch, Roll


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=4242)
    p.add_argument("--yaw", type=float, default=0.0, help="degrees, + is right")
    p.add_argument("--pitch", type=float, default=0.0, help="degrees, + is up")
    p.add_argument("--sweep", action="store_true", help="swing yaw between -20 and +20 every 8 s")
    p.add_argument("--rate", type=float, default=100.0, help="packets per second")
    p.add_argument("--seconds", type=float, default=0.0, help="stop after this long (0 = until Ctrl+C)")
    p.add_argument("--freeze-after", type=float, default=0.0,
                   help="after this many seconds keep sending identical values")
    p.add_argument("--no-noise", action="store_true", help="send perfectly constant values")
    args = p.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    start = time.perf_counter()
    frozen = None
    print(f"Sending to {args.host}:{args.port} at {args.rate:g} packets/s. Ctrl+C to stop.")
    try:
        while True:
            t = time.perf_counter() - start
            if args.seconds and t >= args.seconds:
                break
            if args.freeze_after and t >= args.freeze_after:
                if frozen is None:
                    print("Freezing values now (simulated tracking loss).")
                values = frozen
            else:
                values = None
            if values is None:
                yaw = 20 * math.sin(2 * math.pi * t / 8) if args.sweep else args.yaw
                pitch = args.pitch
                if not args.no_noise:
                    yaw += random.uniform(-0.02, 0.02)
                    pitch += random.uniform(-0.02, 0.02)
                values = (0.0, 0.0, 0.0, yaw, pitch, 0.0)
                if args.freeze_after and t >= args.freeze_after:
                    frozen = values
            sock.sendto(PACKET.pack(*values), (args.host, args.port))
            time.sleep(1.0 / args.rate)
    except KeyboardInterrupt:
        pass
    print("Stopped sending.")


if __name__ == "__main__":
    main()
