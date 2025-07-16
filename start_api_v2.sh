#!/bin/bash

echo "启动 Mapperatorinator API v2.0..."
echo

# 检查Python
if ! command -v python3 &> /dev/null; then
    if ! command -v python &> /dev/null; then
        echo "错误: 找不到Python，请确保Python已安装"
        exit 1
    fi
    PYTHON=python
else
    PYTHON=python3
fi

echo "使用Python: $($PYTHON --version)"

# 检查依赖包
echo "检查依赖包..."
$PYTHON -c "import fastapi, uvicorn, sse_starlette" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "安装缺少的依赖包..."
    $PYTHON -m pip install fastapi uvicorn sse-starlette
    if [ $? -ne 0 ]; then
        echo "错误: 依赖包安装失败"
        exit 1
    fi
fi

# 启动API服务器
echo
echo "==================================="
echo " 🎮 Mapperatorinator API v2.0"
echo "==================================="
echo " 📖 API文档: http://127.0.0.1:8000/docs"
echo " 📚 ReDoc: http://127.0.0.1:8000/redoc"
echo "==================================="
echo

$PYTHON api_v2.py --host 0.0.0.0 --port 8000
