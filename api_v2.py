"""
Mapperatorinator API - 重构版本
支持音频文件和参数一起上传，固定文件夹存储，处理完成后下载结果
"""

import asyncio
import json
import os
import subprocess
import sys
import threading
import time
import uuid
import glob
from pathlib import Path
from typing import Dict, List, Optional, Any

try:
    import uvicorn
    from fastapi import FastAPI, File, Form, HTTPException, UploadFile
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse
    from pydantic import BaseModel, Field
    from sse_starlette.sse import EventSourceResponse
    import redis
    import redis.exceptions
except ImportError as e:
    print(f"缺少必要的包，请安装: pip install fastapi uvicorn sse-starlette redis")
    print(f"导入错误: {e}")
    sys.exit(1)

from config import InferenceConfig

# 全局变量
active_processes: Dict[str, subprocess.Popen] = {}
process_outputs: Dict[str, List[str]] = {}
job_metadata: Dict[str, Dict] = {}
job_progress: Dict[str, Dict] = {}  # 新增进度追踪
process_lock = threading.Lock()

# 固定目录
AUDIO_STORAGE = Path("audio_storage")  # 音频存储目录
OUTPUTS = Path("outputs")              # 输出目录
AUDIO_STORAGE.mkdir(exist_ok=True)
OUTPUTS.mkdir(exist_ok=True)

