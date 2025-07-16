# Mapperatorinator API - CPU部署指南

本指南介绍如何在没有GPU的服务器上部署Mapperatorinator API。

## 文件说明

- `Dockerfile.cpu` - CPU版本的Docker镜像定义
- `docker-compose.simple.yml` - 简单部署配置（仅API服务）
- `docker-compose.cpu.yml` - 完整部署配置（API + Nginx）
- `nginx.conf` - Nginx反向代理配置
- `deploy.sh` / `deploy.bat` - 自动部署脚本
- `progress_monitor.html` - 进度监控Web界面

## 快速开始

### 方式1: 自动部署（推荐）

**Linux/macOS:**
```bash
chmod +x deploy.sh
./deploy.sh
```

**Windows:**
```cmd
deploy.bat
```

### 方式2: 手动部署

**简单部署（仅API服务）:**
```bash
# 创建必要目录
mkdir -p audio_storage outputs logs

# 构建并启动
docker compose -f docker-compose.simple.yml up -d --build

# 查看状态
docker compose -f docker-compose.simple.yml ps
```

**完整部署（带Nginx）:**
```bash
# 创建必要目录
mkdir -p audio_storage outputs logs

# 构建并启动
docker compose -f docker-compose.cpu.yml up -d --build

# 查看状态
docker compose -f docker-compose.cpu.yml ps
```

## 访问地址

### 简单部署
- API服务: http://localhost:8000
- API文档: http://localhost:8000/docs
- ReDoc文档: http://localhost:8000/redoc

### 完整部署
- Web界面: http://localhost/ (进度监控页面)
- API服务: http://localhost/api/ 或 http://localhost:8000
- API文档: http://localhost/docs
- ReDoc文档: http://localhost/redoc

## 使用方法

### 1. Web界面使用

访问 `http://localhost:8000/progress_monitor.html` (简单部署) 或 `http://localhost/` (完整部署)

1. 选择音频文件
2. 配置参数
3. 点击"上传并开始新任务"
4. 实时监控处理进度
5. 下载生成的beatmap文件

### 2. API直接调用

**上传音频并开始处理:**
```bash
curl -X POST "http://localhost:8000/process" \
  -F "audio_file=@your_audio.mp3" \
  -F "model=v30" \
  -F "difficulty=5.0" \
  -F "gamemode=0"
```

**查询任务状态:**
```bash
curl "http://localhost:8000/jobs/{job_id}/status"
```

**查询详细进度:**
```bash
curl "http://localhost:8000/jobs/{job_id}/progress"
```

**下载结果:**
```bash
curl -O "http://localhost:8000/jobs/{job_id}/download"
```

## 配置说明

### 环境变量

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `OMP_NUM_THREADS` | 4 | OpenMP线程数 |
| `MKL_NUM_THREADS` | 4 | MKL线程数 |
| `TORCH_NUM_THREADS` | 4 | PyTorch线程数 |
| `CUDA_VISIBLE_DEVICES` | "" | 禁用GPU |

### 资源限制

默认配置：
- 内存限制: 8GB
- CPU限制: 4核
- 共享内存: 2GB

可在docker-compose文件中调整：
```yaml
deploy:
  resources:
    limits:
      memory: 16G        # 调整内存限制
      cpus: '8.0'        # 调整CPU限制
```

### 数据持久化

数据目录映射：
- `audio_storage/` - 上传的音频文件
- `outputs/` - 生成的beatmap文件
- `logs/` - 日志文件

## 常用命令

```bash
# 查看实时日志
docker compose -f docker-compose.simple.yml logs -f

# 重启服务
docker compose -f docker-compose.simple.yml restart

# 停止服务
docker compose -f docker-compose.simple.yml down

# 查看容器状态
docker compose -f docker-compose.simple.yml ps

# 进入容器
docker exec -it mapperatorinator_api_cpu bash

# 查看资源使用
docker stats mapperatorinator_api_cpu
```

## 性能优化

### CPU优化
1. 调整线程数环境变量
2. 使用更多CPU核心
3. 增加内存限制

### 存储优化
1. 使用SSD存储
2. 定期清理旧文件
3. 使用外部存储挂载

### 网络优化
1. 使用Nginx反向代理
2. 启用gzip压缩
3. 设置适当的超时时间

## 故障排除

### 常见问题

**1. 服务启动失败**
```bash
# 查看详细日志
docker compose logs mapperatorinator-api

# 检查端口占用
netstat -tulpn | grep :8000
```

**2. 内存不足**
```bash
# 增加内存限制
# 编辑docker-compose文件中的memory限制
```

**3. 处理速度慢**
```bash
# 增加CPU核心数
# 调整线程数环境变量
```

**4. 文件上传失败**
```bash
# 检查磁盘空间
df -h

# 检查文件权限
ls -la audio_storage/
```

### 监控和日志

**查看系统资源:**
```bash
docker stats
```

**查看应用日志:**
```bash
docker compose logs -f mapperatorinator-api
```

**查看nginx日志（完整部署）:**
```bash
docker compose logs -f nginx
```

## 生产环境建议

1. **安全性**
   - 配置防火墙规则
   - 使用HTTPS
   - 设置访问限制

2. **可靠性**
   - 配置自动重启
   - 设置健康检查
   - 定期备份数据

3. **性能**
   - 使用负载均衡
   - 配置缓存
   - 监控资源使用

4. **维护**
   - 定期更新镜像
   - 清理旧文件
   - 监控日志

## 技术支持

如有问题，请查看：
1. 容器日志
2. API文档
3. 系统资源状态
4. 网络连接情况
