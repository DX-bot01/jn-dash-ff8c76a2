@echo off
chcp 65001 >nul
title 济南仪表盘 · Netlify 一次性设置

set "PYTHON=C:\Users\L\.workbuddy\binaries\python\versions\3.13.12\python.exe"
set "SCRIPT=%~dp0netlify_setup.py"

echo.
if not exist "%PYTHON%" (
  echo [ERROR] Python 未找到
  pause
  exit /b 1
)

"%PYTHON%" "%SCRIPT%"
echo.
echo 按任意键关闭...
pause >nul
