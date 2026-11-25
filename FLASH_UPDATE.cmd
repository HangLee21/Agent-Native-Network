@echo off
setlocal
cd /d "%~dp0"

rem One-command node update: normalise link state, flash, then verify.
rem
rem   FLASH_UPDATE.cmd                    flash every online node with firmware\mid_edge.bin
rem   FLASH_UPDATE.cmd path\to\image.bin  flash a specific image
rem   FLASH_UPDATE.cmd --skip-normalize   flash only (keep the current NVS link settings)
rem
rem Why normalise first: esptool writes the app partition only, so NVS keeps link_mode and
rem the radio role. A node left in lora24 without role=link would come back unreachable.
rem Normalising to espnow before the flash, then letting the post-flash reset apply it,
rem keeps every node in a known-good state with a single reboot.

set "PY=C:\environment\python3.11\python.exe"
if not exist "%PY%" set "PY=python"
set "FLEET=app\services\app\services\tools\mid_baseline\fleet"
if not exist "%FLEET%\switch_link.py" set "FLEET=app\services\tools\mid_baseline\fleet"

set "IMAGE=firmware\mid_edge.bin"
set "NORMALIZE=1"
set "ARGS="

:parse
if "%~1"=="" goto run
if /i "%~1"=="--skip-normalize" (set "NORMALIZE=0" & shift & goto parse)
set "IMAGE=%~1"
shift
goto parse

:run
if not exist "%IMAGE%" (
  echo image not found: %IMAGE%
  goto end
)

echo == 1/3 normalise link state to espnow
if "%NORMALIZE%"=="1" (
  "%PY%" -X utf8 "%FLEET%\switch_link.py" espnow --no-reboot
  if errorlevel 1 (
    echo    normalization reported a problem; continuing to flash anyway.
  )
) else (
  echo    skipped
)

echo.
echo == 2/3 flash nodes: %IMAGE%
"%PY%" -X utf8 "%FLEET%\flash_nodes.py" "%IMAGE%"
if errorlevel 1 (
  echo.
  echo FLASH FAILED. Do not power-cycle blindly; read the output above.
  goto end
)

echo.
echo == 3/3 verify configuration
"%PY%" -X utf8 "%FLEET%\node_config.py" read
echo.
echo Done. Nodes are on espnow + 470.5 MHz tx. Use SWITCH_LINK.cmd lora24 for the 2.4 GHz link.

:end
endlocal