app = FastAPI(
    title="Mapperatorinator API",
    description="AI生成osu! beatmap的API接口",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 响应模型
class ProcessResponse(BaseModel):
    """处理响应模型"""
    job_id: str = Field(..., description="任务ID")
    status: str = Field(..., description="状态")
    message: str = Field(..., description="消息")

class ProgressResponse(BaseModel):
    """进度响应模型"""
    job_id: str = Field(..., description="任务ID")
    progress: float = Field(..., description="进度百分比 (0-100)")
    stage: str = Field(..., description="当前阶段")
    estimated: bool = Field(..., description="是否为估算进度")
    last_update: float = Field(..., description="最后更新时间戳")
    status: str = Field(..., description="任务状态")

class JobStatus(BaseModel):
    """任务状态模型"""
    job_id: str = Field(..., description="任务ID")
    status: str = Field(..., description="当前状态")
    message: Optional[str] = Field(None, description="状态消息")
    progress: Optional[float] = Field(None, description="进度百分比")
    output_files: Optional[List[str]] = Field(None, description="输出文件列表")
    error: Optional[str] = Field(None, description="错误信息")

def parse_progress_from_output(output_line: str) -> Optional[float]:
    """从输出行解析进度百分比 - 支持tqdm和其他进度格式"""
    import re
    
    # tqdm进度条格式：匹配 "数字%|进度条| 数字/总数" 或 "数字%|"
    tqdm_patterns = [
        r'^\s*(\d+)%\|.*?\|\s*(\d+)/(\d+)',  # 完整tqdm: "  0%|          | 0/65"
        r'^\s*(\d+)%\|',                     # 简化tqdm: "  0%|"
        r'(\d+)%\|.*?\|\s*(\d+)/(\d+)',      # 行中的tqdm格式
    ]
    
    for pattern in tqdm_patterns:
        match = re.search(pattern, output_line)
        if match:
            try:
                if len(match.groups()) == 3:
                    # 完整格式，使用分数计算更精确的进度
                    percent_display = float(match.group(1))
                    current = float(match.group(2))
                    total = float(match.group(3))
                    if total > 0:
                        actual_percent = (current / total) * 100
                        # 使用更精确的分数计算结果
                        return min(100.0, max(0.0, actual_percent))
                    else:
                        return min(100.0, max(0.0, percent_display))
                else:
                    # 简化格式，直接使用百分比
                    percent = float(match.group(1))
                    return min(100.0, max(0.0, percent))
            except ValueError:
                continue
    
    # 备用模式：其他常见进度格式
    backup_patterns = [
        r'(\d+)%(?!\|)',                    # 简单百分比: 50% (但不是 50%|)
        r'(\d+)/(\d+)',                     # 分数格式: 50/100
        r'Progress:\s*(\d+(?:\.\d+)?)%',    # Progress: 50.5%
        r'(\d+(?:\.\d+)?)%\s*complete',     # 50.5% complete
        r'Step\s+(\d+)\s+of\s+(\d+)',       # Step 5 of 10
        r'Processing.*?(\d+)%',             # Processing... 50%
        r'Generating.*?(\d+)%',             # Generating... 50%
    ]
    
    for pattern in backup_patterns:
        match = re.search(pattern, output_line, re.IGNORECASE)
        if match:
            try:
                if len(match.groups()) == 1:
                    # 直接百分比
                    percent = float(match.group(1))
                    return min(100.0, max(0.0, percent))
                elif len(match.groups()) == 2:
                    # 分数格式，计算百分比
                    current = float(match.group(1))
                    total = float(match.group(2))
                    if total > 0:
                        percent = (current / total) * 100
                        return min(100.0, max(0.0, percent))
            except ValueError:
                continue
    
    return None

def estimate_progress_from_stage(output_line: str, current_progress: float) -> Optional[Dict[str, Any]]:
    """根据处理阶段估算进度 - 参考web-ui.js的阶段识别"""
    
    # 基于实际inference.py输出的关键词
    stage_keywords = {
        # 实际观察到的关键词（从用户提供的输出）
        "using cuda for inference": ("initializing", 0, 5),
        "using mps for inference": ("initializing", 0, 5),
        "using cpu for inference": ("initializing", 0, 5),
        "random seed": ("loading_model", 5, 10),
        "model loaded": ("model_ready", 10, 15),
        "generating map": ("generating_map", 15, 85),
        "generating timing": ("generating_timing", 15, 40),
        "generating kiai": ("generating_kiai", 40, 60),
        "generated beatmap saved": ("saving", 85, 95),
        "generated .osz saved": ("completed", 95, 100),
        
        # web-ui.js中的progressTitles对应关键词
        "seq len": ("refining_positions", 85, 95),
        
        # 其他可能的关键词
        "loading": ("loading", 0, 10),
        "load": ("loading", 0, 10),
        "initializing": ("initializing", 0, 5),
        "preprocessing": ("preprocessing", 5, 15),
        "processing": ("processing", 10, 50),
        "inference": ("inference", 30, 80),
        "generating": ("generating", 40, 85),
        "postprocessing": ("postprocessing", 85, 95),
        "saving": ("saving", 95, 100),
        "export": ("export", 95, 100),
        "complete": ("completed", 100, 100),
        "finished": ("completed", 100, 100),
        "done": ("completed", 100, 100),
        
        # 模型相关关键词
        "model": ("loading", 0, 10),
        "tokenizer": ("loading", 5, 15),
        "config": ("loading", 0, 10),
        "checkpoint": ("loading", 5, 15),
        
        # 音频处理关键词
        "audio": ("preprocessing", 10, 25),
        "spectrogram": ("preprocessing", 15, 30),
        "feature": ("preprocessing", 20, 35),
        
        # CUDA/设备关键词
        "cuda": ("initializing", 0, 5),
        "device": ("initializing", 0, 5),
        "gpu": ("initializing", 0, 5),
        
        # 错误关键词
        "error": ("error", current_progress, current_progress),
        "failed": ("error", current_progress, current_progress),
        "exception": ("error", current_progress, current_progress),
        "traceback": ("error", current_progress, current_progress),
    }
    
    line_lower = output_line.lower()
    
    # 查找最佳匹配的关键词
    best_match = None
    best_keyword_len = 0
    
    for keyword, (stage_name, start, end) in stage_keywords.items():
        if keyword in line_lower:
            # 优先选择更长的关键词匹配（更具体）
            if len(keyword) > best_keyword_len:
                best_match = (stage_name, start, end)
                best_keyword_len = len(keyword)
    
    if best_match:
        stage_name, start, end = best_match
        # 如果检测到新阶段，更新进度到该阶段的开始点
        if current_progress < start:
            return {
                "progress": float(start),
                "stage": stage_name,
                "estimated": True
            }
        # 如果在阶段范围内，保持当前进度但更新阶段名
        elif start <= current_progress <= end:
            return {
                "progress": current_progress,
                "stage": stage_name,
                "estimated": True
            }
        # 如果进度已超过该阶段，继续使用当前进度
        else:
            return {
                "progress": current_progress,
                "stage": stage_name,
                "estimated": True
            }
    
    return None

def update_job_progress(job_id: str, output_line: str):
    """更新任务进度 - 参考web-ui.py的进度解析逻辑"""
    with process_lock:
        if job_id not in job_progress:
            job_progress[job_id] = {
                'progress': 0.0,
                'stage': 'initializing',
                'last_update': time.time(),
                'estimated': False
            }
        
        current_progress = job_progress[job_id]['progress']
        current_stage = job_progress[job_id]['stage']
        
        # 首先尝试从输出中解析精确进度（主要是匹配 "数字%|" 格式）
        parsed_progress = parse_progress_from_output(output_line)
        if parsed_progress is not None:
            job_progress[job_id].update({
                'progress': parsed_progress,
                'last_update': time.time(),
                'estimated': False
            })
            # 如果有精确进度，也尝试更新阶段信息
            stage_info = estimate_progress_from_stage(output_line, parsed_progress)
            if stage_info:
                job_progress[job_id]['stage'] = stage_info['stage']
            return
        
        # 如果没有精确进度，根据阶段估算
        stage_info = estimate_progress_from_stage(output_line, current_progress)
        if stage_info:
            job_progress[job_id].update({
                'progress': stage_info['progress'],
                'stage': stage_info['stage'],
                'last_update': time.time(),
                'estimated': stage_info['estimated']
            })
            return
        
        # 如果都没有，根据时间缓慢增加进度
        elapsed = time.time() - job_progress[job_id]['last_update']
        
        # 更积极的时间估算策略
        if elapsed > 5:  # 每5秒检查一次
            # 根据任务运行总时间估算进度
            total_elapsed = time.time() - job_metadata.get(job_id, {}).get('start_time', time.time())
            
            # 基于经验的时间估算（假设一般任务需要2-5分钟）
            estimated_total_time = 180  # 3分钟的估算
            time_based_progress = min(90.0, (total_elapsed / estimated_total_time) * 100)
            
            # 根据当前阶段决定增长速度
            if current_stage in ['generating_map', 'generating_timing', 'generating_kiai', 'inference', 'generating']:
                # 生成阶段进度较慢，每次增加小幅度
                increment = min(2.0, (100 - current_progress) * 0.08)
            elif current_stage in ['loading', 'initializing']:
                # 加载阶段相对较快
                increment = min(5.0, (30 - current_progress) * 0.2)
            else:
                # 其他阶段进度中等
                increment = min(3.0, (100 - current_progress) * 0.1)
            
            # 使用时间估算和增量的较大值，但不超过时间估算的进度
            new_progress = min(
                time_based_progress,
                current_progress + increment,
                95.0  # 最多到95%，留给实际完成检测
            )
            
            if new_progress > current_progress:
                job_progress[job_id].update({
                    'progress': new_progress,
                    'last_update': time.time(),
                    'estimated': True
                })

def parse_optional_int(value: str) -> Optional[int]:
    """解析可选整数参数"""
    if not value or value.strip() == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None

def parse_optional_float(value: str) -> Optional[float]:
    """解析可选浮点数参数"""
    if not value or value.strip() == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None

def save_audio_file(file: UploadFile, job_id: str) -> str:
    """保存音频文件到固定目录"""
    # 验证文件类型
    valid_extensions = {'.mp3', '.wav', '.ogg', '.m4a', '.flac'}
    if not file.filename:
        raise HTTPException(status_code=400, detail="没有提供文件")
    
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in valid_extensions:
        raise HTTPException(
            status_code=400, 
            detail=f"不支持的文件类型。支持的格式: {', '.join(valid_extensions)}"
        )
    
    # 使用job_id作为文件名
    audio_filename = f"{job_id}{file_ext}"
    audio_path = AUDIO_STORAGE / audio_filename
    
    return str(audio_path.absolute())

def build_command(job_id: str, audio_path: str, params: dict) -> List[str]:
    """构建推理命令"""
    python_executable = sys.executable
    
    # 创建job专用输出目录
    job_output_dir = OUTPUTS / job_id
    job_output_dir.mkdir(exist_ok=True)
    
    cmd = [python_executable, "inference.py", "-cn"]
    
    # 模型配置名称（对应configs/inference/下的yaml文件）
    config_name = params.get("model", "v30")  # 默认使用v30配置
    cmd.append(config_name)
    
    # Hydra参数引用函数
    def hydra_quote(value):
        return f"'{str(value).replace(chr(39), chr(92) + chr(39))}'"
    
    def add_param(key, value):
        if value is not None and value != '':
            if key in {"audio_path", "output_path", "beatmap_path"}:
                cmd.append(f"{key}={hydra_quote(value)}")
            else:
                cmd.append(f"{key}={value}")
    
    def add_list_param(key, items):
        if items:
            quoted_items = [f"'{str(item)}'" for item in items]
            items_str = ",".join(quoted_items)
            cmd.append(f"{key}=[{items_str}]")
    
    # 必需参数
    add_param("audio_path", audio_path)
    add_param("output_path", str(job_output_dir))
    
    # 可选参数
    add_param("gamemode", params.get("gamemode", 0))
    add_param("difficulty", params.get("difficulty"))
    add_param("year", params.get("year"))
    add_param("mapper_id", params.get("mapper_id"))
    
    # 难度设置
    for param in ['hp_drain_rate', 'circle_size', 'overall_difficulty', 
                  'approach_rate', 'slider_multiplier', 'slider_tick_rate']:
        add_param(param, params.get(param))
    
    # Mania专用
    add_param("keycount", params.get("keycount"))
    add_param("hold_note_ratio", params.get("hold_note_ratio"))
    add_param("scroll_speed_ratio", params.get("scroll_speed_ratio"))
    
    # 生成设置
    add_param("cfg_scale", params.get("cfg_scale", 1.0))
    add_param("temperature", params.get("temperature", 1.0))
    add_param("top_p", params.get("top_p", 0.95))
    add_param("seed", params.get("seed"))
    
    # 时间设置
    add_param("start_time", params.get("start_time"))
    add_param("end_time", params.get("end_time"))
    
    # 布尔选项
    cmd.append(f"export_osz={str(params.get('export_osz', True)).lower()}")
    cmd.append(f"add_to_beatmap={str(params.get('add_to_beatmap', False)).lower()}")
    cmd.append(f"hitsounded={str(params.get('hitsounded', False)).lower()}")
    cmd.append(f"super_timing={str(params.get('super_timing', False)).lower()}")
    
    # 列表参数
    add_list_param("descriptors", params.get("descriptors"))
    add_list_param("negative_descriptors", params.get("negative_descriptors"))
    
    return cmd

def find_output_files(job_id: str) -> List[str]:
    """查找输出文件"""
    job_output_dir = OUTPUTS / job_id
    if not job_output_dir.exists():
        return []
    
    files = []
    for file_path in job_output_dir.iterdir():
        if file_path.is_file():
            files.append(file_path.name)
    
    return files

@app.get("/")
async def root():
    """根端点"""
    return {
        "message": "Mapperatorinator API v2.0",
        "description": "上传音频+参数，生成osu! beatmap",
        "endpoints": {
            "process": "POST /process - 上传音频和参数开始处理",
            "status": "GET /jobs/{job_id}/status - 查询任务状态",
            "progress": "GET /jobs/{job_id}/progress - 查询任务进度",
            "stream": "GET /jobs/{job_id}/stream - 实时输出流",
            "download": "GET /jobs/{job_id}/download - 下载结果文件",
            "files": "GET /jobs/{job_id}/files - 列出所有输出文件",
            "cancel": "POST /jobs/{job_id}/cancel - 取消任务"
        }
    }

@app.post("/process", response_model=ProcessResponse)
async def process_audio(
    audio_file: UploadFile = File(..., description="音频文件"),
    model: str = Form(default="v30", description="模型配置名称 (v30, v31, default等)"),
    gamemode: int = Form(default=0, description="游戏模式 (0=osu!, 1=taiko, 2=catch, 3=mania)"),
    difficulty: Optional[float] = Form(default=5.0, description="目标难度星级"),
    year: Optional[int] = Form(default=2023, description="年份"),
    mapper_id: Optional[str] = Form(default="", description="Mapper ID"),
    hp_drain_rate: Optional[float] = Form(default=5.0, description="HP消耗率"),
    circle_size: Optional[float] = Form(default=4.0, description="圆圈大小"),
    overall_difficulty: Optional[float] = Form(default=8.0, description="整体难度"),
    approach_rate: Optional[float] = Form(default=9.0, description="接近速度"),
    slider_multiplier: Optional[float] = Form(default=1.4, description="滑条倍率"),
    slider_tick_rate: Optional[float] = Form(default=1.0, description="滑条tick率"),
    keycount: Optional[str] = Form(default="", description="按键数量(mania)"),
    hold_note_ratio: Optional[str] = Form(default="", description="长按音符比例(mania)"),
    scroll_speed_ratio: Optional[str] = Form(default="", description="滚动速度比例"),
    cfg_scale: float = Form(default=1.0, description="CFG引导强度"),
    temperature: float = Form(default=0.9, description="采样温度"),
    top_p: float = Form(default=0.9, description="Top-p采样"),
    seed: Optional[str] = Form(default="", description="随机种子"),
    start_time: Optional[str] = Form(default="", description="开始时间(毫秒)"),
    end_time: Optional[str] = Form(default="", description="结束时间(毫秒)"),
    export_osz: bool = Form(default=True, description="导出.osz文件"),
    add_to_beatmap: bool = Form(default=False, description="添加到现有beatmap"),
    hitsounded: bool = Form(default=False, description="包含打击音效"),
    super_timing: bool = Form(default=False, description="使用超级时间生成"),
    descriptors: Optional[str] = Form(None, description="风格描述符(JSON数组)"),
    negative_descriptors: Optional[str] = Form(None, description="负面描述符(JSON数组)")
):
    """处理音频文件和参数"""
    job_id = str(uuid.uuid4())
    
    with process_lock:
        if job_id in active_processes:
            raise HTTPException(status_code=409, detail="任务ID冲突")
        
        try:
            # 保存音频文件
            audio_path = save_audio_file(audio_file, job_id)
            
            # 保存实际的音频内容
            with open(audio_path, "wb") as buffer:
                content = await audio_file.read()
                buffer.write(content)
            
            # 解析JSON参数
            desc_list = None
            if descriptors and descriptors.strip():
                try:
                    desc_list = json.loads(descriptors)
                except json.JSONDecodeError:
                    desc_list = None
            
            neg_desc_list = None
            if negative_descriptors and negative_descriptors.strip():
                try:
                    neg_desc_list = json.loads(negative_descriptors)
                except json.JSONDecodeError:
                    neg_desc_list = None
            
            # 构建参数字典，处理字符串参数转换
            params = {
                "model": model,
                "gamemode": gamemode,
                "difficulty": difficulty,
                "year": year,
                "mapper_id": parse_optional_int(mapper_id) if mapper_id else None,
                "hp_drain_rate": hp_drain_rate,
                "circle_size": circle_size,
                "overall_difficulty": overall_difficulty,
                "approach_rate": approach_rate,
                "slider_multiplier": slider_multiplier,
                "slider_tick_rate": slider_tick_rate,
                "keycount": parse_optional_int(keycount) if keycount else None,
                "hold_note_ratio": parse_optional_float(hold_note_ratio) if hold_note_ratio else None,
                "scroll_speed_ratio": parse_optional_float(scroll_speed_ratio) if scroll_speed_ratio else None,
                "cfg_scale": cfg_scale,
                "temperature": temperature,
                "top_p": top_p,
                "seed": parse_optional_int(seed) if seed else None,
                "start_time": parse_optional_int(start_time) if start_time else None,
                "end_time": parse_optional_int(end_time) if end_time else None,
                "export_osz": export_osz,
                "add_to_beatmap": add_to_beatmap,
                "hitsounded": hitsounded,
                "super_timing": super_timing,
                "descriptors": desc_list,
                "negative_descriptors": neg_desc_list
            }
            
            # 构建命令
            cmd = build_command(job_id, audio_path, params)
            print(f"启动任务 {job_id}: {' '.join(cmd)}")
            
            # 启动进程
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1,
                universal_newlines=True,
                encoding='utf-8',
                errors='replace'
            )
            
            active_processes[job_id] = process
            process_outputs[job_id] = []
            job_metadata[job_id] = {
                "audio_path": audio_path,
                "audio_filename": audio_file.filename,
                "params": params,
                "start_time": time.time()
            }
            job_progress[job_id] = {
                "progress": 0.0,
                "stage": "started",
                "last_update": time.time(),
                "estimated": False
            }
            
            # 启动后台线程监控进程输出
            def monitor_process_output(job_id, process):
                """后台监控进程输出"""
                try:
                    if process.stdout:
                        for line in iter(process.stdout.readline, ""):
                            if not line:
                                break
                            
                            # 更新进度
                            update_job_progress(job_id, line)
                            
                            # 存储输出
                            with process_lock:
                                if job_id in process_outputs:
                                    process_outputs[job_id].append(line)
                    
                    # 进程结束后标记进度为完成
                    return_code = process.wait()
                    with process_lock:
                        if job_id in job_progress:
                            if return_code == 0:
                                job_progress[job_id]['progress'] = 100.0
                                job_progress[job_id]['stage'] = 'completed'
                            else:
                                job_progress[job_id]['stage'] = 'failed'
                            job_progress[job_id]['completed_at'] = time.time()
                
                except Exception as e:
                    print(f"监控进程输出错误 {job_id}: {e}")
                    with process_lock:
                        if job_id in job_progress:
                            job_progress[job_id]['stage'] = 'error'
            
            # 启动监控线程
            monitor_thread = threading.Thread(
                target=monitor_process_output, 
                args=(job_id, process),
                daemon=True
            )
            monitor_thread.start()
            
            print(f"任务 {job_id} 已启动 (PID: {process.pid})")
            
            return ProcessResponse(
                job_id=job_id,
                status="started",
                message=f"处理已开始，音频文件: {audio_file.filename}"
            )
            
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"JSON参数解析错误: {str(e)}")
        except Exception as e:
            print(f"启动任务失败: {e}")
            raise HTTPException(status_code=500, detail=f"启动处理失败: {str(e)}")

