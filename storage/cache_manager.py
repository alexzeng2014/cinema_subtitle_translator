"""
缓存管理器
提供多层缓存策略：内存缓存、Redis缓存、磁盘缓存
"""

import asyncio
import json
import pickle
from pathlib import Path
from typing import Any, Optional, Union
import structlog

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

import diskcache

from ..security.config import get_config

logger = structlog.get_logger(__name__)


class CacheManager:
    """多层缓存管理器"""
    
    def __init__(self):
        self.config = get_config()
        
        # 内存缓存
        self._memory_cache: dict = {}
        self._memory_cache_ttl: dict = {}
        
        # Redis缓存
        self._redis_client: Optional[redis.Redis] = None
        self._redis_available = False
        
        # 磁盘缓存
        cache_dir = Path(self.config.cache.cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)
        self._disk_cache = diskcache.Cache(str(cache_dir))
        
        # 统计信息
        self.stats = {
            "memory_hits": 0,
            "memory_misses": 0,
            "redis_hits": 0,
            "redis_misses": 0,
            "disk_hits": 0,
            "disk_misses": 0,
            "memory_sets": 0,
            "redis_sets": 0,
            "disk_sets": 0
        }
        
        # 初始化Redis
        asyncio.create_task(self._initialize_redis())
    
    async def _initialize_redis(self):
        """初始化Redis连接"""
        if not REDIS_AVAILABLE or not self.config.cache.redis_host:
            logger.info("Redis不可用，将使用内存和磁盘缓存")
            return
        
        try:
            self._redis_client = redis.Redis(
                host=self.config.cache.redis_host,
                port=self.config.cache.redis_port,
                password=self.config.cache.redis_password,
                db=self.config.cache.redis_db,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5
            )
            
            # 测试连接
            await self._redis_client.ping()
            self._redis_available = True
            logger.info("Redis连接成功")
            
        except Exception as e:
            logger.warning("Redis连接失败，将使用内存和磁盘缓存", error=str(e))
            self._redis_available = False
    
    async def get(self, key: str, default: Any = None) -> Any:
        """获取缓存值"""
        
        # 1. 首先检查内存缓存
        if key in self._memory_cache:
            if self._is_cache_valid(key, self._memory_cache_ttl):
                self.stats["memory_hits"] += 1
                logger.debug("内存缓存命中", key=key)
                return self._memory_cache[key]
            else:
                # 过期缓存清理
                del self._memory_cache[key]
                if key in self._memory_cache_ttl:
                    del self._memory_cache_ttl[key]
        
        self.stats["memory_misses"] += 1
        
        # 2. 检查Redis缓存
        if self._redis_available and self._redis_client:
            try:
                value = await self._redis_client.get(key)
                if value is not None:
                    # 反序列化
                    try:
                        cached_value = json.loads(value)
                    except json.JSONDecodeError:
                        cached_value = value
                    
                    # 回填到内存缓存
                    self._set_memory_cache(key, cached_value, self.config.cache.cache_ttl)
                    
                    self.stats["redis_hits"] += 1
                    logger.debug("Redis缓存命中", key=key)
                    return cached_value
            except Exception as e:
                logger.warning("Redis缓存获取失败", key=key, error=str(e))
        
        self.stats["redis_misses"] += 1
        
        # 3. 检查磁盘缓存
        try:
            if key in self._disk_cache:
                cached_value = self._disk_cache.get(key)
                
                # 回填到内存缓存
                self._set_memory_cache(key, cached_value, self.config.cache.cache_ttl)
                
                self.stats["disk_hits"] += 1
                logger.debug("磁盘缓存命中", key=key)
                return cached_value
        except Exception as e:
            logger.warning("磁盘缓存获取失败", key=key, error=str(e))
        
        self.stats["disk_misses"] += 1
        
        return default
    
    async def set(self, key: str, value: Any, expire: Optional[int] = None):
        """设置缓存值"""
        
        if expire is None:
            expire = self.config.cache.cache_ttl
        
        # 1. 设置内存缓存
        self._set_memory_cache(key, value, expire)
        
        # 2. 设置Redis缓存
        if self._redis_available and self._redis_client:
            try:
                # 序列化
                if isinstance(value, (dict, list)):
                    serialized = json.dumps(value, ensure_ascii=False)
                else:
                    serialized = str(value)
                
                await self._redis_client.setex(key, expire, serialized)
                self.stats["redis_sets"] += 1
            except Exception as e:
                logger.warning("Redis缓存设置失败", key=key, error=str(e))
        
        # 3. 设置磁盘缓存
        try:
            self._disk_cache.set(key, value, expire=expire)
            self.stats["disk_sets"] += 1
        except Exception as e:
            logger.warning("磁盘缓存设置失败", key=key, error=str(e))
    
    def _set_memory_cache(self, key: str, value: Any, expire: int):
        """设置内存缓存"""
        self._memory_cache[key] = value
        self._memory_cache_ttl[key] = asyncio.get_event_loop().time() + expire
        self.stats["memory_sets"] += 1
    
    def _is_cache_valid(self, key: str, ttl_dict: dict) -> bool:
        """检查缓存是否有效"""
        if key not in ttl_dict:
            return False
        
        return ttl_dict[key] > asyncio.get_event_loop().time()
    
    async def delete(self, key: str):
        """删除缓存"""
        
        # 删除内存缓存
        if key in self._memory_cache:
            del self._memory_cache[key]
        if key in self._memory_cache_ttl:
            del self._memory_cache_ttl[key]
        
        # 删除Redis缓存
        if self._redis_available and self._redis_client:
            try:
                await self._redis_client.delete(key)
            except Exception as e:
                logger.warning("Redis缓存删除失败", key=key, error=str(e))
        
        # 删除磁盘缓存
        try:
            if key in self._disk_cache:
                del self._disk_cache[key]
        except Exception as e:
            logger.warning("磁盘缓存删除失败", key=key, error=str(e))
    
    async def clear(self):
        """清空所有缓存"""
        
        # 清空内存缓存
        self._memory_cache.clear()
        self._memory_cache_ttl.clear()
        
        # 清空Redis缓存
        if self._redis_available and self._redis_client:
            try:
                await self._redis_client.flushdb()
            except Exception as e:
                logger.warning("Redis缓存清空失败", error=str(e))
        
        # 清空磁盘缓存
        try:
            self._disk_cache.clear()
        except Exception as e:
            logger.warning("磁盘缓存清空失败", error=str(e))
    
    async def exists(self, key: str) -> bool:
        """检查键是否存在"""
        
        # 检查内存缓存
        if key in self._memory_cache and self._is_cache_valid(key, self._memory_cache_ttl):
            return True
        
        # 检查Redis缓存
        if self._redis_available and self._redis_client:
            try:
                return await self._redis_client.exists(key) > 0
            except Exception:
                pass
        
        # 检查磁盘缓存
        try:
            return key in self._disk_cache
        except Exception:
            pass
        
        return False
    
    async def get_ttl(self, key: str) -> Optional[int]:
        """获取键的过期时间"""
        
        # 检查内存缓存
        if key in self._memory_cache_ttl:
            ttl = self._memory_cache_ttl[key] - asyncio.get_event_loop().time()
            return max(0, int(ttl))
        
        # 检查Redis缓存
        if self._redis_available and self._redis_client:
            try:
                return await self._redis_client.ttl(key)
            except Exception:
                pass
        
        return None
    
    async def cleanup_expired(self):
        """清理过期缓存"""
        
        # 清理内存缓存
        current_time = asyncio.get_event_loop().time()
        expired_keys = [
            key for key, ttl in self._memory_cache_ttl.items()
            if ttl <= current_time
        ]
        
        for key in expired_keys:
            if key in self._memory_cache:
                del self._memory_cache[key]
            del self._memory_cache_ttl[key]
        
        logger.info(f"清理了 {len(expired_keys)} 个过期的内存缓存")
        
        # 磁盘缓存会自动清理过期项
    
    def get_stats(self) -> dict:
        """获取缓存统计信息"""
        
        total_requests = (
            self.stats["memory_hits"] + self.stats["memory_misses"] +
            self.stats["redis_hits"] + self.stats["redis_misses"] +
            self.stats["disk_hits"] + self.stats["disk_misses"]
        )
        
        hit_rate = (
            (self.stats["memory_hits"] + self.stats["redis_hits"] + self.stats["disk_hits"]) /
            total_requests if total_requests > 0 else 0
        )
        
        return {
            "memory": {
                "hits": self.stats["memory_hits"],
                "misses": self.stats["memory_misses"],
                "size": len(self._memory_cache)
            },
            "redis": {
                "hits": self.stats["redis_hits"],
                "misses": self.stats["redis_misses"],
                "available": self._redis_available,
                "sets": self.stats["redis_sets"]
            },
            "disk": {
                "hits": self.stats["disk_hits"],
                "misses": self.stats["disk_misses"],
                "size": len(self._disk_cache),
                "sets": self.stats["disk_sets"]
            },
            "total_requests": total_requests,
            "hit_rate": hit_rate
        }
    
    async def close(self):
        """关闭缓存管理器"""
        
        # 关闭Redis连接
        if self._redis_client:
            await self._redis_client.close()
        
        # 关闭磁盘缓存
        self._disk_cache.close()
    
    def __aenter__(self):
        """异步上下文管理器入口"""
        return self
    
    def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        return asyncio.create_task(self.close())


# 全局缓存管理器实例
cache_manager = CacheManager()