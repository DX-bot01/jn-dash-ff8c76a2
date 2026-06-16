@echo off
chcp 65001 >nul
title 济南仪表盘 · 一键部署到 Netlify

set "PYTHON=C:\Users\L\.workbuddy\binaries\python\versions\3.13.12\python.exe"
set "DEPLOY_PY=%~dp0deploy.py"

echo ========================================
echo   济南仪表盘 · 一键部署到 Netlify
echo ========================================
echo.

if not exist "%PYTHON%" (
  echo [ERROR] Python 未找到: %PYTHON%
  pause
  exit /b 1
)

if not exist "%DEPLOY_PY%" (
  echo [ERROR] deploy.py 未找到: %DEPLOY_PY%
  pause
  exit /b 1
)

"%PYTHON%" "%DEPLOY_PY%"
if errorlevel 1 (
  echo.
  echo [ERROR] 部署失败，请将上方错误信息发给 WorkBuddy
)
echo.
echo 按任意键关闭窗口...
pause >nul
