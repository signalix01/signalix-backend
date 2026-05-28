"""
Alpaca adapter for US equities trading.

Direct integration with Alpaca Markets REST API for US stock execution.
"""

import httpx
from typing import Optional, List, Dict, Any
from datetime import datetime
import logging

from .base import (
    BrokerAdapter, Order, OrderStatus, OrderType, OrderSide,
    Position, MarginInfo, ProductType
)

logger = logging.getLogger(__name__)


class AlpacaAdapter(BrokerAdapter):
    """
    Alpaca Markets adapter for US equities.
    
    Supports stock and options trading on US markets.
    """
    
    # API endpoints
    LIVE_URL = "https://api.alpaca.markets"
    PAPER_URL = "https://paper-api.alpaca.markets"
    
    def __init__(self, config: Dict[str, Any], paper_trading: bool = False):
        """
        Initialize Alpaca adapter.
        
        Config should contain:
        - api_key: Alpaca API key ID
        - api_secret: Alpaca API secret key
        - paper: Use paper trading (optional, default False)
        """
        self.client: Optional[httpx.AsyncClient] = None
        self.use_paper = config.get("paper", False) or paper_trading
        super().__init__(config, paper_trading)
    
    def _validate_config(self) -> None:
        """Validate Alpaca configuration."""
        required_fields = ["api_key", "api_secret"]
        for field in required_fields:
            if field not in self.config:
                raise ValueError(f"Missing required config field: {field}")
    
    def _get_base_url(self) -> str:
        """Get appropriate base URL based on configuration."""
        return self.PAPER_URL if self.use_paper else self.LIVE_URL
    
    async def connect(self) -> bool:
        """Establish connection to Alpaca."""
        try:
            base_url = self._get_base_url()
            self.client = httpx.AsyncClient(
                base_url=base_url,
                headers={
                    "APCA-API-KEY-ID": self.config["api_key"],
                    "APCA-API-SECRET-KEY": self.config["api_secret"]
                },
                timeout=30.0
            )
            
            # Test connection by fetching account info
            response = await self.client.get("/v2/account")
            
            if response.status_code == 200:
                mode = "PAPER" if self.use_paper else "LIVE"
                logger.info(f"Connected to Alpaca ({mode})")
                return True
            else:
                logger.error(f"Alpaca connection failed: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to connect to Alpaca: {e}")
            return False
    
    async def disconnect(self) -> None:
        """Close connection to Alpaca."""
        if self.client:
            await self.client.aclose()
            self.client = None
            logger.info("Disconnected from Alpaca")
    
    async def place_order(self, order: Order) -> Order:
        """Place order on Alpaca."""
        if not self.client:
            raise RuntimeError("Not connected to Alpaca. Call connect() first.")
        
        # Prepare order data
        order_data = {
            "symbol": order.symbol,
            "qty": order.quantity,
            "side": order.side.value.lower(),
            "type": self._map_order_type(order.order_type),
            "time_in_force": "day" if order.validity == "DAY" else "gtc"
        }
        
        if order.order_type == OrderType.LIMIT:
            order_data["limit_price"] = order.price
        
        if order.order_type in [OrderType.STOP_LOSS, OrderType.STOP_LOSS_LIMIT]:
            order_data["stop_price"] = order.trigger_price
            if order.order_type == OrderType.STOP_LOSS_LIMIT:
                order_data["limit_price"] = order.price
        
        # Add extended hours if needed
        if order.metadata.get("extended_hours"):
            order_data["extended_hours"] = True
        
        try:
            response = await self.client.post("/v2/orders", json=order_data)
            response.raise_for_status()
            
            result = response.json()
            
            # Update order with response
            order.broker_order_id = result.get("id")
            order.status = self._parse_order_status(result.get("status"))
            order.placed_at = datetime.fromisoformat(result.get("created_at").replace("Z", "+00:00"))
            order.filled_quantity = float(result.get("filled_qty", 0))
            
            if result.get("filled_avg_price"):
                order.average_price = float(result["filled_avg_price"])
            
            order.metadata["alpaca_response"] = result
            
            logger.info(f"Order placed on Alpaca: {order.broker_order_id} for {order.symbol}")
            return order
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Alpaca order placement failed: {e.response.text}")
            order.status = OrderStatus.REJECTED
            order.metadata["error"] = e.response.text
            raise Exception(f"Order placement failed: {e.response.text}")
        except Exception as e:
            logger.error(f"Alpaca order placement error: {e}")
            order.status = OrderStatus.REJECTED
            raise
    
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel order on Alpaca."""
        if not self.client:
            raise RuntimeError("Not connected to Alpaca")
        
        try:
            response = await self.client.delete(f"/v2/orders/{order_id}")
            response.raise_for_status()
            
            logger.info(f"Order cancelled on Alpaca: {order_id}")
            return True
            
        except Exception as e:
            logger.error(f"Alpaca order cancellation error: {e}")
            return False
    
    async def modify_order(self, order_id: str, quantity: Optional[float] = None,
                          price: Optional[float] = None,
                          trigger_price: Optional[float] = None) -> Order:
        """Modify order on Alpaca."""
        if not self.client:
            raise RuntimeError("Not connected to Alpaca")
        
        # Build modification payload
        patch_data = {}
        if quantity is not None:
            patch_data["qty"] = quantity
        if price is not None:
            patch_data["limit_price"] = price
        if trigger_price is not None:
            patch_data["stop_price"] = trigger_price
        
        try:
            response = await self.client.patch(
                f"/v2/orders/{order_id}",
                json=patch_data
            )
            response.raise_for_status()
            
            result = response.json()
            return self._parse_order(result)
            
        except Exception as e:
            logger.error(f"Alpaca order modification error: {e}")
            raise
    
    async def get_order_status(self, order_id: str) -> Order:
        """Get order status from Alpaca."""
        if not self.client:
            raise RuntimeError("Not connected to Alpaca")
        
        try:
            response = await self.client.get(f"/v2/orders/{order_id}")
            response.raise_for_status()
            
            result = response.json()
            return self._parse_order(result)
            
        except Exception as e:
            logger.error(f"Get order status error: {e}")
            raise
    
    async def get_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """Get all orders from Alpaca."""
        if not self.client:
            raise RuntimeError("Not connected to Alpaca")
        
        try:
            params = {"status": "open"}
            if symbol:
                params["symbols"] = symbol
            
            response = await self.client.get("/v2/orders", params=params)
            response.raise_for_status()
            
            results = response.json()
            return [self._parse_order(o) for o in results]
            
        except Exception as e:
            logger.error(f"Get orders error: {e}")
            return []
    
    async def get_positions(self) -> List[Position]:
        """Get open positions from Alpaca."""
        if not self.client:
            raise RuntimeError("Not connected to Alpaca")
        
        try:
            response = await self.client.get("/v2/positions")
            response.raise_for_status()
            
            results = response.json()
            return [self._parse_position(p) for p in results]
            
        except Exception as e:
            logger.error(f"Get positions error: {e}")
            return []
    
    async def get_position(self, symbol: str, exchange: str) -> Optional[Position]:
        """Get specific position from Alpaca."""
        if not self.client:
            raise RuntimeError("Not connected to Alpaca")
        
        try:
            response = await self.client.get(f"/v2/positions/{symbol}")
            
            if response.status_code == 200:
                result = response.json()
                return self._parse_position(result)
            else:
                return None
            
        except Exception as e:
            logger.error(f"Get position error: {e}")
            return None
    
    async def get_margin(self) -> MarginInfo:
        """Get account balance from Alpaca."""
        if not self.client:
            raise RuntimeError("Not connected to Alpaca")
        
        try:
            response = await self.client.get("/v2/account")
            response.raise_for_status()
            
            result = response.json()
            
            cash = float(result.get("cash", 0))
            buying_power = float(result.get("buying_power", 0))
            portfolio_value = float(result.get("portfolio_value", 0))
            
            return MarginInfo(
                available_cash=cash,
                used_margin=portfolio_value - cash,
                total_margin=buying_power,
                metadata=result
            )
            
        except Exception as e:
            logger.error(f"Get margin error: {e}")
            raise
    
    async def get_holdings(self) -> List[Position]:
        """Get holdings (same as positions for Alpaca)."""
        return await self.get_positions()
    
    def _map_order_type(self, order_type: OrderType) -> str:
        """Map OrderType to Alpaca format."""
        mapping = {
            OrderType.MARKET: "market",
            OrderType.LIMIT: "limit",
            OrderType.STOP_LOSS: "stop",
            OrderType.STOP_LOSS_LIMIT: "stop_limit"
        }
        return mapping.get(order_type, "market")
    
    def _parse_order_status(self, status: str) -> OrderStatus:
        """Parse Alpaca order status to OrderStatus enum."""
        status_map = {
            "new": OrderStatus.OPEN,
            "accepted": OrderStatus.OPEN,
            "pending_new": OrderStatus.PENDING,
            "partially_filled": OrderStatus.PARTIALLY_FILLED,
            "filled": OrderStatus.FILLED,
            "done_for_day": OrderStatus.FILLED,
            "canceled": OrderStatus.CANCELLED,
            "expired": OrderStatus.EXPIRED,
            "replaced": OrderStatus.CANCELLED,
            "pending_cancel": OrderStatus.OPEN,
            "pending_replace": OrderStatus.OPEN,
            "rejected": OrderStatus.REJECTED,
            "suspended": OrderStatus.OPEN,
            "calculated": OrderStatus.OPEN
        }
        return status_map.get(status, OrderStatus.PENDING)
    
    def _parse_order(self, data: Dict[str, Any]) -> Order:
        """Parse Alpaca order response to Order object."""
        return Order(
            symbol=data.get("symbol", ""),
            exchange="ALPACA",
            side=OrderSide.BUY if data.get("side") == "buy" else OrderSide.SELL,
            order_type=OrderType.MARKET if data.get("type") == "market" else OrderType.LIMIT,
            quantity=float(data.get("qty", 0)),
            price=float(data.get("limit_price", 0)) if data.get("limit_price") else None,
            trigger_price=float(data.get("stop_price", 0)) if data.get("stop_price") else None,
            broker_order_id=data.get("id"),
            status=self._parse_order_status(data.get("status", "")),
            filled_quantity=float(data.get("filled_qty", 0)),
            average_price=float(data.get("filled_avg_price", 0)) if data.get("filled_avg_price") else None,
            placed_at=datetime.fromisoformat(data.get("created_at", "").replace("Z", "+00:00")) if data.get("created_at") else None,
            metadata=data
        )
    
    def _parse_position(self, data: Dict[str, Any]) -> Position:
        """Parse Alpaca position response to Position object."""
        quantity = float(data.get("qty", 0))
        avg_price = float(data.get("avg_entry_price", 0))
        current_price = float(data.get("current_price", 0))
        unrealized_pl = float(data.get("unrealized_pl", 0))
        unrealized_plpc = float(data.get("unrealized_plpc", 0))
        
        return Position(
            symbol=data.get("symbol", ""),
            exchange="ALPACA",
            product_type=ProductType.DELIVERY,
            quantity=quantity,
            average_price=avg_price,
            last_price=current_price,
            pnl=unrealized_pl,
            pnl_percentage=unrealized_plpc * 100,
            metadata=data
        )
