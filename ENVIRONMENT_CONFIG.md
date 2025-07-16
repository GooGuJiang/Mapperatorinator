# 环境变量配置说明

## 环境变量优先级

Mapperatorinator API 使用以下优先级加载配置：

1. **Docker/系统环境变量** (最高优先级)
2. **.env文件** (中等优先级)
3. **代码默认值** (最低优先级)

## 部署场景配置

### 本地开发
```bash
# .env 文件
REDIS_HOST=localhost
REDIS_PORT=6379
```

### Docker Compose部署
```yaml
# docker-compose.yaml
environment:
  - REDIS_HOST=redis      # 指向Docker服务名
  - REDIS_PORT=6379
```

### 生产环境
```bash
# 系统环境变量或Kubernetes ConfigMap
export REDIS_HOST=your-redis-server.com
export REDIS_PORT=6379
export REDIS_PASSWORD=your-password
```

## 配置变量

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `REDIS_HOST` | `localhost` | Redis服务器地址 |
| `REDIS_PORT` | `6379` | Redis端口 |
| `REDIS_PASSWORD` | `None` | Redis密码(可选) |
| `REDIS_DB` | `1` | Redis数据库编号 |

## 验证配置

启动API后，访问 `/debug/redis` 端点查看Redis连接状态：

```bash
curl http://localhost:8000/debug/redis
```

响应示例：
```json
{
  "status": "connected",
  "database": 1,
  "redis_info": {
    "version": "7.0.11",
    "used_memory": "1.00M"
  }
}
```
