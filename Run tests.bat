@echo off
rem Runs the automated tests.
cd /d "%~dp0"
py -m unittest -v
pause
