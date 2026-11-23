@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
chcp 65001 >nul

rem 本机 USB 直连刷写（串口）。只有交付包带这套刷写台（app\flash）。
rem 远程机群刷板请用 FLASH_REMOTE.cmd —— 两者完全不同，别混用。
rem 本文件在两棵树里内容一致：开发树没有 app\flash，会给出明确提示而不是静默失败。

set "PYEXE="
if exist "%~dp0runtime\python\python.exe" set "PYEXE=%~dp0runtime\python\python.exe"
if not defined PYEXE if exist "%~dp0.local\espnow\E1-015\tools\python_env\idf5.5_py3.11_env\Scripts\python.exe" set "PYEXE=%~dp0.local\espnow\E1-015\tools\python_env\idf5.5_py3.11_env\Scripts\python.exe"
if not defined PYEXE set "PYEXE=python"

if /i "%~1"=="--which" (
  echo kind=local-usb  target=app\flash\flash_nodes.py
  if exist "%~dp0app\flash\flash_nodes.py" (echo found=yes) else (echo found=no)
  echo python=%PYEXE%
  exit /b 0
)

if not exist "%~dp0app\flash\flash_nodes.py" goto nothere

echo ============================================
echo  本机 USB 刷写（串口直连）
echo ============================================
echo.
"%PYEXE%" -X utf8 app\flash\flash_nodes.py %*
goto finished

:nothere
echo 这个仓库没有本机 USB 刷写台（只有交付包带 app\flash）。
echo   远程机群刷板请用: FLASH_REMOTE.cmd
echo   做卡请用:         MK_CARDS.cmd
if "%~1"=="" pause
exit /b 2

:finished
set "result=%errorlevel%"
if "%~1"=="" pause
exit /b %result%
