@echo off
rem Console calibration (the window's Game calibration button does the same).
cd /d "%~dp0"
py -3 run_headmouse.py --calibrate
pause
