@echo off
rem One-time setup: installs webcam tracking, downloads the face model,
rem checks everything works and puts a HeadMouse shortcut on the desktop.
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
call tools\find_python.bat || (pause & exit /b 1)
echo Using Python %PYV%
echo.
echo [1/5] Installing webcam tracking - MediaPipe. This can take a few minutes...
py -%PYV% -m pip install --upgrade -r requirements.txt
if errorlevel 1 echo WARNING: webcam tracking could not be installed. OpenTrack mode still works.
echo.
echo [2/5] Downloading the face model...
py -%PYV% tools\get_face_model.py
echo.
echo [3/5] Checking that webcam tracking works on this PC...
py -%PYV% tools\check_webcam.py
echo.
echo [4/5] Self-test...
py -%PYV% -m unittest -q
if errorlevel 1 echo WARNING: some self-tests failed - see above.
echo.
echo [5/5] Creating the desktop shortcut...
powershell -NoProfile -ExecutionPolicy Bypass -File tools\make_shortcut.ps1 -PyVersion %PYV%
if errorlevel 1 (
  echo WARNING: no desktop shortcut was made. Use "Start HeadMouse.bat" instead.
  pause
  exit /b 1
)
echo.
echo Setup finished. Double-click "HeadMouse" on the desktop to start.
pause
