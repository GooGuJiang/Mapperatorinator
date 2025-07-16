"""
FastAPI server for Mapperatorinator inference with audio upload and parameter configuration.
Simplified API that accepts audio + parameters in one request and returns downloadable results.
"""

import asyncio
import datetime
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
    from fastapi import FastAPI, File, Form, HTTPException, UploadFile, BackgroundTasks
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
    from pydantic import BaseModel, Field
    from sse_starlette.sse import EventSourceResponse
except ImportError as e:
    print(f"Missing required packages. Please install: pip install fastapi uvicorn sse-starlette")
    print(f"Import error: {e}")
    sys.exit(1)

from config import InferenceConfig
from inference import autofill_paths

# Global variables for process management
active_processes: Dict[str, subprocess.Popen] = {}
process_outputs: Dict[str, List[str]] = {}
job_metadata: Dict[str, Dict] = {}
process_lock = threading.Lock()

# Fixed directories
AUDIO_DIR = Path("audio_storage")  # Fixed directory for audio files
OUTPUT_DIR = Path("outputs")       # Output directory for results
AUDIO_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

app = FastAPI(
    title="Mapperatorinator API",
    description="API for generating osu! beatmaps using AI",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models for request/response
class InferenceRequest(BaseModel):
    """Request model for inference"""
    model: str = Field(..., description="Model configuration name")
    audio_path: Optional[str] = Field(None, description="Path to audio file")
    output_path: Optional[str] = Field(None, description="Output directory path")
    beatmap_path: Optional[str] = Field(None, description="Path to reference beatmap (.osu file)")
    
    # Basic settings
    gamemode: Optional[int] = Field(None, description="Game mode (0=osu!, 1=taiko, 2=catch, 3=mania)")
    difficulty: Optional[float] = Field(None, description="Difficulty star rating")
    year: Optional[int] = Field(None, description="Year for style")
    mapper_id: Optional[int] = Field(None, description="Mapper ID for style")
    
    # Difficulty settings
    hp_drain_rate: Optional[float] = Field(None, description="HP drain rate")
    circle_size: Optional[float] = Field(None, description="Circle size")
    overall_difficulty: Optional[float] = Field(None, description="Overall difficulty")
    approach_rate: Optional[float] = Field(None, description="Approach rate")
    slider_multiplier: Optional[float] = Field(None, description="Slider velocity multiplier")
    slider_tick_rate: Optional[float] = Field(None, description="Slider tick rate")
    
    # Mania specific
    keycount: Optional[int] = Field(None, description="Number of keys for mania")
    hold_note_ratio: Optional[float] = Field(None, description="Ratio of hold notes in mania")
    scroll_speed_ratio: Optional[float] = Field(None, description="Scroll speed changes ratio")
    
    # Generation settings
    cfg_scale: Optional[float] = Field(1.0, description="Classifier-free guidance scale")
    temperature: Optional[float] = Field(1.0, description="Sampling temperature")
    top_p: Optional[float] = Field(0.95, description="Top-p sampling threshold")
    seed: Optional[int] = Field(None, description="Random seed")
    
    # Timing and segmentation
    start_time: Optional[int] = Field(None, description="Start time in milliseconds")
    end_time: Optional[int] = Field(None, description="End time in milliseconds")
    
    # Boolean options
    export_osz: Optional[bool] = Field(True, description="Export as .osz file")
    add_to_beatmap: Optional[bool] = Field(False, description="Add to existing beatmap")
    hitsounded: Optional[bool] = Field(False, description="Include hitsounds")
    super_timing: Optional[bool] = Field(False, description="Use super timing generation")
    
    # Lists
    descriptors: Optional[List[str]] = Field(None, description="Style descriptors")
    negative_descriptors: Optional[List[str]] = Field(None, description="Negative descriptors")
    in_context_options: Optional[List[str]] = Field(None, description="In-context options")


class InferenceResponse(BaseModel):
    """Response model for inference"""
    job_id: str = Field(..., description="Unique job identifier")
    status: str = Field(..., description="Job status")
    message: str = Field(..., description="Status message")


class JobStatus(BaseModel):
    """Job status model"""
    job_id: str = Field(..., description="Job identifier")
    status: str = Field(..., description="Current status")
    progress: Optional[float] = Field(None, description="Progress percentage (0-100)")
    message: Optional[str] = Field(None, description="Current status message")
    output_path: Optional[str] = Field(None, description="Output path when completed")
    error: Optional[str] = Field(None, description="Error message if failed")
    osz_files: Optional[List[str]] = Field(None, description="Available .osz files for download")
    osu_files: Optional[List[str]] = Field(None, description="Available .osu files for download")


class PathValidationRequest(BaseModel):
    """Request model for path validation"""
    audio_path: Optional[str] = Field(None, description="Audio file path")
    beatmap_path: Optional[str] = Field(None, description="Beatmap file path") 
    output_path: Optional[str] = Field(None, description="Output directory path")


class PathValidationResponse(BaseModel):
    """Response model for path validation"""
    success: bool = Field(..., description="Validation success")
    autofilled_audio_path: Optional[str] = Field(None, description="Auto-filled audio path")
    autofilled_output_path: Optional[str] = Field(None, description="Auto-filled output path")
    errors: List[str] = Field(default_factory=list, description="Validation errors")


@app.get("/", response_model=Dict[str, str])
async def root():
    """Root endpoint"""
    return {
        "message": "Mapperatorinator API",
        "version": "1.0.0",
        "docs": "/docs",
        "redoc": "/redoc"
    }


@app.post("/upload/audio", response_model=Dict[str, str])
async def upload_audio(file: UploadFile = File(...)):
    """Upload an audio file"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    
    # Validate file type
    valid_extensions = {'.mp3', '.wav', '.ogg', '.m4a', '.flac'}
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in valid_extensions:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid file type. Allowed: {', '.join(valid_extensions)}"
        )
    
    # Generate unique filename
    unique_id = str(uuid.uuid4())
    safe_filename = f"{unique_id}_{file.filename}"
    file_path = UPLOAD_DIR / safe_filename
    
    try:
        # Save uploaded file
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        return {
            "filename": safe_filename,
            "path": str(file_path.absolute()),
            "size": str(len(content)),
            "message": "Audio file uploaded successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")


@app.post("/upload/beatmap", response_model=Dict[str, str])
async def upload_beatmap(file: UploadFile = File(...)):
    """Upload a beatmap file"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    
    # Validate file type
    if not file.filename.lower().endswith('.osu'):
        raise HTTPException(status_code=400, detail="File must be a .osu beatmap file")
    
    # Generate unique filename
    unique_id = str(uuid.uuid4())
    safe_filename = f"{unique_id}_{file.filename}"
    file_path = UPLOAD_DIR / safe_filename
    
    try:
        # Save uploaded file
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        return {
            "filename": safe_filename,
            "path": str(file_path.absolute()),
            "size": str(len(content)),
            "message": "Beatmap file uploaded successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")


@app.post("/validate-paths", response_model=PathValidationResponse)
async def validate_paths(request: PathValidationRequest):
    """Validate and autofill paths"""
    try:
        # Create temporary inference config for validation
        inference_args = InferenceConfig()
        inference_args.audio_path = request.audio_path or ""
        inference_args.beatmap_path = request.beatmap_path or ""
        inference_args.output_path = request.output_path or ""
        
        result = autofill_paths(inference_args)
        
        return PathValidationResponse(
            success=result['success'],
            autofilled_audio_path=inference_args.audio_path,
            autofilled_output_path=inference_args.output_path,
            errors=result['errors']
        )
    except Exception as e:
        return PathValidationResponse(
            success=False,
            errors=[f"Error during path validation: {str(e)}"],
            autofilled_audio_path=None,
            autofilled_output_path=None
        )


def build_inference_command(request: InferenceRequest, job_output_dir: str) -> List[str]:
    """Build the inference command from request parameters"""
    python_executable = sys.executable
    cmd = [python_executable, "inference.py", "-cn", request.model]
    
    # Helper to quote values for Hydra
    def hydra_quote(value):
        value_str = str(value)
        escaped_value = value_str.replace("'", r"\'")
        return f"'{escaped_value}'"
    
    # Path keys that need quoting
    path_keys = {"audio_path", "output_path", "beatmap_path"}
    
    # Helper to add arguments
    def add_arg(key, value):
        if value is not None and value != '':
            if key in path_keys:
                cmd.append(f"{key}={hydra_quote(value)}")
            else:
                cmd.append(f"{key}={value}")
    
    def add_list_arg(key, items):
        if items:
            quoted_items = [f"'{str(item)}'" for item in items]
            items_str = ",".join(quoted_items)
            cmd.append(f"{key}=[{items_str}]")
    
    # Add all parameters
    add_arg("audio_path", request.audio_path)
    add_arg("output_path", job_output_dir)  # Use job-specific output directory
    add_arg("beatmap_path", request.beatmap_path)
    
    # Basic settings
    add_arg("gamemode", request.gamemode if request.gamemode is not None else 0)
    add_arg("difficulty", request.difficulty)
    add_arg("year", request.year)
    add_arg("mapper_id", request.mapper_id)
    
    # Difficulty settings
    for param in ['hp_drain_rate', 'circle_size', 'overall_difficulty', 
                  'approach_rate', 'slider_multiplier', 'slider_tick_rate']:
        add_arg(param, getattr(request, param))
    
    # Mania specific
    add_arg("keycount", request.keycount)
    add_arg("hold_note_ratio", request.hold_note_ratio)
    add_arg("scroll_speed_ratio", request.scroll_speed_ratio)
    
    # Generation settings
    add_arg("cfg_scale", request.cfg_scale)
    add_arg("temperature", request.temperature)
    add_arg("top_p", request.top_p)
    add_arg("seed", request.seed)
    
    # Timing
    add_arg("start_time", request.start_time)
    add_arg("end_time", request.end_time)
    
    # Boolean options
    cmd.append(f"export_osz={str(request.export_osz).lower()}")
    cmd.append(f"add_to_beatmap={str(request.add_to_beatmap).lower()}")
    cmd.append(f"hitsounded={str(request.hitsounded).lower()}")
    cmd.append(f"super_timing={str(request.super_timing).lower()}")
    
    # Lists
    add_list_arg("descriptors", request.descriptors)
    add_list_arg("negative_descriptors", request.negative_descriptors)
    if request.in_context_options and request.beatmap_path:
        add_list_arg("in_context", request.in_context_options)
    
    return cmd


def find_output_files(output_dir: str) -> Dict[str, List[str]]:
    """Find all output files in the directory"""
    output_path = Path(output_dir)
    if not output_path.exists():
        return {"osz": [], "osu": [], "other": []}
    
    osz_files = list(output_path.glob("*.osz"))
    osu_files = list(output_path.glob("*.osu"))
    other_files = [f for f in output_path.iterdir() if f.is_file() and f.suffix not in ['.osz', '.osu']]
    
    return {
        "osz": [f.name for f in osz_files],
        "osu": [f.name for f in osu_files], 
        "other": [f.name for f in other_files]
    }


@app.post("/inference", response_model=InferenceResponse)
async def start_inference(request: InferenceRequest):
    """Start inference process"""
    job_id = str(uuid.uuid4())
    
    with process_lock:
        if job_id in active_processes:
            raise HTTPException(status_code=409, detail="Job ID conflict")
        
        try:
            # Create job-specific output directory
            job_output_dir = OUTPUT_DIR / job_id
            job_output_dir.mkdir(exist_ok=True)
            
            cmd = build_inference_command(request, str(job_output_dir))
            print(f"Starting inference job {job_id} with command: {' '.join(cmd)}")
            
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
            
            # Initialize job metadata
            job_metadata[job_id] = {
                "audio_path": request.audio_path,
                "output_path": str(job_output_dir),
                "beatmap_path": request.beatmap_path,
                "export_osz": request.export_osz,
                "start_time": time.time()
            }
            
            print(f"Started inference process {job_id} with PID: {process.pid}")
            
            return InferenceResponse(
                job_id=job_id,
                status="started",
                message="Inference process started successfully"
            )
            
        except Exception as e:
            print(f"Error starting inference: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to start inference: {str(e)}")


@app.get("/jobs/{job_id}/status", response_model=JobStatus)
async def get_job_status(job_id: str):
    """Get job status"""
    with process_lock:
        if job_id not in active_processes:
            raise HTTPException(status_code=404, detail="Job not found")
        
        process = active_processes[job_id]
        return_code = process.poll()
        metadata = job_metadata.get(job_id, {})
        output_path = metadata.get("output_path")
        
        if return_code is None:
            # Process is still running
            return JobStatus(
                job_id=job_id,
                status="running",
                message="Inference in progress",
                progress=None,
                output_path=None,
                error=None,
                osz_files=None,
                osu_files=None
            )
        elif return_code == 0:
            # Process completed successfully
            output_files = find_output_files(output_path) if output_path else {"osz": [], "osu": [], "other": []}
            return JobStatus(
                job_id=job_id,
                status="completed",
                message="Inference completed successfully",
                progress=100.0,
                output_path=output_path,
                error=None,
                osz_files=output_files["osz"],
                osu_files=output_files["osu"]
            )
        else:
            # Process failed
            return JobStatus(
                job_id=job_id,
                status="failed",
                message="Process failed",
                progress=None,
                output_path=output_path,
                error=f"Process exited with code {return_code}",
                osz_files=None,
                osu_files=None
            )


@app.get("/jobs/{job_id}/stream")
async def stream_job_output(job_id: str):
    """Stream job output using Server-Sent Events"""
    
    async def event_generator():
        with process_lock:
            if job_id not in active_processes:
                yield {
                    "event": "error",
                    "data": "Job not found"
                }
                return
            
            process = active_processes[job_id]
        
        print(f"Starting to stream output for job {job_id}")
        
        try:
            # Stream output lines
            if process.stdout:
                for line in iter(process.stdout.readline, ""):
                    if not line:
                        break
                    
                    # Store output for later retrieval
                    with process_lock:
                        if job_id in process_outputs:
                            process_outputs[job_id].append(line)
                    
                    yield {
                        "event": "output",
                        "data": line.rstrip()
                    }
            
            # Wait for process to complete
            return_code = process.wait()
            
            if return_code == 0:
                yield {
                    "event": "completed",
                    "data": "Inference completed successfully"
                }
            else:
                yield {
                    "event": "failed", 
                    "data": f"Process failed with exit code {return_code}"
                }
                
        except Exception as e:
            print(f"Error streaming output for job {job_id}: {e}")
            yield {
                "event": "error",
                "data": f"Streaming error: {str(e)}"
            }
        finally:
            # Clean up
            with process_lock:
                if job_id in active_processes:
                    del active_processes[job_id]
                    print(f"Cleaned up job {job_id}")
    
    return EventSourceResponse(event_generator())


@app.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str):
    """Cancel a running job"""
    with process_lock:
        if job_id not in active_processes:
            raise HTTPException(status_code=404, detail="Job not found")
        
        process = active_processes[job_id]
        
        if process.poll() is not None:
            return {"status": "already_finished", "message": "Job already completed"}
        
        try:
            process.terminate()
            
            # Wait a bit for graceful termination
            try:
                process.wait(timeout=5)
                message = "Job cancelled successfully"
            except subprocess.TimeoutExpired:
                process.kill()
                message = "Job force-killed after timeout"
            
            del active_processes[job_id]
            
            return {
                "status": "cancelled",
                "message": message
            }
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error cancelling job: {str(e)}")


