"""Built-in head tracking from a webcam, using Google MediaPipe Face Landmarker.

An alternative to OpenTrack: no separate program to start or configure. Provides
the same start()/stop()/latest() interface as OpenTrackUDPSource, with yaw
positive to the right and pitch positive upward.

OpenCV and MediaPipe are only imported when this source starts, so the rest of
the program works without them installed.
"""

import math
import sys
import threading
import time
import urllib.request
from pathlib import Path

from .filters import OneEuroFilter
from .tracking import HeadSample

MODEL_FILENAME = "face_landmarker.task"
VC_REDIST_URL = "https://aka.ms/vs/17/release/vc_redist.x64.exe"
MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/face_landmarker/"
             "face_landmarker/float16/1/face_landmarker.task")
NOSE_TIP = 1  # landmark index used for the preview dot


def matrix_to_angles(m):
    """(yaw, pitch, roll) in degrees from MediaPipe's 4x4 facial transformation matrix.

    Decomposes the rotation as yaw (about the vertical axis), then pitch, then
    roll. MediaPipe's own signs are: yaw + toward the person's left, pitch +
    looking down, so both are flipped to make right and up positive.
    """
    r02, r12, r22 = m[0][2], m[1][2], m[2][2]
    yaw = math.degrees(math.atan2(r02, r22))
    pitch = math.degrees(math.asin(max(-1.0, min(1.0, -r12))))
    roll = math.degrees(math.atan2(m[1][0], m[1][1]))
    return -yaw, -pitch, roll


def find_model(base_dir, configured=""):
    """Locate the face model: configured path, next to the program, or inside the .exe."""
    candidates = []
    if configured:
        candidates.append(Path(configured))
    candidates.append(Path(base_dir) / MODEL_FILENAME)
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        candidates.append(Path(bundle) / MODEL_FILENAME)
    for c in candidates:
        if c.is_file():
            return c
    return None


def download_model(dest):
    """Download Google's face model (about 3.7 MB) to `dest`."""
    dest = Path(dest)
    tmp = dest.with_suffix(".part")
    with urllib.request.urlopen(MODEL_URL, timeout=60) as resp, tmp.open("wb") as f:
        while chunk := resp.read(65536):
            f.write(chunk)
    with tmp.open("rb") as f:
        if f.read(2) != b"PK" or tmp.stat().st_size < 1_000_000:
            tmp.unlink()
            raise OSError("downloaded face model looks damaged")
    tmp.replace(dest)
    return dest


