"""
Circuit Breaker

Implements circuit breaker pattern for webhook processing.
Requirements: 41.3, 41.4
"""

import time
import logging
from enum import Enum
from typing import Optional, Callable, Any
from dataclasses import dataclass
from datetime import datetime
import asyncio

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"       # Normal operation
    OPEN = "open"          # Failing, rejecting requests
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration"""
    failure_threshold: int = 5          # Failures before opening
    recovery_timeout: int = 60          # Seconds before half-open
    half_open_max_calls: int = 3        # Max calls in half-open state
    success_threshold: int = 2          # Successes to close circuit


class CircuitBreaker:
    """
    Circuit breaker pattern implementation
    
    States:
    - CLOSED: Normal operation, failures are counted
    - OPEN: Circuit is open, requests fail fast
    - HALF_OPEN: Testing if service recovered
    
    Requirements: 41.3, 41.4
    """
    
    def __init__(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None,
        redis_client=None
    ):
        """
        Initialize circuit breaker
        
        Args:
            name: Unique name for this circuit breaker
            config: Circuit breaker configuration
            redis_client: Optional Redis client for distributed state
        """
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.redis = redis_client
        self.logger = logging.getLogger(f"{self.__class__.__name__}:{name}")
        
        # State (use Redis if available for distributed systems)
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = 0
        self._half_open_calls = 0
        self._lock = asyncio.Lock()
    
    def _get_redis_key(self, suffix: str) -> str:
        """Get Redis key for state storage"""
        return f"circuit_breaker:{self.name}:{suffix}"
    
    async def _get_state(self) -> CircuitState:
        """Get current state (from Redis if available)"""
        if self.redis:
            try:
                state_str = await self.redis.get(self._get_redis_key("state"))
                if state_str:
                    return CircuitState(state_str.decode())
            except Exception:
                pass
        return self._state
    
    async def _set_state(self, state: CircuitState):
        """Set current state (to Redis if available)"""
        self._state = state
        if self.redis:
            try:
                await self.redis.set(
                    self._get_redis_key("state"),
                    state.value
                )
            except Exception:
                pass
    
    async def _increment_failure(self):
        """Increment failure counter"""
        self._failure_count += 1
        self._last_failure_time = time.time()
        
        if self.redis:
            try:
                key = self._get_redis_key("failures")
                await self.redis.incr(key)
                await self.redis.expire(key, self.config.recovery_timeout * 2)
            except Exception:
                pass
    
    async def _increment_success(self):
        """Increment success counter"""
        self._success_count += 1
        
        if self.redis:
            try:
                key = self._get_redis_key("successes")
                await self.redis.incr(key)
                await self.redis.expire(key, self.config.recovery_timeout * 2)
            except Exception:
                pass
    
    async def _reset_counts(self):
        """Reset failure and success counters"""
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0
        
        if self.redis:
            try:
                await self.redis.delete(self._get_redis_key("failures"))
                await self.redis.delete(self._get_redis_key("successes"))
            except Exception:
                pass
    
    async def can_execute(self) -> bool:
        """
        Check if request can be executed
        
        Returns:
            True if request should be allowed
        """
        async with self._lock:
            state = await self._get_state()
            
            if state == CircuitState.CLOSED:
                return True
            
            if state == CircuitState.OPEN:
                # Check if recovery timeout has passed
                time_since_failure = time.time() - self._last_failure_time
                
                if time_since_failure >= self.config.recovery_timeout:
                    # Move to half-open
                    await self._set_state(CircuitState.HALF_OPEN)
                    self._half_open_calls = 0
                    self.logger.info(f"Circuit {self.name} moved to HALF_OPEN")
                    return True
                else:
                    # Still open, reject
                    self.logger.warning(
                        f"Circuit {self.name} is OPEN, rejecting request"
                    )
                    return False
            
            if state == CircuitState.HALF_OPEN:
                # Allow limited calls in half-open state
                if self._half_open_calls < self.config.half_open_max_calls:
                    self._half_open_calls += 1
                    return True
                else:
                    self.logger.warning(
                        f"Circuit {self.name} HALF_OPEN max calls reached"
                    )
                    return False
            
            return True
    
    async def record_success(self):
        """Record successful execution"""
        async with self._lock:
            await self._increment_success()
            state = await self._get_state()
            
            if state == CircuitState.HALF_OPEN:
                # Check if we can close the circuit
                if self._success_count >= self.config.success_threshold:
                    await self._set_state(CircuitState.CLOSED)
                    await self._reset_counts()
                    self.logger.info(f"Circuit {self.name} CLOSED (recovered)")
            
            elif state == CircuitState.CLOSED:
                # Reset failure count on success
                if self._failure_count > 0:
                    self._failure_count = 0
    
    async def record_failure(self):
        """Record failed execution"""
        async with self._lock:
            await self._increment_failure()
            state = await self._get_state()
            
            if state == CircuitState.HALF_OPEN:
                # Failed in half-open, go back to open
                await self._set_state(CircuitState.OPEN)
                self.logger.warning(
                    f"Circuit {self.name} OPEN (failure in half-open)"
                )
            
            elif state == CircuitState.CLOSED:
                # Check if we should open the circuit
                if self._failure_count >= self.config.failure_threshold:
                    await self._set_state(CircuitState.OPEN)
                    self._last_failure_time = time.time()
                    self.logger.warning(
                        f"Circuit {self.name} OPEN ({self._failure_count} failures)"
                    )
    
    async def execute(
        self,
        func: Callable,
        *args,
        **kwargs
    ) -> Any:
        """
        Execute function with circuit breaker protection
        
        Args:
            func: Function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments
            
        Returns:
            Function result
            
        Raises:
            CircuitBreakerOpen: If circuit is open
            Exception: If function fails
        """
        if not await self.can_execute():
            raise CircuitBreakerOpen(f"Circuit {self.name} is OPEN")
        
        try:
            result = await func(*args, **kwargs)
            await self.record_success()
            return result
        except Exception as e:
            await self.record_failure()
            raise e
    
    def get_state(self) -> CircuitState:
        """Get current circuit state"""
        return self._state
    
    async def get_metrics(self) -> dict:
        """Get circuit breaker metrics"""
        state = await self._get_state()
        
        return {
            "name": self.name,
            "state": state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "failure_threshold": self.config.failure_threshold,
            "recovery_timeout": self.config.recovery_timeout,
            "last_failure_time": self._last_failure_time,
            "time_since_failure": time.time() - self._last_failure_time 
                                 if self._last_failure_time else None
        }
    
    async def force_open(self):
        """Manually open the circuit"""
        async with self._lock:
            await self._set_state(CircuitState.OPEN)
            self._last_failure_time = time.time()
            self.logger.warning(f"Circuit {self.name} manually OPENED")
    
    async def force_close(self):
        """Manually close the circuit"""
        async with self._lock:
            await self._set_state(CircuitState.CLOSED)
            await self._reset_counts()
            self.logger.info(f"Circuit {self.name} manually CLOSED")


class CircuitBreakerOpen(Exception):
    """Exception raised when circuit breaker is open"""
    pass


class CircuitBreakerManager:
    """Manages multiple circuit breakers"""
    
    def __init__(self, redis_client=None):
        self.breakers: Dict[str, CircuitBreaker] = {}
        self.redis = redis_client
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def get_breaker(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None
    ) -> CircuitBreaker:
        """Get or create circuit breaker"""
        if name not in self.breakers:
            self.breakers[name] = CircuitBreaker(
                name=name,
                config=config,
                redis_client=self.redis
            )
        return self.breakers[name]
    
    async def get_all_metrics(self) -> Dict[str, dict]:
        """Get metrics for all circuit breakers"""
        metrics = {}
        for name, breaker in self.breakers.items():
            metrics[name] = await breaker.get_metrics()
        return metrics
    
    async def force_open_all(self):
        """Open all circuits"""
        for breaker in self.breakers.values():
            await breaker.force_open()
    
    async def force_close_all(self):
        """Close all circuits"""
        for breaker in self.breakers.values():
            await breaker.force_close()


# Global circuit breaker manager instance
_circuit_manager: Optional[CircuitBreakerManager] = None


def get_circuit_manager(redis_client=None) -> CircuitBreakerManager:
    """Get global circuit breaker manager"""
    global _circuit_manager
    if _circuit_manager is None:
        _circuit_manager = CircuitBreakerManager(redis_client)
    return _circuit_manager
