@echo off
rem Runs the automated tests.
cd /d "%~dp0"
call tools\find_python.bat || (pause & exit /b 1)
py -%PYV% -m unittest -v
pause
