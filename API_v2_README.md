# Mapperatorinator API v2.0 使用说明

## 快速开始

### 1. 启动API服务器

```bash
# Windows
start_api_v2.bat

# Linux/macOS
bash start_api_v2.sh

# 或直接使用Python
python api_v2.py
```

### 2. 访问API文档

- **Swagger UI**: http://127.0.0.1:8000/docs
- **ReDoc**: http://127.0.0.1:8000/redoc

### 3. 使用客户端

```bash
# 基本使用
python example_client.py your_audio.mp3

# 指定参数
python example_client.py your_audio.mp3 --model v30 --gamemode 0 --difficulty 5.5

# 带风格描述符
python example_client.py your_audio.mp3 --descriptors "流行" "快节奏" --output-dir downloads
```

## API端点

### POST /process - 处理音频

上传音频文件和参数，开始beatmap生成。

**参数说明 (带默认值):**

- `audio_file`: 音频文件 (mp3, wav, ogg, m4a, flac) - **必需**
- `model`: 模型配置名称 - 默认: `v30`
  - `v30`: 推荐的最新版本 ⭐
  - `v31`: 另一个可用版本
  - `default`: 默认配置
- `gamemode`: 游戏模式 - 默认: `0`
  - `0`: osu!standard
  - `1`: osu!taiko
  - `2`: osu!catch
  - `3`: osu!mania
- `difficulty`: 目标难度星级 - 默认: `5.0`
- `year`: 年份 - 默认: `2023`
- `mapper_id`: Mapper ID - 默认: 空字符串 (可选)
- `hp_drain_rate`: HP消耗率 - 默认: `5.0`
- `circle_size`: 圆圈大小 - 默认: `4.0`
- `overall_difficulty`: 整体难度 - 默认: `8.0`
- `approach_rate`: 接近速度 - 默认: `9.0`
- `slider_multiplier`: 滑条倍率 - 默认: `1.4`
- `slider_tick_rate`: 滑条tick率 - 默认: `1.0`
- `keycount`: 按键数量(mania) - 默认: 空字符串 (可选)
- `hold_note_ratio`: 长按音符比例(mania) - 默认: 空字符串 (可选)
- `scroll_speed_ratio`: 滚动速度比例 - 默认: 空字符串 (可选)
- `cfg_scale`: CFG引导强度 - 默认: `1.0`
- `temperature`: 采样温度 - 默认: `0.9`
- `top_p`: Top-p采样 - 默认: `0.9`
- `seed`: 随机种子 - 默认: 空字符串 (可选)
- `start_time`: 开始时间(毫秒) - 默认: 空字符串 (可选)
- `end_time`: 结束时间(毫秒) - 默认: 空字符串 (可选)
- `export_osz`: 导出.osz文件 - 默认: `true`
- `add_to_beatmap`: 添加到现有beatmap - 默认: `false`
- `hitsounded`: 包含打击音效 - 默认: `false`
- `super_timing`: 使用超级时间生成 - 默认: `false`
- `descriptors`: 风格描述符JSON数组 - 默认: 空字符串 (可选)
- `negative_descriptors`: 负面描述符JSON数组 - 默认: 空字符串 (可选)

**示例请求:**

```python
import requests

files = {'audio_file': open('song.mp3', 'rb')}
data = {
    'model': 'v30',
    'gamemode': 0,
    'difficulty': 5.5,
    'descriptors': '["流行", "快节奏"]',
    'export_osz': True
}

response = requests.post('http://127.0.0.1:8000/process', files=files, data=data)
result = response.json()
job_id = result['job_id']
```

### GET /jobs/{job_id}/status - 查询状态

查询任务处理状态。

**响应状态:**
- `running`: 正在处理
- `completed`: 处理完成
- `failed`: 处理失败

### GET /jobs/{job_id}/stream - 实时输出

获取任务的实时输出流 (Server-Sent Events)。

```javascript
const eventSource = new EventSource(`http://127.0.0.1:8000/jobs/${jobId}/stream`);
eventSource.onmessage = function(event) {
    console.log(event.data);
};
```

### GET /jobs/{job_id}/download - 下载结果

下载生成的beatmap文件。会自动选择.osz文件或其他输出文件。

```python
response = requests.get(f'http://127.0.0.1:8000/jobs/{job_id}/download')
with open('beatmap.osz', 'wb') as f:
    f.write(response.content)
```

### GET /jobs/{job_id}/files - 列出文件

获取所有输出文件的列表。

### POST /jobs/{job_id}/cancel - 取消任务

取消正在运行的任务。

### GET /jobs - 列出所有任务

获取当前所有任务的状态。

## 目录结构

```
├── audio_storage/     # 音频文件存储
├── outputs/          # 输出文件
│   └── {job_id}/     # 每个任务的输出目录
│       ├── beatmap.osu
│       └── beatmap.osz
├── api_v2.py         # API服务器
├── client_v2.py      # 基础客户端
├── example_client.py # 完整示例客户端
└── test_api.py       # API测试脚本
```

## 模型配置

可用的模型配置 (位于 `configs/inference/` 目录):

- **v30** (推荐): 最新训练的模型，质量最高
- **v31**: 另一个可用版本
- **default**: 基础配置

每个配置文件定义了模型路径、默认参数等设置。

## 错误处理

### 常见错误

1. **"Model path is empty"**
   - 原因: 模型配置不正确
   - 解决: 使用正确的模型名称 (v30, v31等)

2. **"JSON参数解析错误"**
   - 原因: descriptors参数格式错误
   - 解决: 使用正确的JSON格式: `'["描述1", "描述2"]'`

3. **"Audio file not found"**
   - 原因: 音频文件路径不存在
   - 解决: 检查文件路径和格式

### 调试技巧

1. 使用测试脚本验证API:
   ```bash
   python test_api.py
   ```

2. 查看实时输出:
   ```python
   client.stream_output(job_id)
   ```

3. 检查任务状态:
   ```python
   status = client.get_status(job_id)
   print(status['error'])  # 如果有错误
   ```

## 高级用法

### 批量处理

```python
client = MapperatorinatorAPIClient()

audio_files = ['song1.mp3', 'song2.mp3', 'song3.mp3']
jobs = []

for audio_file in audio_files:
    result = client.process_audio(audio_file, model='v30')
    jobs.append(result['job_id'])

# 等待所有任务完成
for job_id in jobs:
    status = client.wait_for_completion(job_id)
    if status['status'] == 'completed':
        client.download_file(job_id, output_dir='batch_results')
```

### 自定义参数

```python
result = client.process_audio(
    'song.mp3',
    model='v30',
    gamemode=3,  # mania
    keycount=7,  # 7K mania
    difficulty=6.0,
    descriptors=['电子', '快速'],
    negative_descriptors=['慢节奏'],
    cfg_scale=1.2,
    temperature=0.9,
    seed=12345
)
```

## 性能优化

1. **CPU使用**: API会自动检测可用的计算设备
2. **内存管理**: 定期清理已完成的任务
3. **并发处理**: 支持多个任务同时运行
4. **文件存储**: 使用固定目录避免冲突

## 安全考虑

1. API默认绑定到本地地址 (127.0.0.1)
2. 生产环境中应设置适当的访问控制
3. 定期清理临时文件和任务数据
