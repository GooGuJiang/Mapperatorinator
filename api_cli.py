"""
Mapperatorinator API 客户端工具 - 命令行版本
支持上传音频、配置参数、监控进度、下载结果
"""

import argparse
import json
import sys
import time
from pathlib import Path
from simple_client import SimpleMapperatorinatorClient


def main():
    parser = argparse.ArgumentParser(
        description="Mapperatorinator API 命令行客户端",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  # 基本用法
  python api_cli.py generate audio.mp3 --difficulty 5.0 --gamemode 0
  
  # 指定输出目录
  python api_cli.py generate audio.mp3 -o ./my_outputs/
  
  # 使用参考beatmap
  python api_cli.py generate audio.mp3 --beatmap reference.osu
  
  # 批量生成不同难度
  python api_cli.py batch audio.mp3 --difficulties 3.0 4.5 6.0 7.5
  
  # 查看任务状态
  python api_cli.py status JOB_ID
  
  # 下载文件
  python api_cli.py download JOB_ID ./downloads/
        """)
    
    # 全局参数
    parser.add_argument("--api-url", default="http://127.0.0.1:8000", 
                       help="API服务器地址 (默认: http://127.0.0.1:8000)")
    
    subparsers = parser.add_subparsers(dest='command', help='可用命令')
    
    # generate 命令
    gen_parser = subparsers.add_parser('generate', help='生成单个beatmap')
    gen_parser.add_argument('audio', help='音频文件路径')
    gen_parser.add_argument('--beatmap', help='参考beatmap文件路径')
    gen_parser.add_argument('--model', default='default', help='模型名称')
    gen_parser.add_argument('--gamemode', type=int, choices=[0,1,2,3], default=0,
                           help='游戏模式 (0=osu!, 1=taiko, 2=catch, 3=mania)')
    gen_parser.add_argument('--difficulty', type=float, help='目标难度星级')
    gen_parser.add_argument('--cfg-scale', type=float, default=1.0, help='CFG引导强度')
    gen_parser.add_argument('--temperature', type=float, default=1.0, help='采样温度')
    gen_parser.add_argument('--seed', type=int, help='随机种子')
    gen_parser.add_argument('-o', '--output', default='./downloads/', help='输出目录')
    gen_parser.add_argument('--no-osz', action='store_true', help='不导出.osz文件')
    gen_parser.add_argument('--hitsounds', action='store_true', help='包含打击音效')
    
    # batch 命令
    batch_parser = subparsers.add_parser('batch', help='批量生成多个难度')
    batch_parser.add_argument('audio', help='音频文件路径')
    batch_parser.add_argument('--difficulties', nargs='+', type=float, 
                            default=[3.0, 4.5, 6.0, 7.5], help='难度列表')
    batch_parser.add_argument('--gamemode', type=int, choices=[0,1,2,3], default=0)
    batch_parser.add_argument('--model', default='default', help='模型名称')
    batch_parser.add_argument('-o', '--output', default='./downloads/', help='输出目录')
    
    # status 命令
    status_parser = subparsers.add_parser('status', help='查看任务状态')
    status_parser.add_argument('job_id', help='任务ID')
    
    # download 命令  
    dl_parser = subparsers.add_parser('download', help='下载任务结果')
    dl_parser.add_argument('job_id', help='任务ID')
    dl_parser.add_argument('output_dir', nargs='?', default='./', help='保存目录')
    
    # list 命令
    list_parser = subparsers.add_parser('list', help='列出所有任务')
    
    # cancel 命令
    cancel_parser = subparsers.add_parser('cancel', help='取消任务')
    cancel_parser.add_argument('job_id', help='任务ID')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    client = SimpleMapperatorinatorClient(args.api_url)
    
    try:
        if args.command == 'generate':
            generate_single(client, args)
        elif args.command == 'batch':
            generate_batch(client, args)
        elif args.command == 'status':
            show_status(client, args)
        elif args.command == 'download':
            download_result(client, args)
        elif args.command == 'list':
            list_jobs(client)
        elif args.command == 'cancel':
            cancel_job(client, args)
    except KeyboardInterrupt:
        print("\n⚠️ 用户中断操作")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 错误: {e}")
        sys.exit(1)


def generate_single(client, args):
    """生成单个beatmap"""
    print(f"🎵 处理音频文件: {args.audio}")
    
    # 检查文件存在
    if not Path(args.audio).exists():
        print(f"❌ 音频文件不存在: {args.audio}")
        return
    
    try:
        # 上传音频
        print("📤 上传音频文件...")
        audio_path = client.upload_audio(args.audio)
        
        # 上传beatmap（如果有）
        beatmap_path = None
        if args.beatmap:
            if Path(args.beatmap).exists():
                print("📤 上传参考beatmap...")
                beatmap_path = client.upload_beatmap(args.beatmap)
            else:
                print(f"⚠️ 参考beatmap文件不存在: {args.beatmap}")
        
        # 构建参数
        params = {
            'model': args.model,
            'gamemode': args.gamemode,
            'cfg_scale': args.cfg_scale,
            'temperature': args.temperature,
            'export_osz': not args.no_osz,
            'hitsounded': args.hitsounds
        }
        
        if args.difficulty:
            params['difficulty'] = args.difficulty
        if args.seed:
            params['seed'] = args.seed
        if beatmap_path:
            params['beatmap_path'] = beatmap_path
        
        print(f"🚀 启动推理任务...")
        print(f"   模型: {args.model}")
        print(f"   游戏模式: {args.gamemode}")
        print(f"   难度: {args.difficulty or '自动'}")
        
        # 启动任务
        job_id = client.start_inference(audio_path, **params)
        print(f"✅ 任务已启动: {job_id}")
        
        # 等待完成
        print("⏳ 等待任务完成...")
        status = client.wait_for_completion(job_id)
        
        if status['status'] == 'completed':
            print("🎉 任务完成！")
            
            # 下载结果
            output_path = Path(args.output)
            output_path.mkdir(parents=True, exist_ok=True)
            
            osz_file = client.download_osz(job_id, str(output_path))
            print(f"📥 文件已下载: {osz_file}")
        else:
            print(f"❌ 任务失败: {status.get('error', '未知错误')}")
    
    except Exception as e:
        print(f"💥 生成失败: {e}")


def generate_batch(client, args):
    """批量生成多个难度"""
    print(f"🎵 批量处理音频文件: {args.audio}")
    print(f"📊 目标难度: {args.difficulties}")
    
    if not Path(args.audio).exists():
        print(f"❌ 音频文件不存在: {args.audio}")
        return
    
    try:
        # 上传音频
        print("📤 上传音频文件...")
        audio_path = client.upload_audio(args.audio)
        
        jobs = []
        
        # 启动所有任务
        for i, difficulty in enumerate(args.difficulties):
            print(f"🚀 启动任务 {i+1}/{len(args.difficulties)} (难度: {difficulty})")
            
            job_id = client.start_inference(
                audio_path,
                model=args.model,
                gamemode=args.gamemode,
                difficulty=difficulty,
                export_osz=True
            )
            
            jobs.append((job_id, difficulty))
            print(f"   任务ID: {job_id}")
        
        print(f"\n⏳ 等待 {len(jobs)} 个任务完成...")
        
        # 等待所有任务完成
        output_dir = Path(args.output)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        completed = 0
        for job_id, difficulty in jobs:
            print(f"\n📊 等待难度 {difficulty} 完成...")
            status = client.wait_for_completion(job_id)
            
            if status['status'] == 'completed':
                try:
                    filename = f"difficulty_{difficulty}.osz"
                    save_path = output_dir / filename
                    client.download_osz(job_id, str(save_path))
                    print(f"✅ 难度 {difficulty} 完成: {save_path}")
                    completed += 1
                except Exception as e:
                    print(f"❌ 下载难度 {difficulty} 失败: {e}")
            else:
                print(f"❌ 难度 {difficulty} 生成失败: {status.get('error')}")
        
        print(f"\n🎊 批量生成完成！成功: {completed}/{len(jobs)}")
    
    except Exception as e:
        print(f"💥 批量生成失败: {e}")


def show_status(client, args):
    """显示任务状态"""
    try:
        status = client.get_job_status(args.job_id)
        
        print(f"📋 任务状态: {args.job_id}")
        print(f"   状态: {status['status']}")
        print(f"   消息: {status.get('message', 'N/A')}")
        
        if status.get('progress'):
            print(f"   进度: {status['progress']}%")
        
        if status.get('output_path'):
            print(f"   输出路径: {status['output_path']}")
        
        if status.get('osz_files'):
            print(f"   可下载文件: {', '.join(status['osz_files'])}")
        
        if status.get('error'):
            print(f"   错误: {status['error']}")
    
    except Exception as e:
        print(f"❌ 获取状态失败: {e}")


def download_result(client, args):
    """下载任务结果"""
    try:
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        osz_file = client.download_osz(args.job_id, str(output_dir))
        print(f"✅ 下载完成: {osz_file}")
    
    except Exception as e:
        print(f"❌ 下载失败: {e}")


def list_jobs(client):
    """列出所有任务"""
    try:
        import requests
        response = requests.get(f"{client.base_url}/jobs")
        response.raise_for_status()
        
        data = response.json()
        jobs = data.get('jobs', [])
        
        if not jobs:
            print("📭 没有活动任务")
            return
        
        print(f"📋 活动任务列表 ({len(jobs)} 个):")
        print("-" * 60)
        
        for job in jobs:
            print(f"ID: {job['job_id']}")
            print(f"状态: {job['status']}")
            print(f"PID: {job['pid']}")
            if job.get('start_time'):
                start_time = time.strftime('%Y-%m-%d %H:%M:%S', 
                                         time.localtime(job['start_time']))
                print(f"开始时间: {start_time}")
            print("-" * 40)
    
    except Exception as e:
        print(f"❌ 获取任务列表失败: {e}")


def cancel_job(client, args):
    """取消任务"""
    try:
        result = client.cancel_job(args.job_id)
        print(f"✅ {result['message']}")
    
    except Exception as e:
        print(f"❌ 取消任务失败: {e}")


if __name__ == "__main__":
    main()
