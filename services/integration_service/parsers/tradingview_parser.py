"""
TradingView Parser

Parses TradingView webhook alert payloads.
Requirements: 1.2, 1.5
"""

import re
import logging
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

from services.integration_service.models.webhook_models import SignalAction

logger = logging.getLogger(__name__)


@dataclass
class ParsedSignal:
    """Parsed signal from TradingView alert"""
    symbol: str
    action: SignalAction
    quantity: int
    price: Optional[float]
    order_type: str
    product_type: str
    raw_message: str
    parameters: Dict[str, Any]


class TradingViewParser:
    """
    Parser for TradingView webhook alerts
    
    Supports TradingView alert syntax:
    - {{ticker}} - Trading symbol
    - {{close}} - Current price
    - {{open}} - Open price
    - {{high}} - High price
    - {{low}} - Low price
    - {{volume}} - Volume
    - {{strategy.order.action}} - Buy/Sell action
    - {{strategy.order.contracts}} - Quantity
    - {{strategy.order.price}} - Order price
    - {{time}} - Timestamp
    """
    
    # Order type mappings
    ORDER_TYPE_MAP = {
        "market": "MARKET",
        "limit": "LIMIT",
        "stop": "STOP_LOSS",
        "stop_market": "STOP_LOSS_MARKET",
        "sl": "STOP_LOSS",
        "slm": "STOP_LOSS_MARKET",
    }
    
    # Product type mappings
    PRODUCT_TYPE_MAP = {
        "intraday": "INTRADAY",
        "delivery": "DELIVERY",
        "margin": "MARGIN",
        "carryforward": "DELIVERY",
        "cnc": "DELIVERY",  # Cash and Carry
        "mis": "INTRADAY",  # Margin Intraday Squareoff
        "nrml": "MARGIN",   # Normal
    }
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def parse_alert(self, payload: Dict[str, Any]) -> Optional[ParsedSignal]:
        """
        Parse TradingView alert payload
        
        Args:
            payload: TradingView webhook payload dict
            
        Returns:
            ParsedSignal or None if parsing fails
            
        Requirements: 1.2, 1.5
        """
        try:
            self.logger.debug(f"Parsing TradingView payload: {payload}")
            
            # Extract basic fields
            symbol = self._extract_symbol(payload)
            action = self._extract_action(payload)
            quantity = self._extract_quantity(payload)
            price = self._extract_price(payload)
            order_type = self._extract_order_type(payload)
            product_type = self._extract_product_type(payload)
            
            if not symbol:
                self.logger.error("No symbol found in TradingView payload")
                return None
            
            if not action:
                self.logger.error("No action found in TradingView payload")
                return None
            
            # Get raw message if available
            raw_message = payload.get("message", "")
            if not raw_message:
                raw_message = str(payload)
            
            # Extract additional parameters
            parameters = self._extract_parameters(payload)
            
            return ParsedSignal(
                symbol=symbol,
                action=action,
                quantity=quantity,
                price=price,
                order_type=order_type,
                product_type=product_type,
                raw_message=raw_message,
                parameters=parameters
            )
            
        except Exception as e:
            self.logger.error(f"Error parsing TradingView payload: {str(e)}")
            return None
    
    def _extract_symbol(self, payload: Dict[str, Any]) -> Optional[str]:
        """Extract symbol from payload"""
        # Try common symbol fields
        symbol_fields = ["ticker", "symbol", "sym", "s", "instrument", "scrip", "stock"]
        
        for field in symbol_fields:
            if field in payload:
                symbol = str(payload[field]).strip().upper()
                # Clean symbol (remove exchange prefix if present)
                symbol = self._clean_symbol(symbol)
                return symbol
        
        # Try to extract from message
        if "message" in payload:
            message = str(payload["message"])
            # Look for patterns like "SYMBOL: BUY" or "BUY SYMBOL"
            patterns = [
                r'([A-Z]+\d*\.?[A-Z]*)\s*[:\-]?\s*(?:buy|sell|exit)',
                r'(?:buy|sell|exit)\s+([A-Z]+\d*\.?[A-Z]*)',
            ]
            for pattern in patterns:
                match = re.search(pattern, message, re.IGNORECASE)
                if match:
                    return self._clean_symbol(match.group(1))
        
        return None
    
    def _clean_symbol(self, symbol: str) -> str:
        """Clean and normalize symbol"""
        # Remove common exchange prefixes
        symbol = re.sub(r'^(NSE|BSE|MCX|NFO|CDS|BFO)[:\-]', '', symbol, flags=re.IGNORECASE)
        # Remove extra spaces
        symbol = symbol.strip()
        # Ensure uppercase
        symbol = symbol.upper()
        return symbol
    
    def _extract_action(self, payload: Dict[str, Any]) -> Optional[SignalAction]:
        """Extract action from payload"""
        # Check strategy order action
        strategy_action = payload.get("strategy", {}).get("order_action", "")
        if strategy_action:
            return self._normalize_action(strategy_action)
        
        # Check action field
        if "action" in payload:
            return self._normalize_action(payload["action"])
        
        # Check side field
        if "side" in payload:
            return self._normalize_action(payload["side"])
        
        # Try to extract from message
        if "message" in payload:
            message = str(payload["message"]).lower()
            if "buy" in message and "sell" not in message:
                return SignalAction.BUY
            elif "sell" in message and "buy" not in message:
                return SignalAction.SELL
            elif "exit_long" in message or "exit long" in message:
                return SignalAction.EXIT_LONG
            elif "exit_short" in message or "exit short" in message:
                return SignalAction.EXIT_SHORT
        
        return None
    
    def _normalize_action(self, action: str) -> Optional[SignalAction]:
        """Normalize action string to SignalAction"""
        action_str = str(action).lower().strip()
        
        if action_str in ["buy", "long", "entry_long", "entry long"]:
            return SignalAction.BUY
        elif action_str in ["sell", "short", "entry_short", "entry short"]:
            return SignalAction.SELL
        elif action_str in ["exit_long", "exit long", "close_long", "close long"]:
            return SignalAction.EXIT_LONG
        elif action_str in ["exit_short", "exit short", "close_short", "close short"]:
            return SignalAction.EXIT_SHORT
        
        return None
    
    def _extract_quantity(self, payload: Dict[str, Any]) -> int:
        """Extract quantity from payload"""
        # Try strategy order contracts
        quantity = payload.get("strategy", {}).get("order_contracts", 0)
        if quantity:
            return int(quantity)
        
        # Check quantity field
        if "quantity" in payload:
            return int(payload["quantity"])
        
        # Check qty field
        if "qty" in payload:
            return int(payload["qty"])
        
        # Check contracts field
        if "contracts" in payload:
            return int(payload["contracts"])
        
        # Check shares field
        if "shares" in payload:
            return int(payload["shares"])
        
        # Default quantity
        return 1
    
    def _extract_price(self, payload: Dict[str, Any]) -> Optional[float]:
        """Extract price from payload"""
        # Try strategy order price
        price = payload.get("strategy", {}).get("order_price")
        if price is not None:
            return float(price)
        
        # Check price field
        if "price" in payload:
            return float(payload["price"])
        
        # Check limit_price field
        if "limit_price" in payload:
            return float(payload["limit_price"])
        
        # Check trigger_price for stop orders
        if "trigger_price" in payload:
            return float(payload["trigger_price"])
        
        return None
    
    def _extract_order_type(self, payload: Dict[str, Any]) -> str:
        """Extract order type from payload"""
        # Try strategy order type
        order_type = payload.get("strategy", {}).get("order_type", "")
        if order_type:
            normalized = self.ORDER_TYPE_MAP.get(order_type.lower(), order_type.upper())
            return normalized
        
        # Check order_type field
        if "order_type" in payload:
            normalized = self.ORDER_TYPE_MAP.get(
                str(payload["order_type"]).lower(),
                str(payload["order_type"]).upper()
            )
            return normalized
        
        # Check type field
        if "type" in payload:
            normalized = self.ORDER_TYPE_MAP.get(
                str(payload["type"]).lower(),
                str(payload["type"]).upper()
            )
            return normalized
        
        # Default based on price presence
        if "price" in payload or "limit_price" in payload:
            return "LIMIT"
        
        return "MARKET"
    
    def _extract_product_type(self, payload: Dict[str, Any]) -> str:
        """Extract product type from payload"""
        # Check product field
        if "product" in payload:
            normalized = self.PRODUCT_TYPE_MAP.get(
                str(payload["product"]).lower(),
                str(payload["product"]).upper()
            )
            return normalized
        
        # Check product_type field
        if "product_type" in payload:
            normalized = self.PRODUCT_TYPE_MAP.get(
                str(payload["product_type"]).lower(),
                str(payload["product_type"]).upper()
            )
            return normalized
        
        # Check variety field (used by some brokers)
        if "variety" in payload:
            normalized = self.PRODUCT_TYPE_MAP.get(
                str(payload["variety"]).lower(),
                "INTRADAY"
            )
            return normalized
        
        # Default
        return "INTRADAY"
    
    def _extract_parameters(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Extract additional parameters from payload"""
        parameters = {}
        
        # Extract price-related fields
        price_fields = ["close", "open", "high", "low", "volume", "vwap", "ohlc4"]
        for field in price_fields:
            if field in payload:
                try:
                    parameters[field] = float(payload[field])
                except (ValueError, TypeError):
                    parameters[field] = payload[field]
        
        # Extract time
        if "time" in payload:
            parameters["time"] = payload["time"]
        
        # Extract exchange
        if "exchange" in payload:
            parameters["exchange"] = str(payload["exchange"]).upper()
        
        # Extract trigger price
        if "trigger_price" in payload:
            try:
                parameters["trigger_price"] = float(payload["trigger_price"])
            except (ValueError, TypeError):
                pass
        
        # Extract stop loss and target
        if "stop_loss" in payload:
            try:
                parameters["stop_loss"] = float(payload["stop_loss"])
            except (ValueError, TypeError):
                pass
        
        if "target" in payload or "take_profit" in payload:
            try:
                parameters["target"] = float(payload.get("target") or payload.get("take_profit"))
            except (ValueError, TypeError):
                pass
        
        # Extract strategy name if available
        if "strategy" in payload and isinstance(payload["strategy"], dict):
            strategy_info = payload["strategy"]
            if "strategy_title" in strategy_info:
                parameters["strategy_name"] = strategy_info["strategy_title"]
            if "position_size" in strategy_info:
                parameters["position_size"] = strategy_info["position_size"]
        
        # Extract any additional fields
        known_fields = [
            "ticker", "symbol", "sym", "s", "action", "side", "quantity", "qty",
            "contracts", "shares", "price", "limit_price", "order_type", "type",
            "product", "product_type", "variety", "exchange", "time", "message",
            "strategy", "trigger_price", "stop_loss", "target", "take_profit",
            "close", "open", "high", "low", "volume", "vwap", "ohlc4"
        ]
        
        for key, value in payload.items():
            if key not in known_fields and not key.startswith("_"):
                parameters[f"custom_{key}"] = value
        
        return parameters
    
    def validate_payload(self, payload: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Validate TradingView payload structure
        
        Args:
            payload: Payload to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not payload:
            return False, "Empty payload"
        
        if not isinstance(payload, dict):
            return False, "Payload must be a JSON object"
        
        # Check for required fields (symbol or ticker)
        has_symbol = any(
            field in payload for field in ["ticker", "symbol", "sym", "s"]
        )
        
        if not has_symbol:
            return False, "Missing required field: symbol/ticker"
        
        return True, None
