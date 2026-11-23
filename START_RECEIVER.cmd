@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul

rem Development-side LoRa receiver: UDP 1680 from the gateway -> HTTP 8780 for Studio.
rem This is a SEPARATE entry point on purpose. START_STUDIO.cmd in this package launches
rem the packaged app (runtime\python + app\start\launcher.py) and must keep doing exactly that.

if not exist "tools\mid_baseline\gateway_probe\start_frontend.py" (
  echo 这个包没有附带开发侧接收器 ^(tools\mid_baseline\gateway_probe^)。
  echo 打包版请直接用 START_STUDIO.cmd。
  if "%~1"=="" pause
  exit /b 2
)

set "PYEXE=%~dp0.local\espnow\E1-015\tools\python_env\idf5.5_py3.11_env\Scripts\python.exe"
if not exist "%PYEXE%" set "PYEXE=python"

echo Starting receiver (gateway UDP -> local HTTP) in front of the packaged Studio...
"%PYEXE%" -X utf8 "tools\mid_baseline\gateway_probe\start_frontend.py" %*
set "result=%errorlevel%"
if "%~1"=="" pause
exit /b %result%
