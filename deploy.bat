@echo off
setlocal enabledelayedexpansion

echo 🎮 Mapperatorinator CPU部署脚本
echo ================================

REM 检查Docker
docker --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Docker未安装，请先安装Docker Desktop
    pause
    exit /b 1
)

REM 检查Docker Compose
docker compose version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Docker Compose未安装，请先安装Docker Compose
    pause
    exit /b 1
)

REM 选择部署方式
echo 请选择部署方式:
echo 1) 简单部署 (仅API服务)
echo 2) 完整部署 (API + Nginx)
set /p choice="请输入选择 (1-2): "

if "%choice%"=="1" (
    set COMPOSE_FILE=docker-compose.simple.yml
    echo 📦 使用简单部署模式
) else if "%choice%"=="2" (
    set COMPOSE_FILE=docker-compose.cpu.yml
    echo 📦 使用完整部署模式
) else (
    echo ❌ 无效选择，使用默认简单部署
    set COMPOSE_FILE=docker-compose.simple.yml
)

REM 创建必要的目录
echo 📁 创建必要目录...
if not exist "audio_storage" mkdir audio_storage
if not exist "outputs" mkdir outputs
if not exist "logs" mkdir logs

REM 检查配置文件
if not exist "%COMPOSE_FILE%" (
    echo ❌ 配置文件 %COMPOSE_FILE% 不存在
    pause
    exit /b 1
)

REM 停止现有服务
echo 🛑 停止现有服务...
docker compose -f "%COMPOSE_FILE%" down 2>nul

REM 构建镜像
echo 🔨 构建Docker镜像...
docker compose -f "%COMPOSE_FILE%" build --no-cache
if %errorlevel% neq 0 (
    echo ❌ 镜像构建失败
    pause
    exit /b 1
)

REM 启动服务
echo 🚀 启动服务...
docker compose -f "%COMPOSE_FILE%" up -d
if %errorlevel% neq 0 (
    echo ❌ 服务启动失败
    pause
    exit /b 1
)

REM 等待服务启动
echo ⏳ 等待服务启动...
timeout /t 10 /nobreak >nul

REM 检查服务状态
echo 📊 检查服务状态...
docker compose -f "%COMPOSE_FILE%" ps

REM 显示日志
echo 📝 显示最近日志...
docker compose -f "%COMPOSE_FILE%" logs --tail=20

REM 健康检查
echo 🔍 执行健康检查...
timeout /t 5 /nobreak >nul

curl -f http://localhost:8000/ >nul 2>&1
if %errorlevel% equ 0 (
    echo ✅ API服务运行正常
    echo 🌐 API文档: http://localhost:8000/docs
    echo 📚 ReDoc: http://localhost:8000/redoc
    if "%COMPOSE_FILE%"=="docker-compose.cpu.yml" (
        echo 🎨 Web界面: http://localhost/
    )
) else (
    echo ❌ API服务健康检查失败
    echo 📝 查看详细日志:
    docker compose -f "%COMPOSE_FILE%" logs mapperatorinator-api
    pause
    exit /b 1
)

echo.
echo ✅ 部署完成!
echo ================================
echo 常用命令:
echo   查看日志: docker compose -f %COMPOSE_FILE% logs -f
echo   停止服务: docker compose -f %COMPOSE_FILE% down
echo   重启服务: docker compose -f %COMPOSE_FILE% restart
echo   查看状态: docker compose -f %COMPOSE_FILE% ps
echo ================================
pause
