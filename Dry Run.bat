@echo off
rem Opens the HeadMouse window without ever moving the mouse.
cd /d "%~dp0"
py -3 run_headmouse.py --dry-run
if errorlevel 1 pause
