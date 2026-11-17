@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul

set "PYEXE=%~dp0.local\espnow\E1-015\tools\python_env\idf5.5_py3.11_env\Scripts\python.exe"
if not exist "%PYEXE%" set "PYEXE=python"

echo Starting LoRa frontend (gateway receiver + Studio)...
"%PYEXE%" -X utf8 tools\mid_baseline\gateway_probe\start_frontend.py %*
set "result=%errorlevel%"
if "%~1"=="" pause
exit /b %result%
