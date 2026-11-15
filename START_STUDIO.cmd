@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul
if not exist "runtime\python\python.exe" goto missing
"runtime\python\python.exe" -X utf8 app\start\launcher.py %*
goto finished
:missing
echo Runtime missing. Please restore the complete delivery package.
if "%~1"=="" pause
exit /b 2
:finished
set "result=%errorlevel%"
if "%~1"=="" pause
exit /b %result%
