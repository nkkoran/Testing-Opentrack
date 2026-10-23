"""Download Google's MediaPipe face model next to HeadMouse (done by Setup.bat)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from headmouse.webcam import MODEL_FILENAME, MODEL_URL, download_model  # noqa: E402

dest = Path(__file__).resolve().parent.parent / MODEL_FILENAME
if dest.exists():
    print(f"Face model already present: {dest}")
else:
    print(f"Downloading {MODEL_URL}")
    try:
        download_model(dest)
    except OSError as e:
        print(f"Download failed: {e}\nHeadMouse will try again the first time webcam tracking starts.")
        sys.exit(1)
    print(f"Saved {dest}")
