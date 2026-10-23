@echo off
rem Calibration: sends exact 360-degree turns to find counts_per_360.
cd /d "%~dp0"
py run_headmouse.py --calibrate
pause
