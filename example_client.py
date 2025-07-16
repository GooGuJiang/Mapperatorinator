#!/usr/bin/env python3
"""
Mapperatorinator API v2.0 完整使用示例
演示如何上传音频文件，设置参数，监控进度，下载结果
"""

import json
import requests
import time
from pathlib import Path
from typing import Optional, List

class MapperatorinatorAPIClient:
    """Mapperatorinator API客户端"""
    
    def __init__(self, base_url: str = "http://127.0.0.1:8000"):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        
    def check_connection(self) -> bool:
        """检查API连接"""
        try:
            response = self.session.get(f"{self.base_url}/")
            return response.status_code == 200
        except:
            return False
    
    def process_audio(
        self,
        audio_file_path: str,
        model: str = "v30",
        gamemode: int = 0,
        difficulty: Optional[float] = None,
        descriptors: Optional[List[str]] = None,
        negative_descriptors: Optional[List[str]] = None,
        **kwargs
    ) -> dict:
        """
        处理音频文件
        
        Args:
            audio_file_path: 音频文件路径
            model: 模型配置名称 (v30, v31, default等)
            gamemode: 游戏模式 (0=osu!, 1=taiko, 2=catch, 3=mania)
            difficulty: 目标难度
            descriptors: 风格描述符列表
            negative_descriptors: 负面描述符列表
            **kwargs: 其他参数
            
        Returns:
            包含job_id的响应
        """
        file_path = Path(audio_file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"音频文件不存在: {audio_file_path}")
        
        # 准备文件
        files = {
            'audio_file': (file_path.name, open(file_path, 'rb'))
        }
        
        # 准备基本参数
        data = {
            'model': model,
            'gamemode': gamemode,
        }
        
        # 添加可选参数
        if difficulty is not None:
            data['difficulty'] = difficulty
            
        # 处理JSON参数
        if descriptors:
            data['descriptors'] = json.dumps(descriptors)
        if negative_descriptors:
            data['negative_descriptors'] = json.dumps(negative_descriptors)
        
        # 添加其他kwargs参数
        for key, value in kwargs.items():
            if value is not None:
                data[key] = value
        
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
    
    def get_status(self, job_id: str) -> dict:
        """获取任务状态"""
        response = self.session.get(f"{self.base_url}/jobs/{job_id}/status")
        response.raise_for_status()
        return response.json()
    
    def wait_for_completion(self, job_id: str, timeout: int = 600, check_interval: int = 5) -> dict:
        """
        等待任务完成
        
        Args:
            job_id: 任务ID
            timeout: 超时时间（秒）
            check_interval: 检查间隔（秒）
            
        Returns:
            最终状态
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            status = self.get_status(job_id)
            
            print(f"📊 任务状态: {status['status']} - {status.get('message', '')}")
            
            if status['status'] in ['completed', 'failed']:
                return status
            
            time.sleep(check_interval)
        
        raise TimeoutError(f"任务 {job_id} 在 {timeout} 秒内未完成")
    
    def download_file(self, job_id: str, filename: Optional[str] = None, output_dir: str = ".") -> str:
        """下载结果文件"""
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
        
        # 保存文件
        output_path = Path(output_dir) / download_filename
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'wb') as f:
            f.write(response.content)
        
        return str(output_path)
    
    def list_files(self, job_id: str) -> List[dict]:
        """列出输出文件"""
        response = self.session.get(f"{self.base_url}/jobs/{job_id}/files")
        response.raise_for_status()
        return response.json()['files']


def main():
    """主函数演示"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Mapperatorinator API客户端示例")
    parser.add_argument("audio_file", help="音频文件路径")
    parser.add_argument("--server", default="http://127.0.0.1:8000", help="API服务器地址")
    parser.add_argument("--model", default="v30", help="模型配置名称")
    parser.add_argument("--gamemode", type=int, default=0, help="游戏模式")
    parser.add_argument("--difficulty", type=float, help="目标难度")
    parser.add_argument("--descriptors", nargs='+', help="风格描述符")
    parser.add_argument("--output-dir", default="downloads", help="下载目录")
    
    args = parser.parse_args()
    
    print("🎮 Mapperatorinator API客户端")
    print("=" * 40)
    
    # 创建客户端
    client = MapperatorinatorAPIClient(args.server)
    
    # 检查连接
    print("🔗 检查API连接...")
    if not client.check_connection():
        print(f"❌ 无法连接到API服务器: {args.server}")
        print("请确保API服务器正在运行")
        return
    
    print("✅ API连接正常")
    
    try:
        # 开始处理
        print(f"\n🎵 上传音频文件: {args.audio_file}")
        
        result = client.process_audio(
            audio_file_path=args.audio_file,
            model=args.model,
            gamemode=args.gamemode,
            difficulty=args.difficulty,
            descriptors=args.descriptors,
            export_osz=True
        )
        
        job_id = result['job_id']
        print(f"✅ 任务已启动: {job_id}")
        
        # 等待完成
        print(f"\n⏳ 等待处理完成...")
        final_status = client.wait_for_completion(job_id)
        
        if final_status['status'] == 'completed':
            print("\n🎉 处理完成!")
            
            # 列出文件
            files = client.list_files(job_id)
            print(f"\n📁 输出文件 ({len(files)} 个):")
            for file_info in files:
                size_mb = file_info['size'] / (1024 * 1024)
                print(f"  📄 {file_info['name']} ({size_mb:.2f} MB)")
            
            # 下载文件
            if files:
                print(f"\n⬇️ 下载文件到: {args.output_dir}")
                for file_info in files:
                    try:
                        download_path = client.download_file(
                            job_id, 
                            file_info['name'], 
                            args.output_dir
                        )
                        print(f"  ✅ {download_path}")
                    except Exception as e:
                        print(f"  ❌ 下载 {file_info['name']} 失败: {e}")
                
                print(f"\n🎯 下载完成! 文件保存在: {args.output_dir}")
            else:
                print("\n⚠️ 没有找到输出文件")
        
        else:
            print(f"\n❌ 处理失败: {final_status.get('error', '未知错误')}")
    
    except Exception as e:
        print(f"\n💥 发生错误: {e}")


if __name__ == "__main__":
    main()
