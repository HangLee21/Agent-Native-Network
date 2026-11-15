@echo off
cd /d "%~dp0"
if /i "%~1"=="--rollback" goto rollback
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0app\gateway_setup\bootstrap.ps1"
exit /b %errorlevel%
:rollback
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0app\gateway_setup\bootstrap.ps1" -Rollback
exit /b %errorlevel%
