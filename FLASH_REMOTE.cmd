@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
chcp 65001 >nul

rem 远程刷板（经 Tailscale，可跨网络）
rem
rem   FLASH_REMOTE.cmd                   归一化链路 -> 远程刷机 -> 读回校验
rem   FLASH_REMOTE.cmd --only eora-air-01   只刷指定设备
rem   FLASH_REMOTE.cmd --skip-normalize     不归一化，直接刷（保留 NVS 链路配置）
rem   FLASH_REMOTE.cmd --list               列出可用镜像（不刷机）
rem
rem 为什么默认归一化：esptool 只写 app 分区，NVS 保留 link_mode 与射频角色。
rem 节点若停在 lora24 且未设 role=link，重烧后会既无 Wi-Fi 也无 2.4G 链路。

set "PYEXE="
if exist "%~dp0runtime\python\python.exe" set "PYEXE=%~dp0runtime\python\python.exe"
if not defined PYEXE if exist "%~dp0.local\espnow\E1-015\tools\python_env\idf5.5_py3.11_env\Scripts\python.exe" set "PYEXE=%~dp0.local\espnow\E1-015\tools\python_env\idf5.5_py3.11_env\Scripts\python.exe"
if not defined PYEXE set "PYEXE=python"

set "FLEETDIR="
if exist "%~dp0fleet\flash_nodes.py" set "FLEETDIR=%~dp0fleet"
if not defined FLEETDIR if exist "%~dp0tools\mid_baseline\fleet\flash_nodes.py" set "FLEETDIR=%~dp0tools\mid_baseline\fleet"
if not defined FLEETDIR if exist "%~dp0app\services\tools\mid_baseline\fleet\flash_nodes.py" set "FLEETDIR=%~dp0app\services\tools\mid_baseline\fleet"
if not defined FLEETDIR if exist "%~dp0app\services\tools\fleet\flash_nodes.py" set "FLEETDIR=%~dp0app\services\tools\fleet"

if /i "%~1"=="--which" (
  echo kind=remote  target=flash_nodes.py
  echo fleetdir=%FLEETDIR%
  echo python=%PYEXE%
  exit /b 0
)

set "NORMALIZE=1"
set "ARGS="

:parse
if "%~1"=="" goto haveargs
if /i "%~1"=="--skip-normalize" (set "NORMALIZE=0" & shift & goto parse)
if /i "%~1"=="--list" (set "NORMALIZE=0")
if /i "%~1"=="--which" (set "NORMALIZE=0")
set "ARGS=%ARGS% %1"
shift
goto parse

:haveargs
if not defined FLEETDIR goto nothere

echo ============================================
echo  远程刷板（经 Tailscale，可跨网络）
echo ============================================
echo.

if "%NORMALIZE%"=="1" (
  if exist "%FLEETDIR%\switch_link.py" (
    echo -- 1/3 归一化链路状态为 espnow（只写 NVS，不额外重启）
    "%PYEXE%" -X utf8 "%FLEETDIR%\switch_link.py" espnow --no-reboot
    echo.
  ) else (
    echo -- 1/3 跳过：未找到 switch_link.py
  )
) else (
  echo -- 1/3 跳过归一化
)

echo -- 2/3 刷写固件
"%PYEXE%" -X utf8 "%FLEETDIR%\flash_nodes.py"%ARGS%
if errorlevel 1 goto failed

if "%NORMALIZE%"=="1" (
  if exist "%FLEETDIR%\node_config.py" (
    echo.
    echo -- 3/3 读回校验
    "%PYEXE%" -X utf8 "%FLEETDIR%\node_config.py" read
  )
)
goto finished

:failed
echo.
echo 刷写失败。不要盲目断电重启，先看上面的输出。
if "%~1"=="" pause
exit /b 1

:nothere
echo 找不到 flash_nodes.py（fleet\ / tools\mid_baseline\fleet\ / app\services\tools\...\fleet\）
echo 请在完整的交付包或开发仓库根目录运行。
if "%~1"=="" pause
exit /b 2

:finished
set "result=%errorlevel%"
if "%~1"=="" pause
exit /b %result%