@echo off
setlocal
cd /d "%~dp0"

rem Isolated MOCK workspace (synthetic data): recording + replay, no hardware.
rem Real workspace is START_STUDIO.cmd (port 10518, studio.html).
rem This one runs scripts\network-studio\dev.mjs WITHOUT --real -> mock API on 18081,
rem Vue on port 5188, mock page at /mock-studio.html.

set "PORT=5188"

rem Already running? Just open the mock page.
netstat -ano | findstr /R /C:":%PORT% .*LISTENING" >nul 2>&1
if not errorlevel 1 (
  echo Mock studio already running on port %PORT%.
  start "" "http://127.0.0.1:%PORT%/mock-studio.html"
  goto end
)

echo Starting isolated mock studio ^(synthetic data, no hardware^)...
start "" /b cmd /c "timeout /t 12 >nul & start "" http://127.0.0.1:%PORT%/mock-studio.html"
node "scripts\network-studio\dev.mjs"

:end
endlocal
