@echo off
rem One-time setup (safe to run again): installs Python if needed, HeadMouse's parts,
rem the face model and desktop/Start-menu icons, then starts HeadMouse.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\setup.ps1"
