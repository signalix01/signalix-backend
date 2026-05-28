"""
India Equity Whale Tracker

Tracks large institutional movements in Indian equity markets:
- NSE block deals (>= Rs 10 Cr)
- BSE bulk deals (>= Rs 5 Cr)
- NSDL FII/DII net activity (>= Rs 100 Cr)

Requirements: 12.1, 12.3, 12.4

Data Sources:
- NSE Block Deals API: GET /api/v1/market/block-deals
- BSE Bulk Deals API: (BSE endpoint)
- NSDL FII/DII: Daily data published at ~16:30 IST

Polling Schedule:
- NSE/BSE: Every 5 minutes during market hours (09:15 - 15:30 IST)
- NSDL: Once daily after 16:30 IST

Instrument Correlation:
When large FII buying is detected on HDFC Bank, also flag BANKNIFTY as affected_instrument.
"""

import asyncio
import uuid
from datetime import datetime, time, timedelta
from typing import List, Optional, Dict, Any
from decimal import Decimal
import logging

import httpx
from shared.database.models import AnomalyEvent, AnomalyType, AnomalySeverity

logger = logging.getLogger(__name__)


class IndiaEquityWhaleTracker:
    """
    Tracks large institutional movements in Indian equity markets.
    
    Monitors:
    - NSE block deals (>= Rs 10 Cr)
    - BSE bulk deals (>= Rs 5 Cr)
    - NSDL FII/DII net activity (>= Rs 100 Cr)
    
    Generates AnomalyEvent for each qualifying deal with instrument correlation.
    """
    
    # Thresholds in Crores (Rs)
    NSE_BLOCK_DEAL_THRESHOLD_CR = 10.0
    BSE_BULK_DEAL_THRESHOLD_CR = 5.0
    FII_DII_NET_THRESHOLD_CR = 100.0
    
    # Market hours (IST)
    MARKET_OPEN = time(9, 15)
    MARKET_CLOSE = time(15, 30)
    NSDL_PUBLISH_TIME = time(16, 30)
    
    # Polling intervals
    BLOCK_DEAL_POLL_INTERVAL_SECONDS = 300  # 5 minutes
    
    # Instrument correlation mapping
    # Maps individual stocks to their index/sector instruments
    CORRELATION_MAP = {
        "HDFCBANK": ["BANKNIFTY", "NIFTY50"],
        "ICICIBANK": ["BANKNIFTY", "NIFTY50"],
        "AXISBANK": ["BANKNIFTY", "NIFTY50"],
        "KOTAKBANK": ["BANKNIFTY", "NIFTY50"],
        "SBIN": ["BANKNIFTY", "NIFTY50"],
        "RELIANCE": ["NIFTY50"],
        "TCS": ["NIFTY50", "NIFTYIT"],
        "INFY": ["NIFTY50", "NIFTYIT"],
        "WIPRO": ["NIFTY50", "NIFTYIT"],
        "HCLTECH": ["NIFTY50", "NIFTYIT"],
        "ITC": ["NIFTY50"],
        "HINDUNILVR": ["NIFTY50"],
        "BHARTIARTL": ["NIFTY50"],
        "ASIANPAINT": ["NIFTY50"],
        "MARUTI": ["NIFTY50"],
    }
    
    def __init__(
        self,
        nse_api_base_url: str = "https://www.nseindia.com",
        bse_api_base_url: str = "https://api.bseindia.com",
        nsdl_api_base_url: str = "https://www.fpi.nsdl.co.in",
        timeout_seconds: int = 30
    ):
        """
        Initialize the India Equity Whale Tracker.
        
        Args:
            nse_api_base_url: Base URL for NSE API
            bse_api_base_url: Base URL for BSE API
            nsdl_api_base_url: Base URL for NSDL FII/DII data
            timeout_seconds: HTTP request timeout
        """
        self.nse_api_base_url = nse_api_base_url
        self.bse_api_base_url = bse_api_base_url
        self.nsdl_api_base_url = nsdl_api_base_url
        self.timeout_seconds = timeout_seconds
        
        # Track last processed deals to avoid duplicates
        self._processed_block_deals: set = set()
        self._processed_bulk_deals: set = set()
        self._last_fii_dii_date: Optional[str] = None
    
    async def fetch_nse_block_deals(self) -> List[Dict[str, Any]]:
        """
        Fetch NSE block deals from the NSE API.
        
        Returns:
            List of block deal dictionaries
        """
        url = f"{self.nse_api_base_url}/api/v1/market/block-deals"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.nseindia.com/"
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()
                
                # NSE API returns data in various formats, adapt as needed
                # Expected format: {"data": [{"symbol": "...", "quantity": ..., "price": ..., ...}]}
                if isinstance(data, dict) and "data" in data:
                    return data["data"]
                elif isinstance(data, list):
                    return data
                else:
                    logger.warning(f"Unexpected NSE block deals response format: {type(data)}")
                    return []
                    
        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch NSE block deals: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching NSE block deals: {e}")
            return []
    
    async def fetch_bse_bulk_deals(self) -> List[Dict[str, Any]]:
        """
        Fetch BSE bulk deals from the BSE API.
        
        Returns:
            List of bulk deal dictionaries
        """
        # BSE API endpoint (placeholder - actual endpoint may vary)
        url = f"{self.bse_api_base_url}/api/v1/bulk-deals"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
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
                    logger.warning(f"Unexpected BSE bulk deals response format: {type(data)}")
                    return []
                    
        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch BSE bulk deals: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching BSE bulk deals: {e}")
            return []
    
    async def fetch_nsdl_fii_dii_data(self) -> Optional[Dict[str, Any]]:
        """
        Fetch NSDL FII/DII net activity data.
        
        This data is published daily after NSE closes (~16:30 IST).
        
        Returns:
            Dictionary with FII/DII data or None if not available
        """
        # NSDL API endpoint (placeholder - actual endpoint may vary)
        url = f"{self.nsdl_api_base_url}/api/fii-dii-data"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json"
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()
                return data
                    
        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch NSDL FII/DII data: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching NSDL FII/DII data: {e}")
            return None
    
    def _calculate_deal_value_cr(self, quantity: float, price: float) -> float:
        """
        Calculate deal value in Crores (Rs).
        
        Args:
            quantity: Number of shares
            price: Price per share
        
        Returns:
            Deal value in Crores
        """
        value_rs = quantity * price
        value_cr = value_rs / 10_000_000  # 1 Crore = 1,00,00,000
        return value_cr
    
    def _get_affected_instruments(self, symbol: str) -> List[str]:
        """
        Get correlated instruments for a given symbol.
        
        When large institutional activity is detected on a stock,
        related indices/sectors are also flagged as affected.
        
        Args:
            symbol: Stock symbol (e.g., "HDFCBANK")
        
        Returns:
            List of affected instrument symbols
        """
        return self.CORRELATION_MAP.get(symbol, [])
    
    def _generate_block_deal_event(
        self,
        deal: Dict[str, Any],
        exchange: str = "NSE"
    ) -> Optional[AnomalyEvent]:
        """
        Generate an AnomalyEvent for a qualifying block deal.
        
        Args:
            deal: Block deal data dictionary
            exchange: Exchange name (NSE or BSE)
        
        Returns:
            AnomalyEvent if deal qualifies, None otherwise
        """
        try:
            # Extract deal details (field names may vary by API)
            symbol = deal.get("symbol") or deal.get("scrip_code") or deal.get("security")
            quantity = float(deal.get("quantity") or deal.get("qty") or 0)
            price = float(deal.get("price") or deal.get("trade_price") or 0)
            client_name = deal.get("client_name") or deal.get("buyer") or "Unknown"
            deal_type = deal.get("deal_type") or deal.get("type") or "BUY"
            
            if not symbol or quantity == 0 or price == 0:
                logger.warning(f"Incomplete block deal data: {deal}")
                return None
            
            # Calculate deal value
            value_cr = self._calculate_deal_value_cr(quantity, price)
            
            # Check threshold
            threshold = self.NSE_BLOCK_DEAL_THRESHOLD_CR if exchange == "NSE" else self.BSE_BULK_DEAL_THRESHOLD_CR
            
            if value_cr < threshold:
                return None
            
            # Generate unique deal ID for deduplication
            deal_id = f"{exchange}_{symbol}_{quantity}_{price}_{client_name}"
            
            if deal_id in self._processed_block_deals:
                return None
            
            self._processed_block_deals.add(deal_id)
            
            # Determine severity based on deal size
            if value_cr >= 100:
                severity = AnomalySeverity.CRITICAL
            elif value_cr >= 50:
                severity = AnomalySeverity.HIGH
            else:
                severity = AnomalySeverity.MEDIUM
            
            # Get affected instruments
            affected_instruments = self._get_affected_instruments(symbol)
            
            # Generate description
            deal_type_str = "buying" if deal_type.upper() in ["BUY", "B"] else "selling"
            description = (
                f"{exchange} block deal: {client_name} {deal_type_str} "
                f"{quantity:,.0f} shares of {symbol} at Rs {price:.2f} "
                f"(total value: Rs {value_cr:.2f} Cr)"
            )
            
            if affected_instruments:
                description += f". Potentially affects: {', '.join(affected_instruments)}"
            
            # Create anomaly event
            event = AnomalyEvent(
                id=uuid.uuid4(),
                instrument=symbol,
                asset_class="equity",
                exchange=exchange,
                anomaly_type=AnomalyType.WHALE_MOVEMENT,
                severity=severity,
                detected_at=datetime.utcnow(),
                description=description,
                z_score=None,
                price=price,
                volume=quantity,
                affected_instruments=affected_instruments if affected_instruments else None,
                raw_data={
                    "deal_type": "block_deal" if exchange == "NSE" else "bulk_deal",
                    "exchange": exchange,
                    "symbol": symbol,
                    "quantity": quantity,
                    "price": price,
                    "value_cr": value_cr,
                    "client_name": client_name,
                    "trade_type": deal_type,
                    "threshold_cr": threshold,
                    "deal_id": deal_id,
                    "original_data": deal
                }
            )
            
            logger.info(f"Generated whale movement event: {description}")
            return event
            
        except Exception as e:
            logger.error(f"Error generating block deal event: {e}, deal: {deal}")
            return None
    
    def _generate_fii_dii_event(
        self,
        fii_dii_data: Dict[str, Any]
    ) -> List[AnomalyEvent]:
        """
        Generate AnomalyEvents for qualifying FII/DII net activity.
        
        Args:
            fii_dii_data: FII/DII data dictionary
        
        Returns:
            List of AnomalyEvents for qualifying activity
        """
        events = []
        
        try:
            # Extract FII/DII data (field names may vary)
            date = fii_dii_data.get("date") or fii_dii_data.get("trade_date")
            fii_net_cr = float(fii_dii_data.get("fii_net") or fii_dii_data.get("fii_net_investment") or 0)
            dii_net_cr = float(fii_dii_data.get("dii_net") or fii_dii_data.get("dii_net_investment") or 0)
            
            # Check if we've already processed this date
            if date == self._last_fii_dii_date:
                return events
            
            self._last_fii_dii_date = date
            
            # Check FII net activity
            if abs(fii_net_cr) >= self.FII_DII_NET_THRESHOLD_CR:
                direction = "buying" if fii_net_cr > 0 else "selling"
                severity = AnomalySeverity.CRITICAL if abs(fii_net_cr) >= 500 else AnomalySeverity.HIGH
                
                description = (
                    f"Large FII {direction} detected: Net {direction} of Rs {abs(fii_net_cr):.2f} Cr "
                    f"on {date}. This may impact overall market sentiment."
                )
                
                event = AnomalyEvent(
                    id=uuid.uuid4(),
                    instrument="NIFTY50",  # FII activity affects overall market
                    asset_class="equity",
                    exchange="NSE",
                    anomaly_type=AnomalyType.INSTITUTIONAL_FLOW,
                    severity=severity,
                    detected_at=datetime.utcnow(),
                    description=description,
                    z_score=None,
                    price=None,
                    volume=None,
                    affected_instruments=["BANKNIFTY", "NIFTY50"],
                    raw_data={
                        "flow_type": "fii",
                        "date": date,
                        "net_value_cr": fii_net_cr,
                        "direction": direction,
                        "threshold_cr": self.FII_DII_NET_THRESHOLD_CR,
                        "original_data": fii_dii_data
                    }
                )
                
                events.append(event)
                logger.info(f"Generated FII flow event: {description}")
            
            # Check DII net activity
            if abs(dii_net_cr) >= self.FII_DII_NET_THRESHOLD_CR:
                direction = "buying" if dii_net_cr > 0 else "selling"
                severity = AnomalySeverity.CRITICAL if abs(dii_net_cr) >= 500 else AnomalySeverity.HIGH
                
                description = (
                    f"Large DII {direction} detected: Net {direction} of Rs {abs(dii_net_cr):.2f} Cr "
                    f"on {date}. This may impact overall market sentiment."
                )
                
                event = AnomalyEvent(
                    id=uuid.uuid4(),
                    instrument="NIFTY50",
                    asset_class="equity",
                    exchange="NSE",
                    anomaly_type=AnomalyType.INSTITUTIONAL_FLOW,
                    severity=severity,
                    detected_at=datetime.utcnow(),
                    description=description,
                    z_score=None,
                    price=None,
                    volume=None,
                    affected_instruments=["BANKNIFTY", "NIFTY50"],
                    raw_data={
                        "flow_type": "dii",
                        "date": date,
                        "net_value_cr": dii_net_cr,
                        "direction": direction,
                        "threshold_cr": self.FII_DII_NET_THRESHOLD_CR,
                        "original_data": fii_dii_data
                    }
                )
                
                events.append(event)
                logger.info(f"Generated DII flow event: {description}")
            
            return events
            
        except Exception as e:
            logger.error(f"Error generating FII/DII events: {e}, data: {fii_dii_data}")
            return events
    
    async def poll_nse_block_deals(self) -> List[AnomalyEvent]:
        """
        Poll NSE for block deals and generate events for qualifying deals.
        
        Returns:
            List of AnomalyEvents for qualifying block deals
        """
        deals = await self.fetch_nse_block_deals()
        events = []
        
        for deal in deals:
            event = self._generate_block_deal_event(deal, exchange="NSE")
            if event:
                events.append(event)
        
        return events
    
    async def poll_bse_bulk_deals(self) -> List[AnomalyEvent]:
        """
        Poll BSE for bulk deals and generate events for qualifying deals.
        
        Returns:
            List of AnomalyEvents for qualifying bulk deals
        """
        deals = await self.fetch_bse_bulk_deals()
        events = []
        
        for deal in deals:
            event = self._generate_block_deal_event(deal, exchange="BSE")
            if event:
                events.append(event)
        
        return events
    
    async def poll_nsdl_fii_dii(self) -> List[AnomalyEvent]:
        """
        Poll NSDL for FII/DII data and generate events for qualifying activity.
        
        Returns:
            List of AnomalyEvents for qualifying FII/DII activity
        """
        data = await self.fetch_nsdl_fii_dii_data()
        
        if data:
            return self._generate_fii_dii_event(data)
        
        return []
    
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
    
    def should_poll_fii_dii(self, current_time: Optional[datetime] = None) -> bool:
        """
        Check if it's time to poll FII/DII data (after 16:30 IST).
        
        Args:
            current_time: Time to check (defaults to now)
        
        Returns:
            True if should poll, False otherwise
        """
        if current_time is None:
            current_time = datetime.now()
        
        current_time_only = current_time.time()
        
        # Check if it's a weekday
        if current_time.weekday() >= 5:
            return False
        
        # Check if after NSDL publish time
        return current_time_only >= self.NSDL_PUBLISH_TIME
    
    async def run_continuous_polling(self, stop_event: Optional[asyncio.Event] = None):
        """
        Run continuous polling for all data sources.
        
        This method runs indefinitely, polling NSE/BSE every 5 minutes during
        market hours and NSDL once daily after 16:30 IST.
        
        Args:
            stop_event: Optional asyncio.Event to signal when to stop polling
        """
        logger.info("Starting India Equity Whale Tracker continuous polling")
        
        fii_dii_polled_today = False
        
        while True:
            if stop_event and stop_event.is_set():
                logger.info("Stop event received, ending polling")
                break
            
            current_time = datetime.now()
            
            # Poll block/bulk deals during market hours
            if self.is_market_hours(current_time):
                logger.info("Market hours - polling NSE block deals and BSE bulk deals")
                
                try:
                    # Poll NSE and BSE concurrently
                    nse_events, bse_events = await asyncio.gather(
                        self.poll_nse_block_deals(),
                        self.poll_bse_bulk_deals(),
                        return_exceptions=True
                    )
                    
                    # Handle results
                    if isinstance(nse_events, list):
                        logger.info(f"Found {len(nse_events)} NSE block deal events")
                    else:
                        logger.error(f"NSE polling error: {nse_events}")
                    
                    if isinstance(bse_events, list):
                        logger.info(f"Found {len(bse_events)} BSE bulk deal events")
                    else:
                        logger.error(f"BSE polling error: {bse_events}")
                    
                except Exception as e:
                    logger.error(f"Error during block/bulk deal polling: {e}")
                
                # Reset FII/DII flag at market open
                if current_time.time() < time(10, 0):
                    fii_dii_polled_today = False
            
            # Poll FII/DII after market close (once per day)
            if self.should_poll_fii_dii(current_time) and not fii_dii_polled_today:
                logger.info("After market hours - polling NSDL FII/DII data")
                
                try:
                    fii_dii_events = await self.poll_nsdl_fii_dii()
                    logger.info(f"Found {len(fii_dii_events)} FII/DII flow events")
                    fii_dii_polled_today = True
                    
                except Exception as e:
                    logger.error(f"Error during FII/DII polling: {e}")
            
            # Wait for next poll interval
            await asyncio.sleep(self.BLOCK_DEAL_POLL_INTERVAL_SECONDS)
