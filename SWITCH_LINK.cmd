@echo off
setlocal
cd /d "%~dp0"

rem Switch the field nodes between ESP-NOW and the 2.4 GHz LoRa link layer.
rem
rem   SWITCH_LINK.cmd lora24                 all online nodes -> 2.4 GHz LoRa
rem   SWITCH_LINK.cmd espnow                 all online nodes -> ESP-NOW
rem   SWITCH_LINK.cmd status                 read-only, show current settings
rem   SWITCH_LINK.cmd lora24 eora-air-01     only the named devices
rem   SWITCH_LINK.cmd espnow --no-reboot     write only, no reboot
rem
rem Requires: nodes reachable over Tailscale, .local\mid\pi\sudo_pass.txt current.

set "PY=C:\environment\python3.11\python.exe"
if not exist "%PY%" set "PY=python"

if "%~1"=="" goto usage
"%PY%" -X utf8 "tools\mid_baseline\fleet\switch_link.py" %*
goto end

:usage
echo.
echo   usage: SWITCH_LINK.cmd ^<espnow^|lora24^|status^> [device...] [--no-reboot]
echo.
echo   e.g.   SWITCH_LINK.cmd lora24
echo          SWITCH_LINK.cmd espnow eora-air-01 eora-air-03
echo          SWITCH_LINK.cmd status
echo.

:end
endlocal
