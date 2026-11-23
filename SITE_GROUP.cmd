@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
chcp 65001 >nul

set "PYEXE=%~dp0.local\espnow\E1-015\tools\python_env\idf5.5_py3.11_env\Scripts\python.exe"
if not exist "%PYEXE%" set "PYEXE=python"

set "FLEETDIR="
if exist "%~dp0fleet\fleet.py" set "FLEETDIR=%~dp0fleet"
if exist "%~dp0tools\mid_baseline\fleet\fleet.py" set "FLEETDIR=%~dp0tools\mid_baseline\fleet"

if not exist "%~dp0site.env" (
  echo 还没有 site.env，请先双击 SETUP_SITE.cmd
  pause
  exit /b 1
)

echo ============================================
echo  设置分组（ESP-NOW 同组才互相可见）
echo ============================================
echo.
echo   本地组 = group 1 / 信道 1
echo   远程组 = group 2 / 信道 6
echo.

set "G=%~1"
if "%G%"=="" set /p "G=组号 (1 或 2): "
if "%G%"=="" goto bad

set "CH=%~2"
if "%CH%"=="" set /p "CH=WiFi 信道 (1-13): "
if "%CH%"=="" goto bad

rem 第 3 个参数起是设备名；没有则作用于全部在线设备
shift
shift
set "ONLYARG="
:collect
if "%~1"=="" goto go
set "ONLYARG=!ONLYARG! %~1"
shift
goto collect

:go
if defined ONLYARG (
  echo 只作用于:!ONLYARG!
) else (
  echo 作用于全部在线设备
)
echo.
pause

if defined ONLYARG (
  "%PYEXE%" -X utf8 "%FLEETDIR%\fleet.py" group --group %G% --channel %CH% --only!ONLYARG!
) else (
  "%PYEXE%" -X utf8 "%FLEETDIR%\fleet.py" group --group %G% --channel %CH%
)
set "result=%errorlevel%"
echo.
echo 核对输出里的 group_reported 是否等于 %G%
pause
exit /b %result%

:bad
echo 组号和信道都必须填写。
pause
exit /b 1
