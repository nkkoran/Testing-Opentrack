@echo off
rem Runs everything except moving the mouse. Shows the speeds it would use.
cd /d "%~dp0"
py run_headmouse.py --dry-run
pause