@app.get("/jobs/{job_id}/status", response_model=JobStatus)
async def get_status(job_id: str):
    """获取任务状态"""
    with process_lock:
        # 检查任务是否存在（包括已完成的任务）
        if job_id not in active_processes and job_id not in job_progress:
            raise HTTPException(status_code=404, detail="任务不存在")
        
        metadata = job_metadata.get(job_id, {})
        progress_info = job_progress.get(job_id, {})
        current_progress = progress_info.get('progress', 0.0)
        stage = progress_info.get('stage', 'unknown')
        
        # 如果任务还在活动进程中
        if job_id in active_processes:
            process = active_processes[job_id]
            return_code = process.poll()
            
            if return_code is None:
                # 进程运行中
                return JobStatus(
                    job_id=job_id,
                    status="running",
                    message=f"正在处理中... ({stage})",
                    progress=current_progress,
                    output_files=None,
                    error=None
                )
            elif return_code == 0:
                # 进程成功完成
                output_files = find_output_files(job_id)
                # 确保进度为100%
                with process_lock:
                    if job_id in job_progress:
                        job_progress[job_id]['progress'] = 100.0
                
                return JobStatus(
                    job_id=job_id,
                    status="completed",
                    message="处理完成",
                    progress=100.0,
                    output_files=output_files,
                    error=None
                )
            else:
                # 进程失败
                return JobStatus(
                    job_id=job_id,
                    status="failed",
                    message="处理失败",
                    progress=current_progress,
                    output_files=None,
                    error=f"进程退出代码: {return_code}"
                )
        else:
            # 任务已从活动进程中移除，检查是否已完成
            output_files = find_output_files(job_id)
            if output_files:
                # 有输出文件，说明成功完成
                return JobStatus(
                    job_id=job_id,
                    status="completed",
                    message="处理完成",
                    progress=100.0,
                    output_files=output_files,
                    error=None
                )
            else:
                # 没有输出文件，可能失败或未知状态
                final_progress = 100.0 if current_progress >= 100.0 else current_progress
                status = "completed" if final_progress >= 100.0 else "failed"
                
                return JobStatus(
                    job_id=job_id,
                    status=status,
                    message="处理完成" if status == "completed" else "处理可能失败",
                    progress=final_progress,
                    output_files=output_files if output_files else None,
                    error=None if status == "completed" else "未找到输出文件"
                )

