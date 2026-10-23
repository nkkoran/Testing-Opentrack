@echo off
rem Shows the tracking data (webcam or OpenTrack). Never moves the mouse.
cd /d "%~dp0"
py -3 run_headmouse.py --monitor
pause
