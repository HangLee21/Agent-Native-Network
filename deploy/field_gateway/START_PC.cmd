@echo off
cd /d "%~dp0\..\.."
python -X utf8 -m tools.field_gateway serve %*
