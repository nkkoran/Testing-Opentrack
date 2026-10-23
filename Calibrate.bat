@echo off
rem Console calibration (the window's Game calibration button does the same).
cd /d "%~dp0"
call tools\find_python.bat || (pause & exit /b 1)
%PY% run_headmouse.py --calibrate
pause
