@echo off
echo 🎮 Starting Mapperatorinator API Server
echo ==========================================

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python is not installed or not in PATH
    echo Please install Python 3.8+ and try again
    pause
    exit /b 1
)

REM Check if required packages are installed
echo 📦 Checking dependencies...
python -c "import fastapi, uvicorn" >nul 2>&1
if errorlevel 1 (
    echo ⚠️ Missing required packages. Installing...
    pip install fastapi uvicorn sse-starlette
    if errorlevel 1 (
        echo ❌ Failed to install dependencies
        pause
        exit /b 1
    )
)

REM Create necessary directories
if not exist "uploads" mkdir uploads
if not exist "outputs" mkdir outputs

echo ✅ Dependencies OK
echo 🚀 Starting API server...
echo.
echo 🌐 API Documentation: http://127.0.0.1:8000/docs
echo 📚 ReDoc: http://127.0.0.1:8000/redoc
echo.
echo Press Ctrl+C to stop the server
echo ==========================================

REM Start the server
python api_server.py --host 127.0.0.1 --port 8000

echo.
echo 🛑 Server stopped
pause
