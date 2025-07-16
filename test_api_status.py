#!/usr/bin/env python3
"""
测试API状态端点和进度功能
"""

import requests
import time
import json

def test_api_endpoints():
    """测试API端点"""
    base_url = "http://127.0.0.1:8000"
    
    print("🧪 测试 Mapperatorinator API")
    print("=" * 50)
    
    # 测试根端点
    try:
        response = requests.get(f"{base_url}/")
        if response.status_code == 200:
            print("✅ 根端点正常")
            data = response.json()
            print(f"   API版本: {data.get('message', 'Unknown')}")
        else:
            print("❌ 根端点失败")
            return False
    except requests.exceptions.ConnectionError:
        print("❌ 无法连接到API服务器 (http://127.0.0.1:8000)")
        print("   请确保API服务器正在运行:")
        print("   python api_v2.py")
        return False
    except Exception as e:
        print(f"❌ 根端点测试错误: {e}")
        return False
    
    # 模拟创建一个任务并测试状态查询
    print("\n📊 测试状态端点响应格式:")
    
    # 创建一个不存在的job_id来测试404响应
    fake_job_id = "test-fake-job-12345"
    
    try:
        response = requests.get(f"{base_url}/jobs/{fake_job_id}/status")
        if response.status_code == 404:
            print("✅ 不存在任务的404响应正常")
        else:
            print(f"❌ 期望404，得到 {response.status_code}")
    except Exception as e:
        print(f"❌ 状态端点测试错误: {e}")
    
    # 测试进度端点
    try:
        response = requests.get(f"{base_url}/jobs/{fake_job_id}/progress")
        if response.status_code == 404:
            print("✅ 不存在任务的进度端点404响应正常")
        else:
            print(f"❌ 进度端点期望404，得到 {response.status_code}")
    except Exception as e:
        print(f"❌ 进度端点测试错误: {e}")
    
    # 测试作业列表端点
    try:
        response = requests.get(f"{base_url}/jobs")
        if response.status_code == 200:
            print("✅ 作业列表端点正常")
            data = response.json()
            print(f"   当前活动任务数: {len(data.get('jobs', []))}")
        else:
            print(f"❌ 作业列表端点失败: {response.status_code}")
    except Exception as e:
        print(f"❌ 作业列表端点测试错误: {e}")
    
    print("\n📋 API端点摘要:")
    print("   GET  /                        - API信息")
    print("   POST /process                 - 开始新任务")
    print("   GET  /jobs/{job_id}/status    - 获取任务状态和进度")
    print("   GET  /jobs/{job_id}/progress  - 获取详细进度信息")
    print("   GET  /jobs/{job_id}/stream    - 实时输出流")
    print("   GET  /jobs/{job_id}/download  - 下载结果")
    print("   GET  /jobs/{job_id}/files     - 列出输出文件")
    print("   POST /jobs/{job_id}/cancel    - 取消任务")
    print("   GET  /jobs                    - 列出所有任务")
    
    print("\n💡 测试完成!")
    print("   如需测试完整流程，请使用:")
    print("   1. 访问 http://127.0.0.1:8000/docs 查看API文档")
    print("   2. 打开 progress_monitor.html 进行交互测试")
    
    return True

if __name__ == "__main__":
    test_api_endpoints()