class WebcamSource:
    """Reads the webcam on a background thread and estimates head angles."""

    def __init__(self, webcam_settings, base_dir, clock=time.perf_counter, open_camera=None):
        self.s = webcam_settings
        self._open_camera = open_camera  # tests pass a function returning a cv2.VideoCapture
        self.base_dir = Path(base_dir)
        self._clock = clock
        self._lock = threading.Lock()
        self._latest = None
        self._sequence = 0
        self._running = False
        self._thread = None
        self._preview_png = None
        self.preview_wanted = False
        self.status = "starting"
        self.error = None
        self.packets = 0
        self.face_visible = False
        self._yaw_filter = OneEuroFilter(webcam_settings.smoothing_min_cutoff, webcam_settings.smoothing_beta)
        self._pitch_filter = OneEuroFilter(webcam_settings.smoothing_min_cutoff, webcam_settings.smoothing_beta)

    def describe(self):
        return f"webcam {self.s.camera_index} (built-in tracking)"

    def update_settings(self, webcam_settings):
        """Apply smoothing changes without reopening the camera."""
        self.s = webcam_settings
        for f in (self._yaw_filter, self._pitch_filter):
            f.min_cutoff = webcam_settings.smoothing_min_cutoff
            f.beta = webcam_settings.smoothing_beta

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run, name="webcam", daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=3.0)
        self._thread = None

    def latest(self):
        with self._lock:
            return self._latest

    def preview_png(self):
        with self._lock:
            return self._preview_png

    def _fail(self, message):
        self.error = message
        self.status = message
        self._running = False

    def _run(self):
        try:
            import cv2
            import mediapipe as mp
            from mediapipe.tasks.python import BaseOptions, vision
        except ModuleNotFoundError:
            self._fail("webcam support is not installed - run Setup.bat")
            return
        except (ImportError, OSError) as e:  # usually a missing Visual C++ runtime DLL
            self._fail(f"webcam support could not load ({e}). Install the Microsoft Visual C++ "
                       f"Redistributable from {VC_REDIST_URL} and restart HeadMouse.")
            return

        model = find_model(self.base_dir, self.s.model_path)
        if model is None:
            self.status = "downloading face model (first run only)..."
            try:
                model = download_model(self.base_dir / MODEL_FILENAME)
            except OSError as e:
                self._fail(f"could not download the face model: {e}")
                return

        self.status = "loading face model..."
        try:
            options = vision.FaceLandmarkerOptions(
                # Loaded from memory: MediaPipe cannot open paths with non-English letters.
                base_options=BaseOptions(model_asset_buffer=Path(model).read_bytes()),
                running_mode=vision.RunningMode.VIDEO,
                num_faces=1,
                output_facial_transformation_matrixes=True)
            landmarker = vision.FaceLandmarker.create_from_options(options)
        except Exception as e:  # MediaPipe raises several exception types
            self._fail(f"could not load the face model: {e}")
            return

        self.status = f"opening camera {self.s.camera_index}..."
        if self._open_camera is not None:
            cap = self._open_camera()
        else:
            backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
            cap = cv2.VideoCapture(self.s.camera_index, backend)
        if not cap.isOpened():
            landmarker.close()
            self._fail(f"camera {self.s.camera_index} not found or busy "
                       f"(close OpenTrack or other apps using it)")
            return
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.s.frame_width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.s.frame_height)
        cap.set(cv2.CAP_PROP_FPS, self.s.fps)

        self.status = "running"
        start = self._clock()
        last_ts = -1
        last_preview = 0.0
        failures = 0
        try:
            while self._running:
                ok, frame = cap.read()
                if not ok:
                    failures += 1
                    if failures > 30:
                        self._fail("the camera stopped sending pictures")
                        break
                    time.sleep(0.03)
                    continue
                failures = 0
                now = self._clock()
                ts = int((now - start) * 1000)
                if ts <= last_ts:
                    ts = last_ts + 1
                last_ts = ts
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                result = landmarker.detect_for_video(
                    mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), ts)
                self._handle(result, now)
                if self.preview_wanted and now - last_preview >= 0.1:
                    last_preview = now
                    self._make_preview(cv2, frame, result)
        finally:
            cap.release()
            landmarker.close()

    def _handle(self, result, now):
        if not result.facial_transformation_matrixes:
            # No face: send nothing, so the safety monitor stops movement.
            self.face_visible = False
            self._yaw_filter.reset()
            self._pitch_filter.reset()
            return
        self.face_visible = True
        m = result.facial_transformation_matrixes[0]
        yaw, pitch, roll = matrix_to_angles(m)
        yaw = self._yaw_filter(yaw, now)
        pitch = self._pitch_filter(pitch, now)
        values = (float(m[0][3]), float(m[1][3]), float(m[2][3]), yaw, pitch, roll)
        with self._lock:
            self._sequence += 1
            self._latest = HeadSample(yaw=yaw, pitch=pitch, values=values,
                                      received_at=now, sequence=self._sequence)
        self.packets += 1

    def _make_preview(self, cv2, frame, result):
        h, w = frame.shape[:2]
        scale = min(320 / w, 240 / h)
        small = cv2.resize(frame, (int(w * scale), int(h * scale)))
        small = cv2.flip(small, 1)  # mirror, so it looks like a mirror to the user
        if result.face_landmarks:
            nose = result.face_landmarks[0][NOSE_TIP]
            x = int((1 - nose.x) * small.shape[1])
            y = int(nose.y * small.shape[0])
            cv2.circle(small, (x, y), 6, (0, 200, 0), -1)
        else:
            cv2.putText(small, "No face found", (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                        0.8, (0, 0, 255), 2)
        ok, png = cv2.imencode(".png", small)
        if ok:
            with self._lock:
                self._preview_png = png.tobytes()
