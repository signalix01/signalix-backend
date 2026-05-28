"""
Dhan Broker Adapter

Implements Dhan API integration for trading.

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


class DhanAdapter(EnhancedBrokerAdapter):
    """
    Dhan HTTP API adapter.
    
    Supports: API Key + Access Token authentication
    """
    
    BASE_URL = "https://api.dhan.co"
    
    def __init__(self, config: Dict[str, Any], paper_trading: bool = False):
        self.client: Optional[httpx.AsyncClient] = None
        super().__init__(config, paper_trading)
    
    def _validate_config(self) -> None:
        """Validate Dhan configuration."""
        required = ['api_key', 'client_id']
        for field in required:
            if field not in self.config:
                raise ValueError(f"Missing required config: {field}")
    
    def _get_error_mapping(self) -> Dict[str, BrokerErrorType]:
        """Get Dhan error code mapping."""
        return {
            '401': BrokerErrorType.SESSION_EXPIRED,
            '403': BrokerErrorType.SESSION_EXPIRED,
            '429': BrokerErrorType.RATE_LIMIT_EXCEEDED,
            '500': BrokerErrorType.BROKER_ERROR,
            '502': BrokerErrorType.NETWORK_ERROR,
            '503': BrokerErrorType.BROKER_ERROR,
        }
    
    async def _connect_internal(self) -> bool:
        """Connect to Dhan API."""
        try:
            self.client = httpx.AsyncClient(
                base_url=self.BASE_URL,
                headers={
                    'access-token': self.config['api_key'],
                    'client-id': self.config['client_id'],
                    'Content-Type': 'application/json'
                },
                timeout=30.0
            )
            
            # Test connection
            response = await self.client.get('/fundlimit')
            
            if response.status_code == 200:
                logger.info(f"Connected to Dhan as {self.config['client_id']}")
                return True
            
            logger.error(f"Dhan connection failed: {response.text}")
            return False
            
        except Exception as e:
            logger.error(f"Failed to connect to Dhan: {e}")
            return False
    
    async def _disconnect_internal(self) -> None:
        """Disconnect from Dhan."""
        if self.client:
            await self.client.aclose()
            self.client = None
            logger.info("Disconnected from Dhan")
    
    async def place_order(self, order: Order) -> Order:
        """Place order via Dhan API."""
        if not self.client:
            raise RuntimeError("Not connected to Dhan")
        
        # Convert to Dhan format
        payload = {
            'dhanClientId': self.config['client_id'],
            'transactionType': order.side.value,
            'exchangeSegment': self._map_exchange(order.exchange),
            'productType': self._map_product_type(order.product_type),
            'orderType': self._map_order_type(order.order_type),
            'validity': order.validity,
            'tradingSymbol': order.symbol,
            'securityId': await self._get_security_id(order.symbol, order.exchange),
            'quantity': int(order.quantity)
        }
        
        if order.price:
            payload['price'] = order.price
        if order.trigger_price:
            payload['triggerPrice'] = order.trigger_price
        if order.disclosed_quantity:
            payload['disclosedQuantity'] = int(order.disclosed_quantity)
        
        # Paper trading
        if self.paper_trading:
            order.broker_order_id = f"PAPER_{datetime.utcnow().timestamp()}"
            order.status = OrderStatus.OPEN
            order.placed_at = datetime.utcnow()
            logger.info(f"[PAPER] Placed Dhan order: {order.symbol}")
            return order
        
        try:
            response = await self.client.post('/orders', json=payload)
            response.raise_for_status()
            
            result = response.json()
            
            if result.get('orderId'):
                order.broker_order_id = result['orderId']
                order.status = OrderStatus.OPEN
                order.placed_at = datetime.utcnow()
                logger.info(f"Dhan order placed: {order.broker_order_id}")
            else:
                order.status = OrderStatus.REJECTED
                logger.error(f"Dhan order rejected: {result}")
            
            return order
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Dhan order failed: {e.response.text}")
            order.status = OrderStatus.REJECTED
            raise
    
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel order via Dhan API."""
        if not self.client:
            raise RuntimeError("Not connected to Dhan")
        
        if self.paper_trading:
            logger.info(f"[PAPER] Cancelled Dhan order: {order_id}")
            return True
        
        try:
            response = await self.client.delete(f'/orders/{order_id}')
            response.raise_for_status()
            
            result = response.json()
            return result.get('status') == 'success'
            
        except Exception as e:
            logger.error(f"Failed to cancel Dhan order: {e}")
            return False
    
    async def modify_order(
        self,
        order_id: str,
        quantity: Optional[float] = None,
        price: Optional[float] = None,
        trigger_price: Optional[float] = None
    ) -> Order:
        """Modify order via Dhan API."""
        if not self.client:
            raise RuntimeError("Not connected to Dhan")
        
        payload = {
            'dhanClientId': self.config['client_id'],
            'orderId': order_id
        }
        if quantity is not None:
            payload['quantity'] = int(quantity)
        if price is not None:
            payload['price'] = price
        if trigger_price is not None:
            payload['triggerPrice'] = trigger_price
        
        if self.paper_trading:
            logger.info(f"[PAPER] Modified Dhan order: {order_id}")
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
            response = await self.client.put('/orders', json=payload)
            response.raise_for_status()
            
            return await self.get_order_status(order_id)
            
        except Exception as e:
            logger.error(f"Failed to modify Dhan order: {e}")
            raise
    
    async def get_order_status(self, order_id: str) -> Order:
        """Get order status from Dhan."""
        if not self.client:
            raise RuntimeError("Not connected to Dhan")
        
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
            return self._parse_order(result)
            
        except Exception as e:
            logger.error(f"Failed to get Dhan order status: {e}")
            raise
    
    async def get_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """Get all orders from Dhan."""
        if not self.client:
            raise RuntimeError("Not connected to Dhan")
        
        if self.paper_trading:
            return []
        
        try:
            response = await self.client.get('/orders')
            response.raise_for_status()
            
            result = response.json()
            orders = [self._parse_order(o) for o in result]
            
            if symbol:
                orders = [o for o in orders if o.symbol == symbol]
            
            return orders
            
        except Exception as e:
            logger.error(f"Failed to get Dhan orders: {e}")
            return []
    
    async def get_positions(self) -> List[Position]:
        """Get positions from Dhan."""
        if not self.client:
            raise RuntimeError("Not connected to Dhan")
        
        if self.paper_trading:
            return []
        
        try:
            response = await self.client.get('/positions')
            response.raise_for_status()
            
            result = response.json()
            return [self._parse_position(p) for p in result]
            
        except Exception as e:
            logger.error(f"Failed to get Dhan positions: {e}")
            return []
    
    async def get_position(self, symbol: str, exchange: str) -> Optional[Position]:
        """Get specific position from Dhan."""
        positions = await self.get_positions()
        for pos in positions:
            if pos.symbol == symbol and pos.exchange == exchange:
                return pos
        return None
    
    async def get_margin(self) -> MarginInfo:
        """Get margin info from Dhan."""
        if not self.client:
            raise RuntimeError("Not connected to Dhan")
        
        if self.paper_trading:
            return MarginInfo(
                available_cash=100000.0,
                used_margin=0.0,
                total_margin=100000.0
            )
        
        try:
            response = await self.client.get('/fundlimit')
            response.raise_for_status()
            
            result = response.json()
            
            return MarginInfo(
                available_cash=result.get('availableBalance', 0),
                used_margin=result.get('utilizedAmount', 0),
                total_margin=result.get('totalBalance', 0),
                metadata=result
            )
            
        except Exception as e:
            logger.error(f"Failed to get Dhan margin: {e}")
            raise
    
    async def get_holdings(self) -> List[Position]:
        """Get holdings from Dhan."""
        if not self.client:
            raise RuntimeError("Not connected to Dhan")
        
        if self.paper_trading:
            return []
        
        try:
            response = await self.client.get('/holdings')
            response.raise_for_status()
            
            result = response.json()
            return [self._parse_holding(h) for h in result]
            
        except Exception as e:
            logger.error(f"Failed to get Dhan holdings: {e}")
            return []
    
    async def _get_security_id(self, symbol: str, exchange: str) -> str:
        """Get Dhan security ID for symbol."""
        # This would typically use a mapping service
        # For now, return symbol as-is
        return symbol
    
    def normalize_symbol(self, broker_symbol: str, exchange: Optional[str] = None) -> str:
        """Normalize Dhan symbol to standard format."""
        if exchange:
            return f"{exchange}:{broker_symbol}"
        return broker_symbol
    
    def denormalize_symbol(self, standard_symbol: str) -> Tuple[str, Optional[str]]:
        """Convert standard symbol to Dhan format."""
        if ":" in standard_symbol:
            exchange, symbol = standard_symbol.split(":", 1)
            return symbol, exchange
        return standard_symbol, None
    
    def get_broker_name(self) -> str:
        return "Dhan"
    
    def get_broker_code(self) -> str:
        return "dhan"
    
    def get_capabilities(self) -> Dict[str, bool]:
        return {
            "supports_bracket_orders": False,
            "supports_cover_orders": False,
            "supports_amo": True,
            "supports_modify_order": True,
            "supports_websocket": True,
            "supports_multiple_accounts": False
        }
    
    def _map_exchange(self, exchange: str) -> str:
        """Map exchange to Dhan format."""
        mapping = {
            'NSE': 'NSE_EQ',
            'BSE': 'BSE_EQ',
            'NFO': 'NSE_FNO',
            'MCX': 'MCX_COMM'
        }
        return mapping.get(exchange, exchange)
    
    def _map_order_type(self, order_type: OrderType) -> str:
        """Map order type to Dhan format."""
        mapping = {
            OrderType.MARKET: 'MARKET',
            OrderType.LIMIT: 'LIMIT',
            OrderType.STOP_LOSS: 'SL',
            OrderType.STOP_LOSS_MARKET: 'SL-M'
        }
        return mapping.get(order_type, 'MARKET')
    
    def _map_product_type(self, product_type: ProductType) -> str:
        """Map product type to Dhan format."""
        mapping = {
            ProductType.DELIVERY: 'CNC',
            ProductType.INTRADAY: 'INTRADAY',
            ProductType.MARGIN: 'MARGIN',
            ProductType.BO: 'BO',
            ProductType.CO: 'CO'
        }
        return mapping.get(product_type, 'INTRADAY')
    
    def _parse_order(self, data: Dict[str, Any]) -> Order:
        """Parse Dhan order response."""
        status_map = {
            'PENDING': OrderStatus.PENDING,
            'CONFIRMED': OrderStatus.OPEN,
            'TRANSIT': OrderStatus.OPEN,
            'PARTIALLY_FILLED': OrderStatus.PARTIALLY_FILLED,
            'FILLED': OrderStatus.FILLED,
            'CANCELLED': OrderStatus.CANCELLED,
            'REJECTED': OrderStatus.REJECTED,
            'EXPIRED': OrderStatus.EXPIRED
        }
        
        side = OrderSide.BUY if data.get('transactionType') == 'BUY' else OrderSide.SELL
        
        return Order(
            symbol=data.get('tradingSymbol', ''),
            exchange=data.get('exchangeSegment', '').replace('_EQ', '').replace('_FNO', ''),
            side=side,
            order_type=OrderType(data.get('orderType', 'MARKET')),
            quantity=float(data.get('quantity', 0)),
            price=float(data.get('price', 0)) if data.get('price') else None,
            trigger_price=float(data.get('triggerPrice', 0)) if data.get('triggerPrice') else None,
            broker_order_id=data.get('orderId'),
            status=status_map.get(data.get('orderStatus'), OrderStatus.PENDING),
            filled_quantity=float(data.get('filledQuantity', 0)),
            average_price=float(data.get('averagePrice', 0)) if data.get('averagePrice') else None,
            metadata=data
        )
    
    def _parse_position(self, data: Dict[str, Any]) -> Position:
        """Parse Dhan position response."""
        quantity = float(data.get('netQty', 0))
        
        return Position(
            symbol=data.get('tradingSymbol', ''),
            exchange=data.get('exchangeSegment', '').replace('_EQ', '').replace('_FNO', ''),
            product_type=ProductType.MARGIN if data.get('productType') == 'MARGIN' else ProductType.INTRADAY,
            quantity=quantity,
            average_price=float(data.get('avgPrice', 0)),
            last_price=float(data.get('lastPrice', 0)),
            pnl=float(data.get('unrealizedProfit', 0)),
            pnl_percentage=(float(data.get('unrealizedProfit', 0)) / (abs(quantity) * float(data.get('avgPrice', 1))) * 100) if quantity != 0 else 0,
            metadata=data
        )
    
    def _parse_holding(self, data: Dict[str, Any]) -> Position:
        """Parse Dhan holding response."""
        quantity = float(data.get('quantity', 0))
        avg_price = float(data.get('avgPrice', 0))
        last_price = float(data.get('lastPrice', 0))
        
        return Position(
            symbol=data.get('tradingSymbol', ''),
            exchange=data.get('exchangeSegment', '').replace('_EQ', '').replace('_FNO', ''),
            product_type=ProductType.DELIVERY,
            quantity=quantity,
            average_price=avg_price,
            last_price=last_price,
            pnl=(last_price - avg_price) * quantity,
            pnl_percentage=((last_price - avg_price) / avg_price * 100) if avg_price != 0 else 0,
            metadata=data
        )
