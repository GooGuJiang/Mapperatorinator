# Mapperatorinator API 使用指南

## 简介

Mapperatorinator API 是一个基于 FastAPI 的 RESTful API，用于通过 AI 生成 osu! beatmap。支持音频文件上传、参数配置、实时进度查询和 .osz 文件下载。

## 快速开始

### 1. 安装依赖

```bash
pip install fastapi uvicorn sse-starlette
```

### 2. 启动服务器

```bash
# 启动API服务器
python api_server.py

# 或者指定端口
python api_server.py --port 8000
```

服务器启动后，访问 http://127.0.0.1:8000/docs 查看API文档。

### 3. 使用客户端

```bash
# 运行简单客户端示例
python simple_client.py
```

## API 端点

### 核心端点

| 端点 | 方法 | 描述 |
|------|------|------|
| `/` | GET | 获取API信息 |
| `/upload/audio` | POST | 上传音频文件 |
| `/upload/beatmap` | POST | 上传beatmap文件 |
| `/validate-paths` | POST | 验证和自动填充路径 |
| `/inference` | POST | 启动推理任务 |
| `/jobs/{job_id}/status` | GET | 获取任务状态 |
| `/jobs/{job_id}/stream` | GET | 实时流式输出 |
| `/jobs/{job_id}/download` | GET | 下载生成的.osz文件 |
| `/jobs/{job_id}/files` | GET | 列出所有输出文件 |
| `/jobs/{job_id}/cancel` | POST | 取消任务 |

## 使用流程

### 完整工作流程

```python
from simple_client import SimpleMapperatorinatorClient

# 1. 创建客户端
client = SimpleMapperatorinatorClient("http://127.0.0.1:8000")

# 2. 上传音频文件
audio_path = client.upload_audio("path/to/your/audio.mp3")

# 3. 启动推理任务
job_id = client.start_inference(
    audio_path=audio_path,
    gamemode=0,          # 0=osu!, 1=taiko, 2=catch, 3=mania
    difficulty=5.0,      # 难度星级
    export_osz=True      # 导出.osz文件
)

# 4. 等待完成
status = client.wait_for_completion(job_id)

# 5. 下载结果
if status['status'] == 'completed':
    osz_file = client.download_osz(job_id, "./downloads/")
    print(f"下载完成: {osz_file}")
```

### cURL 示例

#### 上传音频文件
```bash
curl -X POST "http://127.0.0.1:8000/upload/audio" \
     -H "Content-Type: multipart/form-data" \
     -F "file=@path/to/your/audio.mp3"
```

#### 启动推理
```bash
curl -X POST "http://127.0.0.1:8000/inference" \
     -H "Content-Type: application/json" \
     -d '{
       "model": "default",
       "audio_path": "/path/to/uploaded/audio.mp3",
       "gamemode": 0,
       "difficulty": 5.0,
       "export_osz": true
     }'
```

#### 查询状态
```bash
curl "http://127.0.0.1:8000/jobs/{job_id}/status"
```

#### 下载文件
```bash
curl -O "http://127.0.0.1:8000/jobs/{job_id}/download"
```

## 配置参数

### 基本参数

| 参数 | 类型 | 描述 | 默认值 |
|------|------|------|--------|
| `model` | string | 模型配置名称 | 必需 |
| `audio_path` | string | 音频文件路径 | 必需 |
| `gamemode` | int | 游戏模式 (0=osu!, 1=taiko, 2=catch, 3=mania) | 0 |
| `difficulty` | float | 难度星级 | null |
| `export_osz` | bool | 导出.osz文件 | true |

### 难度设置

| 参数 | 类型 | 描述 |
|------|------|------|
| `hp_drain_rate` | float | HP消耗率 |
| `circle_size` | float | 圆圈大小 |
| `overall_difficulty` | float | 整体难度 |
| `approach_rate` | float | 接近速度 |
| `slider_multiplier` | float | 滑条倍率 |
| `slider_tick_rate` | float | 滑条tick率 |

### 生成设置

