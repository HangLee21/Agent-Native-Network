@echo off
setlocal
cd /d "%~dp0..\.."
if exist ".local\espnow\E1-015\tools\python_env\idf5.5_py3.11_env\Scripts\python.exe" (
  ".local\espnow\E1-015\tools\python_env\idf5.5_py3.11_env\Scripts\python.exe" "tools\mid_console\server.py" --open %*
) else (
  py -3 "tools\mid_console\server.py" --open %*
)
if errorlevel 1 pause
