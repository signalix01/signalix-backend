"""
OANDA adapter for forex trading.

Direct integration with OANDA v20 REST API for forex execution.
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


class OandaAdapter(BrokerAdapter):
    """
    OANDA forex broker adapter.
    
    Supports forex trading via OANDA v20 API.
    """
    
    # API endpoints
    LIVE_URL = "https://api-fxtrade.oanda.com"
    PRACTICE_URL = "https://api-fxpractice.oanda.com"
    
    def __init__(self, config: Dict[str, Any], paper_trading: bool = False):
        """
        Initialize OANDA adapter.
        
        Config should contain:
        - api_key: OANDA API token
        - account_id: OANDA account ID
        - practice: Use practice account (optional, default False)
        """
        self.client: Optional[httpx.AsyncClient] = None
        self.use_practice = config.get("practice", False) or paper_trading
        super().__init__(config, paper_trading)
    
    def _validate_config(self) -> None:
        """Validate OANDA configuration."""
        required_fields = ["api_key", "account_id"]
        for field in required_fields:
            if field not in self.config:
                raise ValueError(f"Missing required config field: {field}")
    
    def _get_base_url(self) -> str:
        """Get appropriate base URL based on configuration."""
        return self.PRACTICE_URL if self.use_practice else self.LIVE_URL
    
    async def connect(self) -> bool:
        """Establish connection to OANDA."""
        try:
            base_url = self._get_base_url()
            self.client = httpx.AsyncClient(
                base_url=base_url,
                headers={
                    "Authorization": f"Bearer {self.config['api_key']}",
                    "Content-Type": "application/json"
                },
                timeout=30.0
            )
            
            # Test connection by fetching account info
            account_id = self.config["account_id"]
            response = await self.client.get(f"/v3/accounts/{account_id}")
            
            if response.status_code == 200:
                mode = "PRACTICE" if self.use_practice else "LIVE"
                logger.info(f"Connected to OANDA ({mode})")
                return True
            else:
                logger.error(f"OANDA connection failed: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to connect to OANDA: {e}")
            return False
    
    async def disconnect(self) -> None:
        """Close connection to OANDA."""
        if self.client:
            await self.client.aclose()
            self.client = None
            logger.info("Disconnected from OANDA")
    
    async def place_order(self, order: Order) -> Order:
        """Place order on OANDA."""
        if not self.client:
            raise RuntimeError("Not connected to OANDA. Call connect() first.")
        
        account_id = self.config["account_id"]
        
        # Prepare order data
        order_data = {
            "order": {
                "instrument": order.symbol,
                "units": str(int(order.quantity)) if order.side == OrderSide.BUY else str(-int(order.quantity)),
                "type": self._map_order_type(order.order_type),
                "timeInForce": "FOK" if order.order_type == OrderType.MARKET else "GTC",
            }
        }
        
        if order.order_type == OrderType.LIMIT:
            order_data["order"]["price"] = str(order.price)
        
        if order.order_type in [OrderType.STOP_LOSS, OrderType.STOP_LOSS_LIMIT]:
            order_data["order"]["priceBound"] = str(order.trigger_price)
        
        try:
            response = await self.client.post(
                f"/v3/accounts/{account_id}/orders",
                json=order_data
            )
            response.raise_for_status()
            
            result = response.json()
            
            # OANDA returns different structures based on order type
            if "orderFillTransaction" in result:
                # Market order filled immediately
                fill_txn = result["orderFillTransaction"]
                order.broker_order_id = fill_txn.get("id")
                order.status = OrderStatus.FILLED
                order.filled_quantity = abs(float(fill_txn.get("units", 0)))
                order.average_price = float(fill_txn.get("price", 0))
            elif "orderCreateTransaction" in result:
                # Limit/stop order created
                create_txn = result["orderCreateTransaction"]
                order.broker_order_id = create_txn.get("id")
                order.status = OrderStatus.OPEN
            
            order.placed_at = datetime.utcnow()
            order.metadata["oanda_response"] = result
            
            logger.info(f"Order placed on OANDA: {order.broker_order_id} for {order.symbol}")
            return order
            
        except httpx.HTTPStatusError as e:
            logger.error(f"OANDA order placement failed: {e.response.text}")
            order.status = OrderStatus.REJECTED
            order.metadata["error"] = e.response.text
            raise Exception(f"Order placement failed: {e.response.text}")
        except Exception as e:
            logger.error(f"OANDA order placement error: {e}")
            order.status = OrderStatus.REJECTED
            raise
    
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel order on OANDA."""
        if not self.client:
            raise RuntimeError("Not connected to OANDA")
        
        try:
            account_id = self.config["account_id"]
            response = await self.client.put(
                f"/v3/accounts/{account_id}/orders/{order_id}/cancel"
            )
            response.raise_for_status()
            
            logger.info(f"Order cancelled on OANDA: {order_id}")
            return True
            
        except Exception as e:
            logger.error(f"OANDA order cancellation error: {e}")
            return False
    
    async def modify_order(self, order_id: str, quantity: Optional[float] = None,
                          price: Optional[float] = None,
                          trigger_price: Optional[float] = None) -> Order:
        """Modify order on OANDA."""
        if not self.client:
            raise RuntimeError("Not connected to OANDA")
        
        account_id = self.config["account_id"]
        
        # Build modification payload
        order_spec = {}
        if quantity is not None:
            order_spec["units"] = str(int(quantity))
        if price is not None:
            order_spec["price"] = str(price)
        if trigger_price is not None:
            order_spec["priceBound"] = str(trigger_price)
        
        try:
            response = await self.client.put(
                f"/v3/accounts/{account_id}/orders/{order_id}",
                json={"order": order_spec}
            )
            response.raise_for_status()
            
            # Fetch updated order
            return await self.get_order_status(order_id)
            
        except Exception as e:
            logger.error(f"OANDA order modification error: {e}")
            raise
    
    async def get_order_status(self, order_id: str) -> Order:
        """Get order status from OANDA."""
        if not self.client:
            raise RuntimeError("Not connected to OANDA")
        
        try:
            account_id = self.config["account_id"]
            response = await self.client.get(
                f"/v3/accounts/{account_id}/orders/{order_id}"
            )
            response.raise_for_status()
            
            result = response.json()
            order_data = result.get("order", {})
            
            return self._parse_order(order_data)
            
        except Exception as e:
            logger.error(f"Get order status error: {e}")
            raise
    
    async def get_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """Get all pending orders from OANDA."""
        if not self.client:
            raise RuntimeError("Not connected to OANDA")
        
        try:
            account_id = self.config["account_id"]
            params = {}
            if symbol:
                params["instrument"] = symbol
            
            response = await self.client.get(
                f"/v3/accounts/{account_id}/pendingOrders",
                params=params
            )
            response.raise_for_status()
            
            result = response.json()
            orders = result.get("orders", [])
            
            return [self._parse_order(o) for o in orders]
            
        except Exception as e:
            logger.error(f"Get orders error: {e}")
            return []
    
    async def get_positions(self) -> List[Position]:
        """Get open positions from OANDA."""
        if not self.client:
            raise RuntimeError("Not connected to OANDA")
        
        try:
            account_id = self.config["account_id"]
            response = await self.client.get(
                f"/v3/accounts/{account_id}/openPositions"
            )
            response.raise_for_status()
            
            result = response.json()
            positions = result.get("positions", [])
            
            return [self._parse_position(p) for p in positions]
            
        except Exception as e:
            logger.error(f"Get positions error: {e}")
            return []
    
    async def get_position(self, symbol: str, exchange: str) -> Optional[Position]:
        """Get specific position from OANDA."""
        if not self.client:
            raise RuntimeError("Not connected to OANDA")
        
        try:
            account_id = self.config["account_id"]
            response = await self.client.get(
                f"/v3/accounts/{account_id}/positions/{symbol}"
            )
            
            if response.status_code == 200:
                result = response.json()
                position_data = result.get("position", {})
                return self._parse_position(position_data)
            else:
                return None
            
        except Exception as e:
            logger.error(f"Get position error: {e}")
            return None
    
    async def get_margin(self) -> MarginInfo:
        """Get account balance from OANDA."""
        if not self.client:
            raise RuntimeError("Not connected to OANDA")
        
        try:
            account_id = self.config["account_id"]
            response = await self.client.get(
                f"/v3/accounts/{account_id}/summary"
            )
            response.raise_for_status()
            
            result = response.json()
            account = result.get("account", {})
            
            balance = float(account.get("balance", 0))
            used_margin = float(account.get("marginUsed", 0))
            available = float(account.get("marginAvailable", 0))
            unrealized_pl = float(account.get("unrealizedPL", 0))
            
            return MarginInfo(
                available_cash=available,
                used_margin=used_margin,
                total_margin=balance,
                unrealized_pnl=unrealized_pl,
                metadata=account
            )
            
        except Exception as e:
            logger.error(f"Get margin error: {e}")
            raise
    
    async def get_holdings(self) -> List[Position]:
        """Get holdings (same as positions for forex)."""
        return await self.get_positions()
    
    def _map_order_type(self, order_type: OrderType) -> str:
        """Map OrderType to OANDA format."""
        mapping = {
            OrderType.MARKET: "MARKET",
            OrderType.LIMIT: "LIMIT",
            OrderType.STOP_LOSS: "STOP",
            OrderType.STOP_LOSS_LIMIT: "STOP"
        }
        return mapping.get(order_type, "MARKET")
    
    def _parse_order_status(self, state: str) -> OrderStatus:
        """Parse OANDA order state to OrderStatus enum."""
        status_map = {
            "PENDING": OrderStatus.PENDING,
            "FILLED": OrderStatus.FILLED,
            "TRIGGERED": OrderStatus.OPEN,
            "CANCELLED": OrderStatus.CANCELLED
        }
        return status_map.get(state, OrderStatus.PENDING)
    
    def _parse_order(self, data: Dict[str, Any]) -> Order:
        """Parse OANDA order response to Order object."""
        units = float(data.get("units", 0))
        side = OrderSide.BUY if units > 0 else OrderSide.SELL
        
        return Order(
            symbol=data.get("instrument", ""),
            exchange="OANDA",
            side=side,
            order_type=OrderType.MARKET if data.get("type") == "MARKET" else OrderType.LIMIT,
            quantity=abs(units),
            price=float(data.get("price", 0)) if data.get("price") else None,
            broker_order_id=data.get("id"),
            status=self._parse_order_status(data.get("state", "")),
            filled_quantity=abs(float(data.get("filledUnits", 0))),
            metadata=data
        )
    
    def _parse_position(self, data: Dict[str, Any]) -> Position:
        """Parse OANDA position response to Position object."""
        # OANDA has separate long and short positions
        long_units = float(data.get("long", {}).get("units", 0))
        short_units = float(data.get("short", {}).get("units", 0))
        
        # Net position
        net_units = long_units + short_units
        
        if net_units == 0:
            return None
        
        # Calculate average price and P&L
        if net_units > 0:
            avg_price = float(data.get("long", {}).get("averagePrice", 0))
            unrealized_pl = float(data.get("long", {}).get("unrealizedPL", 0))
        else:
            avg_price = float(data.get("short", {}).get("averagePrice", 0))
            unrealized_pl = float(data.get("short", {}).get("unrealizedPL", 0))
        
        # Get current price (use pl to estimate)
        last_price = avg_price  # Simplified, would need separate price query
        
        return Position(
            symbol=data.get("instrument", ""),
            exchange="OANDA",
            product_type=ProductType.MARGIN,
            quantity=net_units,
            average_price=avg_price,
            last_price=last_price,
            pnl=unrealized_pl,
            pnl_percentage=(unrealized_pl / (abs(net_units) * avg_price) * 100) if net_units != 0 and avg_price != 0 else 0,
            metadata=data
        )
