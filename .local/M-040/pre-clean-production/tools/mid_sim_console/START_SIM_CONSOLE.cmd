@echo off
setlocal
cd /d "%~dp0..\.."
if exist ".local\mid\E1-016\venv\Scripts\python.exe" (
  ".local\mid\E1-016\venv\Scripts\python.exe" "tools\mid_sim_console\launch.py"
) else (
  py -3 "tools\mid_sim_console\launch.py"
)
if errorlevel 1 pause
