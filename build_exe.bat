@echo off
rem Phase 3: builds dist\HeadMouse.exe (needs internet the first time for PyInstaller).
cd /d "%~dp0"
py -m pip install --upgrade pyinstaller || goto :error
py -m PyInstaller --onefile --console --name HeadMouse run_headmouse.py || goto :error
copy /Y headmouse_settings.toml dist\ >nul
echo.
echo Built dist\HeadMouse.exe - keep headmouse_settings.toml in the same folder.
pause
exit /b 0
:error
echo Build failed.
pause
exit /b 1
