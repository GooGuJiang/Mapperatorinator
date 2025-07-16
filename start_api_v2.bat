@echo off
echo 启动 Mapperatorinator API v2.0...
echo.

REM 检查Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo 错误: 找不到Python，请确保Python已安装并在PATH中
    pause
    exit /b 1
)

REM 检查依赖包
echo 检查依赖包...
python -c "import fastapi, uvicorn, sse_starlette" >nul 2>&1
if %errorlevel% neq 0 (
    echo 安装缺少的依赖包...
    pip install fastapi uvicorn sse-starlette
    if %errorlevel% neq 0 (
        echo 错误: 依赖包安装失败
        pause
        exit /b 1
    )
)

REM 启动API服务器
echo.
echo ===================================
echo  🎮 Mapperatorinator API v2.0
echo ===================================
echo  📖 API文档: http://127.0.0.1:8000/docs
echo  📚 ReDoc: http://127.0.0.1:8000/redoc
echo ===================================
echo.

python api_v2.py --host 0.0.0.0 --port 8000

pause
