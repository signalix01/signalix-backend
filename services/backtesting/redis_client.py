"""
Redis client for backtest task management.

This module provides Redis operations for:
- Tracking concurrent backtest limits per user tier
- Caching backtest progress
- Managing task queues

Requirements: 16.6
"""
import os
import logging
from typing import Optional
import redis.asyncio as redis
from shared.config.settings import settings

logger = logging.getLogger(__name__)


class BacktestRedisClient:
    """
    Redis client for backtest task management.
    
    Handles:
    - Concurrent backtest limits per tier (Req 16.6)
    - Task progress tracking
    - Result caching
    """
    
    # Tier limits for concurrent backtests (Req 16.6)
    TIER_LIMITS = {
        'free': 1,
        'equity': 2,
        'fo': 3,
        'pro': 5,
        'enterprise': 999  # Effectively unlimited
    }
    
    def __init__(self):
        """Initialize Redis client"""
        self.redis_url = settings.REDIS_URL
        self._client: Optional[redis.Redis] = None
    
    async def connect(self):
        """Establish Redis connection"""
        if self._client is None:
            try:
                self._client = redis.from_url(
                    self.redis_url,
                    decode_responses=True,
                    max_connections=50,
                    socket_connect_timeout=5,
                    socket_timeout=5
                )
                # Test connection
                await self._client.ping()
                logger.info("Backtest Redis client connected successfully")
            except Exception as e:
                logger.error(f"Failed to connect to Redis: {e}")
                raise
    
    async def disconnect(self):
        """Close Redis connection"""
        if self._client:
            await self._client.close()
            self._client = None
            logger.info("Backtest Redis client disconnected")
    
    async def can_start_backtest(self, user_id: str, tier: str = 'free') -> bool:
        """
        Check if user can start a new backtest based on tier limits.
        
        Args:
            user_id: User identifier
            tier: User tier (free/equity/fo/pro/enterprise)
            
        Returns:
            True if user can start a new backtest, False otherwise
        """
        if not self._client:
            await self.connect()
        
        try:
            key = f"backtest:concurrent:{user_id}"
            current_count = await self._client.get(key)
            current_count = int(current_count) if current_count else 0
            
            limit = self.TIER_LIMITS.get(tier.lower(), 1)
            
            can_start = current_count < limit
            
            if can_start:
                logger.info(
                    f"User {user_id} ({tier}) can start backtest: "
                    f"{current_count}/{limit} running"
                )
            else:
                logger.warning(
                    f"User {user_id} ({tier}) at concurrent limit: "
                    f"{current_count}/{limit} running"
                )
            
            return can_start
            
        except Exception as e:
            logger.error(f"Failed to check concurrent limit: {e}")
            # Fail open - allow the backtest
            return True
    
    async def increment_concurrent_count(self, user_id: str) -> int:
        """
        Increment user's concurrent backtest count.
        
        Args:
            user_id: User identifier
            
        Returns:
            New concurrent count
        """
        if not self._client:
            await self.connect()
        
        try:
            key = f"backtest:concurrent:{user_id}"
            new_count = await self._client.incr(key)
            
            # Set expiry to 2 hours (safety cleanup)
            await self._client.expire(key, 7200)
            
            logger.info(f"Incremented concurrent count for {user_id}: {new_count}")
            return new_count
            
        except Exception as e:
            logger.error(f"Failed to increment concurrent count: {e}")
            return 0
    
    async def decrement_concurrent_count(self, user_id: str) -> int:
        """
        Decrement user's concurrent backtest count.
        
        Args:
            user_id: User identifier
            
        Returns:
            New concurrent count
        """
        if not self._client:
            await self.connect()
        
        try:
            key = f"backtest:concurrent:{user_id}"
            new_count = await self._client.decr(key)
            
            # Don't let it go negative
            if new_count < 0:
                await self._client.set(key, 0)
                new_count = 0
            
            logger.info(f"Decremented concurrent count for {user_id}: {new_count}")
            return new_count
            
        except Exception as e:
            logger.error(f"Failed to decrement concurrent count: {e}")
            return 0
    
    async def set_task_progress(
        self,
        task_id: str,
        progress: int,
        status: str = 'running'
    ):
        """
        Update task progress.
        
        Args:
            task_id: Task identifier
            progress: Progress percentage (0-100)
            status: Task status
        """
        if not self._client:
            await self.connect()
        
        try:
            key = f"backtest:progress:{task_id}"
            data = {
                'progress': progress,
                'status': status
            }
            
            await self._client.hset(key, mapping=data)
            await self._client.expire(key, 86400)  # 24 hour expiry
            
        except Exception as e:
            logger.error(f"Failed to set task progress: {e}")
    
    async def get_task_progress(self, task_id: str) -> Optional[dict]:
        """
        Get task progress.
        
        Args:
            task_id: Task identifier
            
        Returns:
            Progress dict or None if not found
        """
        if not self._client:
            await self.connect()
        
        try:
            key = f"backtest:progress:{task_id}"
            data = await self._client.hgetall(key)
            
            if data:
                return {
                    'progress': int(data.get('progress', 0)),
                    'status': data.get('status', 'unknown')
                }
            return None
            
        except Exception as e:
            logger.error(f"Failed to get task progress: {e}")
            return None
    
    async def get_concurrent_count(self, user_id: str) -> int:
        """
        Get user's current concurrent backtest count.
        
        Args:
            user_id: User identifier
            
        Returns:
            Current concurrent count
        """
        if not self._client:
            await self.connect()
        
        try:
            key = f"backtest:concurrent:{user_id}"
            count = await self._client.get(key)
            return int(count) if count else 0
            
        except Exception as e:
            logger.error(f"Failed to get concurrent count: {e}")
            return 0


# Global Redis client instance
_redis_client: Optional[BacktestRedisClient] = None


async def get_redis_client() -> BacktestRedisClient:
    """
    Get or create the global Redis client instance.
    
    Returns:
        BacktestRedisClient instance
    """
    global _redis_client
    
    if _redis_client is None:
        _redis_client = BacktestRedisClient()
        await _redis_client.connect()
    
    return _redis_client


async def close_redis_client():
    """Close the global Redis client connection"""
    global _redis_client
    
    if _redis_client:
        await _redis_client.disconnect()
        _redis_client = None
