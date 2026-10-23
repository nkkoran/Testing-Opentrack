@echo off
rem Runs the automated tests.
cd /d "%~dp0"
py -3 -m unittest -v
pause
