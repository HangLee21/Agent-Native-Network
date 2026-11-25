@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
chcp 65001 >nul

rem 引导菜单版：选组/选设备后转调 FLASH_REMOTE.cmd（同一个实现，避免两套逻辑）。
rem 两棵树里内容一致；site.env 只影响密码，缺了也能用（fleet 会读环境变量）。

echo ============================================
echo  批量刷固件（远程）
echo ============================================
echo.
echo   1 = 本地组   (group 1)
echo   2 = 远程组   (group 2)
echo   3 = 全部
echo   4 = 只刷一台
echo.
set "WHICH=%~1"
if "%WHICH%"=="" set /p "WHICH=选择 [3]: "
if "%WHICH%"=="" set "WHICH=3"

if "%WHICH%"=="1" call "%~dp0FLASH_REMOTE.cmd" --group 1
if "%WHICH%"=="2" call "%~dp0FLASH_REMOTE.cmd" --group 2
if "%WHICH%"=="3" call "%~dp0FLASH_REMOTE.cmd"
if "%WHICH%"=="4" (
  set /p "ONE=设备名（如 eora-air-06）: "
  call "%~dp0FLASH_REMOTE.cmd" --only !ONE!
)

echo.
echo 刷完再用 SITE_STATUS.cmd 看 build 是否一致。
if "%~1"=="" pause
