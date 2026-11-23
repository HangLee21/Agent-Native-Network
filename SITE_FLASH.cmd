@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
chcp 65001 >nul

set "PYEXE=%~dp0.local\espnow\E1-015\tools\python_env\idf5.5_py3.11_env\Scripts\python.exe"
if not exist "%PYEXE%" set "PYEXE=python"

set "FLEETDIR="
if exist "%~dp0fleet\flash_nodes.py" set "FLEETDIR=%~dp0fleet"
if exist "%~dp0tools\mid_baseline\fleet\flash_nodes.py" set "FLEETDIR=%~dp0tools\mid_baseline\fleet"
if exist "%~dp0app\services\tools\fleet\flash_nodes.py" set "FLEETDIR=%~dp0app\services\tools\fleet"

if not exist "%~dp0site.env" (
  echo 还没有 site.env，请先双击 SETUP_SITE.cmd
  pause
  exit /b 1
)

echo ============================================
echo  批量刷固件
echo ============================================
echo.
echo   1 = 本地组   (group 1)
echo   2 = 远程组   (group 2)
echo   3 = 全部
echo   4 = 只刷一台（接下来输入设备名）
echo.
set "WHICH=%~1"
if "%WHICH%"=="" set /p "WHICH=选择 [3]: "
if "%WHICH%"=="" set "WHICH=3"

set "ARG="
if "%WHICH%"=="1" set "ARG=--group 1"
if "%WHICH%"=="2" set "ARG=--group 2"
if "%WHICH%"=="4" (
  set /p "ONE=设备名（如 eora-air-06）: "
  set "ARG=--only !ONE!"
)

echo.
"%PYEXE%" -X utf8 "%FLEETDIR%\flash_nodes.py" !ARG!
set "result=%errorlevel%"
echo.
echo 刷完再用 SITE_STATUS.cmd 看 build 是否一致。
pause
exit /b %result%
