@echo off
cd /d "%~dp0\..\.."
python -X utf8 -m tools.mobile_node agent %*
