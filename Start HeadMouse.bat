@echo off
rem Normal use: head control of the mouse.
cd /d "%~dp0"
py run_headmouse.py %*
pause
