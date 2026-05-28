"""
Order Splitter Service

Automated splitting for large block orders.
Implements iceberg orders and time-based splitting.

Requirements: Large order auto-splitting
"""

import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
from uuid import uuid4
import logging

logger = logging.getLogger(__name__)


class SplitStrategy(Enum):
    ICEBERG = "iceberg"  # Show only portion of total quantity
    TIME = "time"  # Split across time intervals
    VOLUME = "volume"  # Split based on market volume
    PRICE = "price"  # Split at different price levels


class SplitStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass
class SplitLeg:
    """Individual split order"""
    id: str
    quantity: float
    price: Optional[float]
    display_quantity: Optional[float]  # For iceberg orders
    delay_seconds: int
    status: str = "pending"
    order_id: Optional[str] = None
    executed_at: Optional[datetime] = None
    error_message: Optional[str] = None


@dataclass
class SplitOrder:
    """Split order container"""
    id: str
    broker_id: str
    user_id: str
    symbol: str
    exchange: str
    action: str
    order_type: str
    total_quantity: float
    product_type: str
    strategy: SplitStrategy
    legs: List[SplitLeg]
    status: SplitStatus
    created_at: datetime
    completed_at: Optional[datetime] = None
    metadata: Dict[str, Any] = None


class OrderSplitterService:
    """
    Order Splitter Service for large block orders.
    
    Features:
    - Iceberg orders (hidden quantity)
    - Time-based splitting
    - Volume-based splitting
    - Price-level splitting
    - Randomization to avoid detection
    """
    
    DEFAULT_MIN_CHUNK_SIZE = 1
    DEFAULT_MAX_CHUNKS = 20
    
    def __init__(self, order_manager=None, db_session=None):
        """
        Initialize order splitter service.
        
        Args:
            order_manager: OrderManager for executing split orders
            db_session: Database session for persistence
        """
        self.order_manager = order_manager
        self.db = db_session
        self._split_orders: Dict[str, SplitOrder] = {}
        self._lock = asyncio.Lock()
        self._active_tasks: Dict[str, asyncio.Task] = {}
    
    async def create_split_order(
        self,
        broker_id: str,
        user_id: str,
        symbol: str,
        exchange: str,
        action: str,
        order_type: str,
        total_quantity: float,
        strategy: str,
        strategy_params: Dict[str, Any],
        price: Optional[float] = None,
        trigger_price: Optional[float] = None,
        product_type: str = "INTRADAY"
    ) -> SplitOrder:
        """
        Create a new split order.
        
        Args:
            broker_id: Broker connection ID
            user_id: User ID
            symbol: Trading symbol
            exchange: Exchange
            action: BUY or SELL
            order_type: Order type
            total_quantity: Total order quantity
            strategy: Splitting strategy (iceberg, time, volume, price)
            strategy_params: Strategy-specific parameters
            price: Order price (for limit orders)
            trigger_price: Trigger price
            product_type: Product type
            
        Returns:
            SplitOrder with generated legs
        """
        strategy_enum = SplitStrategy(strategy)
        
        # Generate legs based on strategy
        if strategy_enum == SplitStrategy.ICEBERG:
            legs = self._generate_iceberg_legs(
                total_quantity,
                strategy_params,
                price
            )
        elif strategy_enum == SplitStrategy.TIME:
            legs = self._generate_time_legs(
                total_quantity,
                strategy_params,
                price
            )
        elif strategy_enum == SplitStrategy.PRICE:
            legs = self._generate_price_legs(
                total_quantity,
                strategy_params,
                price
            )
        else:
            legs = self._generate_time_legs(
                total_quantity,
                strategy_params,
                price
            )
        
        split_order = SplitOrder(
            id=str(uuid4()),
            broker_id=broker_id,
            user_id=user_id,
            symbol=symbol,
            exchange=exchange,
            action=action,
            order_type=order_type,
            total_quantity=total_quantity,
            product_type=product_type,
            strategy=strategy_enum,
            legs=legs,
            status=SplitStatus.PENDING,
            created_at=datetime.utcnow(),
            metadata={
                "trigger_price": trigger_price,
                "strategy_params": strategy_params
            }
        )
        
        async with self._lock:
            self._split_orders[split_order.id] = split_order
        
        logger.info(
            f"Split order {split_order.id} created: {total_quantity} {symbol} "
            f"in {len(legs)} leg(s) using {strategy} strategy"
        )
        
        return split_order
    
    def _generate_iceberg_legs(
        self,
        total_quantity: float,
        params: Dict[str, Any],
        price: Optional[float]
    ) -> List[SplitLeg]:
        """Generate iceberg order legs."""
        display_qty = params.get("display_quantity", total_quantity / 10)
        variance = params.get("variance_percent", 10)
        
        legs = []
        remaining = total_quantity
        leg_num = 1
        
        while remaining > 0:
            # Add random variance to display quantity
            import random
            variance_factor = 1 + (random.uniform(-variance, variance) / 100)
            chunk = min(display_qty * variance_factor, remaining)
            
            legs.append(SplitLeg(
                id=str(uuid4()),
                quantity=chunk,
                price=price,
                display_quantity=chunk if leg_num > 1 else display_qty,
                delay_seconds=params.get("refresh_delay", 2)
            ))
            
            remaining -= chunk
            leg_num += 1
        
        return legs
    
    def _generate_time_legs(
        self,
        total_quantity: float,
        params: Dict[str, Any],
        price: Optional[float]
    ) -> List[SplitLeg]:
        """Generate time-based split legs."""
        num_chunks = params.get("num_chunks", 5)
        interval_seconds = params.get("interval_seconds", 60)
        randomize = params.get("randomize_interval", False)
        
        import random
        
        # Calculate base chunk size
        base_chunk = total_quantity / num_chunks
        
        legs = []
        remaining = total_quantity
        
        for i in range(num_chunks):
            if i == num_chunks - 1:
                # Last leg gets remaining quantity
                chunk = remaining
            else:
                # Add slight randomization to chunk sizes
                chunk = min(base_chunk * random.uniform(0.9, 1.1), remaining)
            
            # Calculate delay
            if randomize:
                delay = int(interval_seconds * random.uniform(0.8, 1.2))
            else:
                delay = interval_seconds * i
            
            legs.append(SplitLeg(
                id=str(uuid4()),
                quantity=round(chunk, 2),
                price=price,
                display_quantity=None,
                delay_seconds=delay
            ))
            
            remaining -= chunk
            if remaining <= 0:
                break
        
        return legs
    
    def _generate_price_legs(
        self,
        total_quantity: float,
        params: Dict[str, Any],
        base_price: Optional[float]
    ) -> List[SplitLeg]:
        """Generate price-level split legs."""
        levels = params.get("price_levels", [0, -0.1, -0.2])  # offset from base
        distribution = params.get("distribution", "equal")  # equal or weighted
        
        if not base_price:
            base_price = 0  # Will be filled at market
        
        import random
        
        legs = []
        
        if distribution == "equal":
            qty_per_level = total_quantity / len(levels)
        else:
            # Weighted - more quantity at better prices
            weights = list(range(len(levels), 0, -1))
            total_weight = sum(weights)
        
        for i, level_pct in enumerate(levels):
            if distribution == "weighted":
                qty = total_quantity * weights[i] / total_weight
            else:
                qty = qty_per_level
            
            price = base_price * (1 + level_pct / 100) if base_price else None
            
            legs.append(SplitLeg(
                id=str(uuid4()),
                quantity=round(qty, 2),
                price=round(price, 2) if price else None,
                display_quantity=None,
                delay_seconds=i * 5  # Stagger by 5 seconds
            ))
        
        return legs
    
    async def execute_split_order(self, split_id: str) -> SplitOrder:
        """
        Execute a split order.
        
        Args:
            split_id: Split order ID
            
        Returns:
            Updated SplitOrder
        """
        async with self._lock:
            split_order = self._split_orders.get(split_id)
            if not split_order:
                raise ValueError(f"Split order {split_id} not found")
            
            if split_order.status != SplitStatus.PENDING:
                raise ValueError(f"Split order {split_id} is not pending")
            
            split_order.status = SplitStatus.IN_PROGRESS
        
        # Start execution task
        task = asyncio.create_task(
            self._execute_split_async(split_order),
            name=f"split_{split_id}"
        )
        
        async with self._lock:
            self._active_tasks[split_id] = task
        
        return split_order
    
    async def _execute_split_async(self, split_order: SplitOrder):
        """Execute split legs asynchronously."""
        try:
            for i, leg in enumerate(split_order.legs):
                # Wait for delay (skip first leg)
                if i > 0 and leg.delay_seconds > 0:
                    await asyncio.sleep(leg.delay_seconds)
                
                # Check if cancelled
                if split_order.status == SplitStatus.CANCELLED:
                    leg.status = "cancelled"
                    continue
                
                # Execute leg
                try:
                    await self._execute_leg(split_order, leg)
                except Exception as e:
                    leg.status = "failed"
                    leg.error_message = str(e)
                    logger.error(f"Leg {leg.id} execution failed: {e}")
                    
                    # Continue with next leg unless all must succeed
                    if split_order.metadata.get("abort_on_error"):
                        break
            
            # Update final status
            failed = [l for l in split_order.legs if l.status == "failed"]
            pending = [l for l in split_order.legs if l.status == "pending"]
            
            if failed and not pending:
                split_order.status = SplitStatus.FAILED
            elif pending:
                split_order.status = SplitStatus.IN_PROGRESS
            else:
                split_order.status = SplitStatus.COMPLETED
            
            split_order.completed_at = datetime.utcnow()
            
        except asyncio.CancelledError:
            split_order.status = SplitStatus.CANCELLED
            raise
        finally:
            async with self._lock:
                self._active_tasks.pop(split_order.id, None)
    
    async def _execute_leg(self, split_order: SplitOrder, leg: SplitLeg):
        """Execute a single split leg."""
        if not self.order_manager:
            # Demo mode
            leg.status = "completed"
            leg.order_id = f"demo_{uuid4().hex[:8]}"
            leg.executed_at = datetime.utcnow()
            return
        
        from .order_manager import OrderRequest
        
        order_req = OrderRequest(
            symbol=split_order.symbol,
            exchange=split_order.exchange,
            action=split_order.action,
            order_type=split_order.order_type if leg.price else "MARKET",
            product_type=split_order.product_type,
            quantity=leg.quantity,
            price=leg.price,
            validity="DAY",
            tag=f"split_order:{split_order.id}"
        )
        
        result = await self.order_manager.place_order(
            split_order.broker_id,
            order_req
        )
        
        if result.success:
            leg.status = "completed"
            leg.order_id = result.order_id
            leg.executed_at = datetime.utcnow()
            logger.info(f"Split leg {leg.id} executed: {result.order_id}")
        else:
            leg.status = "failed"
            leg.error_message = result.message
            raise Exception(result.message)
    
    async def cancel_split_order(self, split_id: str) -> bool:
        """
        Cancel a split order.
        
        Args:
            split_id: Split order ID
            
        Returns:
            True if cancelled
        """
        async with self._lock:
            split_order = self._split_orders.get(split_id)
            if not split_order:
                return False
            
            if split_order.status not in [SplitStatus.PENDING, SplitStatus.IN_PROGRESS]:
                return False
            
            split_order.status = SplitStatus.CANCELLED
            
            # Cancel any pending legs with order IDs
            for leg in split_order.legs:
                if leg.order_id and leg.status == "pending":
                    try:
                        if self.order_manager:
                            await self.order_manager.cancel_order(
                                split_order.broker_id,
                                leg.order_id
                            )
                    except Exception as e:
                        logger.error(f"Failed to cancel leg {leg.id}: {e}")
            
            # Cancel the execution task
            task = self._active_tasks.pop(split_id, None)
            if task:
                task.cancel()
            
            return True
    
    async def get_split_order(self, split_id: str) -> Optional[SplitOrder]:
        """Get split order details."""
        return self._split_orders.get(split_id)
    
    async def list_split_orders(
        self,
        broker_id: Optional[str] = None,
        user_id: Optional[str] = None,
        status: Optional[SplitStatus] = None
    ) -> List[SplitOrder]:
        """List split orders with filtering."""
        orders = []
        for order in self._split_orders.values():
            if broker_id and order.broker_id != broker_id:
                continue
            if user_id and order.user_id != user_id:
                continue
            if status and order.status != status:
                continue
            orders.append(order)
        
        return sorted(orders, key=lambda o: o.created_at, reverse=True)
    
    def split_order_to_dict(self, split_order: SplitOrder) -> Dict[str, Any]:
        """Convert split order to dictionary for API responses."""
        executed_qty = sum(
            l.quantity for l in split_order.legs
            if l.status == "completed"
        )
        
        return {
            "id": split_order.id,
            "broker_id": split_order.broker_id,
            "user_id": split_order.user_id,
            "symbol": split_order.symbol,
            "exchange": split_order.exchange,
            "action": split_order.action,
            "order_type": split_order.order_type,
            "total_quantity": split_order.total_quantity,
            "executed_quantity": round(executed_qty, 2),
            "remaining_quantity": round(split_order.total_quantity - executed_qty, 2),
            "product_type": split_order.product_type,
            "strategy": split_order.strategy.value,
            "status": split_order.status.value,
            "created_at": split_order.created_at.isoformat(),
            "completed_at": split_order.completed_at.isoformat() if split_order.completed_at else None,
            "progress": {
                "total_legs": len(split_order.legs),
                "completed": len([l for l in split_order.legs if l.status == "completed"]),
                "failed": len([l for l in split_order.legs if l.status == "failed"]),
                "pending": len([l for l in split_order.legs if l.status == "pending"])
            },
            "legs": [
                {
                    "id": l.id,
                    "quantity": l.quantity,
                    "price": l.price,
                    "display_quantity": l.display_quantity,
                    "delay_seconds": l.delay_seconds,
                    "status": l.status,
                    "order_id": l.order_id,
                    "executed_at": l.executed_at.isoformat() if l.executed_at else None,
                    "error_message": l.error_message
                }
                for l in split_order.legs
            ],
            "metadata": split_order.metadata
        }
