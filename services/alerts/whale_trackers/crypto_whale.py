"""
Crypto Whale Tracker

Tracks large institutional movements in cryptocurrency markets:
- Exchange netflow >= 500 BTC (inflow/outflow from exchanges)
- Whale wallet transfers >= 100 BTC
- AI-generated interpretation using Claude Haiku

Requirements: 12.1, 12.3

Data Sources:
- Glassnode API (free tier endpoints):
  - GET /v1/metrics/transactions/transfers_volume_to_exchanges_sum
  - GET /v1/metrics/transactions/transfers_volume_from_exchanges_sum
  - GET /v1/metrics/transactions/count_above_value_usd_sum

Polling Schedule:
- Every 15 minutes for BTC and ETH (free tier rate limits: 10 API calls/hour per endpoint)
- Cache responses in Redis for 15 minutes

AI Interpretation:
- Uses Claude Haiku to generate contextual interpretation
- "Potential sell pressure signal" for large exchange inflows
- "Accumulation detected" for large exchange outflows
"""

import asyncio
import uuid
import os
from datetime import datetime, time, timedelta
from typing import List, Optional, Dict, Any
from decimal import Decimal
import logging

import httpx
from shared.database.models import AnomalyEvent, AnomalyType, AnomalySeverity

logger = logging.getLogger(__name__)


