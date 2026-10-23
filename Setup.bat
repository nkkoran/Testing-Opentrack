@echo off
rem One-time setup: installs webcam tracking, downloads the face model,
rem runs the self-test and puts a HeadMouse shortcut on the desktop.
setlocal
cd /d "%~dp0"
echo ============================================
echo   HeadMouse setup
echo ============================================
where py >nul 2>&1
if errorlevel 1 (
  echo Python was not found. Install Python 3.13 from https://www.python.org/downloads/windows/
  echo and tick "Add python.exe to PATH" in the installer, then run Setup again.
  pause
  exit /b 1
)
py -3 -c "import sys; sys.exit(sys.version_info < (3, 11))"
if errorlevel 1 (
  echo Python 3.11 or newer is needed. Install Python 3.13 from python.org.
  pause
  exit /b 1
)
echo.
echo [1/4] Installing webcam tracking (MediaPipe) - this can take a few minutes...
py -3 -m pip install --upgrade -r requirements.txt
if errorlevel 1 echo WARNING: webcam tracking could not be installed. OpenTrack mode still works.
echo.
echo [2/4] Downloading the face model...
py -3 tools\get_face_model.py
echo.
echo [3/4] Self-test...
py -3 -m unittest -q
if errorlevel 1 echo WARNING: some self-tests failed - see above.
echo.
echo [4/4] Creating the desktop shortcut...
powershell -NoProfile -ExecutionPolicy Bypass -File tools\make_shortcut.ps1
echo.
echo Setup finished. Double-click "HeadMouse" on the desktop to start.
pause
