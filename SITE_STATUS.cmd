@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
chcp 65001 >nul

set "PYEXE=%~dp0.local\espnow\E1-015\tools\python_env\idf5.5_py3.11_env\Scripts\python.exe"
if not exist "%PYEXE%" set "PYEXE=python"

set "FLEETDIR="
if exist "%~dp0fleet\fleet.py" set "FLEETDIR=%~dp0fleet"
if exist "%~dp0tools\mid_baseline\fleet\fleet.py" set "FLEETDIR=%~dp0tools\mid_baseline\fleet"
if exist "%~dp0app\services\tools\fleet\fleet.py" set "FLEETDIR=%~dp0app\services\tools\fleet"

if not exist "%~dp0site.env" (
  echo 还没有 site.env，请先双击 SETUP_SITE.cmd
  pause
  exit /b 1
)

echo ============================================
echo  看看现在有哪几台设备在线
echo ============================================
echo.
"%PYEXE%" -X utf8 "%FLEETDIR%\fleet.py" status
set "result=%errorlevel%"
echo.
if "%~1"=="" pause
exit /b %result%
