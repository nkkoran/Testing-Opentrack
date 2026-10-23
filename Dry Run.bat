@echo off
rem Opens the HeadMouse window without ever moving the mouse.
cd /d "%~dp0"
call tools\find_python.bat || (pause & exit /b 1)
py -%PYV% run_headmouse.py --dry-run
if errorlevel 1 pause
