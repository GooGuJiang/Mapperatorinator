#!/usr/bin/env python3
"""
Mapperatorinator API进度监控客户端示例
演示如何查询和监控任务进度
"""

import asyncio
import json
import requests
import time
from pathlib import Path
from typing import Optional

class MapperatorinatorProgressClient:
    """支持进度监控的Mapperatorinator API客户端"""
    
    def __init__(self, base_url: str = "http://127.0.0.1:8000"):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
    
    def get_progress(self, job_id: str) -> dict:
        """获取详细进度信息"""
        response = self.session.get(f"{self.base_url}/jobs/{job_id}/progress")
        response.raise_for_status()
        return response.json()
    
    def get_status(self, job_id: str) -> dict:
        """获取任务状态"""
        response = self.session.get(f"{self.base_url}/jobs/{job_id}/status")
        response.raise_for_status()
        return response.json()
    
    def start_job(self, audio_file_path: str, **params) -> str:
        """启动处理任务"""
        file_path = Path(audio_file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"音频文件不存在: {audio_file_path}")
        
        files = {'audio_file': (file_path.name, open(file_path, 'rb'))}
        data = {
            'model': params.get('model', 'v30'),
            'gamemode': params.get('gamemode', 0),
            'difficulty': params.get('difficulty', 5.0),
            'export_osz': params.get('export_osz', True)
        }
        
        # 添加其他参数
        for key, value in params.items():
            if key not in data and value is not None:
                data[key] = value
        
        try:
            response = self.session.post(f"{self.base_url}/process", files=files, data=data)
            response.raise_for_status()
            result = response.json()
            return result['job_id']
        finally:
            files['audio_file'][1].close()
    
    def monitor_progress(self, job_id: str, callback=None, update_interval: float = 2.0):
        """
        监控任务进度
        
        Args:
            job_id: 任务ID
            callback: 进度更新回调函数 callback(progress_info)
            update_interval: 更新间隔（秒）
        """
        print(f"📊 开始监控任务: {job_id}")
        
        last_progress = -1
        start_time = time.time()
        
        while True:
            try:
                # 获取进度信息
                progress_info = self.get_progress(job_id)
                current_progress = progress_info['progress']
                status = progress_info['status']
                stage = progress_info['stage']
                estimated = progress_info['estimated']
                
                # 如果进度有变化，打印更新
                if current_progress != last_progress:
                    elapsed = time.time() - start_time
                    estimated_text = " (估算)" if estimated else ""
                    print(f"⏱️  {elapsed:.1f}s | 📈 {current_progress:.1f}%{estimated_text} | 🔧 {stage}")
                    last_progress = current_progress
                
                # 调用回调函数
                if callback:
                    callback(progress_info)
                
                # 检查是否完成
                if status in ['completed', 'failed']:
                    if status == 'completed':
                        print(f"✅ 任务完成! 总耗时: {time.time() - start_time:.1f}秒")
                    else:
                        print(f"❌ 任务失败")
                    break
                
                time.sleep(update_interval)
                
            except requests.exceptions.RequestException as e:
                print(f"❌ 查询进度失败: {e}")
                time.sleep(update_interval)
            except KeyboardInterrupt:
                print("\n⚠️ 用户中断监控")
                break
    
    def download_result(self, job_id: str, output_dir: str = "downloads") -> Optional[str]:
        """下载结果文件"""
        try:
            response = self.session.get(f"{self.base_url}/jobs/{job_id}/download")
            response.raise_for_status()
            
            # 获取文件名
            filename = f"{job_id}_result.osz"
            if 'content-disposition' in response.headers:
                content_disposition = response.headers['content-disposition']
                if 'filename=' in content_disposition:
                    filename = content_disposition.split('filename=')[1].strip('"')
            
            # 保存文件
            output_path = Path(output_dir) / filename
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path, 'wb') as f:
                f.write(response.content)
            
            return str(output_path)
        except Exception as e:
            print(f"❌ 下载失败: {e}")
            return None
    
    def run_with_progress_monitoring(self, audio_file_path: str, **params):
        """运行完整的处理流程并监控进度"""
        print("🎮 Mapperatorinator API 进度监控客户端")
        print("=" * 50)
        
        try:
            # 启动任务
            print(f"🚀 启动处理任务...")
            print(f"🎵 音频文件: {audio_file_path}")
            print(f"🤖 模型: {params.get('model', 'v30')}")
            print(f"🎯 难度: {params.get('difficulty', 5.0)}")
            
            job_id = self.start_job(audio_file_path, **params)
            print(f"✅ 任务已启动: {job_id}")
            print()
            
            # 定义进度回调
            def progress_callback(progress_info):
                # 可以在这里添加自定义的进度处理逻辑
                pass
            
            # 监控进度
            self.monitor_progress(job_id, progress_callback)
            
            # 下载结果
            print("\n📥 下载结果文件...")
            download_path = self.download_result(job_id)
            if download_path:
                print(f"✅ 文件已下载: {download_path}")
            else:
                print("❌ 下载失败")
            
        except Exception as e:
            print(f"💥 处理失败: {e}")


def main():
    """命令行示例"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Mapperatorinator 进度监控客户端")
    parser.add_argument("audio_file", help="音频文件路径")
    parser.add_argument("--server", default="http://127.0.0.1:8000", help="API服务器地址")
    parser.add_argument("--model", default="v30", help="模型配置")
    parser.add_argument("--gamemode", type=int, default=0, help="游戏模式")
    parser.add_argument("--difficulty", type=float, default=5.0, help="目标难度")
    parser.add_argument("--monitor-only", help="仅监控指定任务ID的进度")
    parser.add_argument("--update-interval", type=float, default=2.0, help="进度更新间隔（秒）")
    
    args = parser.parse_args()
    
    client = MapperatorinatorProgressClient(args.server)
    
    if args.monitor_only:
        # 仅监控现有任务
        print(f"📊 监控现有任务: {args.monitor_only}")
        client.monitor_progress(args.monitor_only, update_interval=args.update_interval)
    else:
        # 启动新任务并监控
        params = {
            'model': args.model,
            'gamemode': args.gamemode,
            'difficulty': args.difficulty
        }
        client.run_with_progress_monitoring(args.audio_file, **params)


if __name__ == "__main__":
    main()
