@echo off
setlocal
cd /d "%~dp0..\..\.."
if exist ".local\espnow\E1-015\tools\python_env\idf5.5_py3.11_env\Scripts\python.exe" (
  ".local\espnow\E1-015\tools\python_env\idf5.5_py3.11_env\Scripts\python.exe" "tools\mid_hardware\console\launch_console.py" %*
) else (
  echo Existing project Python environment was not found.
  pause
  exit /b 1
)
if errorlevel 1 pause
