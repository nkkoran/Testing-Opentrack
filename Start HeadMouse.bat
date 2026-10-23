@echo off
rem Opens the HeadMouse window (same as the desktop shortcut, but with a console for messages).
cd /d "%~dp0"
py -3 run_headmouse.py %*
if errorlevel 1 pause
