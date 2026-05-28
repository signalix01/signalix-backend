"""
US Equity Whale Tracker

Tracks large institutional movements in US equity markets:
- Dark pool prints >= $10M
- Unusual options sweeps >= $1M notional

Requirements: 12.1

Data Sources:
- Unusual Whales API (if available): Dark pool prints, options flow
- Polygon.io block trades endpoint (fallback): Large block trades

Polling Schedule:
- Every 5 minutes during US market hours (09:30 - 16:00 ET)

Detection Thresholds:
- Dark pool prints: >= $10M
- Options sweeps: >= $1M notional value
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


class USEquityWhaleTracker:
    """
    Tracks large institutional movements in US equity markets.
    
    Monitors:
    - Dark pool prints >= $10M
    - Unusual options sweeps >= $1M notional
    
    Generates AnomalyEvent for each qualifying trade.
    """
    
    # Thresholds in USD
    DARK_POOL_THRESHOLD_USD = 10_000_000  # $10M
    OPTIONS_SWEEP_THRESHOLD_USD = 1_000_000  # $1M
    
    # Market hours (ET - Eastern Time)
    MARKET_OPEN = time(9, 30)
    MARKET_CLOSE = time(16, 0)
    
    # Polling interval
    POLL_INTERVAL_SECONDS = 300  # 5 minutes
    
    # API endpoints
    UNUSUAL_WHALES_BASE_URL = "https://api.unusualwhales.com"
    POLYGON_BASE_URL = "https://api.polygon.io"
    
    def __init__(
        self,
        unusual_whales_api_key: Optional[str] = None,
        polygon_api_key: Optional[str] = None,
        timeout_seconds: int = 30
    ):
        """
        Initialize the US Equity Whale Tracker.
        
        Args:
            unusual_whales_api_key: Unusual Whales API key (preferred)
            polygon_api_key: Polygon.io API key (fallback)
            timeout_seconds: HTTP request timeout
        """
        self.unusual_whales_api_key = unusual_whales_api_key or os.getenv("UNUSUAL_WHALES_API_KEY")
        self.polygon_api_key = polygon_api_key or os.getenv("POLYGON_API_KEY")
        self.timeout_seconds = timeout_seconds
        
        # Track last processed trades to avoid duplicates
        self._processed_dark_pool_trades: set = set()
        self._processed_options_sweeps: set = set()
        
        # Determine which API to use
        self.use_unusual_whales = bool(self.unusual_whales_api_key)
        self.use_polygon = bool(self.polygon_api_key)
        
        if not self.use_unusual_whales and not self.use_polygon:
            logger.warning(
                "Neither UNUSUAL_WHALES_API_KEY nor POLYGON_API_KEY is set - "
                "US equity whale tracker will not function"
            )
        elif self.use_unusual_whales:
            logger.info("Using Unusual Whales API for US equity whale tracking")
        else:
            logger.info("Using Polygon.io API for US equity whale tracking")
    
    async def fetch_unusual_whales_dark_pool(self) -> List[Dict[str, Any]]:
        """
        Fetch dark pool prints from Unusual Whales API.
        
        Returns:
            List of dark pool trade dictionaries
        """
        if not self.unusual_whales_api_key:
            return []
        
        url = f"{self.UNUSUAL_WHALES_BASE_URL}/api/darkpool"
        
        headers = {
            "Authorization": f"Bearer {self.unusual_whales_api_key}",
            "Accept": "application/json"
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()
                
                # Expected format: {"data": [{"ticker": "...", "size": ..., "price": ..., ...}]}
                if isinstance(data, dict) and "data" in data:
                    return data["data"]
                elif isinstance(data, list):
                    return data
                else:
                    logger.warning(f"Unexpected Unusual Whales dark pool response format: {type(data)}")
                    return []
                    
        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch Unusual Whales dark pool data: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching Unusual Whales dark pool data: {e}")
            return []
    
    async def fetch_unusual_whales_options_flow(self) -> List[Dict[str, Any]]:
        """
        Fetch unusual options flow from Unusual Whales API.
        
        Returns:
            List of options sweep dictionaries
        """
        if not self.unusual_whales_api_key:
            return []
        
        url = f"{self.UNUSUAL_WHALES_BASE_URL}/api/options-flow"
        
        headers = {
            "Authorization": f"Bearer {self.unusual_whales_api_key}",
            "Accept": "application/json"
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()
                
                if isinstance(data, dict) and "data" in data:
                    return data["data"]
                elif isinstance(data, list):
                    return data
                else:
                    logger.warning(f"Unexpected Unusual Whales options flow response format: {type(data)}")
                    return []
                    
        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch Unusual Whales options flow: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching Unusual Whales options flow: {e}")
            return []
    
    async def fetch_polygon_block_trades(self) -> List[Dict[str, Any]]:
        """
        Fetch block trades from Polygon.io API.
        
        Returns:
            List of block trade dictionaries
        """
        if not self.polygon_api_key:
            return []
        
        # Get today's date for the query
        today = datetime.utcnow().strftime("%Y-%m-%d")
        
        # Polygon.io trades endpoint
        # Note: This is a simplified example - actual endpoint may vary
        url = f"{self.POLYGON_BASE_URL}/v3/trades"
        
        params = {
            "apiKey": self.polygon_api_key,
            "timestamp.gte": today,
            "limit": 100,
            "order": "desc"
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()
                
                # Expected format: {"results": [{"ticker": "...", "size": ..., "price": ..., ...}]}
                if isinstance(data, dict) and "results" in data:
                    return data["results"]
                elif isinstance(data, list):
                    return data
                else:
                    logger.warning(f"Unexpected Polygon.io response format: {type(data)}")
                    return []
                    
        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch Polygon.io block trades: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching Polygon.io block trades: {e}")
            return []
    
    def _calculate_trade_value_usd(self, size: float, price: float) -> float:
        """
        Calculate trade value in USD.
        
        Args:
            size: Number of shares/contracts
            price: Price per share/contract
        
        Returns:
            Trade value in USD
        """
        return size * price
    
    def _generate_dark_pool_event(
        self,
        trade: Dict[str, Any],
        source: str = "unusual_whales"
    ) -> Optional[AnomalyEvent]:
        """
        Generate an AnomalyEvent for a qualifying dark pool print.
        
        Args:
            trade: Dark pool trade data dictionary
            source: Data source ("unusual_whales" or "polygon")
        
        Returns:
            AnomalyEvent if trade qualifies, None otherwise
        """
        try:
            # Extract trade details (field names may vary by API)
            ticker = trade.get("ticker") or trade.get("symbol") or trade.get("T")
            size = float(trade.get("size") or trade.get("volume") or trade.get("s") or 0)
            price = float(trade.get("price") or trade.get("p") or 0)
            timestamp = trade.get("timestamp") or trade.get("t") or trade.get("time")
            venue = trade.get("venue") or trade.get("exchange") or "DARK_POOL"
            
            if not ticker or size == 0 or price == 0:
                logger.warning(f"Incomplete dark pool trade data: {trade}")
                return None
            
            # Calculate trade value
            value_usd = self._calculate_trade_value_usd(size, price)
            
            # Check threshold
            if value_usd < self.DARK_POOL_THRESHOLD_USD:
                return None
            
            # Generate unique trade ID for deduplication
            trade_id = f"darkpool_{ticker}_{size}_{price}_{timestamp}"
            
            if trade_id in self._processed_dark_pool_trades:
                return None
            
            self._processed_dark_pool_trades.add(trade_id)
            
            # Determine severity based on trade size
            if value_usd >= 100_000_000:  # $100M+
                severity = AnomalySeverity.CRITICAL
            elif value_usd >= 50_000_000:  # $50M+
                severity = AnomalySeverity.HIGH
            else:  # $10M+
                severity = AnomalySeverity.MEDIUM
            
            # Generate description
            description = (
                f"Large dark pool print detected: {ticker} - "
                f"{size:,.0f} shares at ${price:.2f} "
                f"(total value: ${value_usd:,.0f}) on {venue}"
            )
            
            # Create anomaly event
            event = AnomalyEvent(
                id=uuid.uuid4(),
                instrument=ticker,
                asset_class="us_equity",
                exchange=venue,
                anomaly_type=AnomalyType.WHALE_MOVEMENT,
                severity=severity,
                detected_at=datetime.utcnow(),
                description=description,
                z_score=None,
                price=price,
                volume=size,
                affected_instruments=None,
                raw_data={
                    "trade_type": "dark_pool",
                    "source": source,
                    "ticker": ticker,
                    "size": size,
                    "price": price,
                    "value_usd": value_usd,
                    "venue": venue,
                    "timestamp": timestamp,
                    "threshold_usd": self.DARK_POOL_THRESHOLD_USD,
                    "trade_id": trade_id,
                    "original_data": trade
                }
            )
            
            logger.info(f"Generated dark pool whale event: {description}")
            return event
            
        except Exception as e:
            logger.error(f"Error generating dark pool event: {e}, trade: {trade}")
            return None
    
    def _generate_options_sweep_event(
        self,
        sweep: Dict[str, Any]
    ) -> Optional[AnomalyEvent]:
        """
        Generate an AnomalyEvent for a qualifying options sweep.
        
        Args:
            sweep: Options sweep data dictionary
        
        Returns:
            AnomalyEvent if sweep qualifies, None otherwise
        """
        try:
            # Extract sweep details
            ticker = sweep.get("ticker") or sweep.get("symbol")
            contracts = float(sweep.get("contracts") or sweep.get("size") or 0)
            premium = float(sweep.get("premium") or sweep.get("notional") or 0)
            strike = float(sweep.get("strike") or 0)
            expiry = sweep.get("expiry") or sweep.get("expiration")
            option_type = sweep.get("type") or sweep.get("put_call") or "CALL"
            sentiment = sweep.get("sentiment") or "BULLISH"
            timestamp = sweep.get("timestamp") or sweep.get("time")
            
            if not ticker or contracts == 0 or premium == 0:
                logger.warning(f"Incomplete options sweep data: {sweep}")
                return None
            
            # Check threshold
            if premium < self.OPTIONS_SWEEP_THRESHOLD_USD:
                return None
            
            # Generate unique sweep ID for deduplication
            sweep_id = f"options_{ticker}_{contracts}_{premium}_{strike}_{timestamp}"
            
            if sweep_id in self._processed_options_sweeps:
                return None
            
            self._processed_options_sweeps.add(sweep_id)
            
            # Determine severity based on premium size
            if premium >= 10_000_000:  # $10M+
                severity = AnomalySeverity.CRITICAL
            elif premium >= 5_000_000:  # $5M+
                severity = AnomalySeverity.HIGH
            else:  # $1M+
                severity = AnomalySeverity.MEDIUM
            
            # Generate description
            description = (
                f"Unusual options sweep detected: {ticker} - "
                f"{contracts:,.0f} {option_type} contracts at ${strike:.2f} strike "
                f"(premium: ${premium:,.0f}, expiry: {expiry}). "
                f"Sentiment: {sentiment}"
            )
            
            # Create anomaly event
            event = AnomalyEvent(
                id=uuid.uuid4(),
                instrument=ticker,
                asset_class="us_equity",
                exchange="OPTIONS",
                anomaly_type=AnomalyType.OPTIONS_UNUSUAL,
                severity=severity,
                detected_at=datetime.utcnow(),
                description=description,
                z_score=None,
                price=strike,
                volume=contracts,
                affected_instruments=None,
                raw_data={
                    "trade_type": "options_sweep",
                    "source": "unusual_whales",
                    "ticker": ticker,
                    "contracts": contracts,
                    "premium": premium,
                    "strike": strike,
                    "expiry": expiry,
                    "option_type": option_type,
                    "sentiment": sentiment,
                    "timestamp": timestamp,
                    "threshold_usd": self.OPTIONS_SWEEP_THRESHOLD_USD,
                    "sweep_id": sweep_id,
                    "original_data": sweep
                }
            )
            
            logger.info(f"Generated options sweep whale event: {description}")
            return event
            
        except Exception as e:
            logger.error(f"Error generating options sweep event: {e}, sweep: {sweep}")
            return None
    
    async def poll_dark_pool_prints(self) -> List[AnomalyEvent]:
        """
        Poll for dark pool prints and generate events for qualifying trades.
        
        Returns:
            List of AnomalyEvents for qualifying dark pool prints
        """
        events = []
        
        # Try Unusual Whales first
        if self.use_unusual_whales:
            trades = await self.fetch_unusual_whales_dark_pool()
            source = "unusual_whales"
        # Fallback to Polygon.io
        elif self.use_polygon:
            trades = await self.fetch_polygon_block_trades()
            source = "polygon"
        else:
            return events
        
        for trade in trades:
            event = self._generate_dark_pool_event(trade, source=source)
            if event:
                events.append(event)
        
        return events
    
    async def poll_options_sweeps(self) -> List[AnomalyEvent]:
        """
        Poll for unusual options sweeps and generate events for qualifying sweeps.
        
        Returns:
            List of AnomalyEvents for qualifying options sweeps
        """
        events = []
        
        # Only available via Unusual Whales
        if not self.use_unusual_whales:
            return events
        
        sweeps = await self.fetch_unusual_whales_options_flow()
        
        for sweep in sweeps:
            event = self._generate_options_sweep_event(sweep)
            if event:
                events.append(event)
        
        return events
    
    def is_market_hours(self, current_time: Optional[datetime] = None) -> bool:
        """
        Check if current time is within US market hours (09:30 - 16:00 ET).
        
        Note: This is a simplified check. In production, you should use
        pytz to properly handle ET timezone and daylight saving time.
        
        Args:
            current_time: Time to check (defaults to now)
        
        Returns:
            True if within market hours, False otherwise
        """
        if current_time is None:
            current_time = datetime.now()
        
        current_time_only = current_time.time()
        
        # Check if it's a weekday (Monday=0, Sunday=6)
        if current_time.weekday() >= 5:  # Saturday or Sunday
            return False
        
        return self.MARKET_OPEN <= current_time_only <= self.MARKET_CLOSE
    
    async def run_continuous_polling(self, stop_event: Optional[asyncio.Event] = None):
        """
        Run continuous polling for US equity whale activity.
        
        This method runs indefinitely, polling for dark pool prints and
        options sweeps every 5 minutes during US market hours.
        
        Args:
            stop_event: Optional asyncio.Event to signal when to stop polling
        """
        logger.info("Starting US Equity Whale Tracker continuous polling")
        
        while True:
            if stop_event and stop_event.is_set():
                logger.info("Stop event received, ending polling")
                break
            
            current_time = datetime.now()
            
            # Poll during market hours
            if self.is_market_hours(current_time):
                logger.info("US market hours - polling dark pool prints and options sweeps")
                
                try:
                    # Poll dark pool and options concurrently
                    dark_pool_events, options_events = await asyncio.gather(
                        self.poll_dark_pool_prints(),
                        self.poll_options_sweeps(),
                        return_exceptions=True
                    )
                    
                    # Handle results
                    if isinstance(dark_pool_events, list):
                        logger.info(f"Found {len(dark_pool_events)} dark pool whale events")
                    else:
                        logger.error(f"Dark pool polling error: {dark_pool_events}")
                    
                    if isinstance(options_events, list):
                        logger.info(f"Found {len(options_events)} options sweep whale events")
                    else:
                        logger.error(f"Options polling error: {options_events}")
                    
                except Exception as e:
                    logger.error(f"Error during US equity whale polling: {e}")
            else:
                logger.debug("Outside US market hours - skipping poll")
            
            # Wait for next poll interval
            await asyncio.sleep(self.POLL_INTERVAL_SECONDS)
