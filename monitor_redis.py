#!/usr/bin/env python3
"""
Redis缓存监控脚本
用于监控Mapperatorinator API的Redis缓存使用情况
"""

import json
import time
import argparse
from typing import Dict, Any, Optional, Union

try:
    import redis
    import redis.exceptions
except ImportError:
    print("❌ 请安装redis包: pip install redis")
    exit(1)

def connect_redis(host: str = 'localhost', port: int = 6379, db: int = 1) -> Optional[redis.Redis]:
    """连接Redis"""
    try:
        r = redis.Redis(host=host, port=port, db=db, decode_responses=True)
        r.ping()
        print(f"✅ 连接到Redis成功: {host}:{port} (db={db})")
        return r
    except redis.exceptions.RedisError as e:
        print(f"❌ Redis连接失败: {e}")
        return None

def get_cache_stats(r: redis.Redis) -> Dict[str, Any]:
    """获取缓存统计信息"""
    if not r:
        return {}
    
    stats = {}
    
    # 获取不同类型的缓存键数量
    prefixes = ["job_progress", "job_metadata", "output_files", "model_config"]
    for prefix in prefixes:
        pattern = f"{prefix}:*"
        try:
            keys = r.keys(pattern)
            if isinstance(keys, (list, tuple)):
                stats[prefix] = {
                    "count": len(keys),
                    "keys": keys[:5]  # 显示前5个键作为示例
                }
            else:
                stats[prefix] = {"count": 0, "keys": []}
        except redis.exceptions.RedisError:
            stats[prefix] = {"count": 0, "keys": []}
    
    # 获取Redis内存使用情况
    try:
        info = r.info()
        if isinstance(info, dict):
            stats["memory"] = {
                "used_memory_human": info.get("used_memory_human", "N/A"),
                "used_memory_peak_human": info.get("used_memory_peak_human", "N/A"),
                "total_commands_processed": info.get("total_commands_processed", 0)
            }
    except redis.exceptions.RedisError:
        stats["memory"] = {"used_memory_human": "N/A", "used_memory_peak_human": "N/A", "total_commands_processed": 0}
    
    # 获取总键数
    try:
        stats["total_keys"] = r.dbsize()
    except redis.exceptions.RedisError:
        stats["total_keys"] = 0
    
    return stats

def monitor_cache(r: redis.Redis, interval: int = 10):
    """持续监控缓存"""
    print(f"🔍 开始监控Redis缓存 (每{interval}秒刷新)...")
    print("按Ctrl+C退出\n")
    
    try:
        while True:
            stats = get_cache_stats(r)
            
            # 清屏
            print("\033[2J\033[H", end="")
            
            # 显示时间戳
            print(f"📊 Redis缓存监控 - {time.strftime('%Y-%m-%d %H:%M:%S')}")
            print("=" * 60)
            
            # 显示内存使用
            if "memory" in stats:
                memory = stats["memory"]
                print(f"💾 内存使用: {memory['used_memory_human']}")
                print(f"📈 峰值内存: {memory['used_memory_peak_human']}")
                print(f"🔢 总命令数: {memory['total_commands_processed']}")
                print()
            
            # 显示总键数
            print(f"🔑 总键数: {stats.get('total_keys', 0)}")
            print()
            
            # 显示各类型缓存统计
            for prefix in ["job_progress", "job_metadata", "output_files", "model_config"]:
                if prefix in stats:
                    cache_info = stats[prefix]
                    count = cache_info['count']
                    print(f"📋 {prefix}: {count} 个缓存项")
                    if cache_info['keys']:
                        print(f"   示例键: {cache_info['keys'][:3]}")
            
            print("\n" + "=" * 60)
            print("按Ctrl+C退出")
            
            time.sleep(interval)
            
    except KeyboardInterrupt:
        print("\n👋 监控已停止")

def clear_cache(r: redis.Redis, pattern: Optional[str] = None):
    """清理缓存"""
    if not r:
        return
    
    if pattern:
        try:
            keys = r.keys(pattern)
            if isinstance(keys, (list, tuple)) and keys:
                deleted = r.delete(*keys)
                print(f"🗑️ 删除了 {deleted} 个匹配 '{pattern}' 的键")
            else:
                print(f"🤷 没有找到匹配 '{pattern}' 的键")
        except redis.exceptions.RedisError as e:
            print(f"❌ 删除缓存失败: {e}")
    else:
        # 只清理job相关的缓存
        job_patterns = ["job_progress:*", "job_metadata:*", "output_files:*"]
        total_deleted = 0
        for pattern in job_patterns:
            try:
                keys = r.keys(pattern)
                if isinstance(keys, (list, tuple)) and keys:
                    deleted = r.delete(*keys)
                    if isinstance(deleted, int):
                        total_deleted += deleted
                    print(f"🗑️ 删除了 {deleted} 个 '{pattern}' 键")
            except redis.exceptions.RedisError as e:
                print(f"❌ 删除 '{pattern}' 失败: {e}")
        
        print(f"✅ 总共删除了 {total_deleted} 个缓存键")

def main():
    parser = argparse.ArgumentParser(description="Redis缓存监控工具")
    parser.add_argument("--host", default="localhost", help="Redis主机")
    parser.add_argument("--port", type=int, default=6379, help="Redis端口")
    parser.add_argument("--db", type=int, default=1, help="Redis数据库")
    parser.add_argument("--interval", type=int, default=10, help="监控刷新间隔(秒)")
    parser.add_argument("--clear", help="清理缓存 (可指定模式，如 'job_progress:*')")
    parser.add_argument("--stats", action="store_true", help="显示一次性统计信息")
    
    args = parser.parse_args()
    
    # 连接Redis
    r = connect_redis(args.host, args.port, args.db)
    if not r:
        return
    
    if args.clear is not None:
        # 清理缓存
        pattern = args.clear if args.clear else None
        clear_cache(r, pattern)
    elif args.stats:
        # 显示统计信息
        stats = get_cache_stats(r)
        print(json.dumps(stats, indent=2, ensure_ascii=False))
    else:
        # 持续监控
        monitor_cache(r, args.interval)

if __name__ == "__main__":
    main()
