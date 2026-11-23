@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
chcp 65001 >nul

set "PYEXE=%~dp0.local\espnow\E1-015\tools\python_env\idf5.5_py3.11_env\Scripts\python.exe"
if not exist "%PYEXE%" set "PYEXE=python"

set "FLEETDIR="
if exist "%~dp0fleet\write_site_env.py" set "FLEETDIR=%~dp0fleet"
if exist "%~dp0tools\mid_baseline\fleet\write_site_env.py" set "FLEETDIR=%~dp0tools\mid_baseline\fleet"
if exist "%~dp0app\services\tools\fleet\write_site_env.py" set "FLEETDIR=%~dp0app\services\tools\fleet"

set "PROBE="
if exist "%~dp0gateway_probe\mkcard.py" set "PROBE=%~dp0gateway_probe"
if exist "%~dp0tools\mid_baseline\gateway_probe\mkcard.py" set "PROBE=%~dp0tools\mid_baseline\gateway_probe"
if exist "%~dp0app\services\tools\gateway_probe\mkcard.py" set "PROBE=%~dp0app\services\tools\gateway_probe"

echo ============================================
echo  设置现场配置（只需做一次）
echo ============================================
echo.
if not defined FLEETDIR (
  echo 找不到 write_site_env.py，请在完整包里运行。
  pause
  exit /b 1
)

"%PYEXE%" -X utf8 "%FLEETDIR%\write_site_env.py" "%~dp0site.env"
if errorlevel 1 (
  echo.
  pause
  exit /b 1
)

echo.
echo == 自检
"%PYEXE%" -X utf8 "%PROBE%\mkcard.py" --check --env "%~dp0site.env"
echo.
echo 下一步：双击 MK_CARDS.cmd 做卡。
pause
