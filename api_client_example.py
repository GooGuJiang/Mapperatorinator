"""
Example client for the Mapperatorinator API
Shows how to use the API endpoints for inference with progress tracking
"""

import asyncio
import json
import time
from pathlib import Path
from typing import Optional

import aiohttp
import requests


class MapperatorinatorClient:
    """Client for the Mapperatorinator API"""
    
    def __init__(self, base_url: str = "http://127.0.0.1:8000"):
        self.base_url = base_url.rstrip('/')
        self.session = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    def upload_audio(self, file_path: str) -> dict:
        """Upload an audio file"""
        with open(file_path, 'rb') as f:
            files = {'file': f}
            response = requests.post(f"{self.base_url}/upload/audio", files=files)
            response.raise_for_status()
            return response.json()
    
    def upload_beatmap(self, file_path: str) -> dict:
        """Upload a beatmap file"""
        with open(file_path, 'rb') as f:
            files = {'file': f}
            response = requests.post(f"{self.base_url}/upload/beatmap", files=files)
            response.raise_for_status()
            return response.json()
    
    def validate_paths(self, audio_path: Optional[str] = None, 
                      beatmap_path: Optional[str] = None,
                      output_path: Optional[str] = None) -> dict:
        """Validate and autofill paths"""
        data = {}
        if audio_path:
            data['audio_path'] = audio_path
        if beatmap_path:
            data['beatmap_path'] = beatmap_path
        if output_path:
            data['output_path'] = output_path
        
        response = requests.post(f"{self.base_url}/validate-paths", json=data)
        response.raise_for_status()
        return response.json()
    
    def start_inference(self, **kwargs) -> dict:
        """Start inference job"""
        response = requests.post(f"{self.base_url}/inference", json=kwargs)
        response.raise_for_status()
        return response.json()
    
    def get_job_status(self, job_id: str) -> dict:
        """Get job status"""
        response = requests.get(f"{self.base_url}/jobs/{job_id}/status")
        response.raise_for_status()
        return response.json()
    
    def cancel_job(self, job_id: str) -> dict:
        """Cancel a job"""
        response = requests.post(f"{self.base_url}/jobs/{job_id}/cancel")
        response.raise_for_status()
        return response.json()
    
    def get_job_output(self, job_id: str) -> dict:
        """Get job output"""
        response = requests.get(f"{self.base_url}/jobs/{job_id}/output")
        response.raise_for_status()
        return response.json()
    
    def list_jobs(self) -> dict:
        """List all jobs"""
        response = requests.get(f"{self.base_url}/jobs")
        response.raise_for_status()
        return response.json()
    
    async def stream_job_output(self, job_id: str, callback=None):
        """Stream job output with Server-Sent Events"""
        if not self.session:
            raise RuntimeError("Client must be used as async context manager")
        
        url = f"{self.base_url}/jobs/{job_id}/stream"
        
        async with self.session.get(url) as response:
            if response.status != 200:
                raise aiohttp.ClientError(f"HTTP {response.status}")
            
            async for line in response.content:
                if line:
                    line_str = line.decode('utf-8').strip()
                    if line_str.startswith('data: '):
                        data = line_str[6:]  # Remove 'data: ' prefix
                        if callback:
                            callback(data)
                        else:
                            print(f"Output: {data}")
                    elif line_str.startswith('event: '):
                        event = line_str[7:]  # Remove 'event: ' prefix
                        if event == 'completed':
                            print("✅ Inference completed!")
                            break
                        elif event == 'failed':
                            print("❌ Inference failed!")
                            break
                        elif event == 'error':
                            print("💥 Stream error!")
                            break


