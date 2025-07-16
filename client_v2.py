#!/usr/bin/env python3
"""
Mapperatorinator API v2.0 客户端
支持完整的音频+参数上传，实时监控，文件下载
"""

import json
import requests
import sseclient
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Any

class MapperatorinatorClient:
    """Mapperatorinator API客户端"""
    
    def __init__(self, base_url: str = "http://127.0.0.1:8000"):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
    
    def process_audio(
        self,
        audio_file: str,
        model: str = "default",
        gamemode: int = 0,
        difficulty: Optional[float] = None,
        year: Optional[int] = None,
        mapper_id: Optional[int] = None,
        hp_drain_rate: Optional[float] = None,
        circle_size: Optional[float] = None,
        overall_difficulty: Optional[float] = None,
        approach_rate: Optional[float] = None,
        slider_multiplier: Optional[float] = None,
        slider_tick_rate: Optional[float] = None,
        keycount: Optional[int] = None,
        hold_note_ratio: Optional[float] = None,
        scroll_speed_ratio: Optional[float] = None,
        cfg_scale: float = 1.0,
        temperature: float = 1.0,
        top_p: float = 0.95,
        seed: Optional[int] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        export_osz: bool = True,
        add_to_beatmap: bool = False,
        hitsounded: bool = False,
        super_timing: bool = False,
        descriptors: Optional[List[str]] = None,
        negative_descriptors: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        上传音频文件和参数开始处理
        
        Args:
            audio_file: 音频文件路径
            其他参数: 生成参数
            
        Returns:
            包含job_id的响应
        """
        audio_path = Path(audio_file)
        if not audio_path.exists():
            raise FileNotFoundError(f"音频文件不存在: {audio_file}")
        
        # 准备文件
        files = {
            'audio_file': (audio_path.name, open(audio_path, 'rb'))
        }
        
        # 准备表单数据
        data = {
            'model': model,
            'gamemode': gamemode,
            'cfg_scale': cfg_scale,
            'temperature': temperature,
            'top_p': top_p,
            'export_osz': export_osz,
            'add_to_beatmap': add_to_beatmap,
            'hitsounded': hitsounded,
            'super_timing': super_timing
        }
        
        # 添加可选参数
        optional_params = {
            'difficulty': difficulty,
            'year': year,
            'mapper_id': mapper_id,
            'hp_drain_rate': hp_drain_rate,
            'circle_size': circle_size,
            'overall_difficulty': overall_difficulty,
            'approach_rate': approach_rate,
            'slider_multiplier': slider_multiplier,
            'slider_tick_rate': slider_tick_rate,
            'keycount': keycount,
            'hold_note_ratio': hold_note_ratio,
            'scroll_speed_ratio': scroll_speed_ratio,
            'seed': seed,
            'start_time': start_time,
            'end_time': end_time
        }
        
        for key, value in optional_params.items():
            if value is not None:
                data[key] = value
        
        # 添加列表参数
        if descriptors:
            data['descriptors'] = json.dumps(descriptors)
        if negative_descriptors:
            data['negative_descriptors'] = json.dumps(negative_descriptors)
        
        try:
            response = self.session.post(
                f"{self.base_url}/process",
                files=files,
                data=data
            )
            response.raise_for_status()
            return response.json()
        
        finally:
            files['audio_file'][1].close()
    
    def get_status(self, job_id: str) -> Dict[str, Any]:
        """获取任务状态"""
        response = self.session.get(f"{self.base_url}/jobs/{job_id}/status")
        response.raise_for_status()
        return response.json()
    
    def stream_output(self, job_id: str, callback=None):
        """
        流式获取输出
        
        Args:
            job_id: 任务ID
            callback: 输出处理回调函数 callback(event_type, data)
        """
        response = self.session.get(
            f"{self.base_url}/jobs/{job_id}/stream",
            stream=True,
            headers={'Accept': 'text/event-stream'}
        )
        response.raise_for_status()
        
        client = sseclient.SSEClient(response)
        
        for event in client.events():
            if callback:
                callback(event.event, event.data)
            else:
                print(f"[{event.event}] {event.data}")
            
            if event.event in ['completed', 'failed', 'error']:
                break
    
    def download_file(self, job_id: str, filename: Optional[str] = None, output_path: Optional[str] = None) -> str:
        """
        下载结果文件
        
        Args:
            job_id: 任务ID
            filename: 指定文件名（可选）
            output_path: 输出路径（可选）
            
        Returns:
            下载的文件路径
        """
        url = f"{self.base_url}/jobs/{job_id}/download"
        if filename:
            url += f"?filename={filename}"
        
        response = self.session.get(url)
        response.raise_for_status()
        
        # 获取文件名
        if 'content-disposition' in response.headers:
            content_disposition = response.headers['content-disposition']
            if 'filename=' in content_disposition:
                download_filename = content_disposition.split('filename=')[1].strip('"')
            else:
                download_filename = filename or f"{job_id}_result"
        else:
            download_filename = filename or f"{job_id}_result"
        
        # 确定保存路径
        if output_path:
            save_path = Path(output_path) / download_filename
        else:
            save_path = Path(download_filename)
        
        # 保存文件
        save_path.parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, 'wb') as f:
            f.write(response.content)
        
        return str(save_path)
    
    def list_files(self, job_id: str) -> List[Dict[str, Any]]:
        """列出所有输出文件"""
        response = self.session.get(f"{self.base_url}/jobs/{job_id}/files")
        response.raise_for_status()
        return response.json()['files']
    
    def cancel_job(self, job_id: str) -> Dict[str, Any]:
        """取消任务"""
        response = self.session.post(f"{self.base_url}/jobs/{job_id}/cancel")
        response.raise_for_status()
        return response.json()
    
    def list_jobs(self) -> List[Dict[str, Any]]:
        """列出所有任务"""
        response = self.session.get(f"{self.base_url}/jobs")
        response.raise_for_status()
        return response.json()['jobs']
    
    def wait_for_completion(self, job_id: str, check_interval: float = 2.0) -> Dict[str, Any]:
        """
        等待任务完成
        
        Args:
            job_id: 任务ID
            check_interval: 检查间隔（秒）
            
        Returns:
            最终状态
        """
        while True:
            status = self.get_status(job_id)
            
            if status['status'] in ['completed', 'failed']:
                return status
            
            time.sleep(check_interval)


def main():
    """命令行工具示例"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Mapperatorinator API客户端")
    parser.add_argument("audio_file", help="音频文件路径")
    parser.add_argument("--server", default="http://127.0.0.1:8000", help="服务器地址")
    parser.add_argument("--model", default="default", help="模型名称")
    parser.add_argument("--gamemode", type=int, default=0, help="游戏模式")
    parser.add_argument("--difficulty", type=float, help="目标难度")
    parser.add_argument("--output-dir", help="输出目录")
    parser.add_argument("--stream", action="store_true", help="实时输出")
    parser.add_argument("--wait", action="store_true", help="等待完成")
    
    args = parser.parse_args()
    
    # 创建客户端
    client = MapperatorinatorClient(args.server)
    
    try:
        print(f"🎵 上传音频文件: {args.audio_file}")
        
        # 开始处理
        result = client.process_audio(
            audio_file=args.audio_file,
            model=args.model,
            gamemode=args.gamemode,
            difficulty=args.difficulty
        )
        
        job_id = result['job_id']
        print(f"✅ 任务已启动: {job_id}")
        
        if args.stream:
            print("📡 实时输出:")
            client.stream_output(job_id)
        elif args.wait:
            print("⏳ 等待完成...")
            final_status = client.wait_for_completion(job_id)
            
            if final_status['status'] == 'completed':
                print("✅ 处理完成!")
                
                # 列出文件
                files = client.list_files(job_id)
                print(f"📁 输出文件 ({len(files)} 个):")
                for file_info in files:
                    print(f"  - {file_info['name']} ({file_info['size']} bytes)")
                
                # 下载主要文件
                if files:
                    download_path = client.download_file(job_id, output_path=args.output_dir)
                    print(f"⬇️ 已下载: {download_path}")
            else:
                print(f"❌ 处理失败: {final_status.get('error', '未知错误')}")
        else:
            print(f"ℹ️ 任务ID: {job_id}")
            print(f"ℹ️ 查看状态: {args.server}/jobs/{job_id}/status")
            print(f"ℹ️ 实时输出: {args.server}/jobs/{job_id}/stream")
    
    except Exception as e:
        print(f"❌ 错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    # 检查依赖
    try:
        import sseclient
    except ImportError:
        print("缺少sseclient-py包，安装: pip install sseclient-py")
        sys.exit(1)
    
    main()
