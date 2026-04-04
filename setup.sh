#!/bin/bash

echo "=========================================="
echo "🚀 歡迎使用 Spoofy iPhone 定位模擬器安裝腳本"
echo "=========================================="

# 檢查 Python 3
if ! command -v python3 &> /dev/null
then
    echo "❌ 找不到 Python 3，請先到 https://www.python.org/ 下載並安裝。"
    exit
fi

# 安裝依賴項
echo "📦 正在安裝必要的 Python 套件 (pymobiledevice3, geopy, certifi)..."
python3 -m pip install -r requirements.txt

if [ $? -eq 0 ]; then
    echo "✅ 安裝成功！"
    echo "=========================================="
    echo "📱 使用方法："
    echo "1. 連接 iPhone 並解鎖"
    echo "2. 執行：python3 spoofy.py"
    echo "=========================================="
else
    echo "❌ 安裝過程中發生錯誤，請手動檢查環境。"
fi
