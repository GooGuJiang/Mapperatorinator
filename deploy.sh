#!/bin/bash

# Mapperatorinator CPU部署脚本

set -e

echo "🎮 Mapperatorinator CPU部署脚本"
echo "================================"

# 检查Docker和Docker Compose
if ! command -v docker &> /dev/null; then
    echo "❌ Docker未安装，请先安装Docker"
    exit 1
fi

if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo "❌ Docker Compose未安装，请先安装Docker Compose"
    exit 1
fi

# 选择部署方式
echo "请选择部署方式:"
echo "1) 简单部署 (仅API服务)"
echo "2) 完整部署 (API + Nginx)"
read -p "请输入选择 (1-2): " choice

case $choice in
    1)
        COMPOSE_FILE="docker-compose.simple.yml"
        echo "📦 使用简单部署模式"
        ;;
    2)
        COMPOSE_FILE="docker-compose.cpu.yml"
        echo "📦 使用完整部署模式"
        ;;
    *)
        echo "❌ 无效选择，使用默认简单部署"
        COMPOSE_FILE="docker-compose.simple.yml"
        ;;
esac

# 创建必要的目录
echo "📁 创建必要目录..."
mkdir -p audio_storage outputs logs

# 检查配置文件
if [ ! -f "$COMPOSE_FILE" ]; then
    echo "❌ 配置文件 $COMPOSE_FILE 不存在"
    exit 1
fi

# 停止现有服务
echo "🛑 停止现有服务..."
docker-compose -f "$COMPOSE_FILE" down 2>/dev/null || true

# 构建镜像
echo "🔨 构建Docker镜像..."
docker-compose -f "$COMPOSE_FILE" build --no-cache

# 启动服务
echo "🚀 启动服务..."
docker-compose -f "$COMPOSE_FILE" up -d

# 等待服务启动
echo "⏳ 等待服务启动..."
sleep 10

# 检查服务状态
echo "📊 检查服务状态..."
docker-compose -f "$COMPOSE_FILE" ps

# 显示日志
echo "📝 显示最近日志..."
docker-compose -f "$COMPOSE_FILE" logs --tail=20

# 健康检查
echo "🔍 执行健康检查..."
sleep 5

if curl -f http://localhost:8000/ &> /dev/null; then
    echo "✅ API服务运行正常"
    echo "🌐 API文档: http://localhost:8000/docs"
    echo "📚 ReDoc: http://localhost:8000/redoc"
    if [ "$COMPOSE_FILE" = "docker-compose.cpu.yml" ]; then
        echo "🎨 Web界面: http://localhost/"
    fi
else
    echo "❌ API服务健康检查失败"
    echo "📝 查看详细日志:"
    docker-compose -f "$COMPOSE_FILE" logs mapperatorinator-api
    exit 1
fi

echo ""
echo "✅ 部署完成!"
echo "================================"
echo "常用命令:"
echo "  查看日志: docker-compose -f $COMPOSE_FILE logs -f"
echo "  停止服务: docker-compose -f $COMPOSE_FILE down"
echo "  重启服务: docker-compose -f $COMPOSE_FILE restart"
echo "  查看状态: docker-compose -f $COMPOSE_FILE ps"
echo "================================"
