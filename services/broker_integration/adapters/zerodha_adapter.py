"""
Zerodha Broker Adapter

Implements Kite Connect API integration for Zerodha.

Requirements: 10.1
"""

import httpx
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
import logging

from .base_adapter import (
    EnhancedBrokerAdapter, Order, OrderStatus, OrderType, OrderSide,
    Position, MarginInfo, ProductType, BrokerErrorType
)

logger = logging.getLogger(__name__)


class ZerodhaAdapter(EnhancedBrokerAdapter):
    """
    Zerodha Kite Connect API adapter.
    
    Supports: API Key + Access Token authentication
    """
    
    BASE_URL = "https://api.kite.trade"
    
    def __init__(self, config: Dict[str, Any], paper_trading: bool = False):
        self.client: Optional[httpx.AsyncClient] = None
        self.access_token: Optional[str] = None
        super().__init__(config, paper_trading)
    
    def _validate_config(self) -> None:
        """Validate Zerodha configuration."""
        required = ['api_key']
        for field in required:
            if field not in self.config:
                raise ValueError(f"Missing required config: {field}")
    
    def _get_error_mapping(self) -> Dict[str, BrokerErrorType]:
        """Get Zerodha error code mapping."""
        return {
            'TokenException': BrokerErrorType.SESSION_EXPIRED,
            'PermissionException': BrokerErrorType.SESSION_EXPIRED,
            'OrderException': BrokerErrorType.BROKER_ERROR,
            'InputException': BrokerErrorType.INVALID_SYMBOL,
            'NetworkException': BrokerErrorType.NETWORK_ERROR,
            'GeneralException': BrokerErrorType.BROKER_ERROR,
            'MarginException': BrokerErrorType.INSUFFICIENT_MARGIN,
        }
    
    async def _connect_internal(self) -> bool:
        """Connect to Zerodha Kite API."""
        try:
            # Get access token (may need to be generated via login flow)
            self.access_token = self.config.get('access_token')
            
            if not self.access_token:
                logger.error("No access token provided for Zerodha")
                return False
            
            # Create HTTP client
            self.client = httpx.AsyncClient(
                base_url=self.BASE_URL,
                headers={
                    'X-Kite-Version': '3',
                    'Authorization': f'token {self.config["api_key"]}:{self.access_token}'
                },
                timeout=30.0
            )
            
            # Test connection by fetching profile
            response = await self.client.get('/user/profile')
            
            if response.status_code == 200:
                data = response.json()
                if data.get('data'):
                    logger.info(f"Connected to Zerodha as {data['data'].get('user_name', 'Unknown')}")
                    return True
            
            logger.error(f"Zerodha connection failed: {response.text}")
            return False
            
        except Exception as e:
            logger.error(f"Failed to connect to Zerodha: {e}")
            return False
    
    async def _disconnect_internal(self) -> None:
        """Disconnect from Zerodha."""
        if self.client:
            await self.client.aclose()
            self.client = None
            logger.info("Disconnected from Zerodha")
    
    async def place_order(self, order: Order) -> Order:
        """Place order via Zerodha API."""
        if not self.client:
            raise RuntimeError("Not connected to Zerodha")
        
        # Convert to Zerodha format
        payload = {
            'tradingsymbol': order.symbol,
            'exchange': order.exchange,
            'transaction_type': order.side.value,
            'order_type': self._map_order_type(order.order_type),
            'quantity': int(order.quantity),
            'product': self._map_product_type(order.product_type),
            'validity': order.validity
        }
        
        if order.price:
            payload['price'] = order.price
        if order.trigger_price:
            payload['trigger_price'] = order.trigger_price
        if order.disclosed_quantity:
            payload['disclosed_quantity'] = int(order.disclosed_quantity)
        if order.tag:
            payload['tag'] = order.tag
        
        # Paper trading simulation
        if self.paper_trading:
            order.broker_order_id = f"PAPER_{datetime.utcnow().timestamp()}"
            order.status = OrderStatus.OPEN
            order.placed_at = datetime.utcnow()
            logger.info(f"[PAPER] Placed Zerodha order: {order.symbol}")
            return order
        
        try:
            response = await self.client.post('/orders/regular', data=payload)
            response.raise_for_status()
            
            result = response.json()
            
            if result.get('data') and result['data'].get('order_id'):
                order.broker_order_id = result['data']['order_id']
                order.status = OrderStatus.OPEN
                order.placed_at = datetime.utcnow()
                logger.info(f"Zerodha order placed: {order.broker_order_id}")
            else:
                order.status = OrderStatus.REJECTED
                logger.error(f"Zerodha order rejected: {result}")
            
            return order
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Zerodha order failed: {e.response.text}")
            order.status = OrderStatus.REJECTED
            raise
    
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel order via Zerodha API."""
        if not self.client:
            raise RuntimeError("Not connected to Zerodha")
        
        if self.paper_trading:
            logger.info(f"[PAPER] Cancelled Zerodha order: {order_id}")
            return True
        
        try:
            response = await self.client.delete(f'/orders/regular/{order_id}')
            response.raise_for_status()
            
            result = response.json()
            return result.get('data', {}).get('order_id') == order_id
            
        except Exception as e:
            logger.error(f"Failed to cancel Zerodha order: {e}")
            return False
    
    async def modify_order(
        self,
        order_id: str,
        quantity: Optional[float] = None,
        price: Optional[float] = None,
        trigger_price: Optional[float] = None
    ) -> Order:
        """Modify order via Zerodha API."""
        if not self.client:
            raise RuntimeError("Not connected to Zerodha")
        
        payload = {}
        if quantity is not None:
            payload['quantity'] = int(quantity)
        if price is not None:
            payload['price'] = price
        if trigger_price is not None:
            payload['trigger_price'] = trigger_price
        
        if self.paper_trading:
            logger.info(f"[PAPER] Modified Zerodha order: {order_id}")
            # Return mock order
            return Order(
                symbol="MOCK",
                exchange="NSE",
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                quantity=quantity or 1,
                price=price,
                broker_order_id=order_id,
                status=OrderStatus.OPEN
            )
        
        try:
            response = await self.client.put(f'/orders/regular/{order_id}', data=payload)
            response.raise_for_status()
            
            # Fetch updated order
            return await self.get_order_status(order_id)
            
        except Exception as e:
            logger.error(f"Failed to modify Zerodha order: {e}")
            raise
    
    async def get_order_status(self, order_id: str) -> Order:
        """Get order status from Zerodha."""
        if not self.client:
            raise RuntimeError("Not connected to Zerodha")
        
        if self.paper_trading:
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
            response = await self.client.get(f'/orders/{order_id}')
            response.raise_for_status()
            
            result = response.json()
            if result.get('data'):
                return self._parse_order(result['data'])
            
            raise ValueError(f"Order not found: {order_id}")
            
        except Exception as e:
            logger.error(f"Failed to get Zerodha order status: {e}")
            raise
    
    async def get_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """Get all orders from Zerodha."""
        if not self.client:
            raise RuntimeError("Not connected to Zerodha")
        
        if self.paper_trading:
            return []
        
        try:
            response = await self.client.get('/orders')
            response.raise_for_status()
            
            result = response.json()
            orders = [self._parse_order(o) for o in result.get('data', [])]
            
            if symbol:
                orders = [o for o in orders if o.symbol == symbol]
            
            return orders
            
        except Exception as e:
            logger.error(f"Failed to get Zerodha orders: {e}")
            return []
    
    async def get_positions(self) -> List[Position]:
        """Get positions from Zerodha."""
        if not self.client:
            raise RuntimeError("Not connected to Zerodha")
        
        if self.paper_trading:
            return []
        
        try:
            response = await self.client.get('/portfolio/positions')
            response.raise_for_status()
            
            result = response.json()
            return [self._parse_position(p) for p in result.get('data', {}).get('net', [])]
            
        except Exception as e:
            logger.error(f"Failed to get Zerodha positions: {e}")
            return []
    
    async def get_position(self, symbol: str, exchange: str) -> Optional[Position]:
        """Get specific position from Zerodha."""
        positions = await self.get_positions()
        for pos in positions:
            if pos.symbol == symbol and pos.exchange == exchange:
                return pos
        return None
    
    async def get_margin(self) -> MarginInfo:
        """Get margin info from Zerodha."""
        if not self.client:
            raise RuntimeError("Not connected to Zerodha")
        
        if self.paper_trading:
            return MarginInfo(
                available_cash=100000.0,
                used_margin=0.0,
                total_margin=100000.0
            )
        
        try:
            response = await self.client.get('/user/margins')
            response.raise_for_status()
            
            result = response.json()
            data = result.get('data', {})
            equity = data.get('equity', {})
            
            return MarginInfo(
                available_cash=equity.get('available', {}).get('cash', 0),
                used_margin=equity.get('utilised', {}).get('debits', 0),
                total_margin=equity.get('net', 0),
                metadata=data
            )
            
        except Exception as e:
            logger.error(f"Failed to get Zerodha margin: {e}")
            raise
    
    async def get_holdings(self) -> List[Position]:
        """Get holdings from Zerodha."""
        if not self.client:
            raise RuntimeError("Not connected to Zerodha")
        
        if self.paper_trading:
            return []
        
        try:
            response = await self.client.get('/portfolio/holdings')
            response.raise_for_status()
            
            result = response.json()
            return [self._parse_holding(h) for h in result.get('data', [])]
            
        except Exception as e:
            logger.error(f"Failed to get Zerodha holdings: {e}")
            return []
    
    def normalize_symbol(self, broker_symbol: str, exchange: Optional[str] = None) -> str:
        """Normalize Zerodha symbol to standard format."""
        if exchange:
            return f"{exchange}:{broker_symbol}"
        return broker_symbol
    
    def denormalize_symbol(self, standard_symbol: str) -> Tuple[str, Optional[str]]:
        """Convert standard symbol to Zerodha format."""
        if ":" in standard_symbol:
            exchange, symbol = standard_symbol.split(":", 1)
            return symbol, exchange
        return standard_symbol, None
    
    def get_broker_name(self) -> str:
        """Get broker name."""
        return "Zerodha"
    
    def get_broker_code(self) -> str:
        """Get broker code."""
        return "zerodha"
    
    def get_capabilities(self) -> Dict[str, bool]:
        """Get Zerodha capabilities."""
        return {
            "supports_bracket_orders": True,
            "supports_cover_orders": True,
            "supports_amo": True,
            "supports_modify_order": True,
            "supports_websocket": True,
            "supports_multiple_accounts": True
        }
    
    def _map_order_type(self, order_type: OrderType) -> str:
        """Map order type to Zerodha format."""
        mapping = {
            OrderType.MARKET: 'MARKET',
            OrderType.LIMIT: 'LIMIT',
            OrderType.STOP_LOSS: 'SL',
            OrderType.STOP_LOSS_LIMIT: 'SL',
            OrderType.STOP_LOSS_MARKET: 'SL-M'
        }
        return mapping.get(order_type, 'MARKET')
    
    def _map_product_type(self, product_type: ProductType) -> str:
        """Map product type to Zerodha format."""
        mapping = {
            ProductType.DELIVERY: 'CNC',
            ProductType.INTRADAY: 'MIS',
            ProductType.MARGIN: 'NRML',
            ProductType.BO: 'BO',
            ProductType.CO: 'CO'
        }
        return mapping.get(product_type, 'MIS')
    
    def _parse_order(self, data: Dict[str, Any]) -> Order:
        """Parse Zerodha order response."""
        status_map = {
            'OPEN': OrderStatus.OPEN,
            'COMPLETE': OrderStatus.FILLED,
            'CANCELLED': OrderStatus.CANCELLED,
            'REJECTED': OrderStatus.REJECTED,
            'PENDING': OrderStatus.PENDING,
            'UPDATE': OrderStatus.OPEN
        }
        
        side = OrderSide.BUY if data.get('transaction_type') == 'BUY' else OrderSide.SELL
        
        return Order(
            symbol=data.get('tradingsymbol', ''),
            exchange=data.get('exchange', ''),
            side=side,
            order_type=OrderType(data.get('order_type', 'MARKET')),
            quantity=float(data.get('quantity', 0)),
            price=float(data.get('price', 0)) if data.get('price') else None,
            trigger_price=float(data.get('trigger_price', 0)) if data.get('trigger_price') else None,
            broker_order_id=data.get('order_id'),
            status=status_map.get(data.get('status'), OrderStatus.PENDING),
            filled_quantity=float(data.get('filled_quantity', 0)),
            average_price=float(data.get('average_price', 0)) if data.get('average_price') else None,
            placed_at=datetime.fromisoformat(data['order_timestamp'].replace('Z', '+00:00')) if data.get('order_timestamp') else None,
            tag=data.get('tag'),
            metadata=data
        )
    
    def _parse_position(self, data: Dict[str, Any]) -> Position:
        """Parse Zerodha position response."""
        quantity = float(data.get('quantity', 0))
        
        return Position(
            symbol=data.get('tradingsymbol', ''),
            exchange=data.get('exchange', ''),
            product_type=ProductType.MARGIN if data.get('product') == 'NRML' else ProductType.INTRADAY,
            quantity=quantity,
            average_price=float(data.get('average_price', 0)),
            last_price=float(data.get('last_price', 0)),
            pnl=float(data.get('pnl', 0)),
            pnl_percentage=(float(data.get('pnl', 0)) / (abs(quantity) * float(data.get('average_price', 1))) * 100) if quantity != 0 else 0,
            day_pnl=float(data.get('day_profit', 0)),
            buy_quantity=float(data.get('buy_quantity', 0)),
            sell_quantity=float(data.get('sell_quantity', 0)),
            buy_value=float(data.get('buy_value', 0)),
            sell_value=float(data.get('sell_value', 0)),
            metadata=data
        )
    
    def _parse_holding(self, data: Dict[str, Any]) -> Position:
        """Parse Zerodha holding response."""
        quantity = float(data.get('quantity', 0))
        avg_price = float(data.get('average_price', 0))
        last_price = float(data.get('last_price', 0))
        
        return Position(
            symbol=data.get('tradingsymbol', ''),
            exchange=data.get('exchange', ''),
            product_type=ProductType.DELIVERY,
            quantity=quantity,
            average_price=avg_price,
            last_price=last_price,
            pnl=(last_price - avg_price) * quantity,
            pnl_percentage=((last_price - avg_price) / avg_price * 100) if avg_price != 0 else 0,
            metadata=data
        )
