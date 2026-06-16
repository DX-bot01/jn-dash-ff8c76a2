@echo off
chcp 65001 >nul
title 济南区域 · 销售数据监督仪表盘

echo ========================================
echo   济南区域 · 销售数据监督仪表盘
echo ========================================
echo.

echo [1/2] 从 D:\zkn\济南\数据\ 读取本月/上月CSV并转换...
python convert.py --mode all
echo.

echo [2/2] 启动网页服务...
echo.
echo   仪表盘地址: http://localhost:8765
echo.
echo   请勿关闭此窗口，按 Ctrl+C 退出
echo ========================================
echo.

start http://localhost:8765
python -m http.server 8765
