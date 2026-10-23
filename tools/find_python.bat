@echo off
rem Sets PY to the command for a Python version HeadMouse supports. Used by the other .bat files.
set PY=
for %%v in (3.13 3.12 3.11 3.14) do (
  if not defined PY (
    py -%%v -c "" >nul 2>&1 && set PY=py -%%v
  )
)
for %%v in (313 312 311 314) do (
  if not defined PY (
    if exist "%LOCALAPPDATA%\Programs\Python\Python%%v\python.exe" set PY="%LOCALAPPDATA%\Programs\Python\Python%%v\python.exe"
  )
)
if not defined PY (
  echo Python was not found. Run Setup.bat first - it installs Python automatically.
  exit /b 1
)
exit /b 0
