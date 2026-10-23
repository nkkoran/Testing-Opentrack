@echo off
rem Step 1 test: shows what OpenTrack sends. Never moves the mouse.
cd /d "%~dp0"
py run_headmouse.py --monitor
pause
