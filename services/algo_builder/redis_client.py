"""
Redis client for caching compiled strategies

This module provides Redis connection and caching utilities for compiled strategy objects.
Compiled strategies are cached with a 24-hour TTL to avoid recompilation on every use.

Requirements: 3.7
"""
import os
import pickle
import logging
from typing import Optional
import redis.asyncio as redis

logger = logging.getLogger(__name__)


class RedisClient:
    """
    Redis client for caching compiled strategies.
    
    Compiled strategies are stored with key pattern: compiled_strategy:{hash}
    TTL: 24 hours (86400 seconds)
    
    Requirements: 3.7
    """
    
    CACHE_TTL_SECONDS = 86400  # 24 hours
    KEY_PREFIX = "compiled_strategy:"
    
    def __init__(self):
        """Initialize Redis client from environment configuration"""
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        self._client: Optional[redis.Redis] = None
    
    async def connect(self):
        """Establish Redis connection"""
        if self._client is None:
            try:
                self._client = redis.from_url(
                    self.redis_url,
                    decode_responses=False,  # We need binary mode for pickle
                    max_connections=int(os.getenv("REDIS_MAX_CONNECTIONS", "50")),
                    socket_connect_timeout=5,
                    socket_timeout=5
                )
                # Test connection
                await self._client.ping()
                logger.info("Redis connected successfully")
            except Exception as e:
                logger.error(f"Failed to connect to Redis: {e}")
                raise
    
    async def disconnect(self):
        """Close Redis connection"""
        if self._client:
            await self._client.close()
            self._client = None
            logger.info("Redis disconnected")
    
    async def get_compiled_strategy(self, compiled_hash: str) -> Optional[str]:
        """
        Retrieve compiled strategy code from cache.
        
        Args:
            compiled_hash: SHA-256 hash of the strategy spec
            
        Returns:
            Compiled Python code string if found, None otherwise
        """
        if not self._client:
            await self.connect()
        
        try:
            key = f"{self.KEY_PREFIX}{compiled_hash}"
            cached_data = await self._client.get(key)
            
            if cached_data:
                # Deserialize the compiled code
                compiled_code = pickle.loads(cached_data)
                logger.info(f"Cache HIT for strategy hash: {compiled_hash[:8]}...")
                return compiled_code
            else:
                logger.info(f"Cache MISS for strategy hash: {compiled_hash[:8]}...")
                return None
                
        except Exception as e:
            logger.error(f"Failed to retrieve from Redis cache: {e}")
            return None
    
    async def set_compiled_strategy(self, compiled_hash: str, compiled_code: str) -> bool:
        """
        Store compiled strategy code in cache with 24h TTL.
        
        Args:
            compiled_hash: SHA-256 hash of the strategy spec
            compiled_code: Compiled Python code string
            
        Returns:
            True if successfully cached, False otherwise
        """
        if not self._client:
            await self.connect()
        
        try:
            key = f"{self.KEY_PREFIX}{compiled_hash}"
            # Serialize the compiled code
            serialized_data = pickle.dumps(compiled_code)
            
            # Store with TTL
            await self._client.setex(
                key,
                self.CACHE_TTL_SECONDS,
                serialized_data
            )
            
            logger.info(
                f"Cached compiled strategy: {compiled_hash[:8]}... "
                f"(TTL: {self.CACHE_TTL_SECONDS}s)"
            )
            return True
            
        except Exception as e:
            logger.error(f"Failed to cache compiled strategy: {e}")
            return False
    
    async def delete_compiled_strategy(self, compiled_hash: str) -> bool:
        """
        Delete compiled strategy from cache.
        
        Args:
            compiled_hash: SHA-256 hash of the strategy spec
            
        Returns:
            True if successfully deleted, False otherwise
        """
        if not self._client:
            await self.connect()
        
        try:
            key = f"{self.KEY_PREFIX}{compiled_hash}"
            deleted = await self._client.delete(key)
            
            if deleted:
                logger.info(f"Deleted cached strategy: {compiled_hash[:8]}...")
                return True
            else:
                logger.warning(f"Strategy not found in cache: {compiled_hash[:8]}...")
                return False
                
        except Exception as e:
            logger.error(f"Failed to delete from Redis cache: {e}")
            return False
    
    async def get_cache_stats(self) -> dict:
        """
        Get Redis cache statistics.
        
        Returns:
            Dictionary with cache statistics
        """
        if not self._client:
            await self.connect()
        
        try:
            info = await self._client.info("stats")
            keyspace = await self._client.info("keyspace")
            
            # Count compiled strategy keys
            cursor = 0
            strategy_count = 0
            while True:
                cursor, keys = await self._client.scan(
                    cursor,
                    match=f"{self.KEY_PREFIX}*",
                    count=100
                )
                strategy_count += len(keys)
                if cursor == 0:
                    break
            
            return {
                "total_connections": info.get("total_connections_received", 0),
                "total_commands": info.get("total_commands_processed", 0),
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
                "hit_rate": (
                    info.get("keyspace_hits", 0) / 
                    max(info.get("keyspace_hits", 0) + info.get("keyspace_misses", 0), 1)
                ) * 100,
                "cached_strategies": strategy_count,
                "db_keys": keyspace.get("db0", {}).get("keys", 0) if keyspace else 0
            }
            
        except Exception as e:
            logger.error(f"Failed to get cache stats: {e}")
            return {}


# Global Redis client instance
_redis_client: Optional[RedisClient] = None


async def get_redis_client() -> RedisClient:
    """
    Get or create the global Redis client instance.
    
    Returns:
        RedisClient instance
    """
    global _redis_client
    
    if _redis_client is None:
        _redis_client = RedisClient()
        await _redis_client.connect()
    
    return _redis_client


async def close_redis_client():
    """Close the global Redis client connection"""
    global _redis_client
    
    if _redis_client:
        await _redis_client.disconnect()
        _redis_client = None
