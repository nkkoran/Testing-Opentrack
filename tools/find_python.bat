@echo off
rem Sets PYV to an installed Python version that HeadMouse supports (newest first
rem among those MediaPipe is known to support). Used by the other .bat files.
set PYV=
for %%v in (3.13 3.12 3.11 3.14) do (
  if not defined PYV (
    py -%%v -c "" >nul 2>&1 && set PYV=%%v
  )
)
if not defined PYV (
  echo Python 3.11 to 3.14 was not found.
  echo Install Python 3.13 from https://www.python.org/downloads/windows/
  echo and tick "Add python.exe to PATH" in the installer.
  exit /b 1
)
exit /b 0
