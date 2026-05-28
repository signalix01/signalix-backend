"""
Angel One Broker Adapter

Implements Angel One SmartAPI integration for trading.

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


class AngelOneAdapter(EnhancedBrokerAdapter):
    """
    Angel One SmartAPI adapter.
    
    Supports: API Key + Client Code + Password + TOTP authentication
    """
    
    BASE_URL = "https://apiconnect.angelbroking.com"
    
    def __init__(self, config: Dict[str, Any], paper_trading: bool = False):
        self.client: Optional[httpx.AsyncClient] = None
        self.feed_token: Optional[str] = None
        super().__init__(config, paper_trading)
    
    def _validate_config(self) -> None:
        """Validate Angel One configuration."""
        required = ['api_key', 'client_code']
        for field in required:
            if field not in self.config:
                raise ValueError(f"Missing required config: {field}")
    
    def _get_error_mapping(self) -> Dict[str, BrokerErrorType]:
        """Get Angel One error code mapping."""
        return {
            'AG8001': BrokerErrorType.SESSION_EXPIRED,
            'AG8002': BrokerErrorType.SESSION_EXPIRED,
            'AB1009': BrokerErrorType.INVALID_SYMBOL,
            'AB1010': BrokerErrorType.INSUFFICIENT_MARGIN,
            'AB1011': BrokerErrorType.MARKET_CLOSED,
            'AB1012': BrokerErrorType.BROKER_ERROR,
            'AB2001': BrokerErrorType.NETWORK_ERROR,
        }
    
    async def _connect_internal(self) -> bool:
        """Connect to Angel One SmartAPI."""
        try:
            self.client = httpx.AsyncClient(
                base_url=self.BASE_URL,
                headers={
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'X-UserType': 'USER',
                    'X-SourceID': 'WEB',
                    'X-ClientLocalIP': '192.168.1.1',
                    'X-ClientPublicIP': '192.168.1.1',
                    'X-MACAddress': '00:00:00:00:00:00',
                    'X-PrivateKey': self.config['api_key']
                },
                timeout=30.0
            )
            
            # Generate session (login)
            if 'password' in self.config and 'totp' in self.config:
                login_payload = {
                    'clientcode': self.config['client_code'],
                    'password': self.config['password'],
                    'totp': self.config['totp']
                }
                
                response = await self.client.post('/rest/auth/angelbroking/user/v1/loginByPassword', json=login_payload)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get('status') and data.get('data'):
                        self.config['access_token'] = data['data'].get('jwtToken')
                        self.config['refresh_token'] = data['data'].get('refreshToken')
                        self.feed_token = data['data'].get('feedToken')
                        
                        # Update auth header
                        self.client.headers['Authorization'] = f'Bearer {self.config["access_token"]}'
                        
                        logger.info(f"Connected to Angel One as {self.config['client_code']}")
                        return True
                
                logger.error(f"Angel One login failed: {response.text}")
                return False
            
            # Use existing access token
            elif 'access_token' in self.config:
                self.client.headers['Authorization'] = f'Bearer {self.config["access_token"]}'
                
                # Test connection
                response = await self.client.get('/rest/secure/angelbroking/user/v1/getProfile')
                
                if response.status_code == 200:
                    logger.info(f"Connected to Angel One as {self.config['client_code']}")
                    return True
                
                logger.error(f"Angel One connection failed: {response.text}")
                return False
            
            else:
                logger.error("No authentication credentials provided for Angel One")
                return False
            
        except Exception as e:
            logger.error(f"Failed to connect to Angel One: {e}")
            return False
    
    async def _disconnect_internal(self) -> None:
        """Disconnect from Angel One."""
        if self.client:
            await self.client.aclose()
            self.client = None
            logger.info("Disconnected from Angel One")
    
    async def place_order(self, order: Order) -> Order:
        """Place order via Angel One API."""
        if not self.client:
            raise RuntimeError("Not connected to Angel One")
        
        # Convert to Angel One format
        payload = {
            'variety': self._map_variety(order.product_type),
            'tradingsymbol': order.symbol,
            'symboltoken': await self._get_symbol_token(order.symbol, order.exchange),
            'transactiontype': order.side.value,
            'exchange': order.exchange,
            'ordertype': self._map_order_type(order.order_type),
            'producttype': self._map_product_type(order.product_type),
            'duration': order.validity,
            'price': str(order.price or 0),
            'squareoff': '0',
            'stoploss': str(order.trigger_price or 0),
            'quantity': str(int(order.quantity))
        }
        
        if order.disclosed_quantity:
            payload['disclosedquantity'] = str(int(order.disclosed_quantity))
        
        # Paper trading
        if self.paper_trading:
            order.broker_order_id = f"PAPER_{datetime.utcnow().timestamp()}"
            order.status = OrderStatus.OPEN
            order.placed_at = datetime.utcnow()
            logger.info(f"[PAPER] Placed Angel One order: {order.symbol}")
            return order
        
        try:
            response = await self.client.post('/rest/secure/angelbroking/order/v1/placeOrder', json=payload)
            response.raise_for_status()
            
            result = response.json()
            
            if result.get('status') and result.get('data') and result['data'].get('orderid'):
                order.broker_order_id = result['data']['orderid']
                order.status = OrderStatus.OPEN
                order.placed_at = datetime.utcnow()
                logger.info(f"Angel One order placed: {order.broker_order_id}")
            else:
                order.status = OrderStatus.REJECTED
                logger.error(f"Angel One order rejected: {result}")
            
            return order
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Angel One order failed: {e.response.text}")
            order.status = OrderStatus.REJECTED
            raise
    
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel order via Angel One API."""
        if not self.client:
            raise RuntimeError("Not connected to Angel One")
        
        if self.paper_trading:
            logger.info(f"[PAPER] Cancelled Angel One order: {order_id}")
            return True
        
        try:
            payload = {
                'variety': 'NORMAL',
                'orderid': order_id
            }
            
            response = await self.client.post('/rest/secure/angelbroking/order/v1/cancelOrder', json=payload)
            response.raise_for_status()
            
            result = response.json()
            return result.get('status') == True
            
        except Exception as e:
            logger.error(f"Failed to cancel Angel One order: {e}")
            return False
    
    async def modify_order(
        self,
        order_id: str,
        quantity: Optional[float] = None,
        price: Optional[float] = None,
        trigger_price: Optional[float] = None
    ) -> Order:
        """Modify order via Angel One API."""
        if not self.client:
            raise RuntimeError("Not connected to Angel One")
        
        # First get current order details
        current_order = await self.get_order_status(order_id)
        
        payload = {
            'variety': 'NORMAL',
            'orderid': order_id,
            'tradingsymbol': current_order.symbol,
            'symboltoken': await self._get_symbol_token(current_order.symbol, current_order.exchange),
            'exchange': current_order.exchange,
            'transactiontype': current_order.side.value,
            'ordertype': self._map_order_type(current_order.order_type),
            'producttype': self._map_product_type(current_order.product_type),
            'duration': current_order.validity,
            'price': str(price if price is not None else (current_order.price or 0)),
            'quantity': str(int(quantity if quantity is not None else current_order.quantity)),
            'stoploss': str(trigger_price if trigger_price is not None else (current_order.trigger_price or 0))
        }
        
        if self.paper_trading:
            logger.info(f"[PAPER] Modified Angel One order: {order_id}")
            return Order(
                symbol=current_order.symbol,
                exchange=current_order.exchange,
                side=current_order.side,
                order_type=current_order.order_type,
                quantity=quantity or current_order.quantity,
                price=price,
                broker_order_id=order_id,
                status=OrderStatus.OPEN
            )
        
        try:
            response = await self.client.post('/rest/secure/angelbroking/order/v1/modifyOrder', json=payload)
            response.raise_for_status()
            
            return await self.get_order_status(order_id)
            
        except Exception as e:
            logger.error(f"Failed to modify Angel One order: {e}")
            raise
    
    async def get_order_status(self, order_id: str) -> Order:
        """Get order status from Angel One."""
        if not self.client:
            raise RuntimeError("Not connected to Angel One")
        
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
            payload = {'orderid': order_id}
            response = await self.client.post('/rest/secure/angelbroking/order/v1/details', json=payload)
            response.raise_for_status()
            
            result = response.json()
            if result.get('status') and result.get('data'):
                return self._parse_order(result['data'])
            
            raise ValueError(f"Order not found: {order_id}")
            
        except Exception as e:
            logger.error(f"Failed to get Angel One order status: {e}")
            raise
    
    async def get_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """Get all orders from Angel One."""
        if not self.client:
            raise RuntimeError("Not connected to Angel One")
        
        if self.paper_trading:
            return []
        
        try:
            response = await self.client.get('/rest/secure/angelbroking/order/v1/getOrderBook')
            response.raise_for_status()
            
            result = response.json()
            orders = []
            
            if result.get('status') and result.get('data'):
                for order_data in result['data']:
                    orders.append(self._parse_order(order_data))
            
            if symbol:
                orders = [o for o in orders if o.symbol == symbol]
            
            return orders
            
        except Exception as e:
            logger.error(f"Failed to get Angel One orders: {e}")
            return []
    
    async def get_positions(self) -> List[Position]:
        """Get positions from Angel One."""
        if not self.client:
            raise RuntimeError("Not connected to Angel One")
        
        if self.paper_trading:
            return []
        
        try:
            response = await self.client.get('/rest/secure/angelbroking/order/v1/getPosition')
            response.raise_for_status()
            
            result = response.json()
            positions = []
            
            if result.get('status') and result.get('data'):
                for pos_data in result['data'].get('net', []):
                    positions.append(self._parse_position(pos_data))
            
            return positions
            
        except Exception as e:
            logger.error(f"Failed to get Angel One positions: {e}")
            return []
    
    async def get_position(self, symbol: str, exchange: str) -> Optional[Position]:
        """Get specific position from Angel One."""
        positions = await self.get_positions()
        for pos in positions:
            if pos.symbol == symbol and pos.exchange == exchange:
                return pos
        return None
    
    async def get_margin(self) -> MarginInfo:
        """Get margin info from Angel One."""
        if not self.client:
            raise RuntimeError("Not connected to Angel One")
        
        if self.paper_trading:
            return MarginInfo(
                available_cash=100000.0,
                used_margin=0.0,
                total_margin=100000.0
            )
        
        try:
            response = await self.client.get('/rest/secure/angelbroking/user/v1/getRMS')
            response.raise_for_status()
            
            result = response.json()
            data = result.get('data', {})
            
            return MarginInfo(
                available_cash=float(data.get('net', 0)),
                used_margin=float(data.get('utiliseddebits', 0)),
                total_margin=float(data.get('gross', 0)),
                metadata=data
            )
            
        except Exception as e:
            logger.error(f"Failed to get Angel One margin: {e}")
            raise
    
    async def get_holdings(self) -> List[Position]:
        """Get holdings from Angel One."""
        if not self.client:
            raise RuntimeError("Not connected to Angel One")
        
        if self.paper_trading:
            return []
        
        try:
            response = await self.client.get('/rest/secure/angelbroking/portfolio/v1/getHolding')
            response.raise_for_status()
            
            result = response.json()
            holdings = []
            
            if result.get('status') and result.get('data'):
                for holding_data in result['data']:
                    holdings.append(self._parse_holding(holding_data))
            
            return holdings
            
        except Exception as e:
            logger.error(f"Failed to get Angel One holdings: {e}")
            return []
    
    async def _get_symbol_token(self, symbol: str, exchange: str) -> str:
        """Get Angel One symbol token."""
        # This would typically use a mapping service
        # For now, return a placeholder
        return f"{exchange}-{symbol}"
    
    def normalize_symbol(self, broker_symbol: str, exchange: Optional[str] = None) -> str:
        """Normalize Angel One symbol to standard format."""
        if exchange:
            return f"{exchange}:{broker_symbol}"
        return broker_symbol
    
    def denormalize_symbol(self, standard_symbol: str) -> Tuple[str, Optional[str]]:
        """Convert standard symbol to Angel One format."""
        if ":" in standard_symbol:
            exchange, symbol = standard_symbol.split(":", 1)
            return symbol, exchange
        return standard_symbol, None
    
    def get_broker_name(self) -> str:
        return "Angel One"
    
    def get_broker_code(self) -> str:
        return "angel_one"
    
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
        """Map order type to Angel One format."""
        mapping = {
            OrderType.MARKET: 'MARKET',
            OrderType.LIMIT: 'LIMIT',
            OrderType.STOP_LOSS: 'STOPLOSS_LIMIT',
            OrderType.STOP_LOSS_MARKET: 'STOPLOSS_MARKET'
        }
        return mapping.get(order_type, 'MARKET')
    
    def _map_product_type(self, product_type: ProductType) -> str:
        """Map product type to Angel One format."""
        mapping = {
            ProductType.DELIVERY: 'DELIVERY',
            ProductType.INTRADAY: 'INTRADAY',
            ProductType.MARGIN: 'CARRYFORWARD',
            ProductType.BO: 'BO',
            ProductType.CO: 'CO'
        }
        return mapping.get(product_type, 'INTRADAY')
    
    def _map_variety(self, product_type: ProductType) -> str:
        """Map product type to order variety."""
        mapping = {
            ProductType.DELIVERY: 'NORMAL',
            ProductType.INTRADAY: 'NORMAL',
            ProductType.MARGIN: 'NORMAL',
            ProductType.BO: 'ROBO',
            ProductType.CO: 'CO'
        }
        return mapping.get(product_type, 'NORMAL')
    
    def _parse_order(self, data: Dict[str, Any]) -> Order:
        """Parse Angel One order response."""
        status_map = {
            'open': OrderStatus.OPEN,
            'complete': OrderStatus.FILLED,
            'cancelled': OrderStatus.CANCELLED,
            'rejected': OrderStatus.REJECTED,
            'pending': OrderStatus.PENDING,
            'after market': OrderStatus.PENDING
        }
        
        side = OrderSide.BUY if data.get('transactiontype') == 'BUY' else OrderSide.SELL
        
        order_type = data.get('ordertype', 'MARKET')
        if order_type == 'STOPLOSS_LIMIT':
            order_type = OrderType.STOP_LOSS
        elif order_type == 'STOPLOSS_MARKET':
            order_type = OrderType.STOP_LOSS_MARKET
        else:
            order_type = OrderType(order_type)
        
        return Order(
            symbol=data.get('tradingsymbol', ''),
            exchange=data.get('exchange', ''),
            side=side,
            order_type=order_type,
            quantity=float(data.get('quantity', 0)),
            price=float(data.get('price', 0)) if data.get('price') else None,
            trigger_price=float(data.get('triggerprice', 0)) if data.get('triggerprice') else None,
            broker_order_id=data.get('orderid'),
            status=status_map.get(data.get('status', '').lower(), OrderStatus.PENDING),
            filled_quantity=float(data.get('filledshares', 0)),
            average_price=float(data.get('averageprice', 0)) if data.get('averageprice') else None,
            placed_at=datetime.strptime(data['updatetime'], '%d-%b-%Y %H:%M') if data.get('updatetime') else None,
            metadata=data
        )
    
    def _parse_position(self, data: Dict[str, Any]) -> Position:
        """Parse Angel One position response."""
        quantity = float(data.get('netqty', 0))
        avg_price = float(data.get('avgnetprice', 0))
        last_price = float(data.get('ltp', 0))
        
        product = data.get('producttype', '')
        if product == 'CARRYFORWARD':
            product_type = ProductType.MARGIN
        elif product == 'INTRADAY':
            product_type = ProductType.INTRADAY
        else:
            product_type = ProductType.DELIVERY
        
        return Position(
            symbol=data.get('tradingsymbol', ''),
            exchange=data.get('exchange', ''),
            product_type=product_type,
            quantity=quantity,
            average_price=avg_price,
            last_price=last_price,
            pnl=float(data.get('pnl', 0)),
            pnl_percentage=(float(data.get('pnl', 0)) / (abs(quantity) * avg_price) * 100) if quantity != 0 and avg_price != 0 else 0,
            day_pnl=float(data.get('daybuyamount', 0)) - float(data.get('daysellamount', 0)),
            metadata=data
        )
    
    def _parse_holding(self, data: Dict[str, Any]) -> Position:
        """Parse Angel One holding response."""
        quantity = float(data.get('quantity', 0))
        avg_price = float(data.get('averageprice', 0))
        last_price = float(data.get('ltp', 0))
        
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
