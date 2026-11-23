@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
chcp 65001 >nul

rem 远程机群刷板：经 Tailscale 把固件刷到各台树莓派上的节点板。
rem 本机的 USB 直连刷写是 FLASH_NODES.cmd，两者不要混用。

set "PYEXE=%~dp0.local\espnow\E1-015\tools\python_env\idf5.5_py3.11_env\Scripts\python.exe"
if not exist "%PYEXE%" set "PYEXE=python"
if exist "%~dp0runtime\python\python.exe" set "PYEXE=%~dp0runtime\python\python.exe"

set "FLEETDIR="
if exist "%~dp0fleet\flash_nodes.py" set "FLEETDIR=%~dp0fleet"
if exist "%~dp0tools\mid_baseline\fleet\flash_nodes.py" set "FLEETDIR=%~dp0tools\mid_baseline\fleet"
if exist "%~dp0app\services\tools\fleet\flash_nodes.py" set "FLEETDIR=%~dp0app\services\tools\fleet"

if not defined FLEETDIR (
  echo 找不到 flash_nodes.py，请在完整交付包内运行。
  if "%~1"=="" pause
  exit /b 2
)

echo ============================================
echo  远程刷板（跨网络，经 Tailscale）
echo ============================================
echo.
"%PYEXE%" -X utf8 "%FLEETDIR%\flash_nodes.py" %*
set "result=%errorlevel%"
echo.
if "%~1"=="" pause
exit /b %result%
