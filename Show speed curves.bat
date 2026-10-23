@echo off
rem Prints the camera speed for each head angle in all four directions.
cd /d "%~dp0"
call tools\find_python.bat || (pause & exit /b 1)
%PY% run_headmouse.py --curves
pause
