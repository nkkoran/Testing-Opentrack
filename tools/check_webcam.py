"""Setup check: can MediaPipe load and run the face model on this PC?"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from headmouse.webcam import MODEL_FILENAME, VC_REDIST_URL  # noqa: E402

try:
    import numpy as np
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions, vision
    model = (ROOT / MODEL_FILENAME).read_bytes()
    landmarker = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_buffer=model), output_facial_transformation_matrixes=True))
    landmarker.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.zeros((240, 320, 3), np.uint8)))
    landmarker.close()
except ModuleNotFoundError as e:
    print(f"Webcam tracking is NOT installed ({e}). OpenTrack mode still works.")
    sys.exit(1)
except FileNotFoundError:
    print("The face model is missing - HeadMouse will download it the first time it starts.")
    sys.exit(1)
except Exception as e:  # DLL problems show up as OSError/ImportError/RuntimeError
    print(f"Webcam tracking could not start: {e}")
    print(f"Install the Microsoft Visual C++ Redistributable from {VC_REDIST_URL}, then run Setup again.")
    sys.exit(1)
print("Webcam tracking works.")
