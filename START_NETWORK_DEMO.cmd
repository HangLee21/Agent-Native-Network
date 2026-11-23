@echo off
setlocal
cd /d "%~dp0frontend"
if not exist "node_modules\vite" (
  echo Installing locked frontend dependencies...
  call npm ci --no-audit --no-fund
  if errorlevel 1 exit /b 1
)
echo ISOLATED SYNTHETIC DEMO: open http://127.0.0.1:5188/mock-studio.html
echo This is NOT the real-data workspace. Do not run both launchers on the same port.
call npm run network:dev
set "result=%errorlevel%"
if not "%result%"=="0" pause
exit /b %result%
