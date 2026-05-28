"""
GTT Order Service (Good Till Triggered)

GTT order logic and status tracking.
Mirrors OpenAlgo's GTT order functionality.

Requirements: Good-Till-Triggered order support
"""

import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime, date
from dataclasses import dataclass
from enum import Enum
from uuid import uuid4
import logging

logger = logging.getLogger(__name__)


class GTTStatus(Enum):
    ACTIVE = "active"
    TRIGGERED = "triggered"
    EXECUTED = "executed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    REJECTED = "rejected"


class GTTType(Enum):
    SINGLE = "single"  # Single trigger condition
    OCO = "oco"  # One-Cancels-Other (two conditions)
    OCO_LIMIT = "oco_limit"  # OCO with limit order on one side


@dataclass
class GTTCondition:
    """GTT trigger condition"""
    id: str
    gtt_type: GTTType
    trigger_price: float
    limit_price: Optional[float] = None  # For OCO_LIMIT
    trigger_type: str = "LTP"  # LTP or ATP
    triggered_at: Optional[datetime] = None
    executed_order_id: Optional[str] = None


@dataclass
class GTTOrder:
    """GTT Order container"""
    id: str
    broker_id: str
    user_id: str
    symbol: str
    exchange: str
    action: str  # BUY or SELL
    product_type: str
    quantity: float
    gtt_type: GTTType
    conditions: List[GTTCondition]
    status: GTTStatus
    validity_days: int  # Days until auto-expiry
    created_at: datetime
    expires_at: datetime
    triggered_at: Optional[datetime] = None
    executed_at: Optional[datetime] = None
    metadata: Dict[str, Any] = None


