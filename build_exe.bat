@echo off
rem Builds dist\HeadMouse\HeadMouse.exe (a folder you can copy anywhere) and a desktop shortcut to it.
cd /d "%~dp0"
call tools\find_python.bat || goto :error
%PY% -m pip install --upgrade pyinstaller -r requirements.txt || goto :error
%PY% tools\get_face_model.py || goto :error
%PY% -m PyInstaller --noconfirm --onedir --windowed --name HeadMouse --collect-all mediapipe --collect-data customtkinter --icon headmouse.ico --add-data "headmouse.ico;." --add-data "face_landmarker.task;." run_headmouse.pyw || goto :error
if not exist dist\HeadMouse\headmouse_settings.toml copy headmouse_settings.toml dist\HeadMouse\ >nul
powershell -NoProfile -ExecutionPolicy Bypass -File tools\make_shortcut.ps1 -Target "%~dp0dist\HeadMouse\HeadMouse.exe"
echo.
echo Built dist\HeadMouse\HeadMouse.exe - the desktop shortcut now points to it.
pause
exit /b 0
:error
echo Build failed.
pause
exit /b 1
