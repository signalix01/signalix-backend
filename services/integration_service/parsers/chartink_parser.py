"""
ChartInk Parser

Parses ChartInk scanner alert payloads.
Requirements: 3.3, 3.5, 3.6
"""

import re
import logging
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import asyncio

from services.integration_service.models.webhook_models import SignalAction

logger = logging.getLogger(__name__)


@dataclass
class ChartInkSymbol:
    """Extracted symbol data from ChartInk alert"""
    symbol: str
    exchange: str
    price: Optional[float] = None
    volume: Optional[int] = None
    change_percent: Optional[float] = None
    scan_name: Optional[str] = None
    conditions: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChartInkAlert:
    """Parsed ChartInk scanner alert"""
    scan_name: str
    scan_url: Optional[str]
    alert_time: datetime
    symbols: List[ChartInkSymbol]
    raw_data: Dict[str, Any]


class ChartInkParser:
    """
    Parser for ChartInk scanner alerts
    
    Supports ChartInk webhook format with:
    - Scanner name and URL
    - Multiple symbols with conditions
    - Price, volume, and other metrics
    """
    
    # Exchange mappings
    EXCHANGE_MAP = {
        "nse": "NSE",
        "bse": "BSE",
        "mcx": "MCX",
        "nfo": "NFO",
        "cds": "CDS",
    }
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def parse_alert(self, payload: Dict[str, Any]) -> Optional[ChartInkAlert]:
        """
        Parse ChartInk webhook alert
        
        Args:
            payload: ChartInk webhook payload
            
        Returns:
            ChartInkAlert or None if parsing fails
            
        Requirements: 3.3
        """
        try:
            self.logger.debug(f"Parsing ChartInk payload: {payload}")
            
            # Extract scan information
            scan_name = self._extract_scan_name(payload)
            scan_url = payload.get("scan_url") or payload.get("scan_link")
            
            # Extract alert time
            alert_time = self._extract_alert_time(payload)
            
            # Extract symbols
            symbols = self._extract_symbols(payload)
            
            if not symbols:
                self.logger.warning("No symbols found in ChartInk alert")
                return None
            
            return ChartInkAlert(
                scan_name=scan_name,
                scan_url=scan_url,
                alert_time=alert_time,
                symbols=symbols,
                raw_data=payload
            )
            
        except Exception as e:
            self.logger.error(f"Error parsing ChartInk payload: {str(e)}")
            return None
    
    def _extract_scan_name(self, payload: Dict[str, Any]) -> str:
        """Extract scan name from payload"""
        name_fields = ["scan_name", "scanner_name", "name", "alert_name", "scan"]
        
        for field in name_fields:
            if field in payload:
                return str(payload[field])
        
        return "Unknown Scan"
    
    def _extract_alert_time(self, payload: Dict[str, Any]) -> datetime:
        """Extract alert timestamp"""
        time_fields = ["time", "timestamp", "alert_time", "triggered_at", "date"]
        
        for field in time_fields:
            if field in payload:
                try:
                    # Try to parse various timestamp formats
                    value = payload[field]
                    
                    if isinstance(value, (int, float)):
                        # Unix timestamp
                        if value > 1_000_000_000_000:
                            value = value / 1000  # Convert from milliseconds
                        return datetime.utcfromtimestamp(value)
                    
                    if isinstance(value, str):
                        # Try ISO format
                        try:
                            return datetime.fromisoformat(value.replace('Z', '+00:00'))
                        except ValueError:
                            pass
                        
                        # Try common formats
                        formats = [
                            "%Y-%m-%d %H:%M:%S",
                            "%Y-%m-%d %H:%M",
                            "%d-%m-%Y %H:%M:%S",
                            "%d/%m/%Y %H:%M:%S",
                        ]
                        for fmt in formats:
                            try:
                                return datetime.strptime(value, fmt)
                            except ValueError:
                                continue
                except Exception:
                    continue
        
        # Default to now
        return datetime.utcnow()
    
    def _extract_symbols(self, payload: Dict[str, Any]) -> List[ChartInkSymbol]:
        """Extract symbols from ChartInk payload"""
        symbols = []
        
        # Check for direct symbol list
        if "symbols" in payload and isinstance(payload["symbols"], list):
            for sym_data in payload["symbols"]:
                symbol = self._parse_symbol_data(sym_data)
                if symbol:
                    symbols.append(symbol)
        
        # Check for stocks field
        elif "stocks" in payload and isinstance(payload["stocks"], list):
            for sym_data in payload["stocks"]:
                symbol = self._parse_symbol_data(sym_data)
                if symbol:
                    symbols.append(symbol)
        
        # Check for data field
        elif "data" in payload and isinstance(payload["data"], list):
            for sym_data in payload["data"]:
                symbol = self._parse_symbol_data(sym_data)
                if symbol:
                    symbols.append(symbol)
        
        # Check for single symbol
        elif "symbol" in payload or "ticker" in payload:
            symbol = self._parse_symbol_data(payload)
            if symbol:
                symbols.append(symbol)
        
        # Check for alert message with symbols
        elif "alert" in payload or "message" in payload:
            message = str(payload.get("alert") or payload.get("message"))
            extracted = self._extract_symbols_from_message(message, payload.get("scan_name"))
            symbols.extend(extracted)
        
        return symbols
    
    def _parse_symbol_data(self, data: Any) -> Optional[ChartInkSymbol]:
        """Parse individual symbol data"""
        if isinstance(data, str):
            # Simple symbol string
            return ChartInkSymbol(
                symbol=self._clean_symbol(data),
                exchange="NSE",
                scan_name=None
            )
        
        if not isinstance(data, dict):
            return None
        
        # Extract symbol
        symbol = None
        symbol_fields = ["symbol", "ticker", "sym", "s", "name", "scrip", "stock"]
        for field in symbol_fields:
            if field in data:
                symbol = self._clean_symbol(str(data[field]))
                break
        
        if not symbol:
            return None
        
        # Extract exchange
        exchange = "NSE"  # Default
        if "exchange" in data:
            exchange = self._normalize_exchange(data["exchange"])
        
        # Extract price
        price = None
        price_fields = ["price", "ltp", "last_price", "close", "current_price"]
        for field in price_fields:
            if field in data:
                try:
                    price = float(data[field])
                    break
                except (ValueError, TypeError):
                    continue
        
        # Extract volume
        volume = None
        volume_fields = ["volume", "vol", "quantity", "qty"]
        for field in volume_fields:
            if field in data:
                try:
                    volume = int(data[field])
                    break
                except (ValueError, TypeError):
                    continue
        
        # Extract change percent
        change_percent = None
        change_fields = ["change_percent", "change", "percent_change", "pchange"]
        for field in change_fields:
            if field in data:
                try:
                    change_percent = float(data[field])
                    break
                except (ValueError, TypeError):
                    continue
        
        # Extract scan name
        scan_name = None
        if "scan_name" in data:
            scan_name = str(data["scan_name"])
        
        # Extract conditions
        conditions = {}
        condition_fields = [
            "conditions", "filters", "criteria", "metrics", "indicators"
        ]
        for field in condition_fields:
            if field in data and isinstance(data[field], dict):
                conditions.update(data[field])
                break
        
        # Add any remaining fields as conditions
        known_fields = set(symbol_fields + ["exchange"] + price_fields + volume_fields + 
                          change_fields + ["scan_name"] + condition_fields)
        for key, value in data.items():
            if key not in known_fields:
                conditions[key] = value
        
        return ChartInkSymbol(
            symbol=symbol,
            exchange=exchange,
            price=price,
            volume=volume,
            change_percent=change_percent,
            scan_name=scan_name,
            conditions=conditions
        )
    
    def _extract_symbols_from_message(
        self,
        message: str,
        scan_name: Optional[str] = None
    ) -> List[ChartInkSymbol]:
        """Extract symbols from alert message text"""
        symbols = []
        
        # Pattern 1: NSE:SYMBOL format
        pattern1 = r'(?:NSE|BSE|MCX)[:\-]?\s*([A-Z]+\d*)'
        matches = re.findall(pattern1, message, re.IGNORECASE)
        for match in matches:
            symbols.append(ChartInkSymbol(
                symbol=self._clean_symbol(match),
                exchange="NSE",
                scan_name=scan_name
            ))
        
        # Pattern 2: Symbol list (comma or space separated)
        if not symbols:
            # Look for capitalized words that look like symbols
            words = re.findall(r'\b[A-Z]{2,10}\b', message)
            for word in words:
                # Filter out common non-symbol words
                if word not in ["NSE", "BSE", "MCX", "THE", "AND", "FOR", "BUY", "SELL"]:
                    symbols.append(ChartInkSymbol(
                        symbol=word,
                        exchange="NSE",
                        scan_name=scan_name
                    ))
        
        return symbols
    
    def _clean_symbol(self, symbol: str) -> str:
        """Clean and normalize symbol"""
        # Remove exchange prefix if present
        symbol = re.sub(r'^(NSE|BSE|MCX|NFO|CDS|BFO)[:\-]', '', symbol, flags=re.IGNORECASE)
        return symbol.strip().upper()
    
    def _normalize_exchange(self, exchange: str) -> str:
        """Normalize exchange name"""
        exchange_lower = str(exchange).lower().strip()
        return self.EXCHANGE_MAP.get(exchange_lower, exchange_upper.upper())
    
    async def enrich_symbols(
        self,
        symbols: List[ChartInkSymbol],
        market_data_service=None
    ) -> List[ChartInkSymbol]:
        """
        Enrich symbols with market data
        
        Args:
            symbols: List of ChartInk symbols
            market_data_service: Optional market data service for fetching prices
            
        Returns:
            Enriched symbols list
            
        Requirements: 3.5
        """
        if not market_data_service:
            self.logger.warning("No market data service available for enrichment")
            return symbols
        
        try:
            # Fetch market data for symbols without price
            symbols_to_enrich = [s for s in symbols if s.price is None]
            
            if not symbols_to_enrich:
                return symbols
            
            symbol_names = [s.symbol for s in symbols_to_enrich]
            
            # Fetch data (this would call your market data service)
            market_data = await self._fetch_market_data(symbol_names, market_data_service)
            
            # Update symbols with market data
            for symbol in symbols_to_enrich:
                if symbol.symbol in market_data:
                    data = market_data[symbol.symbol]
                    if not symbol.price and "price" in data:
                        symbol.price = data["price"]
                    if not symbol.volume and "volume" in data:
                        symbol.volume = data["volume"]
                    if not symbol.change_percent and "change_percent" in data:
                        symbol.change_percent = data["change_percent"]
            
            return symbols
            
        except Exception as e:
            self.logger.error(f"Error enriching symbols: {str(e)}")
            return symbols
    
    async def _fetch_market_data(
        self,
        symbols: List[str],
        market_data_service
    ) -> Dict[str, Dict[str, Any]]:
        """Fetch market data for symbols"""
        # This would integrate with your market data service
        # For now, return empty dict
        return {}
    
    def batch_process(
        self,
        alert: ChartInkAlert,
        default_action: SignalAction = SignalAction.BUY
    ) -> List[Dict[str, Any]]:
        """
        Batch process symbols into signals
        
        Args:
            alert: Parsed ChartInk alert
            default_action: Default action for signals
            
        Returns:
            List of signal dictionaries
            
        Requirements: 3.6
        """
        signals = []
        
        for symbol in alert.symbols:
            signal = {
                "symbol": symbol.symbol,
                "exchange": symbol.exchange,
                "action": default_action.value,
                "quantity": 1,
                "price": symbol.price,
                "order_type": "MARKET",
                "product_type": "INTRADAY",
                "scan_name": alert.scan_name,
                "scan_url": alert.scan_url,
                "alert_time": alert.alert_time.isoformat(),
                "price_data": {
                    "ltp": symbol.price,
                    "volume": symbol.volume,
                    "change_percent": symbol.change_percent,
                },
                "conditions": symbol.conditions,
                "source": "chartink"
            }
            signals.append(signal)
        
        return signals
    
    def validate_alert(self, payload: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Validate ChartInk alert format
        
        Args:
            payload: Payload to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not payload:
            return False, "Empty payload"
        
        if not isinstance(payload, dict):
            return False, "Payload must be a JSON object"
        
        # Check for required fields (scan name or symbols)
        has_scan_name = any(
            field in payload for field in ["scan_name", "scanner_name", "name"]
        )
        
        has_symbols = any(
            field in payload and payload[field] for field in 
            ["symbols", "stocks", "data", "symbol"]
        )
        
        if not has_scan_name and not has_symbols:
            return False, "Missing required fields: scan_name or symbols"
        
        return True, None