| 参数 | 类型 | 描述 | 默认值 |
|------|------|------|--------|
| `cfg_scale` | float | CFG引导强度 | 1.0 |
| `temperature` | float | 采样温度 | 1.0 |
| `top_p` | float | Top-p采样阈值 | 0.95 |
| `seed` | int | 随机种子 | null |

### Mania 专用参数

| 参数 | 类型 | 描述 |
|------|------|------|
| `keycount` | int | 按键数量 |
| `hold_note_ratio` | float | 长按音符比例 |
| `scroll_speed_ratio` | float | 滚动速度变化比例 |

## 错误处理

API 使用标准 HTTP 状态码：

- `200`: 成功
- `400`: 请求错误（如文件格式不支持）
- `404`: 资源不存在（如任务ID不存在）
- `409`: 冲突（如任务已在运行）
- `500`: 服务器内部错误

错误响应格式：
```json
{
  "detail": "错误描述信息"
}
```

## 实时进度监控

使用 Server-Sent Events (SSE) 获取实时输出：

```python
import requests

def stream_progress(job_id):
    url = f"http://127.0.0.1:8000/jobs/{job_id}/stream"
    response = requests.get(url, stream=True)
    
    for line in response.iter_lines():
        if line:
            line_str = line.decode('utf-8')
            if line_str.startswith('data: '):
                print(f"输出: {line_str[6:]}")
            elif line_str.startswith('event: completed'):
                print("任务完成!")
                break
```

## 批量处理

API 支持并发处理多个任务：

```python
import concurrent.futures

def generate_difficulty(audio_path, difficulty, version):
    client = SimpleMapperatorinatorClient()
    job_id = client.start_inference(
        audio_path=audio_path,
        difficulty=difficulty,
        export_osz=True
    )
    status = client.wait_for_completion(job_id)
    if status['status'] == 'completed':
        return client.download_osz(job_id, f"./outputs/{version}_")

# 并行生成多个难度
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
    futures = []
    
    difficulties = [
        (3.0, "Easy"),
        (4.5, "Normal"), 
        (6.0, "Hard"),
        (7.5, "Insane")
    ]
    
    for diff, version in difficulties:
        future = executor.submit(generate_difficulty, audio_path, diff, version)
        futures.append(future)
    
    for future in concurrent.futures.as_completed(futures):
        result = future.result()
        print(f"完成: {result}")
```

## 文件管理

### 上传目录结构
```
uploads/
├── {uuid}_audio1.mp3
├── {uuid}_audio2.wav
└── {uuid}_beatmap.osu
```

### 输出目录结构
```
outputs/
├── {job_id}/
│   ├── generated_beatmap.osz
│   ├── generated_beatmap.osu
│   └── audio.mp3
└── {job_id2}/
    └── ...
```

## 高级配置

### 自定义模型配置

修改 `configs/inference/` 下的配置文件来使用不同的模型：

```bash
# 使用自定义配置
curl -X POST "http://127.0.0.1:8000/inference" \
     -H "Content-Type: application/json" \
     -d '{
       "model": "v29",  # 使用configs/inference/v29.yaml
       "audio_path": "/path/to/audio.mp3",
       "gamemode": 0
     }'
```

### 服务器配置

```bash
# 启动时的配置选项
python api_server.py \
    --host 0.0.0.0 \     # 绑定所有接口
    --port 8000 \        # 端口
    --reload             # 开发模式自动重载
```

## 故障排除

### 常见问题

1. **导入错误**: 确保安装了所有依赖包
2. **文件不存在**: 检查文件路径是否正确
3. **任务失败**: 查看任务输出日志获取详细错误信息
4. **内存不足**: 降低批处理大小或使用更小的模型

### 调试

启用详细日志：
```bash
python api_server.py --reload  # 开发模式
```

查看任务输出：
```bash
curl "http://127.0.0.1:8000/jobs/{job_id}/output"
```

## 示例项目

参考以下文件获取完整示例：

- `simple_client.py`: 简单客户端使用示例
- `api_client_example.py`: 高级客户端功能示例
- `api_server.py`: API服务器实现

## 许可证

参考项目根目录的 LICENSE 文件。
