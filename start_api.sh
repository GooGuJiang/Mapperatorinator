#!/bin/bash

echo "🎮 Starting Mapperatorinator API Server"
echo "=========================================="

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed or not in PATH"
    echo "Please install Python 3.8+ and try again"
    exit 1
fi

# Check if required packages are installed
echo "📦 Checking dependencies..."
if ! python3 -c "import fastapi, uvicorn" &> /dev/null; then
    echo "⚠️ Missing required packages. Installing..."
    pip3 install fastapi uvicorn sse-starlette
    if [ $? -ne 0 ]; then
        echo "❌ Failed to install dependencies"
        exit 1
    fi
fi

# Create necessary directories
mkdir -p uploads
mkdir -p outputs

echo "✅ Dependencies OK"
echo "🚀 Starting API server..."
echo ""
echo "🌐 API Documentation: http://127.0.0.1:8000/docs"
echo "📚 ReDoc: http://127.0.0.1:8000/redoc"
echo ""
echo "Press Ctrl+C to stop the server"
echo "=========================================="

# Start the server
python3 api_server.py --host 127.0.0.1 --port 8000

echo ""
echo "🛑 Server stopped"
