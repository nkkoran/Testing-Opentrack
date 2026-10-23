@echo off
rem Prints the camera speed for each head angle in all four directions.
cd /d "%~dp0"
py run_headmouse.py --curves
pause
