@echo off
setlocal
cd /d "%~dp0frontend"
if not exist "node_modules\vite" (
  echo Installing locked frontend dependencies...
  call npm ci --no-audit --no-fund
  if errorlevel 1 exit /b 1
)
echo Starting REAL workspace only. No mock service is started.
echo Select Server or Local gateway, then explicitly connect.
call npm run network:real
set "result=%errorlevel%"
if not "%result%"=="0" pause
exit /b %result%