@app.get("/jobs/{job_id}/progress", response_model=ProgressResponse)
async def get_progress(job_id: str):
    """获取任务详细进度信息"""
    with process_lock:
        # 检查任务是否存在
        if job_id not in active_processes and job_id not in job_progress:
            raise HTTPException(status_code=404, detail="任务不存在")
        
        progress_info = job_progress.get(job_id, {})
        
        # 确定任务状态
        if job_id in active_processes:
            process = active_processes[job_id]
            return_code = process.poll()
            
            if return_code is None:
                status = "running"
            elif return_code == 0:
                status = "completed"
            else:
                status = "failed"
        else:
            # 任务已完成或失败
            status = "completed" if progress_info.get('progress', 0) == 100.0 else "unknown"
        
        return ProgressResponse(
            job_id=job_id,
            progress=progress_info.get('progress', 0.0),
            stage=progress_info.get('stage', 'unknown'),
            estimated=progress_info.get('estimated', True),
            last_update=progress_info.get('last_update', time.time()),
            status=status
        )

@app.get("/jobs/{job_id}/stream")
async def stream_output(job_id: str):
    """实时输出流"""
    
    async def event_generator():
        with process_lock:
            if job_id not in active_processes:
                yield {
                    "event": "error",
                    "data": "任务不存在"
                }
                return
            
            process = active_processes[job_id]
        
        print(f"开始流式输出任务 {job_id}")
        
        try:
            if process.stdout:
                for line in iter(process.stdout.readline, ""):
                    if not line:
                        break
                    
                    # 更新进度
                    update_job_progress(job_id, line)
                    
                    # 存储输出
                    with process_lock:
                        if job_id in process_outputs:
                            process_outputs[job_id].append(line)
                    
                    # 获取当前进度信息
                    progress_info = job_progress.get(job_id, {})
                    progress_value = progress_info.get('progress', 0.0)
                    
                    yield {
                        "event": "output",
                        "data": line.rstrip(),
                        "progress": progress_value
                    }
            
            # 等待进程完成
            return_code = process.wait()
            
            # 标记进度为完成
            with process_lock:
                if job_id in job_progress:
                    job_progress[job_id]['progress'] = 100.0
            
            if return_code == 0:
                yield {
                    "event": "completed",
                    "data": "处理完成",
                    "progress": 100.0
                }
            else:
                yield {
                    "event": "failed",
                    "data": f"处理失败，退出代码: {return_code}",
                    "progress": job_progress.get(job_id, {}).get('progress', 0.0)
                }
                
        except Exception as e:
            print(f"流式输出错误 {job_id}: {e}")
            yield {
                "event": "error",
                "data": f"流式输出错误: {str(e)}"
            }
        finally:
            # 清理
            with process_lock:
                if job_id in active_processes:
                    del active_processes[job_id]
                if job_id in job_progress:
                    # 保留进度信息一段时间，方便查询
                    job_progress[job_id]['completed_at'] = time.time()
                print(f"清理任务 {job_id}")
    
    return EventSourceResponse(event_generator())

