#!/bin/bash
# 🐂 古牛量化启动脚本（使用虚拟环境）

cd "$(dirname "$0")"

# 检查虚拟环境是否存在，不存在则创建
if [ ! -d "venv" ]; then
    echo "📦 首次运行，正在创建虚拟环境..."
    python3 -m venv venv
    echo "✅ 虚拟环境创建完成"
fi

echo "📦 正在安装/更新依赖..."
./venv/bin/pip install flask flask-cors akshare yfinance pandas numpy ta requests -q

echo ""
echo "🐂 古牛量化系统启动中..."
echo "📍 访问地址: http://127.0.0.1:5888"
echo "📍 按 Ctrl+C 停止服务"
echo ""
./venv/bin/python3 app.py
