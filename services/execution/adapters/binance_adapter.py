"""
Binance adapter for cryptocurrency trading.

Direct integration with Binance REST and WebSocket APIs for crypto execution.
Supports spot, futures, and margin trading.
"""

import httpx
import hmac
import hashlib
import time
from typing import Optional, List, Dict, Any
from datetime import datetime
import logging

from .base import (
    BrokerAdapter, Order, OrderStatus, OrderType, OrderSide,
    Position, MarginInfo, ProductType
)

logger = logging.getLogger(__name__)


class BinanceAdapter(BrokerAdapter):
    """
    Binance cryptocurrency exchange adapter.
    
    Supports spot and futures trading on Binance.
    """
    
    # API endpoints
    SPOT_BASE_URL = "https://api.binance.com"
    FUTURES_BASE_URL = "https://fapi.binance.com"
    TESTNET_SPOT_URL = "https://testnet.binance.vision"
    TESTNET_FUTURES_URL = "https://testnet.binancefuture.com"
    
    def __init__(self, config: Dict[str, Any], paper_trading: bool = False):
        """
        Initialize Binance adapter.
        
        Config should contain:
        - api_key: Binance API key
        - api_secret: Binance API secret
        - testnet: Use testnet (optional, default False)
        - futures: Use futures API (optional, default False for spot)
        """
        self.client: Optional[httpx.AsyncClient] = None
        self.use_futures = config.get("futures", False)
        self.use_testnet = config.get("testnet", False) or paper_trading
        super().__init__(config, paper_trading)
    
    def _validate_config(self) -> None:
        """Validate Binance configuration."""
        required_fields = ["api_key", "api_secret"]
        for field in required_fields:
            if field not in self.config:
                raise ValueError(f"Missing required config field: {field}")
    
    def _get_base_url(self) -> str:
        """Get appropriate base URL based on configuration."""
        if self.use_testnet:
            return self.TESTNET_FUTURES_URL if self.use_futures else self.TESTNET_SPOT_URL
        return self.FUTURES_BASE_URL if self.use_futures else self.SPOT_BASE_URL
    
    def _generate_signature(self, params: Dict[str, Any]) -> str:
        """Generate HMAC SHA256 signature for Binance API."""
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        signature = hmac.new(
            self.config["api_secret"].encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    async def connect(self) -> bool:
        """Establish connection to Binance."""
        try:
            base_url = self._get_base_url()
            self.client = httpx.AsyncClient(
                base_url=base_url,
                headers={
                    "X-MBX-APIKEY": self.config["api_key"]
                },
                timeout=30.0
            )
            
            # Test connection
            response = await self.client.get("/api/v3/ping")
            if response.status_code == 200:
                mode = "TESTNET" if self.use_testnet else "LIVE"
                market = "FUTURES" if self.use_futures else "SPOT"
                logger.info(f"Connected to Binance {market} ({mode})")
                return True
            else:
                logger.error(f"Binance connection failed: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to connect to Binance: {e}")
            return False
    
    async def disconnect(self) -> None:
        """Close connection to Binance."""
        if self.client:
            await self.client.aclose()
            self.client = None
            logger.info("Disconnected from Binance")
    
    async def place_order(self, order: Order) -> Order:
        """Place order on Binance."""
        if not self.client:
            raise RuntimeError("Not connected to Binance. Call connect() first.")
        
        # Prepare order parameters
        params = {
            "symbol": order.symbol.replace("/", ""),  # BTC/USDT -> BTCUSDT
            "side": order.side.value,
            "type": self._map_order_type(order.order_type),
            "quantity": order.quantity,
            "timestamp": int(time.time() * 1000)
        }
        
        if order.order_type == OrderType.LIMIT:
            params["price"] = order.price
            params["timeInForce"] = "GTC"  # Good Till Cancel
        
        if order.order_type in [OrderType.STOP_LOSS, OrderType.STOP_LOSS_LIMIT]:
            params["stopPrice"] = order.trigger_price
        
        # Add signature
        params["signature"] = self._generate_signature(params)
        
        try:
            endpoint = "/fapi/v1/order" if self.use_futures else "/api/v3/order"
            response = await self.client.post(endpoint, params=params)
            response.raise_for_status()
            
            result = response.json()
            
            # Update order with response
            order.broker_order_id = str(result.get("orderId"))
            order.status = self._parse_order_status(result.get("status"))
            order.placed_at = datetime.utcnow()
            order.filled_quantity = float(result.get("executedQty", 0))
            
            if result.get("fills"):
                # Calculate average price from fills
                total_qty = sum(float(f["qty"]) for f in result["fills"])
                total_value = sum(float(f["qty"]) * float(f["price"]) for f in result["fills"])
                order.average_price = total_value / total_qty if total_qty > 0 else None
            
            order.metadata["binance_response"] = result
            
            logger.info(f"Order placed on Binance: {order.broker_order_id} for {order.symbol}")
            return order
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Binance order placement failed: {e.response.text}")
            order.status = OrderStatus.REJECTED
            order.metadata["error"] = e.response.text
            raise Exception(f"Order placement failed: {e.response.text}")
        except Exception as e:
            logger.error(f"Binance order placement error: {e}")
            order.status = OrderStatus.REJECTED
            raise
    
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel order on Binance."""
        if not self.client:
            raise RuntimeError("Not connected to Binance")
        
        try:
            params = {
                "orderId": int(order_id),
                "timestamp": int(time.time() * 1000)
            }
            params["signature"] = self._generate_signature(params)
            
            endpoint = "/fapi/v1/order" if self.use_futures else "/api/v3/order"
            response = await self.client.delete(endpoint, params=params)
            response.raise_for_status()
            
            logger.info(f"Order cancelled on Binance: {order_id}")
            return True
            
        except Exception as e:
            logger.error(f"Binance order cancellation error: {e}")
            return False
    
    async def modify_order(self, order_id: str, quantity: Optional[float] = None,
                          price: Optional[float] = None,
                          trigger_price: Optional[float] = None) -> Order:
        """
        Modify order on Binance.
        Note: Binance doesn't support direct order modification.
        This cancels and replaces the order.
        """
        # Get current order
        current_order = await self.get_order_status(order_id)
        
        # Cancel existing order
        await self.cancel_order(order_id)
        
        # Place new order with modified parameters
        new_order = Order(
            symbol=current_order.symbol,
            exchange=current_order.exchange,
            side=current_order.side,
            order_type=current_order.order_type,
            quantity=quantity if quantity is not None else current_order.quantity,
            price=price if price is not None else current_order.price,
            trigger_price=trigger_price if trigger_price is not None else current_order.trigger_price,
            product_type=current_order.product_type
        )
        
        return await self.place_order(new_order)
    
    async def get_order_status(self, order_id: str) -> Order:
        """Get order status from Binance."""
        if not self.client:
            raise RuntimeError("Not connected to Binance")
        
        try:
            params = {
                "orderId": int(order_id),
                "timestamp": int(time.time() * 1000)
            }
            params["signature"] = self._generate_signature(params)
            
            endpoint = "/fapi/v1/order" if self.use_futures else "/api/v3/order"
            response = await self.client.get(endpoint, params=params)
            response.raise_for_status()
            
            result = response.json()
            return self._parse_order(result)
            
        except Exception as e:
            logger.error(f"Get order status error: {e}")
            raise
    
    async def get_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """Get all open orders from Binance."""
        if not self.client:
            raise RuntimeError("Not connected to Binance")
        
        try:
            params = {
                "timestamp": int(time.time() * 1000)
            }
            if symbol:
                params["symbol"] = symbol.replace("/", "")
            
            params["signature"] = self._generate_signature(params)
            
            endpoint = "/fapi/v1/openOrders" if self.use_futures else "/api/v3/openOrders"
            response = await self.client.get(endpoint, params=params)
            response.raise_for_status()
            
            results = response.json()
            return [self._parse_order(o) for o in results]
            
        except Exception as e:
            logger.error(f"Get orders error: {e}")
            return []
    
    async def get_positions(self) -> List[Position]:
        """Get positions from Binance (futures only)."""
        if not self.client:
            raise RuntimeError("Not connected to Binance")
        
        if not self.use_futures:
            # Spot doesn't have positions, return holdings instead
            return await self.get_holdings()
        
        try:
            params = {
                "timestamp": int(time.time() * 1000)
            }
            params["signature"] = self._generate_signature(params)
            
            response = await self.client.get("/fapi/v2/positionRisk", params=params)
            response.raise_for_status()
            
            results = response.json()
            positions = []
            
            for pos_data in results:
                quantity = float(pos_data.get("positionAmt", 0))
                if quantity != 0:  # Only include non-zero positions
                    positions.append(self._parse_position(pos_data))
            
            return positions
            
        except Exception as e:
            logger.error(f"Get positions error: {e}")
            return []
    
    async def get_position(self, symbol: str, exchange: str) -> Optional[Position]:
        """Get specific position from Binance."""
        positions = await self.get_positions()
        symbol_normalized = symbol.replace("/", "")
        for pos in positions:
            if pos.symbol == symbol_normalized:
                return pos
        return None
    
    async def get_margin(self) -> MarginInfo:
        """Get account balance from Binance."""
        if not self.client:
            raise RuntimeError("Not connected to Binance")
        
        try:
            params = {
                "timestamp": int(time.time() * 1000)
            }
            params["signature"] = self._generate_signature(params)
            
            if self.use_futures:
                response = await self.client.get("/fapi/v2/account", params=params)
            else:
                response = await self.client.get("/api/v3/account", params=params)
            
            response.raise_for_status()
            result = response.json()
            
            if self.use_futures:
                available = float(result.get("availableBalance", 0))
                total = float(result.get("totalWalletBalance", 0))
                used = total - available
                
                return MarginInfo(
                    available_cash=available,
                    used_margin=used,
                    total_margin=total,
                    unrealized_pnl=float(result.get("totalUnrealizedProfit", 0)),
                    metadata=result
                )
            else:
                # Spot account - calculate USDT balance
                balances = result.get("balances", [])
                usdt_balance = next((b for b in balances if b["asset"] == "USDT"), None)
                
                if usdt_balance:
                    free = float(usdt_balance.get("free", 0))
                    locked = float(usdt_balance.get("locked", 0))
                    total = free + locked
                    
                    return MarginInfo(
                        available_cash=free,
                        used_margin=locked,
                        total_margin=total,
                        metadata=result
                    )
                else:
                    return MarginInfo(
                        available_cash=0.0,
                        used_margin=0.0,
                        total_margin=0.0,
                        metadata=result
                    )
            
        except Exception as e:
            logger.error(f"Get margin error: {e}")
            raise
    
    async def get_holdings(self) -> List[Position]:
        """Get spot balances as holdings."""
        if not self.client:
            raise RuntimeError("Not connected to Binance")
        
        try:
            params = {
                "timestamp": int(time.time() * 1000)
            }
            params["signature"] = self._generate_signature(params)
            
            response = await self.client.get("/api/v3/account", params=params)
            response.raise_for_status()
            
            result = response.json()
            balances = result.get("balances", [])
            
            holdings = []
            for balance in balances:
                free = float(balance.get("free", 0))
                locked = float(balance.get("locked", 0))
                total = free + locked
                
                if total > 0:  # Only include non-zero balances
                    holdings.append(Position(
                        symbol=balance["asset"],
                        exchange="BINANCE",
                        product_type=ProductType.DELIVERY,
                        quantity=total,
                        average_price=0.0,  # Not available for spot balances
                        last_price=0.0,     # Would need separate price query
                        pnl=0.0,
                        pnl_percentage=0.0,
                        metadata=balance
                    ))
            
            return holdings
            
        except Exception as e:
            logger.error(f"Get holdings error: {e}")
            return []
    
    def _map_order_type(self, order_type: OrderType) -> str:
        """Map OrderType to Binance format."""
        mapping = {
            OrderType.MARKET: "MARKET",
            OrderType.LIMIT: "LIMIT",
            OrderType.STOP_LOSS: "STOP_MARKET",
            OrderType.STOP_LOSS_LIMIT: "STOP"
        }
        return mapping.get(order_type, "MARKET")
    
    def _parse_order_status(self, status: str) -> OrderStatus:
        """Parse Binance order status to OrderStatus enum."""
        status_map = {
            "NEW": OrderStatus.OPEN,
            "PARTIALLY_FILLED": OrderStatus.PARTIALLY_FILLED,
            "FILLED": OrderStatus.FILLED,
            "CANCELED": OrderStatus.CANCELLED,
            "REJECTED": OrderStatus.REJECTED,
            "EXPIRED": OrderStatus.EXPIRED
        }
        return status_map.get(status, OrderStatus.PENDING)
    
    def _parse_order(self, data: Dict[str, Any]) -> Order:
        """Parse Binance order response to Order object."""
        return Order(
            symbol=data.get("symbol", ""),
            exchange="BINANCE",
            side=OrderSide.BUY if data.get("side") == "BUY" else OrderSide.SELL,
            order_type=OrderType.MARKET if data.get("type") == "MARKET" else OrderType.LIMIT,
            quantity=float(data.get("origQty", 0)),
            price=float(data.get("price", 0)) if data.get("price") else None,
            broker_order_id=str(data.get("orderId")),
            status=self._parse_order_status(data.get("status", "")),
            filled_quantity=float(data.get("executedQty", 0)),
            average_price=float(data.get("avgPrice", 0)) if data.get("avgPrice") else None,
            metadata=data
        )
    
    def _parse_position(self, data: Dict[str, Any]) -> Position:
        """Parse Binance position response to Position object."""
        quantity = float(data.get("positionAmt", 0))
        entry_price = float(data.get("entryPrice", 0))
        mark_price = float(data.get("markPrice", 0))
        unrealized_pnl = float(data.get("unRealizedProfit", 0))
        
        return Position(
            symbol=data.get("symbol", ""),
            exchange="BINANCE",
            product_type=ProductType.MARGIN,
            quantity=quantity,
            average_price=entry_price,
            last_price=mark_price,
            pnl=unrealized_pnl,
            pnl_percentage=(unrealized_pnl / (abs(quantity) * entry_price) * 100) if quantity != 0 and entry_price != 0 else 0,
            metadata=data
        )