def example_sync_usage():
    """Example of synchronous API usage"""
    client = MapperatorinatorClient()
    
    print("🚀 Starting inference example...")
    
    # Example inference request
    request_data = {
        "model": "default",  # Use appropriate model name
        "audio_path": "/path/to/your/audio.mp3",
        "output_path": "/path/to/output/directory",
        "gamemode": 0,  # osu! standard
        "difficulty": 5.0,
        "cfg_scale": 1.0,
        "temperature": 1.0,
        "export_osz": True
    }
    
    try:
        # Start inference
        response = client.start_inference(**request_data)
        job_id = response["job_id"]
        print(f"📝 Started job: {job_id}")
        
        # Poll for status
        while True:
            status = client.get_job_status(job_id)
            print(f"📊 Status: {status['status']}")
            
            if status["status"] in ["completed", "failed"]:
                break
            
            time.sleep(2)
        
        if status["status"] == "completed":
            print("✅ Inference completed successfully!")
            
            # Get output
            output = client.get_job_output(job_id)
            print(f"📄 Output lines: {len(output['output'])}")
        else:
            print(f"❌ Inference failed: {status.get('error', 'Unknown error')}")
    
    except Exception as e:
        print(f"💥 Error: {e}")


async def example_async_usage():
    """Example of asynchronous API usage with streaming"""
    
    async with MapperatorinatorClient() as client:
        print("🚀 Starting async inference example...")
        
        # Example inference request
        request_data = {
            "model": "default",  # Use appropriate model name
            "audio_path": "/path/to/your/audio.mp3",
            "output_path": "/path/to/output/directory",
            "gamemode": 0,  # osu! standard
            "difficulty": 5.0,
            "cfg_scale": 1.0,
            "temperature": 1.0,
            "export_osz": True
        }
        
        try:
            # Start inference
            response = client.start_inference(**request_data)
            job_id = response["job_id"]
            print(f"📝 Started job: {job_id}")
            
            # Stream output
            print("📡 Streaming output...")
            await client.stream_job_output(job_id)
            
        except Exception as e:
            print(f"💥 Error: {e}")


def example_file_upload():
    """Example of file upload"""
    client = MapperatorinatorClient()
    
    print("📁 File upload example...")
    
    # Upload audio file
    audio_path = "/path/to/your/audio.mp3"
    if Path(audio_path).exists():
        try:
            result = client.upload_audio(audio_path)
            print(f"🎵 Uploaded audio: {result['filename']}")
            uploaded_audio_path = result['path']
            
            # Use uploaded file in inference
            request_data = {
                "model": "default",
                "audio_path": uploaded_audio_path,
                "output_path": "/path/to/output",
                "gamemode": 0,
                "export_osz": True
            }
            
            response = client.start_inference(**request_data)
            print(f"📝 Started inference with uploaded file: {response['job_id']}")
            
        except Exception as e:
            print(f"💥 Upload error: {e}")
    else:
        print(f"❌ Audio file not found: {audio_path}")


def example_path_validation():
    """Example of path validation"""
    client = MapperatorinatorClient()
    
    print("🔍 Path validation example...")
    
    try:
        result = client.validate_paths(
            audio_path="/path/to/audio.mp3",
            beatmap_path="/path/to/beatmap.osu"
        )
        
        print(f"✅ Validation success: {result['success']}")
        if result['autofilled_audio_path']:
            print(f"🎵 Audio path: {result['autofilled_audio_path']}")
        if result['autofilled_output_path']:
            print(f"📁 Output path: {result['autofilled_output_path']}")
        if result['errors']:
            print(f"⚠️ Errors: {result['errors']}")
    
    except Exception as e:
        print(f"💥 Validation error: {e}")


if __name__ == "__main__":
    print("🎮 Mapperatorinator API Client Examples")
    print("=" * 50)
    
    # Run examples
    print("\n1. Path Validation Example:")
    example_path_validation()
    
    print("\n2. File Upload Example:")
    example_file_upload()
    
    print("\n3. Synchronous Usage Example:")
    example_sync_usage()
    
    print("\n4. Asynchronous Usage Example:")
    asyncio.run(example_async_usage())
