@echo off
setlocal
cd /d "%~dp0"
title AOD host

rem ---- 1. find Python (or install it) ----
set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY (where python >nul 2>&1 && python -c "import sys" >nul 2>&1 && set "PY=python")

if not defined PY (
  echo Python not found. Installing Python 3.12 ...
  winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
  if not exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    echo winget unavailable or failed, downloading installer from python.org ...
    powershell -NoProfile -Command "Invoke-WebRequest https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe -OutFile '%TEMP%\py_aod.exe'"
    "%TEMP%\py_aod.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0
  )
  if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    set "PY="%LOCALAPPDATA%\Programs\Python\Python312\python.exe""
  )
)
if not defined PY (
  echo Could not install Python automatically. Install it from python.org and run this again.
  pause & exit /b 1
)

rem ---- 2. private environment with all dependencies ----
if not exist ".venv\Scripts\python.exe" (
  echo Setting up AOD environment ...
  %PY% -m venv .venv || (echo Failed to create environment & pause & exit /b 1)
)
:deps
".venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check -r requirements.txt || (
  echo Failed to install dependencies. Check your internet connection.
  pause & exit /b 1
)
rem audio streaming is optional: carry on without it if it fails
for /f "usebackq tokens=*" %%p in ("requirements-optional.txt") do (
  ".venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check %%p >nul 2>&1 || echo (optional %%p not installed, continuing)
)

rem ---- 3. allow the phone through the firewall (needs admin, harmless if skipped) ----
netsh advfirewall firewall show rule name="AOD host" >nul 2>&1 || (
  netsh advfirewall firewall add rule name="AOD host" dir=in action=allow protocol=TCP localport=8765 profile=any remoteip=LocalSubnet,100.64.0.0/10 >nul 2>&1
)

rem ---- 4. run (exit code 75 = AOD updated itself: reinstall deps and start again) ----
set AOD_LOOP=1
".venv\Scripts\python.exe" aod_host.py
if %errorlevel%==75 goto deps
pause
