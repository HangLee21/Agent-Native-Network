@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
chcp 65001 >nul

set "PYEXE=%~dp0.local\espnow\E1-015\tools\python_env\idf5.5_py3.11_env\Scripts\python.exe"
if not exist "%PYEXE%" set "PYEXE=python"

set "PROBE="
if exist "%~dp0gateway_probe\mkcard.py" set "PROBE=%~dp0gateway_probe"
if exist "%~dp0tools\mid_baseline\gateway_probe\mkcard.py" set "PROBE=%~dp0tools\mid_baseline\gateway_probe"
if exist "%~dp0app\services\tools\gateway_probe\mkcard.py" set "PROBE=%~dp0app\services\tools\gateway_probe"

echo ============================================
echo  批量做卡（自动编号，写完提示换下一张）
echo ============================================
echo.
if not exist "%~dp0site.env" (
  echo 还没有 site.env，请先双击 SETUP_SITE.cmd
  pause
  exit /b 1
)

set "FIRST=%~1"
if "%FIRST%"=="" set /p "FIRST=起始编号 [6]: "
if "%FIRST%"=="" set "FIRST=6"

set "COUNT=%~2"
if "%COUNT%"=="" set /p "COUNT=数量 [15]: "
if "%COUNT%"=="" set "COUNT=15"

echo.
echo 先确认：每张卡都已经用 Raspberry Pi Imager 写好基础镜像
echo   用户名必须是 eora，SSH 必须打开
echo.
echo 编号 %FIRST% 到  %FIRST%+%COUNT%-1  共 %COUNT% 张
echo.
pause

"%PYEXE%" -X utf8 "%PROBE%\mkcard.py" --batch --from %FIRST% --count %COUNT% --env "%~dp0site.env"
set "result=%errorlevel%"
echo.
echo 下一步：把卡插到树莓派上电，等 2-5 分钟再看每个卡上的 eora-status.txt
pause
exit /b %result%