@app.get("/jobs/{job_id}/download")
async def download_result(job_id: str, filename: Optional[str] = None):
    """下载结果文件"""
    job_output_dir = OUTPUTS / job_id
    
    if not job_output_dir.exists():
        raise HTTPException(status_code=404, detail="任务输出目录不存在")
    
    # 查找文件
    output_files = find_output_files(job_id)
    if not output_files:
        raise HTTPException(status_code=404, detail="没有找到输出文件")
    
    # 确定要下载的文件
    if filename:
        if filename not in output_files:
            raise HTTPException(status_code=404, detail=f"文件 {filename} 不存在")
        target_file = filename
    else:
        # 优先选择.osz文件
        osz_files = [f for f in output_files if f.endswith('.osz')]
        if osz_files:
            target_file = osz_files[0]
        else:
            target_file = output_files[0]
    
    file_path = job_output_dir / target_file
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    
    return FileResponse(
        path=str(file_path),
        filename=target_file,
        media_type='application/octet-stream'
    )

@app.get("/jobs/{job_id}/files")
async def list_files(job_id: str):
    """列出所有输出文件"""
    job_output_dir = OUTPUTS / job_id
    
    if not job_output_dir.exists():
        return {"files": []}
    
    files = []
    for file_path in job_output_dir.iterdir():
        if file_path.is_file():
            files.append({
                "name": file_path.name,
                "size": file_path.stat().st_size,
                "type": file_path.suffix,
                "download_url": f"/jobs/{job_id}/download?filename={file_path.name}"
            })
    
    return {"files": files}

