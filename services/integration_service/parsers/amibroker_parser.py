"""
Amibroker Parser

Parses Amibroker AFL-generated signal payloads.
Requirements: 2.3, 2.4
"""

import re
import logging
from typing import Dict, Any, Optional, Tuple, List
from dataclasses import dataclass
from datetime import datetime

from services.integration_service.models.webhook_models import SignalAction

logger = logging.getLogger(__name__)


@dataclass
class AFLParameters:
    """AFL signal parameters"""
    symbol: str
    action: SignalAction
    quantity: int
    price: Optional[float]
    order_type: str
    product_type: str
    time_frame: str
    strategy_name: Optional[str]
    custom_fields: Dict[str, Any]


class AmibrokerParser:
    """
    Parser for Amibroker AFL-generated signals
    
    Supports AFL signal format with fields:
    - Symbol: Trading symbol
    - Action: Buy/Sell/Short/Cover
    - Quantity: Number of shares/contracts
    - Price: Entry/exit price
    - OrderType: Market/Limit/Stop
    - TimeFrame: 1m, 5m, 15m, 1h, 1d, etc.
    """
    
    # Action mappings from AFL to standard
    ACTION_MAP = {
        "buy": SignalAction.BUY,
        "long": SignalAction.BUY,
        "sell": SignalAction.SELL,
        "short": SignalAction.SELL,
        "cover": SignalAction.EXIT_SHORT,
        "covershort": SignalAction.EXIT_SHORT,
        "exitlong": SignalAction.EXIT_LONG,
        "exit_long": SignalAction.EXIT_LONG,
        "exitshort": SignalAction.EXIT_SHORT,
        "exit_short": SignalAction.EXIT_SHORT,
    }
    
    # Order type mappings
    ORDER_TYPE_MAP = {
        "market": "MARKET",
        "m": "MARKET",
        "limit": "LIMIT",
        "l": "LIMIT",
        "stop": "STOP_LOSS",
        "sl": "STOP_LOSS",
        "stoplimit": "STOP_LOSS",
        "stplmt": "STOP_LOSS",
    }
    
    # Product type mappings
    PRODUCT_TYPE_MAP = {
        "intraday": "INTRADAY",
        "mis": "INTRADAY",
        "delivery": "DELIVERY",
        "cnc": "DELIVERY",
        "carryforward": "DELIVERY",
        "margin": "MARGIN",
        "nrml": "MARGIN",
    }
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def parse_signal(self, payload: Dict[str, Any]) -> Optional[AFLParameters]:
        """
        Parse Amibroker signal payload
        
        Args:
            payload: AFL signal payload dict
            
        Returns:
            AFLParameters or None if parsing fails
            
        Requirements: 2.3, 2.4
        """
        try:
            self.logger.debug(f"Parsing Amibroker payload: {payload}")
            
            # Extract symbol
            symbol = self._extract_symbol(payload)
            if not symbol:
                self.logger.error("No symbol found in Amibroker payload")
                return None
            
            # Extract action
            action = self._extract_action(payload)
            if not action:
                self.logger.error("No action found in Amibroker payload")
                return None
            
            # Extract other parameters
            quantity = self._extract_quantity(payload)
            price = self._extract_price(payload)
            order_type = self._extract_order_type(payload)
            product_type = self._extract_product_type(payload)
            time_frame = self._extract_timeframe(payload)
            strategy_name = self._extract_strategy_name(payload)
            
            # Extract custom fields
            custom_fields = self._extract_custom_fields(payload)
            
            return AFLParameters(
                symbol=symbol,
                action=action,
                quantity=quantity,
                price=price,
                order_type=order_type,
                product_type=product_type,
                time_frame=time_frame,
                strategy_name=strategy_name,
                custom_fields=custom_fields
            )
            
        except Exception as e:
            self.logger.error(f"Error parsing Amibroker payload: {str(e)}")
            return None
    
    def _extract_symbol(self, payload: Dict[str, Any]) -> Optional[str]:
        """Extract symbol from AFL payload"""
        # Common symbol fields
        symbol_fields = ["symbol", "ticker", "sym", "s", "name", "instrument", "scrip"]
        
        for field in symbol_fields:
            if field in payload:
                symbol = str(payload[field]).strip().upper()
                # Remove exchange prefix if present
                symbol = self._clean_symbol(symbol)
                return symbol
        
        return None
    
    def _clean_symbol(self, symbol: str) -> str:
        """Clean and normalize symbol"""
        # Remove exchange prefixes
        symbol = re.sub(r'^(NSE|BSE|MCX|NFO|CDS|BFO)[:\-]', '', symbol, flags=re.IGNORECASE)
        return symbol.strip()
    
    def _extract_action(self, payload: Dict[str, Any]) -> Optional[SignalAction]:
        """Extract action from AFL payload"""
        # Check action field
        if "action" in payload:
            return self._normalize_action(payload["action"])
        
        # Check signal field
        if "signal" in payload:
            return self._normalize_action(payload["signal"])
        
        # Check side field
        if "side" in payload:
            return self._normalize_action(payload["side"])
        
        # Check for action in comment/description
        if "comment" in payload:
            comment = str(payload["comment"]).lower()
            action = self._parse_action_from_text(comment)
            if action:
                return action
        
        if "description" in payload:
            desc = str(payload["description"]).lower()
            action = self._parse_action_from_text(desc)
            if action:
                return action
        
        return None
    
    def _normalize_action(self, action: str) -> Optional[SignalAction]:
        """Normalize AFL action to SignalAction"""
        action_str = str(action).lower().strip()
        
        # Direct mapping
        if action_str in self.ACTION_MAP:
            return self.ACTION_MAP[action_str]
        
        # Numeric mapping (some AFL scripts use 1=Buy, -1=Sell)
        try:
            action_num = int(action_str)
            if action_num > 0:
                return SignalAction.BUY
            elif action_num < 0:
                return SignalAction.SELL
        except ValueError:
            pass
        
        # Boolean mapping (True=Buy, False=Sell)
        if action_str in ["true", "1", "yes"]:
            return SignalAction.BUY
        if action_str in ["false", "0", "no"]:
            return SignalAction.SELL
        
        return None
    
    def _parse_action_from_text(self, text: str) -> Optional[SignalAction]:
        """Parse action from text description"""
        text = text.lower()
        
        if "buy" in text and "sell" not in text:
            return SignalAction.BUY
        if "sell" in text and "buy" not in text:
            return SignalAction.SELL
        if "short" in text:
            return SignalAction.SELL
        if "cover" in text:
            return SignalAction.EXIT_SHORT
        if "exit" in text and "long" in text:
            return SignalAction.EXIT_LONG
        if "exit" in text and "short" in text:
            return SignalAction.EXIT_SHORT
        
        return None
    
    def _extract_quantity(self, payload: Dict[str, Any]) -> int:
        """Extract quantity from AFL payload"""
        quantity_fields = ["quantity", "qty", "shares", "contracts", "position_size", "size"]
        
        for field in quantity_fields:
            if field in payload:
                try:
                    return int(payload[field])
                except (ValueError, TypeError):
                    continue
        
        # Check for position size (AFL often uses this)
        if "positionsize" in payload:
            try:
                return int(payload["positionsize"])
            except (ValueError, TypeError):
                pass
        
        return 1
    
    def _extract_price(self, payload: Dict[str, Any]) -> Optional[float]:
        """Extract price from AFL payload"""
        price_fields = ["price", "limit_price", "entry_price", "exit_price", "trigger_price"]
        
        for field in price_fields:
            if field in payload:
                try:
                    return float(payload[field])
                except (ValueError, TypeError):
                    continue
        
        # Check for price in value field (common in AFL)
        if "value" in payload:
            try:
                price = float(payload["value"])
                if price > 0:
                    return price
            except (ValueError, TypeError):
                pass
        
        return None
    
    def _extract_order_type(self, payload: Dict[str, Any]) -> str:
        """Extract order type from AFL payload"""
        order_type_fields = ["order_type", "ordertype", "type", "order"]
        
        for field in order_type_fields:
            if field in payload:
                order_type = str(payload[field]).lower()
                return self.ORDER_TYPE_MAP.get(order_type, order_type.upper())
        
        # Default based on price
        if "price" in payload or "limit_price" in payload:
            return "LIMIT"
        
        return "MARKET"
    
    def _extract_product_type(self, payload: Dict[str, Any]) -> str:
        """Extract product type from AFL payload"""
        product_fields = ["product", "product_type", "producttype", "variety", "type"]
        
        for field in product_fields:
            if field in payload:
                product = str(payload[field]).lower()
                normalized = self.PRODUCT_TYPE_MAP.get(product)
                if normalized:
                    return normalized
                return product.upper()
        
        return "INTRADAY"
    
    def _extract_timeframe(self, payload: Dict[str, Any]) -> str:
        """Extract timeframe from AFL payload"""
        timeframe_fields = ["timeframe", "time_frame", "interval", "period", "resolution"]
        
        for field in timeframe_fields:
            if field in payload:
                return str(payload[field]).upper()
        
        # Default timeframe
        return "1D"
    
    def _extract_strategy_name(self, payload: Dict[str, Any]) -> Optional[str]:
        """Extract strategy name from AFL payload"""
        name_fields = ["strategy_name", "strategy", "strategyname", "system", "name"]
        
        for field in name_fields:
            if field in payload:
                return str(payload[field])
        
        # Check in comment field
        if "comment" in payload:
            comment = str(payload["comment"])
            if comment and not comment.lower() in ["buy", "sell", "long", "short"]:
                return comment
        
        return None
    
    def _extract_custom_fields(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Extract custom AFL fields"""
        known_fields = {
            "symbol", "ticker", "sym", "s", "name", "instrument", "scrip",
            "action", "signal", "side",
            "quantity", "qty", "shares", "contracts", "position_size", "positionsize", "size",
            "price", "limit_price", "entry_price", "exit_price", "trigger_price", "value",
            "order_type", "ordertype", "type", "order",
            "product", "product_type", "producttype", "variety",
            "timeframe", "time_frame", "interval", "period", "resolution",
            "strategy_name", "strategy", "strategyname", "system",
            "comment", "description", "exchange", "date", "time", "timestamp"
        }
        
        custom = {}
        for key, value in payload.items():
            if key.lower() not in known_fields:
                custom[key] = value
        
        return custom
    
    def validate_format(self, payload: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Validate AFL signal format
        
        Args:
            payload: Payload to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not payload:
            return False, "Empty payload"
        
        if not isinstance(payload, dict):
            return False, "Payload must be a JSON object"
        
        # Check for required fields
        has_symbol = any(
            field in payload for field in ["symbol", "ticker", "sym", "s", "name"]
        )
        
        if not has_symbol:
            return False, "Missing required field: symbol"
        
        has_action = any(
            field in payload for field in ["action", "signal", "side"]
        )
        
        if not has_action:
            # Check if action can be inferred from comment
            if "comment" not in payload and "description" not in payload:
                return False, "Missing required field: action"
        
        return True, None
    
    def map_to_signal(
        self,
        afl_params: AFLParameters,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Map AFL parameters to standard signal format
        
        Args:
            afl_params: Parsed AFL parameters
            user_id: User ID
            
        Returns:
            Standard signal dict
        """
        return {
            "user_id": user_id,
            "integration_type": "amibroker",
            "symbol": afl_params.symbol,
            "action": afl_params.action.value,
            "quantity": afl_params.quantity,
            "price": afl_params.price,
            "order_type": afl_params.order_type,
            "product_type": afl_params.product_type,
            "parameters": {
                "time_frame": afl_params.time_frame,
                "strategy_name": afl_params.strategy_name,
                **afl_params.custom_fields
            }
        }
