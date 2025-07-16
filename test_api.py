#!/usr/bin/env python3
"""
简单的API测试客户端
"""

import requests
import json
import time
from pathlib import Path

def test_api():
    """测试API基本功能"""
    base_url = "http://127.0.0.1:8000"
    
    print("🧪 测试 Mapperatorinator API v2.0")
    print("=" * 40)
    
    # 1. 测试根端点
    print("1️⃣ 测试根端点...")
    try:
        response = requests.get(f"{base_url}/")
        if response.status_code == 200:
            print("✅ 根端点正常")
            data = response.json()
            print(f"   版本: {data.get('message', 'Unknown')}")
        else:
            print(f"❌ 根端点错误: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 连接API失败: {e}")
        print("请确保API服务器正在运行: python api_v2.py")
        return False
    
    # 2. 测试处理端点（模拟请求，不需要真实音频文件）
    print("\n2️⃣ 测试处理端点参数验证...")
    
    # 创建一个临时的测试文件
    test_file_path = Path("test_audio.mp3")
    if not test_file_path.exists():
        # 创建一个假的音频文件用于测试
        with open(test_file_path, 'wb') as f:
            f.write(b"fake audio content for testing")
        print(f"   创建测试文件: {test_file_path}")
    
    try:
        files = {'audio_file': ('test.mp3', open(test_file_path, 'rb'), 'audio/mpeg')}
        data = {
            'model': 'default',
            'gamemode': 0,
            'difficulty': 5.0,
            'cfg_scale': 1.0,
            'temperature': 1.0,
            'top_p': 0.95,
            'export_osz': True,
            # 测试空的JSON参数
            'descriptors': '',  # 空字符串
            'negative_descriptors': ''  # 空字符串
        }
        
        response = requests.post(f"{base_url}/process", files=files, data=data)
        
        if response.status_code == 200:
            result = response.json()
            job_id = result.get('job_id')
            print(f"✅ 处理请求成功，任务ID: {job_id}")
            
            # 3. 测试状态查询
            print(f"\n3️⃣ 测试状态查询...")
            status_response = requests.get(f"{base_url}/jobs/{job_id}/status")
            if status_response.status_code == 200:
                status = status_response.json()
                print(f"✅ 状态查询成功: {status['status']}")
            else:
                print(f"❌ 状态查询失败: {status_response.status_code}")
            
            # 4. 测试任务列表
            print(f"\n4️⃣ 测试任务列表...")
            jobs_response = requests.get(f"{base_url}/jobs")
            if jobs_response.status_code == 200:
                jobs = jobs_response.json()
                print(f"✅ 任务列表查询成功，当前任务数: {len(jobs.get('jobs', []))}")
            else:
                print(f"❌ 任务列表查询失败: {jobs_response.status_code}")
            
            # 5. 测试取消任务
            print(f"\n5️⃣ 测试取消任务...")
            cancel_response = requests.post(f"{base_url}/jobs/{job_id}/cancel")
            if cancel_response.status_code == 200:
                cancel_result = cancel_response.json()
                print(f"✅ 任务取消成功: {cancel_result.get('message', 'Unknown')}")
            else:
                print(f"❌ 任务取消失败: {cancel_response.status_code}")
            
        else:
            print(f"❌ 处理请求失败: {response.status_code}")
            try:
                error_data = response.json()
                print(f"   错误详情: {error_data.get('detail', 'Unknown error')}")
            except:
                print(f"   响应内容: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ 测试处理端点失败: {e}")
        return False
    finally:
        # 清理测试文件
        if test_file_path.exists():
            test_file_path.unlink()
            print(f"   清理测试文件: {test_file_path}")
    
    print("\n🎉 API测试完成!")
    return True

def test_json_params():
    """测试JSON参数处理"""
    print("\n📋 测试JSON参数处理...")
    
    base_url = "http://127.0.0.1:8000"
    test_file_path = Path("test_audio.mp3")
    
    # 创建测试文件
    with open(test_file_path, 'wb') as f:
        f.write(b"fake audio content for testing")
    
    test_cases = [
        ("空字符串", ""),
        ("有效JSON数组", '["流行", "快节奏"]'),
        ("有效空数组", "[]"),
        ("无效JSON", "{invalid json"),
        ("null值", "null")
    ]
    
    try:
        for desc, json_str in test_cases:
            print(f"   测试 {desc}: {json_str}")
            
            files = {'audio_file': ('test.mp3', open(test_file_path, 'rb'), 'audio/mpeg')}
            data = {
                'model': 'default',
                'descriptors': json_str
            }
            
            response = requests.post(f"{base_url}/process", files=files, data=data)
            files['audio_file'][1].close()
            
            if response.status_code == 200:
                result = response.json()
                job_id = result.get('job_id')
                print(f"     ✅ 成功，任务ID: {job_id}")
                
                # 立即取消任务
                requests.post(f"{base_url}/jobs/{job_id}/cancel")
            else:
                error_data = response.json()
                print(f"     ❌ 失败: {error_data.get('detail', 'Unknown error')}")
    
    finally:
        if test_file_path.exists():
            test_file_path.unlink()

if __name__ == "__main__":
    if test_api():
        test_json_params()
    print("\n✨ 测试完成!")