@app.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str):
    """取消任务"""
    with process_lock:
        if job_id not in active_processes:
            raise HTTPException(status_code=404, detail="任务不存在")
        
        process = active_processes[job_id]
        
        if process.poll() is not None:
            return {"status": "already_finished", "message": "任务已完成"}
        
        try:
            process.terminate()
            
            # 等待优雅终止
            try:
                process.wait(timeout=5)
                message = "任务已取消"
            except subprocess.TimeoutExpired:
                process.kill()
                message = "任务已强制终止"
            
            del active_processes[job_id]
            
            return {
                "status": "cancelled",
                "message": message
            }
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"取消任务失败: {str(e)}")

@app.get("/jobs")
async def list_jobs():
    """列出所有任务"""
    with process_lock:
        jobs = []
        for job_id, process in active_processes.items():
            return_code = process.poll()
            status = "completed" if return_code == 0 else "failed" if return_code is not None else "running"
            
            metadata = job_metadata.get(job_id, {})
            
            jobs.append({
                "job_id": job_id,
                "status": status,
                "audio_filename": metadata.get("audio_filename"),
                "start_time": metadata.get("start_time"),
                "pid": process.pid
            })
        
        return {"jobs": jobs}

def cleanup_finished_jobs():
    """清理已完成的任务"""
    with process_lock:
        current_time = time.time()
        
        # 清理已完成的进程
        finished_jobs = []
        for job_id, process in active_processes.items():
            if process.poll() is not None:
                finished_jobs.append(job_id)
        
        for job_id in finished_jobs:
            print(f"清理已完成任务 {job_id}")
            del active_processes[job_id]
        
        # 清理超过1小时的进度信息
        old_progress_jobs = []
        for job_id, progress_info in job_progress.items():
            completed_at = progress_info.get('completed_at')
            if completed_at and (current_time - completed_at) > 3600:  # 1小时
                old_progress_jobs.append(job_id)
        
        for job_id in old_progress_jobs:
            print(f"清理旧进度信息 {job_id}")
            del job_progress[job_id]

