"""
OpenAlgo-compatible broker adapter.

This adapter integrates with OpenAlgo REST API to support all 30+ Indian brokers
that OpenAlgo supports, including Angel One, Zerodha, Upstox, Fyers, etc.

OpenAlgo API Reference: https://github.com/marketcalls/openalgo
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


class OpenAlgoAdapter(BrokerAdapter):
    """
    OpenAlgo REST API adapter for Indian brokers.
    
    Supports: Angel One, Zerodha, Upstox, Fyers, Shoonya, Finvasia, and 25+ more.
    """
    
    def __init__(self, config: Dict[str, Any], paper_trading: bool = False):
        """
        Initialize OpenAlgo adapter.
        
        Config should contain:
        - base_url: OpenAlgo server URL (e.g., "http://localhost:5000")
        - api_key: OpenAlgo API key
        - broker: Broker name (e.g., "angelone", "zerodha", "upstox")
        - client_id: Broker client ID (optional, for some brokers)
        """
        self.client: Optional[httpx.AsyncClient] = None
        super().__init__(config, paper_trading)
    
    def _validate_config(self) -> None:
        """Validate OpenAlgo configuration."""
        required_fields = ["base_url", "api_key", "broker"]
        for field in required_fields:
            if field not in self.config:
                raise ValueError(f"Missing required config field: {field}")
        
        # Validate broker name
        supported_brokers = [
            "angelone", "zerodha", "upstox", "fyers", "shoonya", "finvasia",
            "aliceblue", "5paisa", "iifl", "kotak", "motilal", "icici"
        ]
        broker = self.config["broker"].lower()
        if broker not in supported_brokers:
            logger.warning(f"Broker '{broker}' may not be supported by OpenAlgo")
    
    async def connect(self) -> bool:
        """Establish connection to OpenAlgo server."""
        try:
            self.client = httpx.AsyncClient(
                base_url=self.config["base_url"],
                headers={
                    "Authorization": f"Bearer {self.config['api_key']}",
                    "Content-Type": "application/json"
                },
                timeout=30.0
            )
            
            # Test connection
            response = await self.client.get("/api/v1/status")
            if response.status_code == 200:
                logger.info(f"Connected to OpenAlgo server for broker: {self.config['broker']}")
                return True
            else:
                logger.error(f"OpenAlgo connection failed: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to connect to OpenAlgo: {e}")
            return False
    
    async def disconnect(self) -> None:
        """Close connection to OpenAlgo server."""
        if self.client:
            await self.client.aclose()
            self.client = None
            logger.info("Disconnected from OpenAlgo")
    
    async def place_order(self, order: Order) -> Order:
        """
        Place order via OpenAlgo API.
        
        OpenAlgo endpoint: POST /api/v1/placeorder
        """
        if not self.client:
            raise RuntimeError("Not connected to OpenAlgo. Call connect() first.")
        
        # Map to OpenAlgo format
        payload = {
            "symbol": order.symbol,
            "exchange": order.exchange,
            "action": order.side.value,
            "quantity": int(order.quantity),
            "price": order.price or 0,
            "trigger_price": order.trigger_price or 0,
            "pricetype": self._map_order_type(order.order_type),
            "product": self._map_product_type(order.product_type),
            "ordertype": "MARKET" if order.order_type == OrderType.MARKET else "LIMIT",
            "validity": order.validity,
            "disclosed_quantity": order.disclosed_quantity or 0,
            "tag": order.tag or ""
        }
        
        if self.paper_trading:
            # Simulate order placement
            order.broker_order_id = f"PAPER_{datetime.utcnow().timestamp()}"
            order.status = OrderStatus.FILLED
            order.filled_quantity = order.quantity
            order.average_price = order.price or 0
            order.placed_at = datetime.utcnow()
            logger.info(f"[PAPER] Placed order: {order.symbol} {order.side} {order.quantity}")
            return order
        
        try:
            response = await self.client.post("/api/v1/placeorder", json=payload)
            response.raise_for_status()
            
            result = response.json()
            
            # Update order with response
            order.broker_order_id = result.get("orderid")
            order.status = OrderStatus.OPEN
            order.placed_at = datetime.utcnow()
            order.metadata["openalgo_response"] = result
            
            logger.info(f"Order placed: {order.broker_order_id} for {order.symbol}")
            return order
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Order placement failed: {e.response.text}")
            order.status = OrderStatus.REJECTED
            order.metadata["error"] = e.response.text
            raise Exception(f"Order placement failed: {e.response.text}")
        except Exception as e:
            logger.error(f"Order placement error: {e}")
            order.status = OrderStatus.REJECTED
            raise
    
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel order via OpenAlgo API."""
        if not self.client:
            raise RuntimeError("Not connected to OpenAlgo")
        
        if self.paper_trading:
            logger.info(f"[PAPER] Cancelled order: {order_id}")
            return True
        
        try:
            payload = {"orderid": order_id}
            response = await self.client.post("/api/v1/cancelorder", json=payload)
            response.raise_for_status()
            
            result = response.json()
            success = result.get("status") == "success"
            
            if success:
                logger.info(f"Order cancelled: {order_id}")
            else:
                logger.warning(f"Order cancellation failed: {result}")
            
            return success
            
        except Exception as e:
            logger.error(f"Order cancellation error: {e}")
            return False
    
    async def modify_order(self, order_id: str, quantity: Optional[float] = None,
                          price: Optional[float] = None,
                          trigger_price: Optional[float] = None) -> Order:
        """Modify order via OpenAlgo API."""
        if not self.client:
            raise RuntimeError("Not connected to OpenAlgo")
        
        payload = {"orderid": order_id}
        if quantity is not None:
            payload["quantity"] = int(quantity)
        if price is not None:
            payload["price"] = price
        if trigger_price is not None:
            payload["trigger_price"] = trigger_price
        
        if self.paper_trading:
            # Return a mock modified order
            order = Order(
                symbol="MOCK",
                exchange="NSE",
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                quantity=quantity or 1,
                price=price,
                broker_order_id=order_id,
                status=OrderStatus.OPEN
            )
            logger.info(f"[PAPER] Modified order: {order_id}")
            return order
        
        try:
            response = await self.client.post("/api/v1/modifyorder", json=payload)
            response.raise_for_status()
            
            result = response.json()
            
            # Fetch updated order details
            return await self.get_order_status(order_id)
            
        except Exception as e:
            logger.error(f"Order modification error: {e}")
            raise
    
    async def get_order_status(self, order_id: str) -> Order:
        """Get order status via OpenAlgo API."""
        if not self.client:
            raise RuntimeError("Not connected to OpenAlgo")
        
        if self.paper_trading:
            # Return mock filled order
            return Order(
                symbol="MOCK",
                exchange="NSE",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=1,
                broker_order_id=order_id,
                status=OrderStatus.FILLED,
                filled_quantity=1,
                average_price=100.0
            )
        
        try:
            response = await self.client.get(f"/api/v1/orderbook")
            response.raise_for_status()
            
            result = response.json()
            orders = result.get("data", [])
            
            # Find the specific order
            for order_data in orders:
                if order_data.get("orderid") == order_id:
                    return self._parse_order(order_data)
            
            raise ValueError(f"Order not found: {order_id}")
            
        except Exception as e:
            logger.error(f"Get order status error: {e}")
            raise
    
    async def get_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """Get all orders via OpenAlgo API."""
        if not self.client:
            raise RuntimeError("Not connected to OpenAlgo")
        
        if self.paper_trading:
            return []
        
        try:
            response = await self.client.get("/api/v1/orderbook")
            response.raise_for_status()
            
            result = response.json()
            orders = result.get("data", [])
            
            parsed_orders = [self._parse_order(o) for o in orders]
            
            if symbol:
                parsed_orders = [o for o in parsed_orders if o.symbol == symbol]
            
            return parsed_orders
            
        except Exception as e:
            logger.error(f"Get orders error: {e}")
            return []
    
    async def get_positions(self) -> List[Position]:
        """Get positions via OpenAlgo API."""
        if not self.client:
            raise RuntimeError("Not connected to OpenAlgo")
        
        if self.paper_trading:
            return []
        
        try:
            response = await self.client.get("/api/v1/positionbook")
            response.raise_for_status()
            
            result = response.json()
            positions = result.get("data", [])
            
            return [self._parse_position(p) for p in positions]
            
        except Exception as e:
            logger.error(f"Get positions error: {e}")
            return []
    
    async def get_position(self, symbol: str, exchange: str) -> Optional[Position]:
        """Get specific position."""
        positions = await self.get_positions()
        for pos in positions:
            if pos.symbol == symbol and pos.exchange == exchange:
                return pos
        return None
    
    async def get_margin(self) -> MarginInfo:
        """Get margin info via OpenAlgo API."""
        if not self.client:
            raise RuntimeError("Not connected to OpenAlgo")
        
        if self.paper_trading:
            return MarginInfo(
                available_cash=100000.0,
                used_margin=0.0,
                total_margin=100000.0
            )
        
        try:
            response = await self.client.get("/api/v1/funds")
            response.raise_for_status()
            
            result = response.json()
            data = result.get("data", {})
            
            return MarginInfo(
                available_cash=float(data.get("availablecash", 0)),
                used_margin=float(data.get("utilisedmargin", 0)),
                total_margin=float(data.get("totalmargin", 0)),
                collateral=float(data.get("collateral", 0)),
                metadata=data
            )
            
        except Exception as e:
            logger.error(f"Get margin error: {e}")
            raise
    
    async def get_holdings(self) -> List[Position]:
        """Get holdings via OpenAlgo API."""
        if not self.client:
            raise RuntimeError("Not connected to OpenAlgo")
        
        if self.paper_trading:
            return []
        
        try:
            response = await self.client.get("/api/v1/holdings")
            response.raise_for_status()
            
            result = response.json()
            holdings = result.get("data", [])
            
            return [self._parse_holding(h) for h in holdings]
            
        except Exception as e:
            logger.error(f"Get holdings error: {e}")
            return []
    
    def _map_order_type(self, order_type: OrderType) -> str:
        """Map OrderType to OpenAlgo format."""
        mapping = {
            OrderType.MARKET: "MARKET",
            OrderType.LIMIT: "LIMIT",
            OrderType.STOP_LOSS: "SL",
            OrderType.STOP_LOSS_LIMIT: "SL-M"
        }
        return mapping.get(order_type, "MARKET")
    
    def _map_product_type(self, product_type: ProductType) -> str:
        """Map ProductType to OpenAlgo format."""
        mapping = {
            ProductType.DELIVERY: "CNC",
            ProductType.INTRADAY: "MIS",
            ProductType.MARGIN: "NRML",
            ProductType.BO: "BO",
            ProductType.CO: "CO"
        }
        return mapping.get(product_type, "MIS")
    
    def _parse_order(self, data: Dict[str, Any]) -> Order:
        """Parse OpenAlgo order response to Order object."""
        return Order(
            symbol=data.get("symbol", ""),
            exchange=data.get("exchange", ""),
            side=OrderSide.BUY if data.get("action") == "BUY" else OrderSide.SELL,
            order_type=OrderType.MARKET if data.get("ordertype") == "MARKET" else OrderType.LIMIT,
            quantity=float(data.get("quantity", 0)),
            price=float(data.get("price", 0)) if data.get("price") else None,
            broker_order_id=data.get("orderid"),
            status=self._parse_order_status(data.get("status", "")),
            filled_quantity=float(data.get("filledqty", 0)),
            average_price=float(data.get("avgprice", 0)) if data.get("avgprice") else None,
            metadata=data
        )
    
    def _parse_order_status(self, status: str) -> OrderStatus:
        """Parse OpenAlgo order status to OrderStatus enum."""
        status_map = {
            "OPEN": OrderStatus.OPEN,
            "COMPLETE": OrderStatus.FILLED,
            "CANCELLED": OrderStatus.CANCELLED,
            "REJECTED": OrderStatus.REJECTED,
            "PENDING": OrderStatus.PENDING
        }
        return status_map.get(status.upper(), OrderStatus.PENDING)
    
    def _parse_position(self, data: Dict[str, Any]) -> Position:
        """Parse OpenAlgo position response to Position object."""
        quantity = float(data.get("netqty", 0))
        avg_price = float(data.get("avgprice", 0))
        last_price = float(data.get("ltp", 0))
        pnl = float(data.get("pnl", 0))
        
        return Position(
            symbol=data.get("symbol", ""),
            exchange=data.get("exchange", ""),
            product_type=ProductType.INTRADAY,  # Default
            quantity=quantity,
            average_price=avg_price,
            last_price=last_price,
            pnl=pnl,
            pnl_percentage=(pnl / (abs(quantity) * avg_price) * 100) if quantity != 0 and avg_price != 0 else 0,
            buy_quantity=float(data.get("buyqty", 0)),
            sell_quantity=float(data.get("sellqty", 0)),
            metadata=data
        )
    
    def _parse_holding(self, data: Dict[str, Any]) -> Position:
        """Parse OpenAlgo holding response to Position object."""
        quantity = float(data.get("quantity", 0))
        avg_price = float(data.get("avgprice", 0))
        last_price = float(data.get("ltp", 0))
        pnl = (last_price - avg_price) * quantity
        
        return Position(
            symbol=data.get("symbol", ""),
            exchange=data.get("exchange", ""),
            product_type=ProductType.DELIVERY,
            quantity=quantity,
            average_price=avg_price,
            last_price=last_price,
            pnl=pnl,
            pnl_percentage=(pnl / (quantity * avg_price) * 100) if quantity != 0 and avg_price != 0 else 0,
            metadata=data
        )
