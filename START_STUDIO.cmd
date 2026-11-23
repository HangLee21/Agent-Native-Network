@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
chcp 65001 >nul

rem 同一个文件在两种树里都能用：
rem   交付包 -> runtime\python + app\start\launcher.py（自带运行时与发布校验）
rem   开发树 -> tools\mid_baseline\gateway_probe\start_frontend.py（接收器 + Studio）
rem 这样两棵树里的本文件内容可以完全一致，不会各自漂移。

set "PYEXE="
if exist "%~dp0runtime\python\python.exe" set "PYEXE=%~dp0runtime\python\python.exe"
if not defined PYEXE if exist "%~dp0.local\espnow\E1-015\tools\python_env\idf5.5_py3.11_env\Scripts\python.exe" set "PYEXE=%~dp0.local\espnow\E1-015\tools\python_env\idf5.5_py3.11_env\Scripts\python.exe"
if not defined PYEXE set "PYEXE=python"

if /i "%~1"=="--which" (
  echo mode=packaged  target=app\start\launcher.py
  if exist "%~dp0app\start\launcher.py" (echo found=yes) else (echo found=no)
  echo mode=dev       target=tools\mid_baseline\gateway_probe\start_frontend.py
  if exist "%~dp0tools\mid_baseline\gateway_probe\start_frontend.py" (echo found=yes) else (echo found=no)
  echo python=%PYEXE%
  exit /b 0
)

if exist "%~dp0app\start\launcher.py" goto packaged
if exist "%~dp0tools\mid_baseline\gateway_probe\start_frontend.py" goto dev
echo 找不到前端入口：既没有 app\start\launcher.py，也没有 tools\mid_baseline\gateway_probe\start_frontend.py
echo 请确认是在完整的交付包或开发仓库根目录运行。
if "%~1"=="" pause
exit /b 2

:packaged
echo Starting packaged Studio (runtime\python + app\start\launcher.py)...
"%PYEXE%" -X utf8 app\start\launcher.py %*
goto finished

:dev
echo Starting development frontend (receiver + Studio)...
"%PYEXE%" -X utf8 tools\mid_baseline\gateway_probe\start_frontend.py %*
goto finished

:finished
set "result=%errorlevel%"
if "%~1"=="" pause
exit /b %result%
