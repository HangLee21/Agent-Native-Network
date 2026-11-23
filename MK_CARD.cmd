@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
chcp 65001 >nul

set "PYEXE=%~dp0.local\espnow\E1-015\tools\python_env\idf5.5_py3.11_env\Scripts\python.exe"
if not exist "%PYEXE%" set "PYEXE=python"

echo ============================================
echo  Prepare one SD card (identity for one Pi)
echo ============================================
echo.
if /i "%~1"=="--check" goto passthrough
if /i "%~1"=="--list" goto passthrough
echo Reminder: write the image with Raspberry Pi Imager FIRST
echo   (user eora, SSH on, your public key), then run this.
echo.

if not "%~1"=="" (
  set "CARD=%~1"
) else (
  set /p "CARD=Card letter (Enter = auto-detect, e.g. F): "
)
if not "%~2"=="" (
  set "NUM=%~2"
) else (
  set /p "NUM=Node number (1-255): "
)

echo.
if "%CARD%"=="" (
  "%PYEXE%" -X utf8 tools\mid_baseline\gateway_probe\mkcard.py --auto --number "%NUM%"
) else (
  "%PYEXE%" -X utf8 tools\mid_baseline\gateway_probe\mkcard.py --card "%CARD%" --number "%NUM%"
)
set "result=%errorlevel%"
echo.
pause
exit /b %result%
:passthrough
"%PYEXE%" -X utf8 tools\mid_baseline\gateway_probe\mkcard.py %1
exit /b %errorlevel%
