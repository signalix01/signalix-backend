"""
Options Analytics Cache Manager

Implements Redis caching for options data with TTL management,
pre-calculation, and cache invalidation.

Requirements: 31.1, 31.2, 31.3, 31.5, 53.1, 53.2, 53.3, 53.6
"""

import json
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from dataclasses import asdict

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

logger = logging.getLogger(__name__)


class CacheManager:
    """
    Cache manager for options analytics data
    
    Features:
    - Redis-based caching with configurable TTL
    - Pre-calculation for popular symbols
    - Cache invalidation on market data updates
    - Cache metrics tracking
    
    Requirements: 31.1, 31.2, 31.3, 31.5
    """
    
    # Default TTL values (in seconds)
    TTL_OPTIONS_CHAIN = 60        # 1 minute
    TTL_GREEKS = 60              # 1 minute
    TTL_MAX_PAIN = 300           # 5 minutes
    TTL_GEX = 300                # 5 minutes
    TTL_OI_DATA = 60             # 1 minute
    
    def __init__(self, redis_client=None):
        self.redis = redis_client
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Track metrics
        self._hits = 0
        self._misses = 0
    
    def _get_key(self, data_type: str, symbol: str, expiry: str, **kwargs) -> str:
        """Generate cache key"""
        key_parts = ["options", data_type, symbol, expiry]
        
        # Add additional qualifiers
        for k, v in sorted(kwargs.items()):
            key_parts.append(f"{k}:{v}")
        
        return ":".join(key_parts)
    
    async def get_options_chain(
        self,
        symbol: str,
        expiry: str
    ) -> Optional[Dict]:
        """Get cached options chain"""
        key = self._get_key("chain", symbol, expiry)
        return await self._get(key)
    
    async def set_options_chain(
        self,
        symbol: str,
        expiry: str,
        data: Dict,
        ttl: int = TTL_OPTIONS_CHAIN
    ):
        """Cache options chain"""
        key = self._get_key("chain", symbol, expiry)
        await self._set(key, data, ttl)
    
    async def get_greeks(
        self,
        symbol: str,
        strike: float,
        option_type: str,
        expiry: str,
        spot_price: float
    ) -> Optional[Dict]:
        """Get cached Greeks"""
        key = self._get_key(
            "greeks", symbol, expiry,
            strike=strike, type=option_type, spot=spot_price
        )
        return await self._get(key)
    
    async def set_greeks(
        self,
        symbol: str,
        strike: float,
        option_type: str,
        expiry: str,
        spot_price: float,
        data: Dict,
        ttl: int = TTL_GREEKS
    ):
        """Cache Greeks calculation"""
        key = self._get_key(
            "greeks", symbol, expiry,
            strike=strike, type=option_type, spot=spot_price
        )
        await self._set(key, data, ttl)
    
    async def get_max_pain(
        self,
        symbol: str,
        expiry: str
    ) -> Optional[Dict]:
        """Get cached max pain"""
        key = self._get_key("maxpain", symbol, expiry)
        return await self._get(key)
    
    async def set_max_pain(
        self,
        symbol: str,
        expiry: str,
        data: Dict,
        ttl: int = TTL_MAX_PAIN
    ):
        """Cache max pain calculation"""
        key = self._get_key("maxpain", symbol, expiry)
        await self._set(key, data, ttl)
    
    async def get_gex(
        self,
        symbol: str,
        expiry: str
    ) -> Optional[Dict]:
        """Get cached GEX"""
        key = self._get_key("gex", symbol, expiry)
        return await self._get(key)
    
    async def set_gex(
        self,
        symbol: str,
        expiry: str,
        data: Dict,
        ttl: int = TTL_GEX
    ):
        """Cache GEX calculation"""
        key = self._get_key("gex", symbol, expiry)
        await self._set(key, data, ttl)
    
    async def invalidate_symbol(self, symbol: str):
        """
        Invalidate all cached data for a symbol
        
        Requirements: 31.5
        """
        if not self.redis:
            return
        
        try:
            # Find and delete all keys for this symbol
            pattern = f"options:*:{symbol}:*"
            keys = await self.redis.keys(pattern)
            
            if keys:
                await self.redis.delete(*keys)
                self.logger.info(f"Invalidated {len(keys)} cache entries for {symbol}")
        except Exception as e:
            self.logger.error(f"Cache invalidation error: {e}")
    
    async def invalidate_expiry(self, symbol: str, expiry: str):
        """Invalidate cached data for specific symbol+expiry"""
        if not self.redis:
            return
        
        try:
            pattern = f"options:*:{symbol}:{expiry}*"
            keys = await self.redis.keys(pattern)
            
            if keys:
                await self.redis.delete(*keys)
                self.logger.info(f"Invalidated {len(keys)} cache entries for {symbol} {expiry}")
        except Exception as e:
            self.logger.error(f"Cache invalidation error: {e}")
    
    async def _get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        if not self.redis:
            self._misses += 1
            return None
        
        try:
            data = await self.redis.get(key)
            if data:
                self._hits += 1
                return json.loads(data)
            else:
                self._misses += 1
                return None
        except Exception as e:
            self.logger.error(f"Cache get error: {e}")
            self._misses += 1
            return None
    
    async def _set(self, key: str, value: Any, ttl: int):
        """Set value in cache"""
        if not self.redis:
            return
        
        try:
            await self.redis.setex(key, ttl, json.dumps(value))
        except Exception as e:
            self.logger.error(f"Cache set error: {e}")
    
    async def get_metrics(self) -> Dict[str, int]:
        """Get cache metrics"""
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0
        
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(hit_rate, 2),
            "total_requests": total
        }
    
    async def prewarm_cache(
        self,
        symbol: str,
        expiry: str,
        spot_price: float,
        strikes: List[float]
    ):
        """
        Pre-calculate Greeks for ATM ± 10 strikes
        
        Requirements: 53.1
        """
        from .calculators.greeks_calculator import GreeksCalculator
        
        calculator = GreeksCalculator()
        
        # Find ATM strike
        atm_strike = min(strikes, key=lambda x: abs(x - spot_price))
        atm_index = strikes.index(atm_strike)
        
        # Get ±10 strikes around ATM
        start_idx = max(0, atm_index - 10)
        end_idx = min(len(strikes), atm_index + 11)
        nearby_strikes = strikes[start_idx:end_idx]
        
        # Calculate TTE (time to expiry)
        from datetime import date
        expiry_date = datetime.strptime(expiry, "%Y-%m-%d").date()
        today = date.today()
        tte = (expiry_date - today).days / 365.0
        if tte <= 0:
            tte = 0.01  # Minimum 1 day
        
        # Pre-calculate for both calls and puts
        for strike in nearby_strikes:
            for option_type in ["CALL", "PUT"]:
                # Skip if already cached
                cached = await self.get_greeks(symbol, strike, option_type, expiry, spot_price)
                if cached:
                    continue
                
                # Estimate IV (would normally come from market data)
                estimated_iv = 0.25
                
                # Calculate Greeks
                try:
                    greeks = calculator.calculate_greeks(
                        option_type, strike, spot_price, tte, estimated_iv
                    )
                    
                    # Cache result
                    await self.set_greeks(
                        symbol, strike, option_type, expiry, spot_price,
                        {
                            "delta": greeks.delta,
                            "gamma": greeks.gamma,
                            "theta": greeks.theta,
                            "vega": greeks.vega,
                            "rho": greeks.rho,
                            "implied_volatility": greeks.implied_volatility,
                            "theoretical_price": greeks.theoretical_price
                        }
                    )
                except Exception as e:
                    self.logger.warning(f"Failed to prewarm Greeks for {strike} {option_type}: {e}")
        
        self.logger.info(f"Pre-warmed cache for {symbol} {expiry}")
