@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ==================================================
echo   古牛量化系统 (Windows)
echo ==================================================

where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 未找到 python，请先安装 Python 3.10+ 并加入 PATH
    pause
    exit /b 1
)

echo 正在检查/安装依赖...
python -m pip install -q -r requirements.txt

echo.
echo 可选：设置美股 Alpha Vantage Key（不设则用 demo，额度极低）
echo   set ALPHA_VANTAGE_KEY=你的key
echo.
echo 启动中... 访问地址: http://127.0.0.1:5888
echo 按 Ctrl+C 停止
echo.
python app.py
pause
