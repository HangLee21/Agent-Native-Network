@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul
if not exist "runtime\python\python.exe" goto checkpy
"runtime\python\python.exe" -X utf8 app\flash\flash_nodes.py %*
goto finished
:checkpy
py -3 --version >nul 2>nul
if errorlevel 1 goto checkpython
py -3 -X utf8 app\flash\flash_nodes.py %*
goto finished
:checkpython
python --version >nul 2>nul
if errorlevel 1 goto missing
python -X utf8 app\flash\flash_nodes.py %*
goto finished
:missing
echo Python runtime is missing. No devices were flashed.
echo Please restore the complete delivery package.
if "%~1"=="" pause
exit /b 2
:finished
set "result=%errorlevel%"
if "%~1"=="" pause
exit /b %result%
