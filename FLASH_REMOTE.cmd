@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
chcp 65001 >nul

rem 远程机群刷板（经 Tailscale，可跨网络）。两棵树里内容一致：
rem   fleet\                        -> 生产做卡包
rem   tools\mid_baseline\fleet\    -> 开发仓库
rem   app\services\tools\fleet\    -> 交付包
rem 参数直通 flash_nodes.py，例如 --group 2 或 --only eora-air-06。

set "PYEXE="
if exist "%~dp0runtime\python\python.exe" set "PYEXE=%~dp0runtime\python\python.exe"
if not defined PYEXE if exist "%~dp0.local\espnow\E1-015\tools\python_env\idf5.5_py3.11_env\Scripts\python.exe" set "PYEXE=%~dp0.local\espnow\E1-015\tools\python_env\idf5.5_py3.11_env\Scripts\python.exe"
if not defined PYEXE set "PYEXE=python"

set "FLEETDIR="
if exist "%~dp0fleet\flash_nodes.py" set "FLEETDIR=%~dp0fleet"
if not defined FLEETDIR if exist "%~dp0tools\mid_baseline\fleet\flash_nodes.py" set "FLEETDIR=%~dp0tools\mid_baseline\fleet"
if not defined FLEETDIR if exist "%~dp0app\services\tools\fleet\flash_nodes.py" set "FLEETDIR=%~dp0app\services\tools\fleet"

if /i "%~1"=="--which" (
  echo kind=remote  target=flash_nodes.py
  echo fleetdir=%FLEETDIR%
  echo python=%PYEXE%
  exit /b 0
)

if not defined FLEETDIR goto nothere

echo ============================================
echo  远程刷板（经 Tailscale，可跨网络）
echo ============================================
echo.
"%PYEXE%" -X utf8 "%FLEETDIR%\flash_nodes.py" %*
goto finished

:nothere
echo 找不到 flash_nodes.py（fleet\ / tools\mid_baseline\fleet\ / app\services\tools\fleet\）
echo 请在完整的交付包或开发仓库根目录运行。
if "%~1"=="" pause
exit /b 2

:finished
set "result=%errorlevel%"
if "%~1"=="" pause
exit /b %result%
