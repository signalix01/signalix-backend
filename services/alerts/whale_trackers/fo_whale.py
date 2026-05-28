"""
F&O Whale Tracker

Tracks large institutional movements in Indian F&O (Futures & Options) markets:
- OI (Open Interest) change >= 1,000 lots in single 5-minute window
- IV (Implied Volatility) spike >= 20% in one candle
- Large premium trade >= Rs 5 Cr in single trade

Requirements: 12.1

Data Sources:
- Angel One SmartAPI: Options chain data
- Polling every 5 minutes during NSE hours (09:15 - 15:30 IST)

Detection Logic:
- Compare current OI against previous snapshot stored in Redis
- Calculate IV percentage change from previous candle
- Monitor premium (price * lot_size * quantity) for large trades
"""

import asyncio
import uuid
import json
from datetime import datetime, time, timedelta
from typing import List, Optional, Dict, Any, Tuple
from decimal import Decimal
import logging

import httpx
from shared.database.models import AnomalyEvent, AnomalyType, AnomalySeverity

logger = logging.getLogger(__name__)


class FOWhaleTracker:
    """
    Tracks large institutional movements in Indian F&O markets.
    
    Monitors:
    - OI change >= 1,000 lots in single 5-minute window
    - IV spike >= 20% in one candle
    - Large premium trade >= Rs 5 Cr
    
    Generates AnomalyEvent for each qualifying activity.
    """
    
    # Thresholds
    OI_CHANGE_THRESHOLD_LOTS = 1000  # lots
    IV_SPIKE_THRESHOLD_PCT = 20.0    # percentage
    PREMIUM_THRESHOLD_CR = 5.0       # Crores (Rs)
    
    # Market hours (IST)
    MARKET_OPEN = time(9, 15)
    MARKET_CLOSE = time(15, 30)
    
    # Polling interval
    POLL_INTERVAL_SECONDS = 300  # 5 minutes
    
    # Redis key prefixes for OI snapshots
    REDIS_OI_PREFIX = "fo_whale:oi:"
    REDIS_IV_PREFIX = "fo_whale:iv:"
    
    # Standard lot sizes for major F&O instruments
    LOT_SIZES = {
        "NIFTY": 50,
        "BANKNIFTY": 15,
        "FINNIFTY": 40,
        "MIDCPNIFTY": 75,
        "SENSEX": 10,
        "BANKEX": 15,
    }
    
    def __init__(
        self,
        angel_one_api_key: Optional[str] = None,
        angel_one_api_base_url: str = "https://apiconnect.angelbroking.com",
        redis_client: Optional[Any] = None,
        timeout_seconds: int = 30
    ):
        """
        Initialize the F&O Whale Tracker.
        
        Args:
            angel_one_api_key: Angel One SmartAPI key
            angel_one_api_base_url: Base URL for Angel One API
            redis_client: Redis client for storing OI/IV snapshots
            timeout_seconds: HTTP request timeout
        """
        self.angel_one_api_key = angel_one_api_key
        self.angel_one_api_base_url = angel_one_api_base_url
        self.redis_client = redis_client
        self.timeout_seconds = timeout_seconds
        
        # In-memory fallback if Redis is not available
        self._oi_snapshots: Dict[str, float] = {}
        self._iv_snapshots: Dict[str, float] = {}
    
    async def fetch_options_chain(
        self,
        symbol: str,
        expiry_date: str
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch options chain data from Angel One SmartAPI.
        
        Args:
            symbol: Underlying symbol (e.g., "NIFTY", "BANKNIFTY")
            expiry_date: Expiry date in format "YYYY-MM-DD"
        
        Returns:
            Options chain data dictionary or None if fetch fails
        """
        # Angel One SmartAPI endpoint for options chain
        url = f"{self.angel_one_api_base_url}/rest/secure/angelbroking/order/v1/getOptionChain"
        
        headers = {
            "Authorization": f"Bearer {self.angel_one_api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-UserType": "USER",
            "X-SourceID": "WEB",
        }
        
        payload = {
            "mode": "FULL",
            "exchangeSegment": "NFO",
            "symbol": symbol,
            "expiryDate": expiry_date
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                
                # Angel One API returns data in format: {"status": true, "data": {...}}
                if isinstance(data, dict) and data.get("status") and "data" in data:
                    return data["data"]
                else:
                    logger.warning(f"Unexpected Angel One options chain response format: {type(data)}")
                    return None
                    
        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch options chain for {symbol}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching options chain for {symbol}: {e}")
            return None
    
    def _get_lot_size(self, symbol: str) -> int:
        """
        Get the lot size for a given F&O symbol.
        
        Args:
            symbol: F&O symbol (e.g., "NIFTY", "BANKNIFTY")
        
        Returns:
            Lot size (default 50 if not found)
        """
        return self.LOT_SIZES.get(symbol.upper(), 50)
    
    async def _get_previous_oi(self, option_key: str) -> Optional[float]:
        """
        Get previous OI snapshot from Redis or in-memory cache.
        
        Args:
            option_key: Unique key for the option (e.g., "NIFTY_24000_CE_2024-01-25")
        
        Returns:
            Previous OI value or None if not found
        """
        if self.redis_client:
            try:
                redis_key = f"{self.REDIS_OI_PREFIX}{option_key}"
                value = await self.redis_client.get(redis_key)
                if value:
                    return float(value)
            except Exception as e:
                logger.error(f"Error fetching OI from Redis: {e}")
        
        # Fallback to in-memory cache
        return self._oi_snapshots.get(option_key)
    
    async def _store_current_oi(self, option_key: str, oi: float):
        """
        Store current OI snapshot to Redis or in-memory cache.
        
        Args:
            option_key: Unique key for the option
            oi: Current OI value
        """
        if self.redis_client:
            try:
                redis_key = f"{self.REDIS_OI_PREFIX}{option_key}"
                # Store with 1-hour TTL (enough for 5-minute polling)
                await self.redis_client.setex(redis_key, 3600, str(oi))
            except Exception as e:
                logger.error(f"Error storing OI to Redis: {e}")
        
        # Always update in-memory cache as fallback
        self._oi_snapshots[option_key] = oi
    
    async def _get_previous_iv(self, option_key: str) -> Optional[float]:
        """
        Get previous IV snapshot from Redis or in-memory cache.
        
        Args:
            option_key: Unique key for the option
        
        Returns:
            Previous IV value or None if not found
        """
        if self.redis_client:
            try:
                redis_key = f"{self.REDIS_IV_PREFIX}{option_key}"
                value = await self.redis_client.get(redis_key)
                if value:
                    return float(value)
            except Exception as e:
                logger.error(f"Error fetching IV from Redis: {e}")
        
        # Fallback to in-memory cache
        return self._iv_snapshots.get(option_key)
    
    async def _store_current_iv(self, option_key: str, iv: float):
        """
        Store current IV snapshot to Redis or in-memory cache.
        
        Args:
            option_key: Unique key for the option
            iv: Current IV value
        """
        if self.redis_client:
            try:
                redis_key = f"{self.REDIS_IV_PREFIX}{option_key}"
                # Store with 1-hour TTL
                await self.redis_client.setex(redis_key, 3600, str(iv))
            except Exception as e:
                logger.error(f"Error storing IV to Redis: {e}")
        
        # Always update in-memory cache as fallback
        self._iv_snapshots[option_key] = iv
    
    def _calculate_premium_cr(
        self,
        price: float,
        quantity: int,
        lot_size: int
    ) -> float:
        """
        Calculate premium value in Crores (Rs).
        
        Args:
            price: Option price per unit
            quantity: Number of lots
            lot_size: Lot size for the instrument
        
        Returns:
            Premium value in Crores
        """
        premium_rs = price * quantity * lot_size
        premium_cr = premium_rs / 1_00_00_000  # 1 Crore = 1,00,00,000
        return premium_cr
    
    def _generate_oi_change_event(
        self,
        symbol: str,
        strike: float,
        option_type: str,
        expiry: str,
        current_oi: float,
        previous_oi: float,
        oi_change_lots: float,
        price: float,
        lot_size: int
    ) -> Optional[AnomalyEvent]:
        """
        Generate an AnomalyEvent for significant OI change.
        
        Args:
            symbol: Underlying symbol
            strike: Strike price
            option_type: "CE" or "PE"
            expiry: Expiry date
            current_oi: Current open interest
            previous_oi: Previous open interest
            oi_change_lots: OI change in lots
            price: Current option price
            lot_size: Lot size
        
        Returns:
            AnomalyEvent if OI change qualifies, None otherwise
        """
        try:
            # Check threshold
            if abs(oi_change_lots) < self.OI_CHANGE_THRESHOLD_LOTS:
                return None
            
            # Determine severity based on OI change magnitude
            abs_change = abs(oi_change_lots)
            if abs_change >= 5000:
                severity = AnomalySeverity.CRITICAL
            elif abs_change >= 2500:
                severity = AnomalySeverity.HIGH
            else:
                severity = AnomalySeverity.MEDIUM
            
            # Determine direction
            direction = "buildup" if oi_change_lots > 0 else "unwinding"
            
            # Generate description
            option_name = f"{symbol} {strike} {option_type}"
            description = (
                f"Large OI {direction} detected in {option_name} (Expiry: {expiry}): "
                f"{abs(oi_change_lots):,.0f} lots change "
                f"(from {previous_oi:,.0f} to {current_oi:,.0f}). "
                f"Current price: Rs {price:.2f}"
            )
            
            # Create anomaly event
            event = AnomalyEvent(
                id=uuid.uuid4(),
                instrument=symbol,
                asset_class="fo",
                exchange="NFO",
                anomaly_type=AnomalyType.OPTIONS_UNUSUAL,
                severity=severity,
                detected_at=datetime.utcnow(),
                description=description,
                z_score=None,
                price=price,
                volume=abs(oi_change_lots) * lot_size,
                affected_instruments=None,
                raw_data={
                    "detection_type": "oi_change",
                    "symbol": symbol,
                    "strike": strike,
                    "option_type": option_type,
                    "expiry": expiry,
                    "current_oi": current_oi,
                    "previous_oi": previous_oi,
                    "oi_change_lots": oi_change_lots,
                    "direction": direction,
                    "price": price,
                    "lot_size": lot_size,
                    "threshold_lots": self.OI_CHANGE_THRESHOLD_LOTS
                }
            )
            
            logger.info(f"Generated OI change event: {description}")
            return event
            
        except Exception as e:
            logger.error(f"Error generating OI change event: {e}")
            return None
    
    def _generate_iv_spike_event(
        self,
        symbol: str,
        strike: float,
        option_type: str,
        expiry: str,
        current_iv: float,
        previous_iv: float,
        iv_change_pct: float,
        price: float,
        oi: float
    ) -> Optional[AnomalyEvent]:
        """
        Generate an AnomalyEvent for significant IV spike.
        
        Args:
            symbol: Underlying symbol
            strike: Strike price
            option_type: "CE" or "PE"
            expiry: Expiry date
            current_iv: Current implied volatility
            previous_iv: Previous implied volatility
            iv_change_pct: IV change percentage
            price: Current option price
            oi: Current open interest
        
        Returns:
            AnomalyEvent if IV spike qualifies, None otherwise
        """
        try:
            # Check threshold
            if abs(iv_change_pct) < self.IV_SPIKE_THRESHOLD_PCT:
                return None
            
            # Determine severity based on IV spike magnitude
            abs_change = abs(iv_change_pct)
            if abs_change >= 50:
                severity = AnomalySeverity.CRITICAL
            elif abs_change >= 35:
                severity = AnomalySeverity.HIGH
            else:
                severity = AnomalySeverity.MEDIUM
            
            # Generate description
            option_name = f"{symbol} {strike} {option_type}"
            direction = "spike" if iv_change_pct > 0 else "drop"
            description = (
                f"Large IV {direction} detected in {option_name} (Expiry: {expiry}): "
                f"{abs(iv_change_pct):.1f}% change "
                f"(from {previous_iv:.2f}% to {current_iv:.2f}%). "
                f"Current price: Rs {price:.2f}, OI: {oi:,.0f}"
            )
            
            # Create anomaly event
            event = AnomalyEvent(
                id=uuid.uuid4(),
                instrument=symbol,
                asset_class="fo",
                exchange="NFO",
                anomaly_type=AnomalyType.OPTIONS_UNUSUAL,
                severity=severity,
                detected_at=datetime.utcnow(),
                description=description,
                z_score=None,
                price=price,
                volume=oi,
                affected_instruments=None,
                raw_data={
                    "detection_type": "iv_spike",
                    "symbol": symbol,
                    "strike": strike,
                    "option_type": option_type,
                    "expiry": expiry,
                    "current_iv": current_iv,
                    "previous_iv": previous_iv,
                    "iv_change_pct": iv_change_pct,
                    "direction": direction,
                    "price": price,
                    "oi": oi,
                    "threshold_pct": self.IV_SPIKE_THRESHOLD_PCT
                }
            )
            
            logger.info(f"Generated IV spike event: {description}")
            return event
            
        except Exception as e:
            logger.error(f"Error generating IV spike event: {e}")
            return None
    
    def _generate_large_premium_event(
        self,
        symbol: str,
        strike: float,
        option_type: str,
        expiry: str,
        price: float,
        quantity_lots: int,
        lot_size: int,
        premium_cr: float,
        oi: float,
        iv: Optional[float] = None
    ) -> Optional[AnomalyEvent]:
        """
        Generate an AnomalyEvent for large premium trade.
        
        Args:
            symbol: Underlying symbol
            strike: Strike price
            option_type: "CE" or "PE"
            expiry: Expiry date
            price: Option price
            quantity_lots: Trade quantity in lots
            lot_size: Lot size
            premium_cr: Premium value in Crores
            oi: Current open interest
            iv: Current implied volatility (optional)
        
        Returns:
            AnomalyEvent if premium qualifies, None otherwise
        """
        try:
            # Check threshold
            if premium_cr < self.PREMIUM_THRESHOLD_CR:
                return None
            
            # Determine severity based on premium size
            if premium_cr >= 50:
                severity = AnomalySeverity.CRITICAL
            elif premium_cr >= 20:
                severity = AnomalySeverity.HIGH
            else:
                severity = AnomalySeverity.MEDIUM
            
            # Generate description
            option_name = f"{symbol} {strike} {option_type}"
            description = (
                f"Large premium trade detected in {option_name} (Expiry: {expiry}): "
                f"Rs {premium_cr:.2f} Cr "
                f"({quantity_lots:,} lots @ Rs {price:.2f}). "
                f"OI: {oi:,.0f}"
            )
            
            if iv is not None:
                description += f", IV: {iv:.2f}%"
            
            # Create anomaly event
            event = AnomalyEvent(
                id=uuid.uuid4(),
                instrument=symbol,
                asset_class="fo",
                exchange="NFO",
                anomaly_type=AnomalyType.WHALE_MOVEMENT,
                severity=severity,
                detected_at=datetime.utcnow(),
                description=description,
                z_score=None,
                price=price,
                volume=quantity_lots * lot_size,
                affected_instruments=None,
                raw_data={
                    "detection_type": "large_premium",
                    "symbol": symbol,
                    "strike": strike,
                    "option_type": option_type,
                    "expiry": expiry,
                    "price": price,
                    "quantity_lots": quantity_lots,
                    "lot_size": lot_size,
                    "premium_cr": premium_cr,
                    "oi": oi,
                    "iv": iv,
                    "threshold_cr": self.PREMIUM_THRESHOLD_CR
                }
            )
            
            logger.info(f"Generated large premium event: {description}")
            return event
            
        except Exception as e:
            logger.error(f"Error generating large premium event: {e}")
            return None
    
    async def analyze_options_chain(
        self,
        symbol: str,
        expiry_date: str
    ) -> List[AnomalyEvent]:
        """
        Analyze options chain data and detect whale movements.
        
        Args:
            symbol: Underlying symbol (e.g., "NIFTY", "BANKNIFTY")
            expiry_date: Expiry date in format "YYYY-MM-DD"
        
        Returns:
            List of AnomalyEvents for detected whale movements
        """
        events = []
        
        # Fetch options chain
        chain_data = await self.fetch_options_chain(symbol, expiry_date)
        
        if not chain_data:
            logger.warning(f"No options chain data available for {symbol} {expiry_date}")
            return events
        
        # Get lot size
        lot_size = self._get_lot_size(symbol)
        
        # Process each option in the chain
        # Expected format: {"strikes": [{"strike": 24000, "CE": {...}, "PE": {...}}]}
        strikes = chain_data.get("strikes", [])
        
        for strike_data in strikes:
            strike = strike_data.get("strike")
            
            if not strike:
                continue
            
            # Process Call option (CE)
            ce_data = strike_data.get("CE")
            if ce_data:
                await self._analyze_option(
                    symbol, strike, "CE", expiry_date,
                    ce_data, lot_size, events
                )
            
            # Process Put option (PE)
            pe_data = strike_data.get("PE")
            if pe_data:
                await self._analyze_option(
                    symbol, strike, "PE", expiry_date,
                    pe_data, lot_size, events
                )
        
        return events
    
    async def _analyze_option(
        self,
        symbol: str,
        strike: float,
        option_type: str,
        expiry: str,
        option_data: Dict[str, Any],
        lot_size: int,
        events: List[AnomalyEvent]
    ):
        """
        Analyze a single option and detect anomalies.
        
        Args:
            symbol: Underlying symbol
            strike: Strike price
            option_type: "CE" or "PE"
            expiry: Expiry date
            option_data: Option data dictionary
            lot_size: Lot size
            events: List to append detected events to
        """
        try:
            # Extract option data
            current_oi = float(option_data.get("openInterest", 0))
            price = float(option_data.get("lastPrice", 0))
            current_iv = float(option_data.get("impliedVolatility", 0))
            volume = float(option_data.get("volume", 0))
            
            if current_oi == 0 or price == 0:
                return
            
            # Create unique key for this option
            option_key = f"{symbol}_{strike}_{option_type}_{expiry}"
            
            # Check OI change
            previous_oi = await self._get_previous_oi(option_key)
            if previous_oi is not None:
                oi_change_lots = (current_oi - previous_oi) / lot_size
                
                event = self._generate_oi_change_event(
                    symbol, strike, option_type, expiry,
                    current_oi, previous_oi, oi_change_lots,
                    price, lot_size
                )
                
                if event:
                    events.append(event)
            
            # Store current OI for next comparison
            await self._store_current_oi(option_key, current_oi)
            
            # Check IV spike
            if current_iv > 0:
                previous_iv = await self._get_previous_iv(option_key)
                if previous_iv is not None and previous_iv > 0:
                    iv_change_pct = ((current_iv - previous_iv) / previous_iv) * 100
                    
                    event = self._generate_iv_spike_event(
                        symbol, strike, option_type, expiry,
                        current_iv, previous_iv, iv_change_pct,
                        price, current_oi
                    )
                    
                    if event:
                        events.append(event)
                
                # Store current IV for next comparison
                await self._store_current_iv(option_key, current_iv)
            
            # Check large premium trade (based on volume)
            if volume > 0:
                # Estimate quantity in lots from volume
                quantity_lots = int(volume / lot_size)
                
                if quantity_lots > 0:
                    premium_cr = self._calculate_premium_cr(price, quantity_lots, lot_size)
                    
                    event = self._generate_large_premium_event(
                        symbol, strike, option_type, expiry,
                        price, quantity_lots, lot_size, premium_cr,
                        current_oi, current_iv if current_iv > 0 else None
                    )
                    
                    if event:
                        events.append(event)
        
        except Exception as e:
            logger.error(f"Error analyzing option {symbol} {strike} {option_type}: {e}")
    
    def is_market_hours(self, current_time: Optional[datetime] = None) -> bool:
        """
        Check if current time is within NSE market hours (09:15 - 15:30 IST).
        
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
    
    async def poll_fo_markets(
        self,
        symbols: List[str] = None,
        expiry_dates: List[str] = None
    ) -> List[AnomalyEvent]:
        """
        Poll F&O markets for whale movements.
        
        Args:
            symbols: List of symbols to monitor (defaults to major indices)
            expiry_dates: List of expiry dates to monitor (defaults to current week)
        
        Returns:
            List of AnomalyEvents for detected whale movements
        """
        if symbols is None:
            symbols = ["NIFTY", "BANKNIFTY", "FINNIFTY"]
        
        if expiry_dates is None:
            # Default to current week expiry (placeholder - should calculate actual expiry)
            expiry_dates = [datetime.now().strftime("%Y-%m-%d")]
        
        all_events = []
        
        for symbol in symbols:
            for expiry in expiry_dates:
                try:
                    events = await self.analyze_options_chain(symbol, expiry)
                    all_events.extend(events)
                    logger.info(f"Analyzed {symbol} {expiry}: found {len(events)} events")
                except Exception as e:
                    logger.error(f"Error polling {symbol} {expiry}: {e}")
        
        return all_events
    
    async def run_continuous_polling(
        self,
        symbols: List[str] = None,
        expiry_dates: List[str] = None,
        stop_event: Optional[asyncio.Event] = None
    ):
        """
        Run continuous polling for F&O whale movements.
        
        This method runs indefinitely, polling options chain every 5 minutes
        during market hours.
        
        Args:
            symbols: List of symbols to monitor
            expiry_dates: List of expiry dates to monitor
            stop_event: Optional asyncio.Event to signal when to stop polling
        """
        logger.info("Starting F&O Whale Tracker continuous polling")
        
        while True:
            if stop_event and stop_event.is_set():
                logger.info("Stop event received, ending polling")
                break
            
            current_time = datetime.now()
            
            # Poll during market hours
            if self.is_market_hours(current_time):
                logger.info("Market hours - polling F&O options chain")
                
                try:
                    events = await self.poll_fo_markets(symbols, expiry_dates)
                    logger.info(f"Found {len(events)} F&O whale movement events")
                    
                    # Events would be published to Redis pub/sub or stored in DB here
                    # This is handled by the anomaly orchestrator in production
                    
                except Exception as e:
                    logger.error(f"Error during F&O polling: {e}")
            else:
                logger.debug("Outside market hours - skipping F&O polling")
            
            # Wait for next poll interval
            await asyncio.sleep(self.POLL_INTERVAL_SECONDS)
