# Redis缓存集成

Mapperatorinator API现在支持Redis缓存来优化性能，减少重复计算和提高响应速度。

## 功能特性

### 缓存内容
- **任务进度信息** (`job_progress:*`): 缓存任务的实时进度和状态
- **任务元数据** (`job_metadata:*`): 缓存任务配置参数和基本信息  
- **输出文件列表** (`output_files:*`): 缓存生成的文件列表
- **模型配置** (`model_config:*`): 缓存模型配置信息

### 缓存策略
- **进度信息**: 2小时过期，实时更新
- **元数据**: 2小时过期，任务启动时缓存
- **文件列表**: 1小时过期，文件生成后缓存
- **模型配置**: 24小时过期，长期缓存

## 配置

### 环境变量
```bash
REDIS_HOST=localhost      # Redis主机地址
REDIS_PORT=6379          # Redis端口
```

### 默认配置
- **数据库**: db=1 (避免与其他应用冲突)
- **连接超时**: 5秒
- **内存策略**: allkeys-lru (自动清理旧数据)
- **最大内存**: 256MB

## 部署

### Docker Compose部署
```bash
# 启动完整服务 (包括Redis)
docker-compose up -d

# 仅CPU版本
docker-compose -f docker-compose.cpu.yaml up -d
```

### 本地Redis
```bash
# 安装Redis (Windows)
# 下载并安装Redis for Windows

# 启动Redis服务器
redis-server

# 启动API (会自动连接Redis)
python api_v2.py
```

## 监控工具

### Redis缓存监控
```bash
# 实时监控缓存状态
python monitor_redis.py

# 显示一次性统计信息
python monitor_redis.py --stats

# 清理所有任务缓存
python monitor_redis.py --clear

# 清理特定模式的缓存
python monitor_redis.py --clear "job_progress:*"

# 自定义Redis连接
python monitor_redis.py --host redis-server --port 6380 --db 1
```

### API端点监控
```bash
# Redis状态查询
GET /debug/redis

# 任务缓存调试
GET /jobs/{job_id}/debug
```

## 性能优化

### 优势
1. **减少文件系统访问**: 输出文件列表缓存避免重复遍历目录
2. **跨重启保持状态**: 服务重启后可恢复任务状态信息
3. **减少重复计算**: 进度计算结果缓存
4. **提高响应速度**: 常用数据快速获取

### 内存使用
- 每个任务约占用2-5KB缓存空间
- 100个任务约占用200-500KB
- Redis配置256MB内存可支持数万个任务

## 故障恢复

### Redis不可用
- API会自动降级为内存缓存模式
- 不影响核心功能正常运行
- 仅失去跨重启状态保持能力

### 缓存一致性
- 文件变更时自动更新缓存
- 任务完成时清理相关缓存
- 定期清理过期数据

## 调试

### 检查Redis连接
```bash
curl http://localhost:8000/debug/redis
```

### 查看任务缓存状态
```bash
curl http://localhost:8000/jobs/{job_id}/debug
```

### 手动清理缓存
```python
import redis
r = redis.Redis(host='localhost', port=6379, db=1, decode_responses=True)

# 清理特定任务
r.delete('job_progress:your-job-id')
r.delete('job_metadata:your-job-id') 
r.delete('output_files:your-job-id')

# 清理所有任务缓存
for pattern in ['job_progress:*', 'job_metadata:*', 'output_files:*']:
    keys = r.keys(pattern)
    if keys:
        r.delete(*keys)
```

## 配置调优

### 生产环境建议
```yaml
# docker-compose.yaml
redis:
  command: redis-server --appendonly yes --maxmemory 512mb --maxmemory-policy allkeys-lru
  deploy:
    resources:
      limits:
        memory: 1GB
```

### 性能监控
```bash
# Redis内存使用
redis-cli info memory

# 键数量统计
redis-cli dbsize

# 实时监控
redis-cli monitor
```
