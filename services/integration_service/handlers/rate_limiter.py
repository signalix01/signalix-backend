"""
Rate Limiter

Sliding window rate limiting using Redis.
Requirements: 17.6, 34.1, 34.2, 34.3
"""

import time
import logging
from typing import Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Sliding window rate limiter using Redis
    
    Features:
    - Per-user rate limiting
    - Per-source rate limiting
    - Sliding window with millisecond precision
    - Configurable limits per integration type
    """
    
    def __init__(self, redis_client=None):
        """
        Initialize rate limiter
        
        Args:
            redis_client: Redis client instance (optional)
        """
        self.redis = redis_client
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Default limits (per minute)
        self.default_limits = {
            "tradingview": {"requests": 100, "window": 60},
            "amibroker": {"requests": 1000, "window": 60},
            "chartink": {"requests": 60, "window": 60},
            "default": {"requests": 100, "window": 60},
        }
    
    async def is_allowed(
        self,
        key: str,
        max_requests: int = 100,
        window_seconds: int = 60,
        increment: bool = True
    ) -> Tuple[bool, dict]:
        """
        Check if request is allowed under rate limit (sliding window)
        
        Args:
            key: Unique identifier for the rate limit bucket
            max_requests: Maximum requests allowed in window
            window_seconds: Time window in seconds
            increment: Whether to increment the counter
            
        Returns:
            Tuple of (allowed, metadata)
            metadata contains: current_count, remaining, reset_time
            
        Requirements: 17.6, 34.1, 34.2
        """
        if not self.redis:
            # Allow all if Redis not available (fail open)
            self.logger.warning("Redis not available, allowing request")
            return True, {"current_count": 0, "remaining": max_requests, "reset_time": 0}
        
        try:
            now = time.time()
            window_start = now - window_seconds
            
            # Use sorted set for sliding window
            # Score = timestamp, Value = unique request ID (using timestamp + counter)
            
            # Remove old entries outside the window
            await self.redis.zremrangebyscore(key, 0, window_start)
            
            # Count current requests in window
            current_count = await self.redis.zcard(key)
            
            if increment:
                if current_count >= max_requests:
                    # Get oldest entry to calculate reset time
                    oldest = await self.redis.zrange(key, 0, 0, withscores=True)
                    reset_time = int(oldest[0][1] + window_seconds) if oldest else int(now + window_seconds)
                    
                    return False, {
                        "current_count": current_count,
                        "remaining": 0,
                        "reset_time": reset_time,
                        "limit": max_requests,
                        "window": window_seconds
                    }
                
                # Add current request
                request_id = f"{now}:{key}:{current_count}"
                await self.redis.zadd(key, {request_id: now})
                
                # Set expiry on the key
                await self.redis.expire(key, window_seconds + 1)
                
                current_count += 1
            
            remaining = max(0, max_requests - current_count)
            oldest = await self.redis.zrange(key, 0, 0, withscores=True)
            reset_time = int(oldest[0][1] + window_seconds) if oldest else int(now + window_seconds)
            
            return True, {
                "current_count": current_count,
                "remaining": remaining,
                "reset_time": reset_time,
                "limit": max_requests,
                "window": window_seconds
            }
            
        except Exception as e:
            self.logger.error(f"Rate limit check error: {str(e)}")
            # Fail open on error
            return True, {"error": str(e), "current_count": 0, "remaining": max_requests}
    
    async def check_user_limit(
        self,
        user_id: str,
        integration_type: str,
        custom_limit: Optional[int] = None
    ) -> Tuple[bool, dict]:
        """
        Check rate limit for a user + integration combination
        
        Args:
            user_id: User identifier
            integration_type: Type of integration (tradingview, amibroker, chartink)
            custom_limit: Optional custom limit to override default
            
        Returns:
            Tuple of (allowed, metadata)
        """
        key = f"rate_limit:user:{user_id}:{integration_type}"
        
        # Get limit config
        if custom_limit:
            max_requests = custom_limit
            window = 60
        else:
            config = self.default_limits.get(integration_type, self.default_limits["default"])
            max_requests = config["requests"]
            window = config["window"]
        
        return await self.is_allowed(key, max_requests, window)
    
    async def check_source_limit(
        self,
        source_ip: str,
        window_seconds: int = 60,
        max_requests: int = 1000
    ) -> Tuple[bool, dict]:
        """
        Check rate limit for a source IP (global protection)
        
        Args:
            source_ip: Source IP address
            window_seconds: Time window
            max_requests: Max requests per window
            
        Returns:
            Tuple of (allowed, metadata)
        """
        key = f"rate_limit:source:{source_ip}"
        return await self.is_allowed(key, max_requests, window_seconds)
    
    async def get_current_usage(
        self,
        user_id: str,
        integration_type: str
    ) -> dict:
        """
        Get current rate limit usage without incrementing
        
        Args:
            user_id: User identifier
            integration_type: Integration type
            
        Returns:
            Usage statistics
        """
        key = f"rate_limit:user:{user_id}:{integration_type}"
        
        config = self.default_limits.get(integration_type, self.default_limits["default"])
        
        allowed, metadata = await self.is_allowed(
            key,
            config["requests"],
            config["window"],
            increment=False
        )
        
        return {
            "user_id": user_id,
            "integration_type": integration_type,
            "allowed": allowed,
            **metadata
        }
    
    async def reset_limit(
        self,
        user_id: str,
        integration_type: Optional[str] = None
    ) -> bool:
        """
        Reset rate limit for a user
        
        Args:
            user_id: User identifier
            integration_type: Optional specific integration, or all if None
            
        Returns:
            True if successful
        """
        if not self.redis:
            return False
        
        try:
            if integration_type:
                key = f"rate_limit:user:{user_id}:{integration_type}"
                await self.redis.delete(key)
            else:
                # Delete all rate limit keys for user
                pattern = f"rate_limit:user:{user_id}:*"
                keys = await self.redis.keys(pattern)
                if keys:
                    await self.redis.delete(*keys)
            return True
        except Exception as e:
            self.logger.error(f"Rate limit reset error: {str(e)}")
            return False
    
    def get_limit_config(self, integration_type: str) -> dict:
        """Get rate limit configuration for integration type"""
        return self.default_limits.get(
            integration_type,
            self.default_limits["default"]
        ).copy()
    
    async def get_all_limits(self, user_id: str) -> dict:
        """
        Get rate limit status for all integration types
        
        Args:
            user_id: User identifier
            
        Returns:
            Dict with status for each integration type
        """
        results = {}
        
        for integration_type in ["tradingview", "amibroker", "chartink"]:
            results[integration_type] = await self.get_current_usage(user_id, integration_type)
        
        return results
