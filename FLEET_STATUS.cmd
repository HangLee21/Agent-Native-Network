@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul

set "PYEXE=%~dp0.local\espnow\E1-015\tools\python_env\idf5.5_py3.11_env\Scripts\python.exe"
if not exist "%PYEXE%" set "PYEXE=python"

echo ============================================
echo  Fleet status: every Raspberry Pi and its node
echo ============================================
echo.
"%PYEXE%" -X utf8 tools\mid_baseline\fleet\fleet.py status %*
set "result=%errorlevel%"
echo.
echo Columns: rdr=reader service, node/node id, build=firmware tail,
echo          wifi/cable=addresses, disk/temp/uptime.
echo.
if "%~1"=="" pause
exit /b %result%