@app.get("/jobs/{job_id}/output")
async def get_job_output(job_id: str):
    """Get full job output"""
    with process_lock:
        if job_id not in process_outputs:
            raise HTTPException(status_code=404, detail="Job output not found")
        
        return {
            "job_id": job_id,
            "output": process_outputs[job_id]
        }


@app.get("/jobs")
async def list_jobs():
    """List all active jobs"""
    with process_lock:
        jobs = []
        for job_id, process in active_processes.items():
            return_code = process.poll()
            status = "completed" if return_code == 0 else "failed" if return_code is not None else "running"
            
            jobs.append({
                "job_id": job_id,
                "status": status,
                "pid": process.pid
            })
        
        return {"jobs": jobs}


@app.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    """Delete job and cleanup resources"""
    with process_lock:
        if job_id in active_processes:
            process = active_processes[job_id]
            if process.poll() is None:
                process.terminate()
            del active_processes[job_id]
        
        if job_id in process_outputs:
            del process_outputs[job_id]
    
    return {"message": f"Job {job_id} deleted successfully"}


def cleanup_finished_jobs():
    """Background task to cleanup finished jobs"""
    with process_lock:
        finished_jobs = []
        for job_id, process in active_processes.items():
            if process.poll() is not None:
                finished_jobs.append(job_id)
        
        for job_id in finished_jobs:
            print(f"Cleaning up finished job {job_id}")
            del active_processes[job_id]


