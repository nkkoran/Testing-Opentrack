@echo off
rem Shows the tracking data (webcam or OpenTrack). Never moves the mouse.
cd /d "%~dp0"
call tools\find_python.bat || (pause & exit /b 1)
%PY% run_headmouse.py --monitor
pause
