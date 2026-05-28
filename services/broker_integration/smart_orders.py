"""
Smart Order Service

Position-aware order routing and duplicate prevention.
Mirrors OpenAlgo's place_smart_order_service.py functionality.

Requirements: Smart order placement with position awareness
"""

import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime
from decimal import Decimal
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class SmartOrderStatus(Enum):
    PENDING = "pending"
    VALIDATING = "validating"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    DUPLICATE_BLOCKED = "duplicate_blocked"
    POSITION_ADJUSTED = "position_adjusted"


class OrderAction(Enum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass
class PositionInfo:
    """Current position information"""
    symbol: str
    exchange: str
    quantity: float
    average_price: float
    side: str  # LONG or SHORT
    unrealized_pnl: float
    realized_pnl: float


@dataclass
class SmartOrderRequest:
    """Smart order request with position awareness"""
    symbol: str
    exchange: str
    action: OrderAction
    order_type: str
    quantity: float
    price: Optional[float] = None
    trigger_price: Optional[float] = None
    product_type: str = "INTRADAY"
    validity: str = "DAY"
    tag: Optional[str] = None
    
    # Smart order specific
    check_duplicates: bool = True
    duplicate_window_seconds: int = 60
    adjust_for_position: bool = True
    max_position_size: Optional[float] = None


@dataclass
class SmartOrderResult:
    """Result of smart order processing"""
    success: bool
    order_id: Optional[str] = None
    status: SmartOrderStatus = SmartOrderStatus.PENDING
    message: str = ""
    adjusted_quantity: Optional[float] = None
    blocked_reason: Optional[str] = None
    original_request: Optional[SmartOrderRequest] = None
    position_info: Optional[PositionInfo] = None
    metadata: Dict[str, Any] = None


class SmartOrderService:
    """
    Smart Order Service for position-aware order routing.
    
    Features:
    - Duplicate order detection and prevention
    - Position-aware quantity adjustment
    - Risk limit validation
    - Order batching for similar requests
    """
    
    def __init__(self, order_manager=None, db_session=None):
        """
        Initialize smart order service.
        
        Args:
            order_manager: OrderManager instance for placing orders
            db_session: Database session for storing order history
        """
        self.order_manager = order_manager
        self.db = db_session
        self._recent_orders: Dict[str, datetime] = {}
        self._lock = asyncio.Lock()
        
    async def place_smart_order(
        self,
        broker_id: str,
        request: SmartOrderRequest,
        user_id: Optional[str] = None
    ) -> SmartOrderResult:
        """
        Place a smart order with position awareness and duplicate detection.
        
        Args:
            broker_id: Broker connection ID
            request: Smart order request
            user_id: Optional user ID for position tracking
            
        Returns:
            SmartOrderResult with status and details
        """
        async with self._lock:
            try:
                # Step 1: Check for duplicate orders
                if request.check_duplicates:
                    is_duplicate, duplicate_info = await self._check_duplicate(
                        broker_id, request
                    )
                    if is_duplicate:
                        return SmartOrderResult(
                            success=False,
                            status=SmartOrderStatus.DUPLICATE_BLOCKED,
                            message=f"Duplicate order detected within {request.duplicate_window_seconds}s",
                            blocked_reason="duplicate",
                            original_request=request,
                            metadata=duplicate_info
                        )
                
                # Step 2: Get current position
                position = await self._get_position(broker_id, request.symbol, request.exchange)
                
                # Step 3: Validate against position limits
                if request.adjust_for_position and request.max_position_size:
                    adjusted_qty = self._calculate_adjusted_quantity(
                        request, position, request.max_position_size
                    )
                    if adjusted_qty != request.quantity:
                        logger.info(
                            f"Adjusted quantity from {request.quantity} to {adjusted_qty} "
                            f"based on position limits"
                        )
                        request.quantity = adjusted_qty
                
                # Step 4: Check for position closure scenario
                if position and self._is_position_closure(request, position):
                    logger.info(f"Order will close existing position for {request.symbol}")
                
                # Step 5: Place the order
                if self.order_manager:
                    from .order_manager import OrderRequest
                    
                    order_req = OrderRequest(
                        symbol=request.symbol,
                        exchange=request.exchange,
                        action=request.action.value,
                        order_type=request.order_type,
                        product_type=request.product_type,
                        quantity=request.quantity,
                        price=request.price,
                        trigger_price=request.trigger_price,
                        validity=request.validity,
                        tag=request.tag or "smart_order"
                    )
                    
                    result = await self.order_manager.place_order(broker_id, order_req)
                    
                    if result.success:
                        # Record this order for duplicate detection
                        order_key = self._generate_order_key(broker_id, request)
                        self._recent_orders[order_key] = datetime.utcnow()
                        
                        return SmartOrderResult(
                            success=True,
                            order_id=result.order_id,
                            status=SmartOrderStatus.EXECUTED,
                            message=result.message,
                            adjusted_quantity=request.quantity,
                            original_request=request,
                            position_info=position,
                            metadata={
                                "broker_order_id": result.broker_order_id,
                                "status": result.status
                            }
                        )
                    else:
                        return SmartOrderResult(
                            success=False,
                            status=SmartOrderStatus.REJECTED,
                            message=result.message,
                            original_request=request,
                            position_info=position
                        )
                else:
                    # Demo mode - no order manager
                    order_key = self._generate_order_key(broker_id, request)
                    self._recent_orders[order_key] = datetime.utcnow()
                    
                    return SmartOrderResult(
                        success=True,
                        order_id=f"smart_{datetime.utcnow().timestamp()}",
                        status=SmartOrderStatus.APPROVED,
                        message="Smart order validated (demo mode - no execution)",
                        adjusted_quantity=request.quantity,
                        original_request=request,
                        position_info=position,
                        metadata={"demo": True}
                    )
                    
            except Exception as e:
                logger.error(f"Smart order processing failed: {e}")
                return SmartOrderResult(
                    success=False,
                    status=SmartOrderStatus.REJECTED,
                    message=f"Processing error: {str(e)}",
                    original_request=request
                )
    
    async def _check_duplicate(
        self,
        broker_id: str,
        request: SmartOrderRequest
    ) -> tuple[bool, Dict[str, Any]]:
        """Check if this is a duplicate order within the time window."""
        order_key = self._generate_order_key(broker_id, request)
        now = datetime.utcnow()
        
        # Clean old entries
        cutoff = now.timestamp() - request.duplicate_window_seconds
        old_keys = [
            k for k, ts in self._recent_orders.items()
            if ts.timestamp() < cutoff
        ]
        for k in old_keys:
            del self._recent_orders[k]
        
        # Check for duplicate
        if order_key in self._recent_orders:
            time_diff = (now - self._recent_orders[order_key]).total_seconds()
            return True, {
                "original_time": self._recent_orders[order_key].isoformat(),
                "seconds_ago": time_diff,
                "key": order_key
            }
        
        return False, {}
    
    def _generate_order_key(self, broker_id: str, request: SmartOrderRequest) -> str:
        """Generate a unique key for duplicate detection."""
        return (
            f"{broker_id}:{request.symbol}:{request.exchange}:"
            f"{request.action.value}:{request.quantity}:{request.price or 'MKT'}"
        )
    
    async def _get_position(
        self,
        broker_id: str,
        symbol: str,
        exchange: str
    ) -> Optional[PositionInfo]:
        """Get current position for a symbol."""
        try:
            # In a real implementation, this would query positions from the broker
            # For now, return None to indicate no position
            return None
        except Exception as e:
            logger.warning(f"Could not fetch position: {e}")
            return None
    
    def _calculate_adjusted_quantity(
        self,
        request: SmartOrderRequest,
        position: Optional[PositionInfo],
        max_position_size: float
    ) -> float:
        """Calculate adjusted quantity based on position limits."""
        if not position:
            return min(request.quantity, max_position_size)
        
        current_qty = abs(position.quantity)
        
        if request.action == OrderAction.BUY:
            # Buying adds to position
            if position.side == "LONG":
                # Adding to long position
                allowed = max_position_size - current_qty
                return min(request.quantity, max(0, allowed))
            else:
                # Short position - buying reduces it first
                if request.quantity <= current_qty:
                    # Closing part of short
                    return request.quantity
                else:
                    # Will flip to long - check limit
                    new_long_qty = request.quantity - current_qty
                    if new_long_qty <= max_position_size:
                        return request.quantity
                    else:
                        return current_qty + max_position_size
        else:
            # Selling
            if position.side == "SHORT":
                # Adding to short position
                allowed = max_position_size - current_qty
                return min(request.quantity, max(0, allowed))
            else:
                # Long position - selling reduces it
                return min(request.quantity, current_qty * 2)  # Allow some flexibility
    
    def _is_position_closure(
        self,
        request: SmartOrderRequest,
        position: PositionInfo
    ) -> bool:
        """Check if this order would close the existing position."""
        if not position or position.quantity == 0:
            return False
        
        if request.action == OrderAction.SELL and position.side == "LONG":
            return request.quantity >= position.quantity
        
        if request.action == OrderAction.BUY and position.side == "SHORT":
            return request.quantity >= abs(position.quantity)
        
        return False
    
    async def get_smart_order_history(
        self,
        broker_id: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get recent smart order history."""
        # In production, this would query the database
        return []
    
    async def validate_order_request(
        self,
        request: SmartOrderRequest
    ) -> tuple[bool, str]:
        """Validate a smart order request without placing it."""
        if request.quantity <= 0:
            return False, "Quantity must be greater than 0"
        
        if not request.symbol or not request.exchange:
            return False, "Symbol and exchange are required"
        
        if request.price is not None and request.price <= 0:
            return False, "Price must be greater than 0 for limit orders"
        
        if request.trigger_price is not None and request.trigger_price <= 0:
            return False, "Trigger price must be greater than 0 for stop orders"
        
        return True, "Order request is valid"
