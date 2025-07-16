#!/usr/bin/env python3
"""
测试进度解析功能
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from api_v2 import parse_progress_from_output, estimate_progress_from_stage

def test_progress_parsing():
    """测试进度解析功能"""
    print("🧪 测试进度解析功能")
    print("=" * 50)
    
    # 测试用例 - 基于web-ui.js的实际输出格式
    test_cases = [
        # web-ui.js的主要格式
        ("  50%|██████████                    | 1/2 [00:30<00:30, 30.00s/it]", 50.0),
        ("100%|██████████████████████████████| 2/2 [01:00<00:00, 30.00s/it]", 100.0),
        ("  25%|███████                       | 1/4 [00:15<00:45, 15.00s/it]", 25.0),
        
        # 其他格式
        ("Processing 75%", 75.0),
        ("Progress: 33.5%", 33.5),
        ("50% complete", 50.0),
        ("Step 3 of 10", 30.0),
        ("Generating timing points...", None),
        ("No progress here", None),
    ]
    
    print("📊 进度百分比解析测试:")
    for i, (line, expected) in enumerate(test_cases, 1):
        result = parse_progress_from_output(line)
        status = "✅" if result == expected else "❌"
        print(f"  {status} Test {i}: '{line}' -> {result} (期望: {expected})")
    
    print("\n📋 阶段识别测试:")
    stage_test_cases = [
        ("Generating timing points for the beatmap", "generating_timing"),
        ("Generating kiai sections", "generating_kiai"), 
        ("Generating map structure", "generating_map"),
        ("Processing seq len optimization", "refining_positions"),
        ("Generated beatmap saved to output/test.osu", "completed"),
        ("Loading model weights", "loading"),
        ("Unknown operation", None),
    ]
    
    for i, (line, expected_stage) in enumerate(stage_test_cases, 1):
        result = estimate_progress_from_stage(line, 50.0)  # 假设当前进度50%
        stage = result['stage'] if result else None
        status = "✅" if stage == expected_stage else "❌"
        print(f"  {status} Test {i}: '{line}' -> {stage} (期望: {expected_stage})")
    
    print("\n🎯 综合测试:")
    # 模拟真实的推理输出序列
    real_output_sequence = [
        "Loading model configuration...",
        "  10%|███                           | 1/10 [00:05<00:45, 5.00s/it]",
        "Generating timing points for the beatmap",
        "  25%|███████                       | 2/8 [00:10<00:30, 5.00s/it]",
        "Generating map structure with difficulty 5.0",
        "  50%|██████████████                | 4/8 [00:20<00:20, 5.00s/it]",
        "Processing seq len optimization",
        "  75%|█████████████████████         | 6/8 [00:30<00:10, 5.00s/it]",
        "Saving beatmap to output directory",
        " 100%|██████████████████████████████| 8/8 [00:40<00:00, 5.00s/it]",
        "Generated beatmap saved to outputs/test_beatmap.osu"
    ]
    
    current_progress = 0.0
    for i, line in enumerate(real_output_sequence, 1):
        # 模拟API中的处理逻辑
        parsed = parse_progress_from_output(line)
        if parsed is not None:
            current_progress = parsed
            estimated = False
        else:
            stage_info = estimate_progress_from_stage(line, current_progress)
            if stage_info:
                current_progress = stage_info['progress']
                estimated = True
            else:
                estimated = True
        
        progress_type = "精确" if not estimated else "估算"
        print(f"  Step {i:2d}: {current_progress:5.1f}% ({progress_type}) - {line[:50]}...")

if __name__ == "__main__":
    test_progress_parsing()
