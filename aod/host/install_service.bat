@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (echo Run start_aod.bat once first. & pause & exit /b 1)
.venv\Scripts\python.exe aod_launcher.py install
pause
