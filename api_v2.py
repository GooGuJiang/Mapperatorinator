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
except ImportError as e:
    print(f"缺少必要的包，请安装: pip install fastapi uvicorn sse-starlette")
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
    """从输出行解析进度百分比"""
    import re
    
    # 匹配各种进度格式
    patterns = [
        r'(\d+)%',                          # 简单百分比: 50%
        r'(\d+)/(\d+)',                     # 分数格式: 50/100
        r'Progress:\s*(\d+(?:\.\d+)?)%',    # Progress: 50.5%
        r'(\d+(?:\.\d+)?)%\s*complete',     # 50.5% complete
        r'Step\s+(\d+)\s+of\s+(\d+)',       # Step 5 of 10
        r'Processing.*?(\d+)%',             # Processing... 50%
        r'Generating.*?(\d+)%',             # Generating... 50%
    ]
    
    for pattern in patterns:
        match = re.search(pattern, output_line, re.IGNORECASE)
        if match:
            if len(match.groups()) == 1:
                # 直接百分比
                return float(match.group(1))
            elif len(match.groups()) == 2:
                # 分数格式，计算百分比
                current = float(match.group(1))
                total = float(match.group(2))
                if total > 0:
                    return (current / total) * 100
    
    return None

def estimate_progress_from_stage(output_line: str, current_progress: float) -> Optional[float]:
    """根据处理阶段估算进度"""
    import re
    
    # 定义各个处理阶段及其大概进度范围
    stages = {
        'loading': (0, 10),
        'preprocessing': (10, 25),
        'segmenting': (25, 35),
        'generating': (35, 85),
        'postprocessing': (85, 95),
        'saving': (95, 100),
        'export': (95, 100),
    }
    
    line_lower = output_line.lower()
    
    for stage, (start, end) in stages.items():
        if stage in line_lower:
            # 如果当前进度小于阶段开始进度，更新到阶段开始
            if current_progress < start:
                return float(start)
            # 如果在阶段范围内，保持当前进度
            elif start <= current_progress <= end:
                return current_progress
            # 如果超过阶段结束，更新到阶段结束
            elif current_progress > end:
                continue
    
    return None

def update_job_progress(job_id: str, output_line: str):
    """更新任务进度"""
    with process_lock:
        if job_id not in job_progress:
            job_progress[job_id] = {
                'progress': 0.0,
                'stage': 'initializing',
                'last_update': time.time(),
                'estimated': False
            }
        
        current_progress = job_progress[job_id]['progress']
        
        # 首先尝试从输出中解析精确进度
        parsed_progress = parse_progress_from_output(output_line)
        if parsed_progress is not None:
            job_progress[job_id].update({
                'progress': min(100.0, max(0.0, parsed_progress)),
                'last_update': time.time(),
                'estimated': False
            })
            return
        
        # 如果没有精确进度，根据阶段估算
        estimated_progress = estimate_progress_from_stage(output_line, current_progress)
        if estimated_progress is not None:
            job_progress[job_id].update({
                'progress': estimated_progress,
                'last_update': time.time(),
                'estimated': True
            })
            return
        
        # 如果都没有，根据时间缓慢增加进度
        elapsed = time.time() - job_progress[job_id]['last_update']
        if elapsed > 10:  # 每10秒增加一点进度
            increment = min(2.0, (100 - current_progress) * 0.1)
            if increment > 0:
                job_progress[job_id].update({
                    'progress': min(95.0, current_progress + increment),  # 最多到95%
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
        if job_id not in active_processes:
            raise HTTPException(status_code=404, detail="任务不存在")
        
        process = active_processes[job_id]
        return_code = process.poll()
        metadata = job_metadata.get(job_id, {})
        progress_info = job_progress.get(job_id, {})
        
        if return_code is None:
            # 进程运行中
            current_progress = progress_info.get('progress', 0.0)
            stage = progress_info.get('stage', 'running')
            
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
                progress=progress_info.get('progress', 0.0),
                output_files=None,
                error=f"进程退出代码: {return_code}"
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
