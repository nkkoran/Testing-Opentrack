@echo off
rem Opens the HeadMouse window (same as the desktop shortcut, but with a console for messages).
cd /d "%~dp0"
call tools\find_python.bat || (pause & exit /b 1)
%PY% run_headmouse.py %*
if errorlevel 1 pause
