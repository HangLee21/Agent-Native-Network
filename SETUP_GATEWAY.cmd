@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0app\gateway_setup\bootstrap.ps1"
exit /b %errorlevel%