class GTTOrderService:
    """
    GTT (Good Till Triggered) Order Service.
    
    Features:
    - Single trigger orders
    - OCO (One-Cancels-Other) orders
    - OCO with limit orders
    - Automatic expiry handling
    - Price monitoring and triggering
    """
    
    MAX_VALIDITY_DAYS = 365
    
    def __init__(self, order_manager=None, db_session=None):
        """
        Initialize GTT order service.
        
        Args:
            order_manager: OrderManager for executing triggered orders
            db_session: Database session for persistence
        """
        self.order_manager = order_manager
        self.db = db_session
        self._gtt_orders: Dict[str, GTTOrder] = {}
        self._lock = asyncio.Lock()
        self._monitor_task: Optional[asyncio.Task] = None
        self._price_cache: Dict[str, float] = {}  # symbol -> last_price
    
    async def start(self):
        """Start the GTT monitoring service."""
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("GTT Order Service started")
    
    async def stop(self):
        """Stop the GTT monitoring service."""
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        logger.info("GTT Order Service stopped")
    
    async def create_gtt(
        self,
        broker_id: str,
        user_id: str,
        symbol: str,
        exchange: str,
        action: str,
        quantity: float,
        gtt_type: str,
        trigger_conditions: List[Dict[str, Any]],
        product_type: str = "DELIVERY",
        validity_days: int = 30
    ) -> GTTOrder:
        """
        Create a new GTT order.
        
        Args:
            broker_id: Broker connection ID
            user_id: User ID
            symbol: Trading symbol
            exchange: Exchange
            action: BUY or SELL
            quantity: Order quantity
            gtt_type: "single", "oco", or "oco_limit"
            trigger_conditions: List of trigger conditions
            product_type: Product type
            validity_days: Days until expiry (max 365)
            
        Returns:
            GTTOrder with assigned ID
        """
        if validity_days > self.MAX_VALIDITY_DAYS:
            raise ValueError(f"Validity cannot exceed {self.MAX_VALIDITY_DAYS} days")
        
        if len(trigger_conditions) < 1:
            raise ValueError("At least one trigger condition required")
        
        if gtt_type in ["oco", "oco_limit"] and len(trigger_conditions) != 2:
            raise ValueError("OCO orders require exactly 2 trigger conditions")
        
        conditions = []
        for i, cond_data in enumerate(trigger_conditions):
            conditions.append(GTTCondition(
                id=str(uuid4()),
                gtt_type=GTTType(gtt_type),
                trigger_price=cond_data["trigger_price"],
                limit_price=cond_data.get("limit_price"),
                trigger_type=cond_data.get("trigger_type", "LTP")
            ))
        
        now = datetime.utcnow()
        gtt = GTTOrder(
            id=str(uuid4()),
            broker_id=broker_id,
            user_id=user_id,
            symbol=symbol,
            exchange=exchange,
            action=action,
            product_type=product_type,
            quantity=quantity,
            gtt_type=GTTType(gtt_type),
            conditions=conditions,
            status=GTTStatus.ACTIVE,
            validity_days=validity_days,
            created_at=now,
            expires_at=now + timedelta(days=validity_days),
            metadata={"created_by": user_id}
        )
        
        async with self._lock:
            self._gtt_orders[gtt.id] = gtt
        
        logger.info(
            f"GTT {gtt.id} created: {symbol} {action} {gtt_type} "
            f"with {len(conditions)} condition(s)"
        )
        
        return gtt
    
    async def cancel_gtt(self, gtt_id: str) -> bool:
        """
        Cancel an active GTT order.
        
        Args:
            gtt_id: GTT order ID
            
        Returns:
            True if cancelled successfully
        """
        async with self._lock:
            gtt = self._gtt_orders.get(gtt_id)
            if not gtt:
                return False
            
            if gtt.status != GTTStatus.ACTIVE:
                logger.warning(f"Cannot cancel GTT {gtt_id} with status {gtt.status}")
                return False
            
            gtt.status = GTTStatus.CANCELLED
            gtt.metadata["cancelled_at"] = datetime.utcnow().isoformat()
            
            logger.info(f"GTT {gtt_id} cancelled")
            return True
    
    async def modify_gtt(
        self,
        gtt_id: str,
        trigger_conditions: Optional[List[Dict[str, Any]]] = None,
        validity_days: Optional[int] = None
    ) -> Optional[GTTOrder]:
        """
        Modify an active GTT order.
        
        Args:
            gtt_id: GTT order ID
            trigger_conditions: New trigger conditions
            validity_days: New validity period
            
        Returns:
            Updated GTTOrder or None if not found
        """
        async with self._lock:
            gtt = self._gtt_orders.get(gtt_id)
            if not gtt or gtt.status != GTTStatus.ACTIVE:
                return None
            
            if trigger_conditions:
                # Validate condition count for GTT type
                if gtt.gtt_type in [GTTType.OCO, GTTType.OCO_LIMIT]:
                    if len(trigger_conditions) != 2:
                        raise ValueError("OCO orders require exactly 2 conditions")
                
                gtt.conditions = [
                    GTTCondition(
                        id=str(uuid4()),
                        gtt_type=gtt.gtt_type,
                        trigger_price=c["trigger_price"],
                        limit_price=c.get("limit_price"),
                        trigger_type=c.get("trigger_type", "LTP")
                    )
                    for c in trigger_conditions
                ]
            
            if validity_days:
                gtt.validity_days = validity_days
                gtt.expires_at = datetime.utcnow() + timedelta(days=validity_days)
            
            gtt.metadata["modified_at"] = datetime.utcnow().isoformat()
            
            logger.info(f"GTT {gtt_id} modified")
            return gtt
    
    async def get_gtt(self, gtt_id: str) -> Optional[GTTOrder]:
        """Get GTT order details."""
        return self._gtt_orders.get(gtt_id)
    
    async def list_gtts(
        self,
        broker_id: Optional[str] = None,
        user_id: Optional[str] = None,
        status: Optional[GTTStatus] = None,
        symbol: Optional[str] = None
    ) -> List[GTTOrder]:
        """List GTT orders with filtering."""
        gtts = []
        for gtt in self._gtt_orders.values():
            if broker_id and gtt.broker_id != broker_id:
                continue
            if user_id and gtt.user_id != user_id:
                continue
            if status and gtt.status != status:
                continue
            if symbol and gtt.symbol != symbol:
                continue
            gtts.append(gtt)
        
        # Sort by creation time, newest first
        return sorted(gtts, key=lambda g: g.created_at, reverse=True)
    
    async def update_price(self, symbol: str, price: float):
        """Update current market price for a symbol."""
        self._price_cache[symbol] = price
    
    async def _monitor_loop(self):
        """Background loop to monitor prices and trigger GTTs."""
        while True:
            try:
                await asyncio.sleep(5)  # Check every 5 seconds
                
                now = datetime.utcnow()
                
                async with self._lock:
                    for gtt in list(self._gtt_orders.values()):
                        if gtt.status != GTTStatus.ACTIVE:
                            continue
                        
                        # Check expiry
                        if now > gtt.expires_at:
                            gtt.status = GTTStatus.EXPIRED
                            logger.info(f"GTT {gtt.id} expired")
                            continue
                        
                        # Check price and trigger
                        current_price = self._price_cache.get(gtt.symbol)
                        if current_price is None:
                            continue
                        
                        await self._check_and_trigger(gtt, current_price)
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"GTT monitor error: {e}")
    
    async def _check_and_trigger(self, gtt: GTTOrder, current_price: float):
        """Check if GTT should be triggered at current price."""
        triggered_conditions = []
        
        for condition in gtt.conditions:
            if condition.triggered_at:
                continue  # Already triggered
            
            # Check trigger condition
            if gtt.action == "BUY":
                # For BUY: trigger when price drops to or below trigger
                if current_price <= condition.trigger_price:
                    triggered_conditions.append(condition)
            else:  # SELL
                # For SELL: trigger when price rises to or above trigger
                if current_price >= condition.trigger_price:
                    triggered_conditions.append(condition)
        
        if triggered_conditions:
            # For OCO, trigger the first one and cancel the other
            if gtt.gtt_type in [GTTType.OCO, GTTType.OCO_LIMIT]:
                # Trigger the first condition
                primary = triggered_conditions[0]
                primary.triggered_at = datetime.utcnow()
                
                # Mark other conditions as cancelled
                for cond in gtt.conditions:
                    if cond != primary:
                        cond.triggered_at = datetime.utcnow()
                        # Mark as implicitly cancelled
                
                await self._execute_triggered_order(gtt, primary)
            else:
                # Single condition - just trigger it
                for cond in triggered_conditions:
                    cond.triggered_at = datetime.utcnow()
                    await self._execute_triggered_order(gtt, cond)
    
    async def _execute_triggered_order(self, gtt: GTTOrder, condition: GTTCondition):
        """Execute order when GTT is triggered."""
        gtt.status = GTTStatus.TRIGGERED
        gtt.triggered_at = datetime.utcnow()
        
        logger.info(
            f"GTT {gtt.id} triggered at {condition.trigger_price} "
            f"(current action: {gtt.action})"
        )
        
        if not self.order_manager:
            # Demo mode
            gtt.status = GTTStatus.EXECUTED
            gtt.executed_at = datetime.utcnow()
            condition.executed_order_id = f"demo_{uuid4().hex[:8]}"
            return
        
        try:
            from .order_manager import OrderRequest
            
            # Determine order type based on GTT type
            if gtt.gtt_type == GTTType.OCO_LIMIT and condition.limit_price:
                order_type = "LIMIT"
                price = condition.limit_price
            else:
                order_type = "MARKET"
                price = None
            
            order_req = OrderRequest(
                symbol=gtt.symbol,
                exchange=gtt.exchange,
                action=gtt.action,
                order_type=order_type,
                product_type=gtt.product_type,
                quantity=gtt.quantity,
                price=price,
                validity="DAY",
                tag="gtt_triggered"
            )
            
            result = await self.order_manager.place_order(gtt.broker_id, order_req)
            
            if result.success:
                gtt.status = GTTStatus.EXECUTED
                gtt.executed_at = datetime.utcnow()
                condition.executed_order_id = result.order_id
                logger.info(f"GTT {gtt.id} executed: order {result.order_id}")
            else:
                gtt.status = GTTStatus.REJECTED
                gtt.metadata["rejection_reason"] = result.message
                logger.error(f"GTT {gtt.id} execution failed: {result.message}")
                
        except Exception as e:
            gtt.status = GTTStatus.REJECTED
            gtt.metadata["error"] = str(e)
            logger.exception(f"GTT {gtt.id} execution error: {e}")
    
    def gtt_to_dict(self, gtt: GTTOrder) -> Dict[str, Any]:
        """Convert GTT order to dictionary for API responses."""
        return {
            "id": gtt.id,
            "broker_id": gtt.broker_id,
            "user_id": gtt.user_id,
            "symbol": gtt.symbol,
            "exchange": gtt.exchange,
            "action": gtt.action,
            "quantity": gtt.quantity,
            "gtt_type": gtt.gtt_type.value,
            "product_type": gtt.product_type,
            "status": gtt.status.value,
            "validity_days": gtt.validity_days,
            "created_at": gtt.created_at.isoformat(),
            "expires_at": gtt.expires_at.isoformat(),
            "triggered_at": gtt.triggered_at.isoformat() if gtt.triggered_at else None,
            "executed_at": gtt.executed_at.isoformat() if gtt.executed_at else None,
            "conditions": [
                {
                    "id": c.id,
                    "trigger_price": c.trigger_price,
                    "limit_price": c.limit_price,
                    "trigger_type": c.trigger_type,
                    "triggered_at": c.triggered_at.isoformat() if c.triggered_at else None,
                    "executed_order_id": c.executed_order_id
                }
                for c in gtt.conditions
            ],
            "metadata": gtt.metadata
        }


# Import timedelta for use in the module
from datetime import timedelta
