"""
Basket Order Service

Multi-symbol atomic order placement.
Mirrors OpenAlgo's basket order functionality.

Requirements: Multi-symbol atomic order placement
"""

import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime
from dataclasses import dataclass
from enum import Enum
from uuid import uuid4
import logging

logger = logging.getLogger(__name__)


class BasketStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    PARTIAL = "partial"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class BasketLeg:
    """Individual order in a basket"""
    symbol: str
    exchange: str
    action: str  # BUY or SELL
    order_type: str
    quantity: float
    price: Optional[float] = None
    trigger_price: Optional[float] = None
    product_type: str = "INTRADAY"
    
    # Execution results
    order_id: Optional[str] = None
    broker_order_id: Optional[str] = None
    status: str = "pending"
    message: Optional[str] = None
    executed_at: Optional[datetime] = None


@dataclass
class BasketOrder:
    """Basket order container"""
    id: str
    broker_id: str
    user_id: str
    legs: List[BasketLeg]
    status: BasketStatus
    created_at: datetime
    completed_at: Optional[datetime] = None
    execution_mode: str = "sequential"  # sequential or parallel
    atomic: bool = True  # If True, all must succeed or all cancelled
    metadata: Dict[str, Any] = None


class BasketOrderService:
    """
    Basket Order Service for multi-symbol atomic order placement.
    
    Features:
    - Multi-symbol order batching
    - Atomic execution (all-or-none)
    - Sequential or parallel execution modes
    - Automatic rollback on failure
    - Progress tracking
    """
    
    def __init__(self, order_manager=None, db_session=None):
        """
        Initialize basket order service.
        
        Args:
            order_manager: OrderManager instance for placing orders
            db_session: Database session for persistence
        """
        self.order_manager = order_manager
        self.db = db_session
        self._baskets: Dict[str, BasketOrder] = {}
        self._lock = asyncio.Lock()
    
    async def create_basket(
        self,
        broker_id: str,
        user_id: str,
        legs: List[Dict[str, Any]],
        execution_mode: str = "sequential",
        atomic: bool = True
    ) -> BasketOrder:
        """
        Create a new basket order.
        
        Args:
            broker_id: Broker connection ID
            user_id: User ID
            legs: List of order leg configurations
            execution_mode: "sequential" or "parallel"
            atomic: If True, all orders must succeed
            
        Returns:
            BasketOrder with assigned ID
        """
        basket_legs = []
        for leg_data in legs:
            basket_legs.append(BasketLeg(
                symbol=leg_data["symbol"],
                exchange=leg_data.get("exchange", "NSE"),
                action=leg_data["action"],
                order_type=leg_data["order_type"],
                quantity=leg_data["quantity"],
                price=leg_data.get("price"),
                trigger_price=leg_data.get("trigger_price"),
                product_type=leg_data.get("product_type", "INTRADAY")
            ))
        
        basket = BasketOrder(
            id=str(uuid4()),
            broker_id=broker_id,
            user_id=user_id,
            legs=basket_legs,
            status=BasketStatus.PENDING,
            created_at=datetime.utcnow(),
            execution_mode=execution_mode,
            atomic=atomic,
            metadata={"created_by": user_id}
        )
        
        async with self._lock:
            self._baskets[basket.id] = basket
        
        logger.info(f"Basket {basket.id} created with {len(legs)} legs")
        return basket
    
    async def execute_basket(self, basket_id: str) -> BasketOrder:
        """
        Execute a basket order.
        
        Args:
            basket_id: Basket order ID to execute
            
        Returns:
            Updated BasketOrder
        """
        async with self._lock:
            basket = self._baskets.get(basket_id)
            if not basket:
                raise ValueError(f"Basket {basket_id} not found")
            
            if basket.status != BasketStatus.PENDING:
                raise ValueError(f"Basket {basket_id} is not pending (status: {basket.status})")
            
            basket.status = BasketStatus.IN_PROGRESS
        
        try:
            if basket.execution_mode == "parallel":
                await self._execute_parallel(basket)
            else:
                await self._execute_sequential(basket)
            
            # Check results
            failed_legs = [l for l in basket.legs if l.status == "failed"]
            
            if failed_legs and basket.atomic:
                # Rollback - cancel successful orders
                await self._rollback_basket(basket)
                basket.status = BasketStatus.FAILED
                basket.metadata["failure_reason"] = f"{len(failed_legs)} legs failed, rolled back"
            elif failed_legs:
                basket.status = BasketStatus.PARTIAL
            else:
                basket.status = BasketStatus.COMPLETED
            
            basket.completed_at = datetime.utcnow()
            
        except Exception as e:
            logger.exception(f"Basket {basket_id} execution error: {e}")
            basket.status = BasketStatus.FAILED
            basket.metadata["error"] = str(e)
        
        return basket
    
    async def _execute_sequential(self, basket: BasketOrder):
        """Execute legs sequentially."""
        for i, leg in enumerate(basket.legs):
            try:
                if basket.atomic and any(l.status == "failed" for l in basket.legs[:i]):
                    # Skip remaining legs due to earlier failure
                    leg.status = "skipped"
                    continue
                
                result = await self._execute_leg(basket.broker_id, leg)
                
                if not result.success and basket.atomic:
                    # Stop on first failure in atomic mode
                    break
                    
            except Exception as e:
                logger.error(f"Leg execution error: {e}")
                leg.status = "failed"
                leg.message = str(e)
    
    async def _execute_parallel(self, basket: BasketOrder):
        """Execute legs in parallel."""
        tasks = [
            self._execute_leg(basket.broker_id, leg)
            for leg in basket.legs
        ]
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _execute_leg(self, broker_id: str, leg: BasketLeg):
        """Execute a single basket leg."""
        if not self.order_manager:
            # Demo mode
            leg.status = "completed"
            leg.order_id = f"demo_{uuid4().hex[:8]}"
            leg.executed_at = datetime.utcnow()
            return type('Result', (), {'success': True})()
        
        try:
            from .order_manager import OrderRequest
            
            order_req = OrderRequest(
                symbol=leg.symbol,
                exchange=leg.exchange,
                action=leg.action,
                order_type=leg.order_type,
                product_type=leg.product_type,
                quantity=leg.quantity,
                price=leg.price,
                trigger_price=leg.trigger_price,
                validity="DAY",
                tag="basket_order"
            )
            
            result = await self.order_manager.place_order(broker_id, order_req)
            
            if result.success:
                leg.status = "completed"
                leg.order_id = result.order_id
                leg.broker_order_id = result.broker_order_id
                leg.executed_at = datetime.utcnow()
            else:
                leg.status = "failed"
                leg.message = result.message
            
            return result
            
        except Exception as e:
            leg.status = "failed"
            leg.message = str(e)
            raise
    
    async def _rollback_basket(self, basket: BasketOrder):
        """Cancel successful orders in a failed atomic basket."""
        for leg in basket.legs:
            if leg.status == "completed" and leg.order_id:
                try:
                    if self.order_manager:
                        await self.order_manager.cancel_order(
                            basket.broker_id,
                            leg.order_id
                        )
                        leg.status = "cancelled"
                        logger.info(f"Rolled back leg {leg.order_id}")
                except Exception as e:
                    logger.error(f"Rollback failed for leg {leg.order_id}: {e}")
    
    async def cancel_basket(self, basket_id: str) -> bool:
        """
        Cancel a pending basket order.
        
        Args:
            basket_id: Basket order ID to cancel
            
        Returns:
            True if cancelled successfully
        """
        async with self._lock:
            basket = self._baskets.get(basket_id)
            if not basket:
                return False
            
            if basket.status not in [BasketStatus.PENDING, BasketStatus.IN_PROGRESS]:
                return False
            
            # Cancel any in-progress legs
            for leg in basket.legs:
                if leg.status == "completed" and leg.order_id:
                    try:
                        if self.order_manager:
                            await self.order_manager.cancel_order(
                                basket.broker_id,
                                leg.order_id
                            )
                        leg.status = "cancelled"
                    except Exception as e:
                        logger.error(f"Failed to cancel leg {leg.order_id}: {e}")
            
            basket.status = BasketStatus.CANCELLED
            basket.completed_at = datetime.utcnow()
            
            return True
    
    async def get_basket(self, basket_id: str) -> Optional[BasketOrder]:
        """Get basket order details."""
        return self._baskets.get(basket_id)
    
    async def list_baskets(
        self,
        broker_id: Optional[str] = None,
        user_id: Optional[str] = None,
        status: Optional[BasketStatus] = None
    ) -> List[BasketOrder]:
        """List basket orders with filtering."""
        baskets = []
        for basket in self._baskets.values():
            if broker_id and basket.broker_id != broker_id:
                continue
            if user_id and basket.user_id != user_id:
                continue
            if status and basket.status != status:
                continue
            baskets.append(basket)
        
        # Sort by creation time, newest first
        return sorted(baskets, key=lambda b: b.created_at, reverse=True)
    
    def basket_to_dict(self, basket: BasketOrder) -> Dict[str, Any]:
        """Convert basket to dictionary for API responses."""
        return {
            "id": basket.id,
            "broker_id": basket.broker_id,
            "user_id": basket.user_id,
            "status": basket.status.value,
            "execution_mode": basket.execution_mode,
            "atomic": basket.atomic,
            "created_at": basket.created_at.isoformat(),
            "completed_at": basket.completed_at.isoformat() if basket.completed_at else None,
            "legs": [
                {
                    "symbol": l.symbol,
                    "exchange": l.exchange,
                    "action": l.action,
                    "order_type": l.order_type,
                    "quantity": l.quantity,
                    "price": l.price,
                    "status": l.status,
                    "order_id": l.order_id,
                    "broker_order_id": l.broker_order_id,
                    "message": l.message,
                    "executed_at": l.executed_at.isoformat() if l.executed_at else None
                }
                for l in basket.legs
            ],
            "progress": {
                "total": len(basket.legs),
                "completed": len([l for l in basket.legs if l.status == "completed"]),
                "failed": len([l for l in basket.legs if l.status == "failed"]),
                "pending": len([l for l in basket.legs if l.status == "pending"])
            },
            "metadata": basket.metadata
        }
