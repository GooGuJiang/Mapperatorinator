"""
简单的 Mapperatorinator API 客户端
演示：上传音频 -> 配置参数 -> 启动推理 -> 查询进度 -> 下载osz文件
"""

import json
import time
from pathlib import Path
import requests


class SimpleMapperatorinatorClient:
    """简单的 Mapperatorinator API 客户端"""
    
    def __init__(self, base_url: str = "http://127.0.0.1:8000"):
        self.base_url = base_url.rstrip('/')
        print(f"🎮 连接到 Mapperatorinator API: {self.base_url}")
    
    def upload_audio(self, audio_file_path: str) -> str:
        """上传音频文件，返回服务器上的文件路径"""
        print(f"🎵 上传音频文件: {audio_file_path}")
        
        if not Path(audio_file_path).exists():
            raise FileNotFoundError(f"音频文件不存在: {audio_file_path}")
        
        with open(audio_file_path, 'rb') as f:
            files = {'file': f}
            response = requests.post(f"{self.base_url}/upload/audio", files=files)
            response.raise_for_status()
            
        result = response.json()
        print(f"✅ 音频上传成功: {result['filename']}")
        return result['path']
    
    def upload_beatmap(self, beatmap_file_path: str) -> str:
        """上传beatmap文件，返回服务器上的文件路径"""
        print(f"🗂️ 上传beatmap文件: {beatmap_file_path}")
        
        if not Path(beatmap_file_path).exists():
            raise FileNotFoundError(f"Beatmap文件不存在: {beatmap_file_path}")
        
        with open(beatmap_file_path, 'rb') as f:
            files = {'file': f}
            response = requests.post(f"{self.base_url}/upload/beatmap", files=files)
            response.raise_for_status()
            
        result = response.json()
        print(f"✅ Beatmap上传成功: {result['filename']}")
        return result['path']
    
    def start_inference(self, audio_path: str, **params) -> str:
        """启动推理，返回任务ID"""
        print("🚀 启动推理任务...")
        
        # 默认参数
        inference_params = {
            "model": "default",
            "audio_path": audio_path,
            "gamemode": 0,  # osu! standard
            "export_osz": True,  # 导出osz文件
            **params  # 用户自定义参数
        }
        
        print(f"📋 推理参数: {json.dumps(inference_params, indent=2, ensure_ascii=False)}")
        
        response = requests.post(f"{self.base_url}/inference", json=inference_params)
        response.raise_for_status()
        
        result = response.json()
        job_id = result['job_id']
        print(f"✅ 推理任务已启动，任务ID: {job_id}")
        return job_id
    
    def wait_for_completion(self, job_id: str, check_interval: float = 5.0) -> dict:
        """等待任务完成，返回最终状态"""
        print(f"⏳ 等待任务完成: {job_id}")
        
        while True:
            status = self.get_job_status(job_id)
            print(f"📊 任务状态: {status['status']}")
            
            if status['status'] in ['completed', 'failed']:
                return status
            
            time.sleep(check_interval)
    
    def get_job_status(self, job_id: str) -> dict:
        """获取任务状态"""
        response = requests.get(f"{self.base_url}/jobs/{job_id}/status")
        response.raise_for_status()
        return response.json()
    
    def download_osz(self, job_id: str, save_path: str = "./") -> str:
        """下载生成的osz文件"""
        print(f"📥 下载osz文件: {job_id}")
        
        # 获取任务状态查看可用的文件
        status = self.get_job_status(job_id)
        
        if status['status'] != 'completed':
            raise RuntimeError(f"任务未完成，当前状态: {status['status']}")
        
        osz_files = status.get('osz_files', [])
        if not osz_files:
            raise RuntimeError("没有找到osz文件")
        
        # 下载第一个osz文件
        osz_filename = osz_files[0]
        print(f"📦 下载文件: {osz_filename}")
        
        response = requests.get(f"{self.base_url}/jobs/{job_id}/download")
        response.raise_for_status()
        
        # 保存文件
        save_path_obj = Path(save_path)
        if save_path_obj.is_dir():
            final_path = save_path_obj / osz_filename
        else:
            final_path = save_path_obj
        
        with open(final_path, 'wb') as f:
            f.write(response.content)
        
        print(f"✅ 文件已保存到: {final_path}")
        return str(final_path)
    
    def get_output_files(self, job_id: str) -> list:
        """获取任务输出的所有文件列表"""
        response = requests.get(f"{self.base_url}/jobs/{job_id}/files")
        response.raise_for_status()
        return response.json()['files']


