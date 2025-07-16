# 🎮 Mapperatorinator API 完整测试指南

## 快速部署测试

### 1. 启动API服务器

**方式1: 直接运行**
```bash
cd "d:\GitHub\Mapperatorinator-gu"
python api_v2.py
```

**方式2: Docker部署**
```bash
# 使用部署脚本
deploy.bat  # Windows
# 或
./deploy.sh  # Linux/Mac
```

### 2. 验证服务状态

运行API测试脚本：
```bash
python test_api_status.py
```

预期输出：
```
🧪 测试 Mapperatorinator API
==================================================
✅ 根端点正常
   API版本: Mapperatorinator API v2.0
✅ 不存在任务的404响应正常
✅ 不存在任务的进度端点404响应正常
✅ 作业列表端点正常
   当前活动任务数: 0
```

### 3. 访问接口

- **API文档**: http://127.0.0.1:8000/docs
- **ReDoc文档**: http://127.0.0.1:8000/redoc
- **进度监控界面**: http://127.0.0.1:8000/progress_monitor.html

## 进度监控功能验证

### 状态端点测试

1. **获取任务状态（包含进度）**：
   ```bash
   curl -X GET "http://127.0.0.1:8000/jobs/{job_id}/status"
   ```
   
   响应格式：
   ```json
   {
     "job_id": "12345-67890",
     "status": "running",
     "message": "正在处理中... (generating_map)",
     "progress": 65.5,
     "output_files": null,
     "error": null
   }
   ```

2. **获取详细进度信息**：
   ```bash
   curl -X GET "http://127.0.0.1:8000/jobs/{job_id}/progress"
   ```
   
   响应格式：
   ```json
   {
     "job_id": "12345-67890",
     "progress": 65.5,
     "stage": "generating_map",
     "estimated": false,
     "last_update": 1642123456.789,
     "status": "running"
   }
   ```

### 上传测试文件

使用curl上传音频文件测试：
```bash
curl -X POST "http://127.0.0.1:8000/process" \
  -F "audio_file=@test_audio.mp3" \
  -F "model=v30" \
  -F "difficulty=5.0" \
  -F "gamemode=0" \
  -F "export_osz=true"
```

### Web界面测试流程

1. 打开 `http://127.0.0.1:8000/progress_monitor.html`
2. 选择音频文件（支持格式：mp3, wav, ogg, m4a, flac）
3. 配置参数（或使用默认值）
4. 点击"上传并开始新任务"
5. 观察实时进度更新
6. 任务完成后下载结果

## 进度解析机制

### 1. 精确进度解析
- **主要格式**：`50%|████████████          | 1/2 [00:30<00:30, 30.00s/it]`
- **备用格式**：`Processing 75%`, `Progress: 33.5%`, `Step 3 of 10`

### 2. 阶段识别
- `generating timing` → generating_timing (10-30%)
- `generating kiai` → generating_kiai (30-50%)
- `generating map` → generating_map (50-85%)
- `seq len` → refining_positions (85-95%)
- `generated beatmap saved` → completed (100%)

### 3. 进度更新策略
1. **精确进度**：从输出直接解析百分比
2. **阶段估算**：根据关键词推断阶段和进度范围
3. **时间估算**：无明确进度时根据时间缓慢增长

## 故障排除

### 常见问题

1. **端口被占用**：
   ```bash
   netstat -ano | findstr :8000  # Windows
   lsof -i :8000                # Linux/Mac
   ```

2. **依赖缺失**：
   ```bash
   pip install fastapi uvicorn sse-starlette python-multipart
   ```

3. **权限问题**：
   确保有读写以下目录的权限：
   - `audio_storage/`
   - `outputs/`
   - `logs/`

4. **模型文件缺失**：
   检查 `configs/inference/` 目录下是否有对应的配置文件

### 调试技巧

1. **查看API日志**：
   ```bash
   # 直接运行时在控制台查看
   python api_v2.py
   
   # Docker部署时查看容器日志
   docker compose logs -f mapperatorinator-api
   ```

2. **检查进程状态**：
   ```bash
   curl -X GET "http://127.0.0.1:8000/jobs"
   ```

3. **测试进度解析**：
   ```bash
   python test_progress.py
   ```

## 生产环境部署

### Docker部署（推荐）

1. **构建镜像**：
   ```bash
   docker build -f Dockerfile.cpu -t mapperatorinator-api:latest .
   ```

2. **运行容器**：
   ```bash
   docker compose -f docker-compose.simple.yml up -d
   ```

3. **查看状态**：
   ```bash
   docker compose ps
   ```

### 性能优化

1. **CPU优化**：
   ```yaml
   environment:
     - OMP_NUM_THREADS=8
     - MKL_NUM_THREADS=8
     - TORCH_NUM_THREADS=8
   ```

2. **内存配置**：
   ```yaml
   deploy:
     resources:
       limits:
         memory: 16G
   ```

3. **存储优化**：
   - 使用SSD存储
   - 定期清理旧文件
   - 配置外部存储挂载

## 监控和维护

### 健康检查
```bash
curl -f http://localhost:8000/ || echo "API服务异常"
```

### 清理任务
```bash
# 清理完成的任务
curl -X GET "http://127.0.0.1:8000/jobs"

# 取消长时间运行的任务
curl -X POST "http://127.0.0.1:8000/jobs/{job_id}/cancel"
```

### 日志轮转
定期清理日志文件以避免磁盘空间不足。

---

## 📞 技术支持

如有问题，请检查：
1. API服务器状态和日志
2. 网络连接和端口状态
3. 系统资源使用情况
4. 模型文件和配置完整性
