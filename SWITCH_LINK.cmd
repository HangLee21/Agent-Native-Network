@echo off
setlocal
cd /d "%~dp0"

rem Switch the field nodes between ESP-NOW and the 2.4 GHz LoRa link layer.
rem   SWITCH_LINK.cmd lora24 | espnow | status [device...] [--no-reboot]

set "PY=C:\environment\python3.11\python.exe"
if not exist "%PY%" set "PY=python"

if "%~1"=="" goto usage
"%PY%" -X utf8 "app\services\tools\mid_baseline\fleet\switch_link.py" %*
goto end

:usage
echo.
echo   usage: SWITCH_LINK.cmd ^<espnow^|lora24^|status^> [device...] [--no-reboot]
echo.

:end
endlocal