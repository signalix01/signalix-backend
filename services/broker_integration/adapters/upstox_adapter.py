"""
Upstox Broker Adapter

Implements Upstox API 2.0 integration for trading.

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


class UpstoxAdapter(EnhancedBrokerAdapter):
    """
    Upstox API 2.0 adapter.
    
    Supports: OAuth 2.0 authentication
    """
    
    BASE_URL = "https://api-v2.upstox.com"
    
    def __init__(self, config: Dict[str, Any], paper_trading: bool = False):
        self.client: Optional[httpx.AsyncClient] = None
        super().__init__(config, paper_trading)
    
    def _validate_config(self) -> None:
        """Validate Upstox configuration."""
        required = ['api_key', 'access_token']
        for field in required:
            if field not in self.config:
                raise ValueError(f"Missing required config: {field}")
    
    def _get_error_mapping(self) -> Dict[str, BrokerErrorType]:
        """Get Upstox error code mapping."""
        return {
            '401': BrokerErrorType.SESSION_EXPIRED,
            '403': BrokerErrorType.SESSION_EXPIRED,
            '429': BrokerErrorType.RATE_LIMIT_EXCEEDED,
            '400': BrokerErrorType.BROKER_ERROR,
            '500': BrokerErrorType.BROKER_ERROR,
        }
    
    async def _connect_internal(self) -> bool:
        """Connect to Upstox API."""
        try:
            self.client = httpx.AsyncClient(
                base_url=self.BASE_URL,
                headers={
                    'Api-Version': '2.0',
                    'Authorization': f'Bearer {self.config["access_token"]}',
                    'Accept': 'application/json'
                },
                timeout=30.0
            )
            
            # Test connection
            response = await self.client.get('/user/profile')
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"Connected to Upstox as {data.get('data', {}).get('user_name', 'Unknown')}")
                return True
            
            logger.error(f"Upstox connection failed: {response.text}")
            return False
            
        except Exception as e:
            logger.error(f"Failed to connect to Upstox: {e}")
            return False
    
    async def _disconnect_internal(self) -> None:
        """Disconnect from Upstox."""
        if self.client:
            await self.client.aclose()
            self.client = None
            logger.info("Disconnected from Upstox")
    
    async def place_order(self, order: Order) -> Order:
        """Place order via Upstox API."""
        if not self.client:
            raise RuntimeError("Not connected to Upstox")
        
        # Convert to Upstox format
        payload = {
            'quantity': int(order.quantity),
            'product': self._map_product_type(order.product_type),
            'validity': order.validity,
            'price': order.price or 0,
            'tag': order.tag or '',
            'instrument_token': await self._get_instrument_token(order.symbol, order.exchange),
            'order_type': self._map_order_type(order.order_type),
            'transaction_type': order.side.value,
            'disclosed_quantity': int(order.disclosed_quantity or 0),
            'trigger_price': order.trigger_price or 0,
            'is_amo': False
        }
        
        # Paper trading
        if self.paper_trading:
            order.broker_order_id = f"PAPER_{datetime.utcnow().timestamp()}"
            order.status = OrderStatus.OPEN
            order.placed_at = datetime.utcnow()
            logger.info(f"[PAPER] Placed Upstox order: {order.symbol}")
            return order
        
        try:
            response = await self.client.post('/order/place', json=payload)
            response.raise_for_status()
            
            result = response.json()
            
            if result.get('data') and result['data'].get('order_id'):
                order.broker_order_id = result['data']['order_id']
                order.status = OrderStatus.OPEN
                order.placed_at = datetime.utcnow()
                logger.info(f"Upstox order placed: {order.broker_order_id}")
            else:
                order.status = OrderStatus.REJECTED
                logger.error(f"Upstox order rejected: {result}")
            
            return order
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Upstox order failed: {e.response.text}")
            order.status = OrderStatus.REJECTED
            raise
    
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel order via Upstox API."""
        if not self.client:
            raise RuntimeError("Not connected to Upstox")
        
        if self.paper_trading:
            logger.info(f"[PAPER] Cancelled Upstox order: {order_id}")
            return True
        
        try:
            response = await self.client.delete(f'/order/cancel?order_id={order_id}')
            response.raise_for_status()
            
            result = response.json()
            return result.get('status') == 'success'
            
        except Exception as e:
            logger.error(f"Failed to cancel Upstox order: {e}")
            return False
    
    async def modify_order(
        self,
        order_id: str,
        quantity: Optional[float] = None,
        price: Optional[float] = None,
        trigger_price: Optional[float] = None
    ) -> Order:
        """Modify order via Upstox API."""
        if not self.client:
            raise RuntimeError("Not connected to Upstox")
        
        payload = {'order_id': order_id}
        if quantity is not None:
            payload['quantity'] = int(quantity)
        if price is not None:
            payload['price'] = price
        if trigger_price is not None:
            payload['trigger_price'] = trigger_price
        
        if self.paper_trading:
            logger.info(f"[PAPER] Modified Upstox order: {order_id}")
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
            response = await self.client.put('/order/modify', json=payload)
            response.raise_for_status()
            
            return await self.get_order_status(order_id)
            
        except Exception as e:
            logger.error(f"Failed to modify Upstox order: {e}")
            raise
    
    async def get_order_status(self, order_id: str) -> Order:
        """Get order status from Upstox."""
        if not self.client:
            raise RuntimeError("Not connected to Upstox")
        
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
            response = await self.client.get(f'/order/history?order_id={order_id}')
            response.raise_for_status()
            
            result = response.json()
            if result.get('data'):
                return self._parse_order(result['data'][0])
            
            raise ValueError(f"Order not found: {order_id}")
            
        except Exception as e:
            logger.error(f"Failed to get Upstox order status: {e}")
            raise
    
    async def get_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """Get all orders from Upstox."""
        if not self.client:
            raise RuntimeError("Not connected to Upstox")
        
        if self.paper_trading:
            return []
        
        try:
            response = await self.client.get('/order/get-orders')
            response.raise_for_status()
            
            result = response.json()
            orders = [self._parse_order(o) for o in result.get('data', [])]
            
            if symbol:
                orders = [o for o in orders if o.symbol == symbol]
            
            return orders
            
        except Exception as e:
            logger.error(f"Failed to get Upstox orders: {e}")
            return []
    
    async def get_positions(self) -> List[Position]:
        """Get positions from Upstox."""
        if not self.client:
            raise RuntimeError("Not connected to Upstox")
        
        if self.paper_trading:
            return []
        
        try:
            response = await self.client.get('/portfolio/short-term-positions')
            response.raise_for_status()
            
            result = response.json()
            return [self._parse_position(p) for p in result.get('data', [])]
            
        except Exception as e:
            logger.error(f"Failed to get Upstox positions: {e}")
            return []
    
    async def get_position(self, symbol: str, exchange: str) -> Optional[Position]:
        """Get specific position from Upstox."""
        positions = await self.get_positions()
        for pos in positions:
            if pos.symbol == symbol and pos.exchange == exchange:
                return pos
        return None
    
    async def get_margin(self) -> MarginInfo:
        """Get margin info from Upstox."""
        if not self.client:
            raise RuntimeError("Not connected to Upstox")
        
        if self.paper_trading:
            return MarginInfo(
                available_cash=100000.0,
                used_margin=0.0,
                total_margin=100000.0
            )
        
        try:
            response = await self.client.get('/portfolio/limits')
            response.raise_for_status()
            
            result = response.json()
            data = result.get('data', {})
            
            return MarginInfo(
                available_cash=data.get('available_cash', 0),
                used_margin=data.get('used_margin', 0),
                total_margin=data.get('available_cash', 0) + data.get('used_margin', 0),
                collateral=data.get('collateral', 0),
                unrealized_pnl=data.get('unrealized_pnl', 0),
                realized_pnl=data.get('realized_pnl', 0),
                metadata=data
            )
            
        except Exception as e:
            logger.error(f"Failed to get Upstox margin: {e}")
            raise
    
    async def get_holdings(self) -> List[Position]:
        """Get holdings from Upstox."""
        if not self.client:
            raise RuntimeError("Not connected to Upstox")
        
        if self.paper_trading:
            return []
        
        try:
            response = await self.client.get('/portfolio/long-term-holdings')
            response.raise_for_status()
            
            result = response.json()
            return [self._parse_holding(h) for h in result.get('data', [])]
            
        except Exception as e:
            logger.error(f"Failed to get Upstox holdings: {e}")
            return []
    
    async def _get_instrument_token(self, symbol: str, exchange: str) -> str:
        """Get Upstox instrument token for symbol."""
        # This would typically use the market data service
        return f"{exchange}:{symbol}"
    
    def normalize_symbol(self, broker_symbol: str, exchange: Optional[str] = None) -> str:
        """Normalize Upstox symbol to standard format."""
        if exchange:
            return f"{exchange}:{broker_symbol}"
        return broker_symbol
    
    def denormalize_symbol(self, standard_symbol: str) -> Tuple[str, Optional[str]]:
        """Convert standard symbol to Upstox format."""
        if ":" in standard_symbol:
            exchange, symbol = standard_symbol.split(":", 1)
            return symbol, exchange
        return standard_symbol, None
    
    def get_broker_name(self) -> str:
        return "Upstox"
    
    def get_broker_code(self) -> str:
        return "upstox"
    
    def get_capabilities(self) -> Dict[str, bool]:
        return {
            "supports_bracket_orders": True,
            "supports_cover_orders": True,
            "supports_amo": True,
            "supports_modify_order": True,
            "supports_websocket": True,
            "supports_multiple_accounts": False
        }
    
    def _map_order_type(self, order_type: OrderType) -> str:
        """Map order type to Upstox format."""
        mapping = {
            OrderType.MARKET: 'MARKET',
            OrderType.LIMIT: 'LIMIT',
            OrderType.STOP_LOSS: 'SL',
            OrderType.STOP_LOSS_MARKET: 'SL-M'
        }
        return mapping.get(order_type, 'MARKET')
    
    def _map_product_type(self, product_type: ProductType) -> str:
        """Map product type to Upstox format."""
        mapping = {
            ProductType.DELIVERY: 'D',
            ProductType.INTRADAY: 'I',
            ProductType.MARGIN: 'M',
            ProductType.BO: 'B',
            ProductType.CO: 'C'
        }
        return mapping.get(product_type, 'I')
    
    def _parse_order(self, data: Dict[str, Any]) -> Order:
        """Parse Upstox order response."""
        status_map = {
            'pending': OrderStatus.PENDING,
            'open': OrderStatus.OPEN,
            'complete': OrderStatus.FILLED,
            'cancelled': OrderStatus.CANCELLED,
            'rejected': OrderStatus.REJECTED
        }
        
        instrument = data.get('instrument_token', '').split(':')
        exchange = instrument[0] if len(instrument) > 0 else ''
        symbol = instrument[1] if len(instrument) > 1 else data.get('instrument_token', '')
        
        side = OrderSide.BUY if data.get('transaction_type') == 'BUY' else OrderSide.SELL
        
        return Order(
            symbol=symbol,
            exchange=exchange,
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
        """Parse Upstox position response."""
        quantity = float(data.get('quantity', 0))
        
        return Position(
            symbol=data.get('tradingsymbol', ''),
            exchange=data.get('exchange', ''),
            product_type=ProductType.INTRADAY if data.get('product') == 'I' else ProductType.MARGIN,
            quantity=quantity,
            average_price=float(data.get('average_price', 0)),
            last_price=float(data.get('last_price', 0)),
            pnl=float(data.get('pnl', 0)),
            pnl_percentage=(float(data.get('pnl', 0)) / (abs(quantity) * float(data.get('average_price', 1))) * 100) if quantity != 0 else 0,
            day_pnl=float(data.get('day_pnl', 0)),
            metadata=data
        )
    
    def _parse_holding(self, data: Dict[str, Any]) -> Position:
        """Parse Upstox holding response."""
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
