"""
Order Manager

Manages order operations including placement, modification, cancellation,
status tracking, and order lifecycle management.

Requirements: 30.1, 30.2, 30.3, 30.4, 30.5, 30.6, 30.7, 30.8, 52.1, 52.2, 52.3, 52.4, 52.5
"""

import asyncio
from typing import Optional, List, Dict, Any, Callable
from datetime import datetime
from decimal import Decimal
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class OrderRequest:
    """Order request parameters"""
    symbol: str
    exchange: str
    action: str  # BUY, SELL
    order_type: str  # MARKET, LIMIT, STOP_LOSS, STOP_LOSS_MARKET
    product_type: str  # INTRADAY, DELIVERY, MARGIN
    quantity: float
    price: Optional[float] = None
    trigger_price: Optional[float] = None
    disclosed_quantity: Optional[float] = None
    validity: str = "DAY"
    tag: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class OrderResponse:
    """Order response"""
    success: bool
    order_id: Optional[str] = None
    broker_order_id: Optional[str] = None
    status: Optional[str] = None
    message: Optional[str] = None
    error_code: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class OrderManager:
    """
    Manages order lifecycle and operations.
    
    Features:
    - Order placement with validation
    - Order modification
    - Order cancellation
    - Status polling and tracking
    - Order history
    """
    
    STATUS_POLL_INTERVAL = 2  # seconds
    
    def __init__(self, connection_manager, db_session=None, redis_client=None):
        """
        Initialize order manager.
        
        Args:
            connection_manager: ConnectionManager instance
            db_session: Database session
            redis_client: Redis client for caching
        """
        self.connection_manager = connection_manager
        self.db = db_session
        self.redis = redis_client
        self._status_tasks: Dict[str, asyncio.Task] = {}
        self._callbacks: Dict[str, list] = {}
    
    async def place_order(
        self,
        broker_id: str,
        request: OrderRequest
    ) -> OrderResponse:
        """
        Place an order with validation.
        
        Requirements: 30.2
        
        Args:
            broker_id: Broker connection ID
            request: Order request parameters
            
        Returns:
            OrderResponse with result
        """
        # Validate order
        is_valid, error = self._validate_order(request)
        if not is_valid:
            return OrderResponse(success=False, message=error)
        
        try:
            # Get adapter
            adapter = self.connection_manager.get_adapter(broker_id)
            if not adapter:
                return OrderResponse(success=False, message="Broker adapter not found")
            
            # Convert to adapter Order format
            from .adapters.base_adapter import Order as AdapterOrder, OrderSide, OrderType, ProductType
            
            order = AdapterOrder(
                symbol=request.symbol,
                exchange=request.exchange,
                side=OrderSide(request.action),
                order_type=OrderType(request.order_type),
                quantity=request.quantity,
                price=request.price,
                trigger_price=request.trigger_price,
                product_type=ProductType(request.product_type),
                validity=request.validity,
                disclosed_quantity=request.disclosed_quantity,
                tag=request.tag,
                metadata=request.metadata or {}
            )
            
            # Place order
            result = await adapter.place_order(order)
            
            # Store in database
            if self.db and result.broker_order_id:
                await self._store_order(broker_id, request, result)
            
            # Start status tracking
            if result.broker_order_id:
                await self._start_status_tracking(broker_id, result.broker_order_id)
            
            # Emit event
            await self._emit_event('order_placed', {
                'broker_id': broker_id,
                'order_id': result.order_id,
                'broker_order_id': result.broker_order_id,
                'symbol': request.symbol,
                'action': request.action,
                'quantity': request.quantity
            })
            
            return OrderResponse(
                success=True,
                order_id=result.order_id,
                broker_order_id=result.broker_order_id,
                status=result.status.value if hasattr(result.status, 'value') else str(result.status),
                message="Order placed successfully"
            )
            
        except Exception as e:
            logger.error(f"Failed to place order: {e}")
            return OrderResponse(success=False, message=str(e))
    
    async def modify_order(
        self,
        broker_id: str,
        order_id: str,
        quantity: Optional[float] = None,
        price: Optional[float] = None,
        trigger_price: Optional[float] = None
    ) -> OrderResponse:
        """
        Modify a pending order.
        
        Requirements: 30.3
        
        Args:
            broker_id: Broker connection ID
            order_id: Order ID to modify
            quantity: New quantity (optional)
            price: New price (optional)
            trigger_price: New trigger price (optional)
            
        Returns:
            OrderResponse with result
        """
        try:
            adapter = self.connection_manager.get_adapter(broker_id)
            if not adapter:
                return OrderResponse(success=False, message="Broker adapter not found")
            
            # Modify order
            result = await adapter.modify_order(order_id, quantity, price, trigger_price)
            
            # Update database
            if self.db:
                await self._update_order_status(broker_id, order_id, result)
            
            return OrderResponse(
                success=True,
                order_id=result.order_id,
                broker_order_id=result.broker_order_id,
                status=result.status.value if hasattr(result.status, 'value') else str(result.status),
                message="Order modified successfully"
            )
            
        except Exception as e:
            logger.error(f"Failed to modify order: {e}")
            return OrderResponse(success=False, message=str(e))
    
    async def cancel_order(
        self,
        broker_id: str,
        order_id: str
    ) -> OrderResponse:
        """
        Cancel a pending order.
        
        Requirements: 30.4
        
        Args:
            broker_id: Broker connection ID
            order_id: Order ID to cancel
            
        Returns:
            OrderResponse with result
        """
        try:
            adapter = self.connection_manager.get_adapter(broker_id)
            if not adapter:
                return OrderResponse(success=False, message="Broker adapter not found")
            
            # Cancel order
            success = await adapter.cancel_order(order_id)
            
            # Update database
            if success and self.db:
                await self._mark_order_cancelled(broker_id, order_id)
            
            return OrderResponse(
                success=success,
                order_id=order_id,
                status="CANCELLED" if success else None,
                message="Order cancelled successfully" if success else "Failed to cancel order"
            )
            
        except Exception as e:
            logger.error(f"Failed to cancel order: {e}")
            return OrderResponse(success=False, message=str(e))
    
    async def get_order_status(
        self,
        broker_id: str,
        order_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get current status of an order.
        
        Requirements: 30.5, 52.2
        
        Args:
            broker_id: Broker connection ID
            order_id: Order ID
            
        Returns:
            Order status dictionary or None
        """
        try:
            adapter = self.connection_manager.get_adapter(broker_id)
            if not adapter:
                return None
            
            order = await adapter.get_order_status(order_id)
            
            if order:
                return {
                    'order_id': order.order_id,
                    'broker_order_id': order.broker_order_id,
                    'symbol': order.symbol,
                    'status': order.status.value if hasattr(order.status, 'value') else str(order.status),
                    'filled_quantity': order.filled_quantity,
                    'average_price': order.average_price,
                    'updated_at': order.updated_at.isoformat() if order.updated_at else None
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get order status: {e}")
            return None
    
    async def get_orders(
        self,
        broker_id: str,
        status: Optional[str] = None,
        symbol: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all orders with optional filtering.
        
        Args:
            broker_id: Broker connection ID
            status: Filter by status (optional)
            symbol: Filter by symbol (optional)
            
        Returns:
            List of order dictionaries
        """
        try:
            adapter = self.connection_manager.get_adapter(broker_id)
            if not adapter:
                return []
            
            orders = await adapter.get_orders(symbol)
            
            # Filter by status if specified
            if status:
                orders = [
                    o for o in orders
                    if (o.status.value if hasattr(o.status, 'value') else str(o.status)) == status
                ]
            
            return [
                {
                    'order_id': o.order_id,
                    'broker_order_id': o.broker_order_id,
                    'symbol': o.symbol,
                    'action': o.side.value if hasattr(o.side, 'value') else str(o.side),
                    'order_type': o.order_type.value if hasattr(o.order_type, 'value') else str(o.order_type),
                    'quantity': o.quantity,
                    'filled_quantity': o.filled_quantity,
                    'price': o.price,
                    'status': o.status.value if hasattr(o.status, 'value') else str(o.status),
                    'placed_at': o.placed_at.isoformat() if o.placed_at else None
                }
                for o in orders
            ]
            
        except Exception as e:
            logger.error(f"Failed to get orders: {e}")
            return []
    
    async def _start_status_tracking(self, broker_id: str, order_id: str):
        """Start polling for order status updates."""
        task_key = f"{broker_id}:{order_id}"
        
        # Cancel existing task if any
        if task_key in self._status_tasks:
            self._status_tasks[task_key].cancel()
        
        # Start new tracking task
        task = asyncio.create_task(
            self._status_polling_loop(broker_id, order_id),
            name=f"status_{task_key}"
        )
        self._status_tasks[task_key] = task
    
    async def _status_polling_loop(self, broker_id: str, order_id: str):
        """Poll for order status updates."""
        terminal_statuses = ['COMPLETE', 'CANCELLED', 'REJECTED', 'EXPIRED', 'FILLED']
        
        while True:
            try:
                await asyncio.sleep(self.STATUS_POLL_INTERVAL)
                
                # Get current status
                status = await self.get_order_status(broker_id, order_id)
                
                if not status:
                    logger.warning(f"Order {order_id} not found during status polling")
                    break
                
                current_status = status.get('status', '')
                
                # Update database
                if self.db:
                    await self._update_order_status_from_poll(broker_id, order_id, status)
                
                # Emit event
                await self._emit_event('order_status_update', {
                    'broker_id': broker_id,
                    'order_id': order_id,
                    'status': current_status,
                    'filled_quantity': status.get('filled_quantity'),
                    'average_price': status.get('average_price')
                })
                
                # Check if terminal status
                if any(ts in current_status for ts in terminal_statuses):
                    logger.info(f"Order {order_id} reached terminal status: {current_status}")
                    break
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in status polling for {order_id}: {e}")
        
        # Clean up task
        task_key = f"{broker_id}:{order_id}"
        if task_key in self._status_tasks:
            del self._status_tasks[task_key]
    
    def _validate_order(self, request: OrderRequest) -> tuple[bool, Optional[str]]:
        """Validate order request."""
        if not request.symbol:
            return False, "Symbol is required"
        
        if not request.exchange:
            return False, "Exchange is required"
        
        if request.quantity <= 0:
            return False, "Quantity must be greater than 0"
        
        if request.order_type in ['LIMIT', 'STOP_LOSS', 'STOP_LOSS_LIMIT']:
            if request.price is None or request.price <= 0:
                return False, f"Price is required for {request.order_type} orders"
        
        if request.order_type in ['STOP_LOSS', 'STOP_LOSS_LIMIT', 'STOP_LOSS_MARKET']:
            if request.trigger_price is None or request.trigger_price <= 0:
                return False, "Trigger price is required for stop-loss orders"
        
        return True, None
    
    async def _store_order(
        self,
        broker_id: str,
        request: OrderRequest,
        result: Any
    ):
        """Store order in database."""
        def _do_store():
            try:
                from ..models import BrokerOrder, OrderStatus
                from uuid import uuid4
                
                # Get connection ID from broker_id
                connection = self.db.query(BrokerOrder).filter(
                    BrokerOrder.connection_id == broker_id
                ).first()
                
                order = BrokerOrder(
                    id=uuid4(),
                    user_id=getattr(connection, 'user_id', None) if connection else None,
                    connection_id=broker_id,
                    order_id=result.order_id or str(uuid4()),
                    broker_order_id=result.broker_order_id,
                    symbol=request.symbol,
                    exchange=request.exchange,
                    action=request.action,
                    order_type=request.order_type,
                    product_type=request.product_type,
                    quantity=Decimal(str(request.quantity)),
                    price=Decimal(str(request.price)) if request.price else None,
                    trigger_price=Decimal(str(request.trigger_price)) if request.trigger_price else None,
                    disclosed_quantity=Decimal(str(request.disclosed_quantity)) if request.disclosed_quantity else None,
                    validity=request.validity,
                    status=OrderStatus.OPEN,
                    tag=request.tag,
                    metadata=request.metadata or {},
                    placed_at=datetime.utcnow(),
                    last_updated_at=datetime.utcnow()
                )
                
                self.db.add(order)
                self.db.commit()
                
            except Exception as e:
                logger.error(f"Failed to store order: {e}")
                self.db.rollback()
                
        if self.db:
            await asyncio.to_thread(_do_store)
    
    async def _update_order_status(self, broker_id: str, order_id: str, result: Any):
        """Update order status in database."""
        def _do_update():
            try:
                from ..models import BrokerOrder, OrderStatusHistory
                from uuid import uuid4
                
                order = self.db.query(BrokerOrder).filter(
                    BrokerOrder.broker_order_id == order_id
                ).first()
                
                if order:
                    # Record status history
                    old_status = order.status
                    new_status = result.status.value if hasattr(result.status, 'value') else str(result.status)
                    # For compatibility, assume new_status is strings and we need enum or vice versa, but we just set it.
                    
                    if str(old_status) != str(new_status):
                        history = OrderStatusHistory(
                            id=uuid4(),
                            order_id=order.id,
                            previous_status=old_status,
                            new_status=new_status,
                            changed_at=datetime.utcnow()
                        )
                        self.db.add(history)
                    
                    # Update order
                    order.status = new_status
                    order.last_updated_at = datetime.utcnow()
                    
                    self.db.commit()
                    
            except Exception as e:
                logger.error(f"Failed to update order status: {e}")
                self.db.rollback()

        if self.db:
            await asyncio.to_thread(_do_update)
    
    async def _mark_order_cancelled(self, broker_id: str, order_id: str):
        """Mark order as cancelled in database."""
        def _do_mark():
            try:
                from ..models import BrokerOrder, OrderStatus, OrderStatusHistory
                from uuid import uuid4
                
                order = self.db.query(BrokerOrder).filter(
                    BrokerOrder.broker_order_id == order_id
                ).first()
                
                if order:
                    # Record status change
                    history = OrderStatusHistory(
                        id=uuid4(),
                        order_id=order.id,
                        previous_status=order.status,
                        new_status=OrderStatus.CANCELLED,
                        changed_at=datetime.utcnow()
                    )
                    self.db.add(history)
                    
                    # Update order
                    order.status = OrderStatus.CANCELLED
                    order.cancelled_at = datetime.utcnow()
                    order.last_updated_at = datetime.utcnow()
                    
                    self.db.commit()
                    
            except Exception as e:
                logger.error(f"Failed to mark order cancelled: {e}")
                self.db.rollback()

        if self.db:
            await asyncio.to_thread(_do_mark)
    
    async def _update_order_status_from_poll(
        self,
        broker_id: str,
        order_id: str,
        status: Dict[str, Any]
    ):
        """Update order status from polling result."""
        def _do_update_poll():
            try:
                from ..models import BrokerOrder, OrderStatus, OrderStatusHistory
                from uuid import uuid4
                from decimal import Decimal
                
                order = self.db.query(BrokerOrder).filter(
                    BrokerOrder.broker_order_id == order_id
                ).first()
                
                if order:
                    # Map status string to enum
                    status_map = {
                        'PENDING': OrderStatus.PENDING,
                        'OPEN': OrderStatus.OPEN,
                        'COMPLETE': OrderStatus.COMPLETE,
                        'CANCELLED': OrderStatus.CANCELLED,
                        'REJECTED': OrderStatus.REJECTED,
                        'PARTIALLY_FILLED': OrderStatus.PARTIALLY_FILLED,
                        'FILLED': OrderStatus.COMPLETE
                    }
                    
                    new_status = status_map.get(status.get('status', ''), OrderStatus.OPEN)
                    
                    if order.status != new_status:
                        # Record status history
                        history = OrderStatusHistory(
                            id=uuid4(),
                            order_id=order.id,
                            previous_status=order.status,
                            new_status=new_status,
                            filled_quantity=Decimal(str(status.get('filled_quantity', 0))) if status.get('filled_quantity') else None,
                            average_price=Decimal(str(status.get('average_price', 0))) if status.get('average_price') else None,
                            changed_at=datetime.utcnow()
                        )
                        self.db.add(history)
                    
                    # Update order
                    order.status = new_status
                    if status.get('filled_quantity'):
                        order.filled_quantity = Decimal(str(status['filled_quantity']))
                    if status.get('average_price'):
                        order.average_price = Decimal(str(status['average_price']))
                    order.last_updated_at = datetime.utcnow()
                    
                    self.db.commit()
                    
            except Exception as e:
                logger.error(f"Failed to update order from poll: {e}")
                self.db.rollback()
                
        if self.db:
            await asyncio.to_thread(_do_update_poll)
    
    def on(self, event: str, callback: Callable):
        """Register event callback."""
        if event not in self._callbacks:
            self._callbacks[event] = []
        self._callbacks[event].append(callback)
    
    async def _emit_event(self, event: str, data: Dict[str, Any]):
        """Emit event to callbacks."""
        if event in self._callbacks:
            for callback in self._callbacks[event]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(data)
                    else:
                        callback(data)
                except Exception as e:
                    logger.error(f"Error in order event callback: {e}")
    
    async def stop(self):
        """Stop all status tracking tasks."""
        for task in self._status_tasks.values():
            task.cancel()
        
        for task in self._status_tasks.values():
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        self._status_tasks.clear()
