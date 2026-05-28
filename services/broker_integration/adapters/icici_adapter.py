"""
ICICI Direct Broker Adapter

Implements ICICI Direct Breeze API integration for trading.

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


class ICICIAdapter(EnhancedBrokerAdapter):
    """
    ICICI Direct Breeze API adapter.
    
    Supports: API Key + Session Token authentication
    """
    
    BASE_URL = "https://api.icicidirect.com/breezeapi/api/v1"
    
    def __init__(self, config: Dict[str, Any], paper_trading: bool = False):
        self.client: Optional[httpx.AsyncClient] = None
        super().__init__(config, paper_trading)
    
    def _validate_config(self) -> None:
        """Validate ICICI Direct configuration."""
        required = ['api_key', 'session_token', 'user_id']
        for field in required:
            if field not in self.config:
                raise ValueError(f"Missing required config: {field}")
    
    def _get_error_mapping(self) -> Dict[str, BrokerErrorType]:
        """Get ICICI Direct error code mapping."""
        return {
            '401': BrokerErrorType.SESSION_EXPIRED,
            '403': BrokerErrorType.SESSION_EXPIRED,
            '429': BrokerErrorType.RATE_LIMIT_EXCEEDED,
            '500': BrokerErrorType.BROKER_ERROR,
            'EX8001': BrokerErrorType.INSUFFICIENT_MARGIN,
            'EX8002': BrokerErrorType.INVALID_SYMBOL,
            'EX8003': BrokerErrorType.MARKET_CLOSED,
        }
    
    async def _connect_internal(self) -> bool:
        """Connect to ICICI Direct Breeze API."""
        try:
            self.client = httpx.AsyncClient(
                base_url=self.BASE_URL,
                headers={
                    'Content-Type': 'application/json',
                    'X-Authorization-Token': self.config['session_token']
                },
                timeout=30.0
            )
            
            # Test connection by fetching customer details
            response = await self.client.get('/customerdetails')
            
            if response.status_code == 200:
                data = response.json()
                if data.get('Success'):
                    logger.info(f"Connected to ICICI Direct as {self.config['user_id']}")
                    return True
            
            logger.error(f"ICICI Direct connection failed: {response.text}")
            return False
            
        except Exception as e:
            logger.error(f"Failed to connect to ICICI Direct: {e}")
            return False
    
    async def _disconnect_internal(self) -> None:
        """Disconnect from ICICI Direct."""
        if self.client:
            await self.client.aclose()
            self.client = None
            logger.info("Disconnected from ICICI Direct")
    
    async def place_order(self, order: Order) -> Order:
        """Place order via ICICI Direct API."""
        if not self.client:
            raise RuntimeError("Not connected to ICICI Direct")
        
        # Convert to ICICI format
        payload = {
            'stock_code': order.symbol,
            'exchange_code': self._map_exchange(order.exchange),
            'product': self._map_product_type(order.product_type),
            'action': order.side.value,
            'order_type': self._map_order_type(order.order_type),
            'quantity': str(int(order.quantity)),
            'price': str(order.price or 0),
            'validity': order.validity
        }
        
        if order.trigger_price:
            payload['stoploss'] = str(order.trigger_price)
        
        # Paper trading
        if self.paper_trading:
            order.broker_order_id = f"PAPER_{datetime.utcnow().timestamp()}"
            order.status = OrderStatus.OPEN
            order.placed_at = datetime.utcnow()
            logger.info(f"[PAPER] Placed ICICI order: {order.symbol}")
            return order
        
        try:
            response = await self.client.post('/order', json=payload)
            response.raise_for_status()
            
            result = response.json()
            
            if result.get('Success') and result.get('Success', {}).get('order_id'):
                order.broker_order_id = result['Success']['order_id']
                order.status = OrderStatus.OPEN
                order.placed_at = datetime.utcnow()
                logger.info(f"ICICI order placed: {order.broker_order_id}")
            else:
                order.status = OrderStatus.REJECTED
                error = result.get('Error', result.get('message', 'Unknown error'))
                logger.error(f"ICICI order rejected: {error}")
            
            return order
            
        except httpx.HTTPStatusError as e:
            logger.error(f"ICICI order failed: {e.response.text}")
            order.status = OrderStatus.REJECTED
            raise
    
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel order via ICICI Direct API."""
        if not self.client:
            raise RuntimeError("Not connected to ICICI Direct")
        
        if self.paper_trading:
            logger.info(f"[PAPER] Cancelled ICICI order: {order_id}")
            return True
        
        try:
            payload = {'order_id': order_id}
            response = await self.client.delete('/order', params=payload)
            response.raise_for_status()
            
            result = response.json()
            return result.get('Success', False)
            
        except Exception as e:
            logger.error(f"Failed to cancel ICICI order: {e}")
            return False
    
    async def modify_order(
        self,
        order_id: str,
        quantity: Optional[float] = None,
        price: Optional[float] = None,
        trigger_price: Optional[float] = None
    ) -> Order:
        """Modify order via ICICI Direct API."""
        if not self.client:
            raise RuntimeError("Not connected to ICICI Direct")
        
        payload = {'order_id': order_id}
        if quantity is not None:
            payload['quantity'] = str(int(quantity))
        if price is not None:
            payload['price'] = str(price)
        if trigger_price is not None:
            payload['stoploss'] = str(trigger_price)
        
        if self.paper_trading:
            logger.info(f"[PAPER] Modified ICICI order: {order_id}")
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
            response = await self.client.put('/order', json=payload)
            response.raise_for_status()
            
            return await self.get_order_status(order_id)
            
        except Exception as e:
            logger.error(f"Failed to modify ICICI order: {e}")
            raise
    
    async def get_order_status(self, order_id: str) -> Order:
        """Get order status from ICICI Direct."""
        if not self.client:
            raise RuntimeError("Not connected to ICICI Direct")
        
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
            response = await self.client.get('/order', params={'order_id': order_id})
            response.raise_for_status()
            
            result = response.json()
            if result.get('Success') and len(result['Success']) > 0:
                return self._parse_order(result['Success'][0])
            
            raise ValueError(f"Order not found: {order_id}")
            
        except Exception as e:
            logger.error(f"Failed to get ICICI order status: {e}")
            raise
    
    async def get_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """Get all orders from ICICI Direct."""
        if not self.client:
            raise RuntimeError("Not connected to ICICI Direct")
        
        if self.paper_trading:
            return []
        
        try:
            response = await self.client.get('/order')
            response.raise_for_status()
            
            result = response.json()
            orders = []
            
            if result.get('Success'):
                for order_data in result['Success']:
                    orders.append(self._parse_order(order_data))
            
            if symbol:
                orders = [o for o in orders if o.symbol == symbol]
            
            return orders
            
        except Exception as e:
            logger.error(f"Failed to get ICICI orders: {e}")
            return []
    
    async def get_positions(self) -> List[Position]:
        """Get positions from ICICI Direct."""
        if not self.client:
            raise RuntimeError("Not connected to ICICI Direct")
        
        if self.paper_trading:
            return []
        
        try:
            response = await self.client.get('/portfolio/positions')
            response.raise_for_status()
            
            result = response.json()
            positions = []
            
            if result.get('Success'):
                for pos_data in result['Success']:
                    positions.append(self._parse_position(pos_data))
            
            return positions
            
        except Exception as e:
            logger.error(f"Failed to get ICICI positions: {e}")
            return []
    
    async def get_position(self, symbol: str, exchange: str) -> Optional[Position]:
        """Get specific position from ICICI Direct."""
        positions = await self.get_positions()
        for pos in positions:
            if pos.symbol == symbol and pos.exchange == exchange:
                return pos
        return None
    
    async def get_margin(self) -> MarginInfo:
        """Get margin info from ICICI Direct."""
        if not self.client:
            raise RuntimeError("Not connected to ICICI Direct")
        
        if self.paper_trading:
            return MarginInfo(
                available_cash=100000.0,
                used_margin=0.0,
                total_margin=100000.0
            )
        
        try:
            response = await self.client.get('/funds')
            response.raise_for_status()
            
            result = response.json()
            data = result.get('Success', {})
            
            return MarginInfo(
                available_cash=float(data.get('bank_balance', 0)),
                used_margin=float(data.get('blocked_amount', 0)),
                total_margin=float(data.get('limit', 0)),
                collateral=float(data.get('collateral', 0)),
                metadata=data
            )
            
        except Exception as e:
            logger.error(f"Failed to get ICICI margin: {e}")
            raise
    
    async def get_holdings(self) -> List[Position]:
        """Get holdings from ICICI Direct."""
        if not self.client:
            raise RuntimeError("Not connected to ICICI Direct")
        
        if self.paper_trading:
            return []
        
        try:
            response = await self.client.get('/portfolio/holdings')
            response.raise_for_status()
            
            result = response.json()
            holdings = []
            
            if result.get('Success'):
                for holding_data in result['Success']:
                    holdings.append(self._parse_holding(holding_data))
            
            return holdings
            
        except Exception as e:
            logger.error(f"Failed to get ICICI holdings: {e}")
            return []
    
    def normalize_symbol(self, broker_symbol: str, exchange: Optional[str] = None) -> str:
        """Normalize ICICI symbol to standard format."""
        if exchange:
            return f"{exchange}:{broker_symbol}"
        return broker_symbol
    
    def denormalize_symbol(self, standard_symbol: str) -> Tuple[str, Optional[str]]:
        """Convert standard symbol to ICICI format."""
        if ":" in standard_symbol:
            exchange, symbol = standard_symbol.split(":", 1)
            return symbol, exchange
        return standard_symbol, None
    
    def get_broker_name(self) -> str:
        return "ICICI Direct"
    
    def get_broker_code(self) -> str:
        return "icici_direct"
    
    def get_capabilities(self) -> Dict[str, bool]:
        return {
            "supports_bracket_orders": False,
            "supports_cover_orders": False,
            "supports_amo": True,
            "supports_modify_order": True,
            "supports_websocket": False,
            "supports_multiple_accounts": False
        }
    
    def _map_exchange(self, exchange: str) -> str:
        """Map exchange to ICICI format."""
        mapping = {
            'NSE': 'NSE',
            'BSE': 'BSE',
            'NFO': 'NFO',
            'MCX': 'MCX'
        }
        return mapping.get(exchange, exchange)
    
    def _map_order_type(self, order_type: OrderType) -> str:
        """Map order type to ICICI format."""
        mapping = {
            OrderType.MARKET: 'market',
            OrderType.LIMIT: 'limit',
            OrderType.STOP_LOSS: 'sl',
            OrderType.STOP_LOSS_MARKET: 'sl-m'
        }
        return mapping.get(order_type, 'market')
    
    def _map_product_type(self, product_type: ProductType) -> str:
        """Map product type to ICICI format."""
        mapping = {
            ProductType.DELIVERY: 'cash',
            ProductType.INTRADAY: 'margin',
            ProductType.MARGIN: 'margin',
            ProductType.BO: 'bo',
            ProductType.CO: 'co'
        }
        return mapping.get(product_type, 'margin')
    
    def _parse_order(self, data: Dict[str, Any]) -> Order:
        """Parse ICICI order response."""
        status_map = {
            'open': OrderStatus.OPEN,
            'complete': OrderStatus.FILLED,
            'cancelled': OrderStatus.CANCELLED,
            'rejected': OrderStatus.REJECTED,
            'pending': OrderStatus.PENDING,
            'after_market': OrderStatus.PENDING,
            'partially_executed': OrderStatus.PARTIALLY_FILLED
        }
        
        side = OrderSide.BUY if data.get('action') == 'BUY' else OrderSide.SELL
        
        order_type = data.get('order_type', 'market').upper()
        if order_type == 'SL':
            order_type = OrderType.STOP_LOSS
        elif order_type == 'SL-M':
            order_type = OrderType.STOP_LOSS_MARKET
        else:
            order_type = OrderType(order_type)
        
        return Order(
            symbol=data.get('stock_code', ''),
            exchange=data.get('exchange_code', ''),
            side=side,
            order_type=order_type,
            quantity=float(data.get('quantity', 0)),
            price=float(data.get('price', 0)) if data.get('price') else None,
            trigger_price=float(data.get('stoploss', 0)) if data.get('stoploss') else None,
            broker_order_id=data.get('order_id'),
            status=status_map.get(data.get('status', '').lower(), OrderStatus.PENDING),
            filled_quantity=float(data.get('executed_quantity', 0)),
            average_price=float(data.get('average_price', 0)) if data.get('average_price') else None,
            metadata=data
        )
    
    def _parse_position(self, data: Dict[str, Any]) -> Position:
        """Parse ICICI position response."""
        quantity = float(data.get('quantity', 0))
        avg_price = float(data.get('average_price', 0))
        last_price = float(data.get('last_price', 0))
        
        product = data.get('product', '')
        if product == 'cash':
            product_type = ProductType.DELIVERY
        elif product == 'margin':
            product_type = ProductType.INTRADAY
        else:
            product_type = ProductType.MARGIN
        
        return Position(
            symbol=data.get('stock_code', ''),
            exchange=data.get('exchange_code', ''),
            product_type=product_type,
            quantity=quantity,
            average_price=avg_price,
            last_price=last_price,
            pnl=float(data.get('pnl', 0)),
            pnl_percentage=(float(data.get('pnl', 0)) / (abs(quantity) * avg_price) * 100) if quantity != 0 and avg_price != 0 else 0,
            metadata=data
        )
    
    def _parse_holding(self, data: Dict[str, Any]) -> Position:
        """Parse ICICI holding response."""
        quantity = float(data.get('quantity', 0))
        avg_price = float(data.get('average_price', 0))
        last_price = float(data.get('last_price', 0))
        
        return Position(
            symbol=data.get('stock_code', ''),
            exchange=data.get('exchange_code', ''),
            product_type=ProductType.DELIVERY,
            quantity=quantity,
            average_price=avg_price,
            last_price=last_price,
            pnl=(last_price - avg_price) * quantity,
            pnl_percentage=((last_price - avg_price) / avg_price * 100) if avg_price != 0 else 0,
            metadata=data
        )
