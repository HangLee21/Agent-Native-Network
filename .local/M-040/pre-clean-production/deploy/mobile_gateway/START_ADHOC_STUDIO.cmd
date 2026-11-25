@echo off
setlocal
cd /d "%~dp0..\.."
python -X utf8 -m tools.mobile_gateway.launch_studio
if errorlevel 1 pause