def example_complete_workflow():
    """完整的工作流程示例：从上传到下载"""
    client = SimpleMapperatorinatorClient()
    
    # 配置文件路径（请修改为实际路径）
    audio_file = "path/to/your/audio.mp3"  # 修改为你的音频文件路径
    beatmap_file = "path/to/your/beatmap.osu"  # 可选：参考beatmap文件
    
    try:
        print("=" * 60)
        print("🎮 Mapperatorinator 完整工作流程演示")
        print("=" * 60)
        
        # 步骤1：上传音频文件
        if Path(audio_file).exists():
            uploaded_audio_path = client.upload_audio(audio_file)
        else:
            print(f"⚠️ 音频文件不存在: {audio_file}")
            print("请修改 audio_file 变量为实际的音频文件路径")
            return
        
        # 步骤2：可选上传beatmap文件作为参考
        uploaded_beatmap_path = None
        if Path(beatmap_file).exists():
            uploaded_beatmap_path = client.upload_beatmap(beatmap_file)
        
        # 步骤3：配置推理参数并启动
        inference_params = {
            "gamemode": 0,          # 0=osu!, 1=taiko, 2=catch, 3=mania
            "difficulty": 5.0,      # 难度星级
            "cfg_scale": 1.0,       # CFG引导强度
            "temperature": 1.0,     # 采样温度
            "export_osz": True,     # 导出osz文件
            "hitsounded": False,    # 是否包含打击音效
        }
        
        if uploaded_beatmap_path:
            inference_params["beatmap_path"] = uploaded_beatmap_path
        
        job_id = client.start_inference(uploaded_audio_path, **inference_params)
        
        # 步骤4：等待完成
        final_status = client.wait_for_completion(job_id)
        
        if final_status['status'] == 'completed':
            print("🎉 推理完成！")
            
            # 步骤5：查看输出文件
            files = client.get_output_files(job_id)
            print(f"📁 输出文件:")
            for file_info in files:
                print(f"  - {file_info['name']} ({file_info['size']} bytes)")
            
            # 步骤6：下载osz文件
            osz_path = client.download_osz(job_id, "./downloads/")
            print(f"🎊 成功！beatmap已保存到: {osz_path}")
            
        else:
            print(f"❌ 推理失败: {final_status.get('error', '未知错误')}")
            
    except Exception as e:
        print(f"💥 错误: {e}")


def example_simple_usage():
    """简单使用示例"""
    client = SimpleMapperatorinatorClient()
    
    # 如果你已经有音频文件在服务器上
    audio_path = "/path/to/uploaded/audio.mp3"  # 修改为实际路径
    
    try:
        # 启动推理
        job_id = client.start_inference(
            audio_path=audio_path,
            gamemode=0,          # osu! standard
            difficulty=4.5,      # 4.5星难度
            export_osz=True
        )
        
        # 等待完成
        print("等待推理完成...")
        final_status = client.wait_for_completion(job_id)
        
        if final_status['status'] == 'completed':
            # 下载结果
            osz_file = client.download_osz(job_id)
            print(f"✅ 下载完成: {osz_file}")
        else:
            print(f"❌ 失败: {final_status.get('error')}")
            
    except Exception as e:
        print(f"💥 错误: {e}")


def example_batch_generation():
    """批量生成示例"""
    client = SimpleMapperatorinatorClient()
    
    audio_path = "/path/to/uploaded/audio.mp3"  # 修改为实际路径
    
    # 不同难度配置
    difficulty_configs = [
        {"difficulty": 3.0, "gamemode": 0, "version": "Easy"},
        {"difficulty": 4.5, "gamemode": 0, "version": "Normal"}, 
        {"difficulty": 6.0, "gamemode": 0, "version": "Hard"},
        {"difficulty": 7.5, "gamemode": 0, "version": "Insane"},
    ]
    
    jobs = []
    
    try:
        # 启动多个任务
        for config in difficulty_configs:
            print(f"🚀 启动 {config['version']} 难度生成...")
            job_id = client.start_inference(
                audio_path=audio_path,
                export_osz=True,
                **config
            )
            jobs.append((job_id, config['version']))
        
        # 等待所有任务完成
        for job_id, version in jobs:
            print(f"⏳ 等待 {version} 完成...")
            status = client.wait_for_completion(job_id)
            
            if status['status'] == 'completed':
                osz_file = client.download_osz(job_id, f"./downloads/{version}_")
                print(f"✅ {version} 完成: {osz_file}")
            else:
                print(f"❌ {version} 失败: {status.get('error')}")
                
    except Exception as e:
        print(f"💥 错误: {e}")


if __name__ == "__main__":
    print("🎮 Mapperatorinator 简单客户端示例")
    print("=" * 50)
    
    print("\n选择示例:")
    print("1. 完整工作流程演示")
    print("2. 简单使用示例") 
    print("3. 批量生成示例")
    
    choice = input("\n请输入选择 (1-3): ").strip()
    
    if choice == "1":
        example_complete_workflow()
    elif choice == "2":
        example_simple_usage()
    elif choice == "3":
        example_batch_generation()
    else:
        print("无效选择，显示完整工作流程演示:")
        example_complete_workflow()