@app.on_event("startup")
async def startup_event():
    """启动事件"""
    print("🚀 启动 Mapperatorinator API v2.0...")
    print(f"📁 音频存储目录: {AUDIO_STORAGE.absolute()}")
    print(f"📂 输出目录: {OUTPUTS.absolute()}")
    
    # 启动后台清理任务
    async def periodic_cleanup():
        while True:
            await asyncio.sleep(300)  # 每5分钟清理一次
            cleanup_finished_jobs()
    
    asyncio.create_task(periodic_cleanup())

@app.on_event("shutdown")
async def shutdown_event():
    """关闭事件"""
    print("🛑 关闭 Mapperatorinator API...")
    
    # 终止所有活动进程
    with process_lock:
        for job_id, process in active_processes.items():
            if process.poll() is None:
                print(f"终止任务 {job_id}")
                process.terminate()

@app.get("/jobs/{job_id}/debug")
async def debug_job_output(job_id: str):
    """调试端点：查看任务的最近输出行"""
    with process_lock:
        if job_id not in active_processes and job_id not in process_outputs:
            raise HTTPException(status_code=404, detail="任务不存在")
        
        # 获取最近的输出行
        recent_outputs = process_outputs.get(job_id, [])[-20:]  # 最近20行
        progress_info = job_progress.get(job_id, {})
        metadata = job_metadata.get(job_id, {})
        
        return {
            "job_id": job_id,
            "recent_outputs": recent_outputs,
            "progress_info": progress_info,
            "total_output_lines": len(process_outputs.get(job_id, [])),
            "start_time": metadata.get("start_time"),
            "elapsed_time": time.time() - metadata.get("start_time", time.time()),
            "is_active": job_id in active_processes
        }

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Mapperatorinator API Server v2.0")
    parser.add_argument("--host", default="127.0.0.1", help="绑定主机")
    parser.add_argument("--port", type=int, default=8000, help="绑定端口")
    parser.add_argument("--reload", action="store_true", help="启用自动重载")
    
    args = parser.parse_args()
    
    print("🎮 Mapperatorinator API v2.0")
    print("=" * 50)
    print(f"🌐 API文档: http://{args.host}:{args.port}/docs")
    print(f"📚 ReDoc: http://{args.host}:{args.port}/redoc")
    print("=" * 50)
    
    uvicorn.run(
        "api_v2:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        access_log=True
    )
