#!/usr/bin/env python3
"""
测试API参数处理的简单脚本
"""

import requests
import json
from pathlib import Path

def test_api_with_form_data():
    """测试API表单数据处理"""
    base_url = "http://127.0.0.1:8000"
    
    print("🧪 测试API参数处理...")
    
    # 创建测试音频文件
    test_file_path = Path("test_audio.mp3")
    with open(test_file_path, 'wb') as f:
        f.write(b"fake audio content for testing")
    
    try:
        # 模拟HTML表单提交的数据 (包含空字符串)
        files = {'audio_file': ('test.mp3', open(test_file_path, 'rb'), 'audio/mpeg')}
        data = {
            'model': 'v30',
            'gamemode': '0',
            'difficulty': '5.0',
            'year': '2023',
            'mapper_id': '',  # 空字符串
            'hp_drain_rate': '5.0',
            'circle_size': '4.0',
            'overall_difficulty': '8.0',
            'approach_rate': '9.0',
            'slider_multiplier': '1.4',
            'slider_tick_rate': '1.0',
            'keycount': '',  # 空字符串
            'hold_note_ratio': '',  # 空字符串
            'scroll_speed_ratio': '',  # 空字符串
            'cfg_scale': '1.0',
            'temperature': '0.9',
            'top_p': '0.9',
            'seed': '',  # 空字符串
            'start_time': '',  # 空字符串
            'end_time': '',  # 空字符串
            'export_osz': 'true',
            'add_to_beatmap': 'false',
            'hitsounded': 'false',
            'super_timing': 'false',
            'descriptors': '',  # 空字符串
            'negative_descriptors': ''  # 空字符串
        }
        
        print("📤 发送请求...")
        response = requests.post(f"{base_url}/process", files=files, data=data)
        
        if response.status_code == 200:
            result = response.json()
            job_id = result.get('job_id')
            print(f"✅ 请求成功！任务ID: {job_id}")
            
            # 立即取消任务
            cancel_response = requests.post(f"{base_url}/jobs/{job_id}/cancel")
            if cancel_response.status_code == 200:
                print("✅ 任务已取消")
            
            return True
        else:
            print(f"❌ 请求失败: {response.status_code}")
            try:
                error_data = response.json()
                print(f"错误详情: {json.dumps(error_data, indent=2, ensure_ascii=False)}")
            except:
                print(f"响应内容: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False
    finally:
        files['audio_file'][1].close()
        if test_file_path.exists():
            test_file_path.unlink()

def test_api_with_descriptors():
    """测试带描述符的请求"""
    base_url = "http://127.0.0.1:8000"
    
    print("\n🎨 测试描述符处理...")
    
    test_file_path = Path("test_audio.mp3")
    with open(test_file_path, 'wb') as f:
        f.write(b"fake audio content for testing")
    
    try:
        files = {'audio_file': ('test.mp3', open(test_file_path, 'rb'), 'audio/mpeg')}
        data = {
            'model': 'v30',
            'gamemode': '0',
            'difficulty': '6.5',
            'descriptors': '["流行", "快节奏"]',  # JSON数组
            'negative_descriptors': '["慢节奏"]',  # JSON数组
            'mapper_id': '123456',  # 有效的mapper ID
            'keycount': '4',  # 有效的keycount
            'seed': '12345'  # 有效的seed
        }
        
        response = requests.post(f"{base_url}/process", files=files, data=data)
        
        if response.status_code == 200:
            result = response.json()
            job_id = result.get('job_id')
            print(f"✅ 描述符请求成功！任务ID: {job_id}")
            
            # 取消任务
            requests.post(f"{base_url}/jobs/{job_id}/cancel")
            return True
        else:
            print(f"❌ 描述符请求失败: {response.status_code}")
            try:
                error_data = response.json()
                print(f"错误详情: {json.dumps(error_data, indent=2, ensure_ascii=False)}")
            except:
                print(f"响应内容: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ 描述符测试失败: {e}")
        return False
    finally:
        files['audio_file'][1].close()
        if test_file_path.exists():
            test_file_path.unlink()

if __name__ == "__main__":
    print("🎮 Mapperatorinator API参数测试")
    print("=" * 40)
    
    # 检查API是否运行
    try:
        response = requests.get("http://127.0.0.1:8000/")
        if response.status_code != 200:
            print("❌ API服务器未运行，请先启动: python api_v2.py")
            exit(1)
        print("✅ API服务器运行正常")
    except:
        print("❌ 无法连接API服务器，请先启动: python api_v2.py")
        exit(1)
    
    # 运行测试
    test1 = test_api_with_form_data()
    test2 = test_api_with_descriptors()
    
    if test1 and test2:
        print("\n🎉 所有测试通过！")
    else:
        print("\n💥 部分测试失败")
