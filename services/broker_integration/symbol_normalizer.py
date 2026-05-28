"""
Symbol Normalizer

Normalizes broker-specific symbols to standard EXCHANGE:SYMBOL format.
Maintains symbol mapping table per broker with Redis caching.

Requirements: 10.5, 35.1, 35.2, 35.3, 35.4, 35.8, 35.9
"""

import re
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta
import logging
from difflib import get_close_matches

logger = logging.getLogger(__name__)


class SymbolNormalizer:
    """
    Symbol normalization service for broker adapters.
    
    Provides:
    - Broker symbol to standard format conversion
    - Redis caching for mappings
    - Fuzzy symbol search
    - Daily mapping updates from broker master contracts
    """
    
    CACHE_TTL = 86400  # 24 hours in seconds
    CACHE_PREFIX = "symbol_mapping:"
    
    def __init__(self, redis_client=None, db_session=None):
        """
        Initialize symbol normalizer.
        
        Args:
            redis_client: Redis client for caching
            db_session: Database session for persistent storage
        """
        self.redis = redis_client
        self.db = db_session
        self._local_cache: Dict[str, Dict[str, str]] = {}
        self._last_update: Dict[str, datetime] = {}
    
    def normalize(
        self,
        broker: str,
        broker_symbol: str,
        exchange: Optional[str] = None
    ) -> str:
        """
        Convert broker symbol to standard NSE:SYMBOL format.
        
        Args:
            broker: Broker code (e.g., 'zerodha', 'angel_one')
            broker_symbol: Broker-specific symbol
            exchange: Optional exchange hint
            
        Returns:
            Standard symbol in EXCHANGE:SYMBOL format
        """
        cache_key = f"{self.CACHE_PREFIX}{broker}:{broker_symbol}"
        
        # Try Redis cache first
        if self.redis:
            cached = self.redis.get(cache_key)
            if cached:
                return cached.decode('utf-8')
        
        # Try local cache
        broker_cache = self._local_cache.get(broker, {})
        if broker_symbol in broker_cache:
            return broker_cache[broker_symbol]
        
        # Try database
        if self.db:
            mapping = self._get_mapping_from_db(broker, broker_symbol)
            if mapping:
                standard_symbol = mapping['standard_symbol']
                self._cache_mapping(broker, broker_symbol, standard_symbol)
                return standard_symbol
        
        # Fallback: convert based on broker-specific rules
        standard_symbol = self._convert_to_standard(broker, broker_symbol, exchange)
        self._cache_mapping(broker, broker_symbol, standard_symbol)
        
        return standard_symbol
    
    def denormalize(
        self,
        broker: str,
        standard_symbol: str
    ) -> Tuple[str, Optional[str]]:
        """
        Convert standard EXCHANGE:SYMBOL to broker-specific format.
        
        Args:
            broker: Broker code
            standard_symbol: Standard symbol in EXCHANGE:SYMBOL format
            
        Returns:
            Tuple of (broker_symbol, exchange)
        """
        cache_key = f"{self.CACHE_PREFIX}{broker}:reverse:{standard_symbol}"
        
        # Try Redis cache
        if self.redis:
            cached = self.redis.get(cache_key)
            if cached:
                decoded = cached.decode('utf-8')
                parts = decoded.split(':')
                return parts[0], parts[1] if len(parts) > 1 else None
        
        # Try database
        if self.db:
            mapping = self._get_reverse_mapping_from_db(broker, standard_symbol)
            if mapping:
                broker_symbol = mapping['broker_symbol']
                exchange = mapping['exchange']
                self._cache_reverse_mapping(broker, standard_symbol, broker_symbol, exchange)
                return broker_symbol, exchange
        
        # Fallback: convert based on broker-specific rules
        broker_symbol, exchange = self._convert_to_broker(broker, standard_symbol)
        self._cache_reverse_mapping(broker, standard_symbol, broker_symbol, exchange)
        
        return broker_symbol, exchange
    
    def search_symbol(self, query: str, broker: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Fuzzy search for symbols.
        
        Requirements: 35.8, 35.9
        
        Args:
            query: Search query string
            broker: Broker code to search within
            limit: Maximum results to return
            
        Returns:
            List of matching symbol mappings
        """
        results = []
        
        # Get all mappings for broker from database
        if self.db:
            from ..models import SymbolMapping
            db_mappings = self.db.query(SymbolMapping).filter(
                SymbolMapping.broker_type == broker,
                SymbolMapping.is_active == True
            ).all()
            
            # Create searchable text
            searchable_items = []
            for mapping in db_mappings:
                text = f"{mapping.name or ''} {mapping.standard_symbol} {mapping.broker_symbol}"
                searchable_items.append((text, mapping))
            
            # Fuzzy match
            texts = [item[0] for item in searchable_items]
            matches = get_close_matches(query.upper(), texts, n=limit, cutoff=0.3)
            
            for match in matches:
                for text, mapping in searchable_items:
                    if text == match:
                        results.append(mapping.to_dict())
                        break
        
        return results[:limit]
    
    async def update_mappings(self, broker: str) -> int:
        """
        Update symbol mappings from broker master contract.
        
        Requirements: 35.4
        
        Args:
            broker: Broker code to update
            
        Returns:
            Number of mappings updated
        """
        logger.info(f"Updating symbol mappings for {broker}")
        
        # Check if recently updated
        last_update = self._last_update.get(broker)
        if last_update and (datetime.utcnow() - last_update) < timedelta(hours=1):
            logger.info(f"Skipping update for {broker} - updated recently")
            return 0
        
        # This would be implemented per broker to fetch master contract
        # For now, return 0 as placeholder
        self._last_update[broker] = datetime.utcnow()
        return 0
    
    def get_cached_mapping(
        self,
        broker: str,
        symbol: str,
        reverse: bool = False
    ) -> Optional[str]:
        """
        Get cached mapping from Redis.
        
        Args:
            broker: Broker code
            symbol: Symbol to lookup
            reverse: If True, lookup reverse mapping
            
        Returns:
            Cached mapping or None
        """
        if not self.redis:
            return None
        
        if reverse:
            key = f"{self.CACHE_PREFIX}{broker}:reverse:{symbol}"
        else:
            key = f"{self.CACHE_PREFIX}{broker}:{symbol}"
        
        cached = self.redis.get(key)
        if cached:
            return cached.decode('utf-8')
        
        return None
    
    def _cache_mapping(self, broker: str, broker_symbol: str, standard_symbol: str):
        """Cache a symbol mapping in Redis and local cache."""
        # Local cache
        if broker not in self._local_cache:
            self._local_cache[broker] = {}
        self._local_cache[broker][broker_symbol] = standard_symbol
        
        # Redis cache
        if self.redis:
            key = f"{self.CACHE_PREFIX}{broker}:{broker_symbol}"
            self.redis.setex(key, self.CACHE_TTL, standard_symbol)
    
    def _cache_reverse_mapping(
        self,
        broker: str,
        standard_symbol: str,
        broker_symbol: str,
        exchange: Optional[str]
    ):
        """Cache a reverse symbol mapping."""
        value = f"{broker_symbol}:{exchange or ''}"
        
        # Local cache
        if broker not in self._local_cache:
            self._local_cache[broker] = {}
        self._local_cache[broker][f"reverse:{standard_symbol}"] = value
        
        # Redis cache
        if self.redis:
            key = f"{self.CACHE_PREFIX}{broker}:reverse:{standard_symbol}"
            self.redis.setex(key, self.CACHE_TTL, value)
    
    def _get_mapping_from_db(self, broker: str, broker_symbol: str) -> Optional[Dict[str, Any]]:
        """Get mapping from database."""
        if not self.db:
            return None
        
        try:
            from ..models import SymbolMapping
            mapping = self.db.query(SymbolMapping).filter(
                SymbolMapping.broker_type == broker,
                SymbolMapping.broker_symbol == broker_symbol,
                SymbolMapping.is_active == True
            ).first()
            
            if mapping:
                return {
                    'broker_symbol': mapping.broker_symbol,
                    'standard_symbol': mapping.standard_symbol,
                    'exchange': mapping.exchange
                }
        except Exception as e:
            logger.error(f"Error fetching mapping from DB: {e}")
        
        return None
    
    def _get_reverse_mapping_from_db(
        self,
        broker: str,
        standard_symbol: str
    ) -> Optional[Dict[str, Any]]:
        """Get reverse mapping from database."""
        if not self.db:
            return None
        
        try:
            from ..models import SymbolMapping
            mapping = self.db.query(SymbolMapping).filter(
                SymbolMapping.broker_type == broker,
                SymbolMapping.standard_symbol == standard_symbol,
                SymbolMapping.is_active == True
            ).first()
            
            if mapping:
                return {
                    'broker_symbol': mapping.broker_symbol,
                    'standard_symbol': mapping.standard_symbol,
                    'exchange': mapping.exchange
                }
        except Exception as e:
            logger.error(f"Error fetching reverse mapping from DB: {e}")
        
        return None
    
    def _convert_to_standard(
        self,
        broker: str,
        broker_symbol: str,
        exchange: Optional[str]
    ) -> str:
        """
        Convert broker symbol to standard format using broker-specific rules.
        
        Args:
            broker: Broker code
            broker_symbol: Broker-specific symbol
            exchange: Optional exchange hint
            
        Returns:
            Standard symbol in EXCHANGE:SYMBOL format
        """
        # If already in standard format, return as-is
        if ":" in broker_symbol:
            return broker_symbol
        
        # Apply broker-specific conversion rules
        if broker == "zerodha":
            return self._convert_zerodha_to_standard(broker_symbol, exchange)
        elif broker == "angel_one":
            return self._convert_angel_one_to_standard(broker_symbol, exchange)
        elif broker == "dhan":
            return self._convert_dhan_to_standard(broker_symbol, exchange)
        elif broker == "upstox":
            return self._convert_upstox_to_standard(broker_symbol, exchange)
        elif broker == "icici_direct":
            return self._convert_icici_to_standard(broker_symbol, exchange)
        
        # Default: assume NSE if not specified
        exchange = exchange or "NSE"
        return f"{exchange}:{broker_symbol}"
    
    def _convert_to_broker(
        self,
        broker: str,
        standard_symbol: str
    ) -> Tuple[str, Optional[str]]:
        """
        Convert standard symbol to broker-specific format.
        
        Args:
            broker: Broker code
            standard_symbol: Standard EXCHANGE:SYMBOL format
            
        Returns:
            Tuple of (broker_symbol, exchange)
        """
        # Parse standard symbol
        if ":" in standard_symbol:
            exchange, symbol = standard_symbol.split(":", 1)
        else:
            exchange, symbol = "NSE", standard_symbol
        
        # Apply broker-specific conversion rules
        if broker == "zerodha":
            return self._convert_to_zerodha_format(symbol, exchange)
        elif broker == "angel_one":
            return self._convert_to_angel_one_format(symbol, exchange)
        elif broker == "dhan":
            return self._convert_to_dhan_format(symbol, exchange)
        elif broker == "upstox":
            return self._convert_to_upstox_format(symbol, exchange)
        elif broker == "icici_direct":
            return self._convert_to_icici_format(symbol, exchange)
        
        return symbol, exchange
    
    # Broker-specific conversion methods
    def _convert_zerodha_to_standard(
        self,
        symbol: str,
        exchange: Optional[str]
    ) -> str:
        """Convert Zerodha symbol to standard format."""
        # Zerodha format: SYMBOL (exchange implied or separate)
        # For F&O: SYMBOLYYMDD (e.g., NIFTY24JANFUT)
        exchange = exchange or "NSE"
        return f"{exchange}:{symbol}"
    
    def _convert_angel_one_to_standard(
        self,
        symbol: str,
        exchange: Optional[str]
    ) -> str:
        """Convert Angel One symbol to standard format."""
        # Angel One uses similar format to standard
        exchange = exchange or "NSE"
        return f"{exchange}:{symbol}"
    
    def _convert_dhan_to_standard(
        self,
        symbol: str,
        exchange: Optional[str]
    ) -> str:
        """Convert Dhan symbol to standard format."""
        exchange = exchange or "NSE"
        return f"{exchange}:{symbol}"
    
    def _convert_upstox_to_standard(
        self,
        symbol: str,
        exchange: Optional[str]
    ) -> str:
        """Convert Upstox symbol to standard format."""
        exchange = exchange or "NSE"
        return f"{exchange}:{symbol}"
    
    def _convert_icici_to_standard(
        self,
        symbol: str,
        exchange: Optional[str]
    ) -> str:
        """Convert ICICI Direct symbol to standard format."""
        exchange = exchange or "NSE"
        return f"{exchange}:{symbol}"
    
    def _convert_to_zerodha_format(
        self,
        symbol: str,
        exchange: str
    ) -> Tuple[str, str]:
        """Convert to Zerodha format."""
        return symbol, exchange
    
    def _convert_to_angel_one_format(
        self,
        symbol: str,
        exchange: str
    ) -> Tuple[str, str]:
        """Convert to Angel One format."""
        return symbol, exchange
    
    def _convert_to_dhan_format(
        self,
        symbol: str,
        exchange: str
    ) -> Tuple[str, str]:
        """Convert to Dhan format."""
        return symbol, exchange
    
    def _convert_to_upstox_format(
        self,
        symbol: str,
        exchange: str
    ) -> Tuple[str, str]:
        """Convert to Upstox format."""
        return symbol, exchange
    
    def _convert_to_icici_format(
        self,
        symbol: str,
        exchange: str
    ) -> Tuple[str, str]:
        """Convert to ICICI Direct format."""
        return symbol, exchange
    
    def invalidate_cache(self, broker: Optional[str] = None):
        """
        Invalidate symbol mapping cache.
        
        Args:
            broker: Specific broker to invalidate, or None for all
        """
        # Clear local cache
        if broker:
            if broker in self._local_cache:
                del self._local_cache[broker]
        else:
            self._local_cache.clear()
        
        # Clear Redis cache
        if self.redis:
            if broker:
                pattern = f"{self.CACHE_PREFIX}{broker}:*"
                keys = self.redis.scan_iter(match=pattern)
                for key in keys:
                    self.redis.delete(key)
            else:
                pattern = f"{self.CACHE_PREFIX}*"
                keys = self.redis.scan_iter(match=pattern)
                for key in keys:
                    self.redis.delete(key)
        
        logger.info(f"Invalidated symbol cache for {broker or 'all brokers'}")
