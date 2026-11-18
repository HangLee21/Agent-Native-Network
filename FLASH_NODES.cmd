@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul

set "PYEXE=%~dp0.local\espnow\E1-015\tools\python_env\idf5.5_py3.11_env\Scripts\python.exe"
if not exist "%PYEXE%" set "PYEXE=python"

echo ============================================
echo  Flash every node in the fleet (one click)
echo ============================================
echo.
"%PYEXE%" -X utf8 tools\mid_baseline\fleet\flash_nodes.py %*
set "result=%errorlevel%"
echo.
if "%~1"=="" pause
exit /b %result%