@app.on_event("startup")
async def startup_event():
    """Startup event handler"""
    print("Starting Mapperatorinator API server...")
    
    # Start background cleanup task
    async def periodic_cleanup():
        while True:
            await asyncio.sleep(300)  # Cleanup every 5 minutes
            cleanup_finished_jobs()
    
    asyncio.create_task(periodic_cleanup())


@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown event handler"""
    print("Shutting down Mapperatorinator API server...")
    
    # Terminate all active processes
    with process_lock:
        for job_id, process in active_processes.items():
            if process.poll() is None:
                print(f"Terminating job {job_id}")
                process.terminate()


@app.get("/jobs/{job_id}/download")
async def download_osz_file(job_id: str, filename: Optional[str] = None):
    """Download .osz or .osu file from completed job"""
    with process_lock:
        if job_id not in job_metadata:
            raise HTTPException(status_code=404, detail="Job not found")
        
        metadata = job_metadata[job_id]
        output_path = metadata.get("output_path")
        
        if not output_path or not Path(output_path).exists():
            raise HTTPException(status_code=404, detail="No output directory found")
        
        # Find available files
        output_files = find_output_files(output_path)
        all_files = output_files["osz"] + output_files["osu"]
        
        if not all_files:
            raise HTTPException(status_code=404, detail="No downloadable files found")
        
        # If filename specified, use it; otherwise use the first .osz file or .osu file
        if filename:
            if filename not in all_files:
                raise HTTPException(status_code=404, detail=f"File {filename} not found")
            target_file = filename
        else:
            # Prefer .osz files
            if output_files["osz"]:
                target_file = output_files["osz"][0]
            elif output_files["osu"]:
                target_file = output_files["osu"][0]
            else:
                raise HTTPException(status_code=404, detail="No .osz or .osu files found")
        
        file_path = Path(output_path) / target_file
        
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found on disk")
        
        return FileResponse(
            path=str(file_path),
            filename=target_file,
            media_type='application/octet-stream'
        )


@app.get("/jobs/{job_id}/files")
async def list_job_files(job_id: str):
    """List all output files for a job"""
    with process_lock:
        if job_id not in job_metadata:
            raise HTTPException(status_code=404, detail="Job not found")
        
        metadata = job_metadata[job_id]
        output_path = metadata.get("output_path")
        
        if not output_path or not Path(output_path).exists():
            return {"files": []}
        
        output_files = find_output_files(output_path)
        files = []
        
        for file_type, file_list in output_files.items():
            for filename in file_list:
                file_path = Path(output_path) / filename
                if file_path.exists():
                    files.append({
                        "name": filename,
                        "type": file_type,
                        "size": file_path.stat().st_size,
                        "download_url": f"/jobs/{job_id}/download?filename={filename}"
                    })
        
        return {"files": files}


# Mount static files for download
app.mount("/downloads", StaticFiles(directory="outputs"), name="downloads")


@app.get("/download/{job_id}")
async def download_output(job_id: str):
    """Download the output file of a job (legacy endpoint)"""
    return await download_osz_file(job_id)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Mapperatorinator API Server")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    
    args = parser.parse_args()
    
    uvicorn.run(
        "api:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        access_log=True
    )