class CryptoWhaleTracker:
    """
    Tracks large institutional movements in cryptocurrency markets.
    
    Monitors:
    - Exchange netflow >= 500 BTC (inflow to exchanges = potential sell pressure)
    - Exchange netflow >= 500 BTC (outflow from exchanges = accumulation)
    - Whale transfers >= 100 BTC
    
    Generates AnomalyEvent for each qualifying movement with AI interpretation.
    """
    
    # Thresholds
    NETFLOW_THRESHOLD_BTC = 500.0  # BTC
    WHALE_TRANSFER_THRESHOLD_BTC = 100.0  # BTC
    
    # Polling interval
    POLL_INTERVAL_SECONDS = 900  # 15 minutes
    
    # Glassnode API rate limits (free tier)
    # 10 API calls per hour per endpoint
    # With 3 endpoints and 2 assets (BTC, ETH), that's 6 calls per poll
    # At 15-minute intervals (4 polls/hour), we're at 24 calls/hour
    # This exceeds the limit, so we need caching
    CACHE_TTL_SECONDS = 900  # 15 minutes
    
    # Redis key prefix for caching
    REDIS_CACHE_PREFIX = "crypto_whale:glassnode:"
    
    # Supported cryptocurrencies
    SUPPORTED_ASSETS = ["BTC", "ETH"]
    
    def __init__(
        self,
        glassnode_api_key: Optional[str] = None,
        anthropic_api_key: Optional[str] = None,
        glassnode_api_base_url: str = "https://api.glassnode.com",
        redis_client: Optional[Any] = None,
        timeout_seconds: int = 30
    ):
        """
        Initialize the Crypto Whale Tracker.
        
        Args:
            glassnode_api_key: Glassnode API key (free tier)
            anthropic_api_key: Anthropic API key for Claude Haiku
            glassnode_api_base_url: Base URL for Glassnode API
            redis_client: Redis client for caching API responses
            timeout_seconds: HTTP request timeout
        """
        self.glassnode_api_key = glassnode_api_key or os.getenv("GLASSNODE_API_KEY")
        self.anthropic_api_key = anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")
        self.glassnode_api_base_url = glassnode_api_base_url
        self.redis_client = redis_client
        self.timeout_seconds = timeout_seconds
        
        # In-memory cache fallback if Redis is not available
        self._cache: Dict[str, tuple[Any, datetime]] = {}
        
        if not self.glassnode_api_key:
            logger.warning("GLASSNODE_API_KEY not set - crypto whale tracker will not function")
        
        if not self.anthropic_api_key:
            logger.warning("ANTHROPIC_API_KEY not set - AI interpretation will be disabled")
    
    async def _get_cached_data(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """
        Get cached data from Redis or in-memory cache.
        
        Args:
            cache_key: Cache key
        
        Returns:
            Cached data or None if not found or expired
        """
        # Try Redis first
        if self.redis_client:
            try:
                import json
                redis_key = f"{self.REDIS_CACHE_PREFIX}{cache_key}"
                cached = await self.redis_client.get(redis_key)
                if cached:
                    return json.loads(cached)
            except Exception as e:
                logger.error(f"Error fetching from Redis cache: {e}")
        
        # Fallback to in-memory cache
        if cache_key in self._cache:
            data, timestamp = self._cache[cache_key]
            if datetime.utcnow() - timestamp < timedelta(seconds=self.CACHE_TTL_SECONDS):
                return data
            else:
                # Expired, remove from cache
                del self._cache[cache_key]
        
        return None
    
    async def _set_cached_data(self, cache_key: str, data: Dict[str, Any]):
        """
        Store data in Redis or in-memory cache.
        
        Args:
            cache_key: Cache key
            data: Data to cache
        """
        # Store in Redis
        if self.redis_client:
            try:
                import json
                redis_key = f"{self.REDIS_CACHE_PREFIX}{cache_key}"
                await self.redis_client.setex(
                    redis_key,
                    self.CACHE_TTL_SECONDS,
                    json.dumps(data)
                )
            except Exception as e:
                logger.error(f"Error storing in Redis cache: {e}")
        
        # Always store in in-memory cache as fallback
        self._cache[cache_key] = (data, datetime.utcnow())
    
    async def fetch_exchange_inflow(self, asset: str = "BTC") -> Optional[Dict[str, Any]]:
        """
        Fetch exchange inflow data from Glassnode API.
        
        This metric shows the total volume of coins transferred TO exchanges.
        High inflow typically indicates potential sell pressure.
        
        Args:
            asset: Cryptocurrency asset (BTC or ETH)
        
        Returns:
            Exchange inflow data or None if fetch fails
        """
        if not self.glassnode_api_key:
            logger.error("Glassnode API key not configured")
            return None
        
        # Check cache first
        cache_key = f"inflow_{asset}"
        cached = await self._get_cached_data(cache_key)
        if cached:
            logger.debug(f"Using cached exchange inflow data for {asset}")
            return cached
        
        # Fetch from API
        url = f"{self.glassnode_api_base_url}/v1/metrics/transactions/transfers_volume_to_exchanges_sum"
        
        params = {
            "a": asset,
            "api_key": self.glassnode_api_key,
            "i": "24h",  # 24-hour aggregation
            "c": "native"  # Native units (BTC, ETH)
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()
                
                # Glassnode returns array of [{t: timestamp, v: value}]
                # We want the most recent value
                if isinstance(data, list) and len(data) > 0:
                    latest = data[-1]
                    result = {
                        "timestamp": latest.get("t"),
                        "value_btc": float(latest.get("v", 0)),
                        "asset": asset,
                        "metric": "exchange_inflow"
                    }
                    
                    # Cache the result
                    await self._set_cached_data(cache_key, result)
                    
                    return result
                else:
                    logger.warning(f"Unexpected Glassnode inflow response format: {type(data)}")
                    return None
                    
        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch Glassnode exchange inflow for {asset}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching exchange inflow for {asset}: {e}")
            return None
    
    async def fetch_exchange_outflow(self, asset: str = "BTC") -> Optional[Dict[str, Any]]:
        """
        Fetch exchange outflow data from Glassnode API.
        
        This metric shows the total volume of coins transferred FROM exchanges.
        High outflow typically indicates accumulation (coins moving to cold storage).
        
        Args:
            asset: Cryptocurrency asset (BTC or ETH)
        
        Returns:
            Exchange outflow data or None if fetch fails
        """
        if not self.glassnode_api_key:
            logger.error("Glassnode API key not configured")
            return None
        
        # Check cache first
        cache_key = f"outflow_{asset}"
        cached = await self._get_cached_data(cache_key)
        if cached:
            logger.debug(f"Using cached exchange outflow data for {asset}")
            return cached
        
        # Fetch from API
        url = f"{self.glassnode_api_base_url}/v1/metrics/transactions/transfers_volume_from_exchanges_sum"
        
        params = {
            "a": asset,
            "api_key": self.glassnode_api_key,
            "i": "24h",  # 24-hour aggregation
            "c": "native"  # Native units (BTC, ETH)
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()
                
                # Glassnode returns array of [{t: timestamp, v: value}]
                if isinstance(data, list) and len(data) > 0:
                    latest = data[-1]
                    result = {
                        "timestamp": latest.get("t"),
                        "value_btc": float(latest.get("v", 0)),
                        "asset": asset,
                        "metric": "exchange_outflow"
                    }
                    
                    # Cache the result
                    await self._set_cached_data(cache_key, result)
                    
                    return result
                else:
                    logger.warning(f"Unexpected Glassnode outflow response format: {type(data)}")
                    return None
                    
        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch Glassnode exchange outflow for {asset}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching exchange outflow for {asset}: {e}")
            return None
    
    async def fetch_large_transactions(self, asset: str = "BTC") -> Optional[Dict[str, Any]]:
        """
        Fetch large transaction count from Glassnode API.
        
        This metric shows the count of transactions above a certain USD value threshold.
        High count indicates whale activity.
        
        Args:
            asset: Cryptocurrency asset (BTC or ETH)
        
        Returns:
            Large transaction data or None if fetch fails
        """
        if not self.glassnode_api_key:
            logger.error("Glassnode API key not configured")
            return None
        
        # Check cache first
        cache_key = f"large_txns_{asset}"
        cached = await self._get_cached_data(cache_key)
        if cached:
            logger.debug(f"Using cached large transactions data for {asset}")
            return cached
        
        # Fetch from API
        url = f"{self.glassnode_api_base_url}/v1/metrics/transactions/count_above_value_usd_sum"
        
        params = {
            "a": asset,
            "api_key": self.glassnode_api_key,
            "i": "24h",  # 24-hour aggregation
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()
                
                # Glassnode returns array of [{t: timestamp, v: value}]
                if isinstance(data, list) and len(data) > 0:
                    latest = data[-1]
                    result = {
                        "timestamp": latest.get("t"),
                        "count": int(latest.get("v", 0)),
                        "asset": asset,
                        "metric": "large_transactions"
                    }
                    
                    # Cache the result
                    await self._set_cached_data(cache_key, result)
                    
                    return result
                else:
                    logger.warning(f"Unexpected Glassnode large txns response format: {type(data)}")
                    return None
                    
        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch Glassnode large transactions for {asset}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching large transactions for {asset}: {e}")
            return None
    
    async def generate_ai_interpretation(
        self,
        asset: str,
        netflow_btc: float,
        direction: str,
        large_txn_count: Optional[int] = None
    ) -> str:
        """
        Generate AI interpretation using Claude Haiku.
        
        Args:
            asset: Cryptocurrency asset
            netflow_btc: Net flow in BTC (positive = inflow, negative = outflow)
            direction: "inflow" or "outflow"
            large_txn_count: Count of large transactions (optional)
        
        Returns:
            AI-generated interpretation string
        """
        if not self.anthropic_api_key:
            # Fallback to simple interpretation if AI is not available
            if direction == "inflow":
                return "Potential sell pressure signal"
            else:
                return "Accumulation detected"
        
        try:
            import anthropic
            
            client = anthropic.Anthropic(api_key=self.anthropic_api_key)
            
            # Build context
            context = f"""
You are a crypto market analyst. Analyze this whale movement data and provide a brief interpretation (max 2 sentences).

Asset: {asset}
Exchange {direction}: {abs(netflow_btc):.2f} {asset}
"""
            
            if large_txn_count is not None:
                context += f"Large transactions (24h): {large_txn_count}\n"
            
            context += f"""
Direction: {"Coins moving TO exchanges" if direction == "inflow" else "Coins moving FROM exchanges"}

Provide a concise interpretation focusing on:
1. What this movement likely indicates (sell pressure vs accumulation)
2. Potential market impact

Keep it under 2 sentences and actionable.
"""
            
            # Call Claude Haiku (fast and cheap)
            message = client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=150,
                messages=[
                    {"role": "user", "content": context}
                ]
            )
            
            interpretation = message.content[0].text.strip()
            logger.info(f"Generated AI interpretation for {asset} {direction}: {interpretation}")
            
            return interpretation
            
        except Exception as e:
            logger.error(f"Error generating AI interpretation: {e}")
            # Fallback to simple interpretation
            if direction == "inflow":
                return "Potential sell pressure signal"
            else:
                return "Accumulation detected"
    
    async def detect_netflow_anomaly(
        self,
        asset: str,
        inflow_data: Optional[Dict[str, Any]],
        outflow_data: Optional[Dict[str, Any]],
        large_txn_data: Optional[Dict[str, Any]]
    ) -> List[AnomalyEvent]:
        """
        Detect exchange netflow anomalies.
        
        Args:
            asset: Cryptocurrency asset
            inflow_data: Exchange inflow data
            outflow_data: Exchange outflow data
            large_txn_data: Large transaction data
        
        Returns:
            List of AnomalyEvents for qualifying netflow
        """
        events = []
        
        if not inflow_data or not outflow_data:
            return events
        
        try:
            inflow_btc = inflow_data.get("value_btc", 0)
            outflow_btc = outflow_data.get("value_btc", 0)
            netflow_btc = inflow_btc - outflow_btc  # Positive = net inflow (bearish)
            
            large_txn_count = large_txn_data.get("count") if large_txn_data else None
            
            # Check if netflow exceeds threshold
            if abs(netflow_btc) >= self.NETFLOW_THRESHOLD_BTC:
                direction = "inflow" if netflow_btc > 0 else "outflow"
                
                # Determine severity based on magnitude
                abs_netflow = abs(netflow_btc)
                if abs_netflow >= 1500:
                    severity = AnomalySeverity.CRITICAL
                elif abs_netflow >= 1000:
                    severity = AnomalySeverity.HIGH
                elif abs_netflow >= 500:
                    severity = AnomalySeverity.CRITICAL  # 500+ BTC is CRITICAL per requirements
                else:
                    severity = AnomalySeverity.MEDIUM
                
                # Generate AI interpretation
                ai_interpretation = await self.generate_ai_interpretation(
                    asset, netflow_btc, direction, large_txn_count
                )
                
                # Generate description
                description = (
                    f"Large exchange {direction} detected for {asset}: "
                    f"{abs(netflow_btc):.2f} {asset} net {direction} "
                    f"(Inflow: {inflow_btc:.2f}, Outflow: {outflow_btc:.2f}). "
                    f"{ai_interpretation}"
                )
                
                # Create anomaly event
                event = AnomalyEvent(
                    id=uuid.uuid4(),
                    instrument=f"{asset}/USD",
                    asset_class="crypto",
                    exchange="AGGREGATE",  # Aggregated across all exchanges
                    anomaly_type=AnomalyType.WHALE_MOVEMENT,
                    severity=severity,
                    detected_at=datetime.utcnow(),
                    description=description,
                    z_score=None,
                    price=None,
                    volume=abs(netflow_btc),
                    affected_instruments=None,
                    raw_data={
                        "detection_type": "exchange_netflow",
                        "asset": asset,
                        "inflow_btc": inflow_btc,
                        "outflow_btc": outflow_btc,
                        "netflow_btc": netflow_btc,
                        "direction": direction,
                        "large_txn_count": large_txn_count,
                        "ai_interpretation": ai_interpretation,
                        "threshold_btc": self.NETFLOW_THRESHOLD_BTC,
                        "inflow_timestamp": inflow_data.get("timestamp"),
                        "outflow_timestamp": outflow_data.get("timestamp")
                    }
                )
                
                events.append(event)
                logger.info(f"Generated crypto whale netflow event: {description}")
            
            return events
            
        except Exception as e:
            logger.error(f"Error detecting netflow anomaly for {asset}: {e}")
            return events
    
    async def detect_whale_transfers(
        self,
        asset: str,
        large_txn_data: Optional[Dict[str, Any]]
    ) -> List[AnomalyEvent]:
        """
        Detect whale wallet transfers based on large transaction count.
        
        Note: The free tier Glassnode API provides transaction count, not individual
        transaction details. We use the count as a proxy for whale activity.
        
        Args:
            asset: Cryptocurrency asset
            large_txn_data: Large transaction data
        
        Returns:
            List of AnomalyEvents for whale transfers
        """
        events = []
        
        if not large_txn_data:
            return events
        
        try:
            txn_count = large_txn_data.get("count", 0)
            
            # Threshold: if there are more than 50 large transactions in 24h,
            # it indicates significant whale activity
            WHALE_TXN_COUNT_THRESHOLD = 50
            
            if txn_count >= WHALE_TXN_COUNT_THRESHOLD:
                # Determine severity
                if txn_count >= 200:
                    severity = AnomalySeverity.CRITICAL
                elif txn_count >= 100:
                    severity = AnomalySeverity.HIGH
                else:
                    severity = AnomalySeverity.MEDIUM
                
                # Generate AI interpretation
                ai_interpretation = await self.generate_ai_interpretation(
                    asset, 0, "transfer", txn_count
                )
                
                # Generate description
                description = (
                    f"High whale activity detected for {asset}: "
                    f"{txn_count} large transactions (>$100k) in 24h. "
                    f"{ai_interpretation}"
                )
                
                # Create anomaly event
                event = AnomalyEvent(
                    id=uuid.uuid4(),
                    instrument=f"{asset}/USD",
                    asset_class="crypto",
                    exchange="BLOCKCHAIN",
                    anomaly_type=AnomalyType.WHALE_MOVEMENT,
                    severity=severity,
                    detected_at=datetime.utcnow(),
                    description=description,
                    z_score=None,
                    price=None,
                    volume=None,
                    affected_instruments=None,
                    raw_data={
                        "detection_type": "whale_transfers",
                        "asset": asset,
                        "large_txn_count": txn_count,
                        "threshold_count": WHALE_TXN_COUNT_THRESHOLD,
                        "ai_interpretation": ai_interpretation,
                        "timestamp": large_txn_data.get("timestamp")
                    }
                )
                
                events.append(event)
                logger.info(f"Generated crypto whale transfer event: {description}")
            
            return events
            
        except Exception as e:
            logger.error(f"Error detecting whale transfers for {asset}: {e}")
            return events
    
    async def poll_crypto_whale_activity(
        self,
        assets: List[str] = None
    ) -> List[AnomalyEvent]:
        """
        Poll crypto whale activity for specified assets.
        
        Args:
            assets: List of assets to monitor (defaults to BTC and ETH)
        
        Returns:
            List of AnomalyEvents for detected whale activity
        """
        if assets is None:
            assets = self.SUPPORTED_ASSETS
        
        all_events = []
        
        for asset in assets:
            try:
                # Fetch all data concurrently
                inflow_data, outflow_data, large_txn_data = await asyncio.gather(
                    self.fetch_exchange_inflow(asset),
                    self.fetch_exchange_outflow(asset),
                    self.fetch_large_transactions(asset),
                    return_exceptions=True
                )
                
                # Handle exceptions
                if isinstance(inflow_data, Exception):
                    logger.error(f"Error fetching inflow for {asset}: {inflow_data}")
                    inflow_data = None
                
                if isinstance(outflow_data, Exception):
                    logger.error(f"Error fetching outflow for {asset}: {outflow_data}")
                    outflow_data = None
                
                if isinstance(large_txn_data, Exception):
                    logger.error(f"Error fetching large txns for {asset}: {large_txn_data}")
                    large_txn_data = None
                
                # Detect netflow anomalies
                netflow_events = await self.detect_netflow_anomaly(
                    asset, inflow_data, outflow_data, large_txn_data
                )
                all_events.extend(netflow_events)
                
                # Detect whale transfers
                whale_events = await self.detect_whale_transfers(asset, large_txn_data)
                all_events.extend(whale_events)
                
                logger.info(f"Analyzed {asset}: found {len(netflow_events) + len(whale_events)} events")
                
            except Exception as e:
                logger.error(f"Error polling crypto whale activity for {asset}: {e}")
        
        return all_events
    
    async def run_continuous_polling(
        self,
        assets: List[str] = None,
        stop_event: Optional[asyncio.Event] = None
    ):
        """
        Run continuous polling for crypto whale activity.
        
        This method runs indefinitely, polling Glassnode API every 15 minutes
        for BTC and ETH whale activity.
        
        Args:
            assets: List of assets to monitor (defaults to BTC and ETH)
            stop_event: Optional asyncio.Event to signal when to stop polling
        """
        logger.info("Starting Crypto Whale Tracker continuous polling")
        
        if assets is None:
            assets = self.SUPPORTED_ASSETS
        
        while True:
            if stop_event and stop_event.is_set():
                logger.info("Stop event received, ending polling")
                break
            
            logger.info(f"Polling crypto whale activity for {', '.join(assets)}")
            
            try:
                events = await self.poll_crypto_whale_activity(assets)
                logger.info(f"Found {len(events)} crypto whale movement events")
                
                # Events would be published to Redis pub/sub or stored in DB here
                # This is handled by the anomaly orchestrator in production
                
            except Exception as e:
                logger.error(f"Error during crypto whale polling: {e}")
            
            # Wait for next poll interval (15 minutes)
            await asyncio.sleep(self.POLL_INTERVAL_SECONDS)
