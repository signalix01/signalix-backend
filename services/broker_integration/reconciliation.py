"""
Position Reconciliation

Implements position reconciliation between broker and internal tracking.
Fetches positions from broker every 5 minutes and compares with internal records.

Requirements: 39.1, 39.2, 39.3, 39.4, 39.5
"""

import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


@dataclass
class ReconciliationResult:
    """Result of position reconciliation"""
    broker_id: str
    timestamp: datetime
    positions_matched: int
    positions_mismatched: int
    positions_missing: int
    positions_unexpected: int
    discrepancies: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "success"  # success, partial, failed
    error_message: Optional[str] = None


class PositionReconciliation:
    """
    Position reconciliation service.
    
    Periodically reconciles positions with broker to ensure data accuracy.
    """
    
    RECONCILE_INTERVAL = 300  # 5 minutes
    
    def __init__(self, connection_manager, order_manager, db_session=None):
        """
        Initialize reconciliation service.
        
        Args:
            connection_manager: ConnectionManager instance
            order_manager: OrderManager instance
            db_session: Database session for persistence
        """
        self.connection_manager = connection_manager
        self.order_manager = order_manager
        self.db = db_session
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._last_results: Dict[str, ReconciliationResult] = {}
        self._callbacks = []
    
    async def start(self):
        """Start the reconciliation service."""
        self._running = True
        self._task = asyncio.create_task(self._reconciliation_loop())
        logger.info("Position reconciliation service started")
    
    async def stop(self):
        """Stop the reconciliation service."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Position reconciliation service stopped")
    
    async def _reconciliation_loop(self):
        """Main reconciliation loop."""
        while self._running:
            try:
                await asyncio.sleep(self.RECONCILE_INTERVAL)
                
                if not self._running:
                    break
                
                # Get all active connections
                statuses = self.connection_manager.get_all_statuses()
                
                for broker_id, status in statuses.items():
                    if status.connected:
                        try:
                            result = await self.reconcile_positions(broker_id)
                            self._last_results[broker_id] = result
                            
                            # Emit event if discrepancies found
                            if result.positions_mismatched > 0 or result.positions_missing > 0:
                                await self._emit_reconciliation_alert(result)
                                
                        except Exception as e:
                            logger.error(f"Reconciliation failed for {broker_id}: {e}")
                            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in reconciliation loop: {e}")
    
    async def reconcile_positions(self, broker_id: str) -> ReconciliationResult:
        """
        Reconcile positions for a broker.
        
        Args:
            broker_id: Broker connection ID
            
        Returns:
            ReconciliationResult
        """
        start_time = datetime.utcnow()
        
        try:
            # Get adapter
            adapter = self.connection_manager.get_adapter(broker_id)
            if not adapter:
                return ReconciliationResult(
                    broker_id=broker_id,
                    timestamp=start_time,
                    positions_matched=0,
                    positions_mismatched=0,
                    positions_missing=0,
                    positions_unexpected=0,
                    status="failed",
                    error_message="Adapter not found"
                )
            
            # Fetch positions from broker
            broker_positions = await adapter.get_positions()
            broker_positions_dict = {
                f"{p.symbol}:{p.exchange}": p for p in broker_positions
            }
            
            # Get internal positions from database
            internal_positions = await self._get_internal_positions(broker_id)
            internal_positions_dict = {
                f"{p.symbol}:{p.exchange}": p for p in internal_positions
            }
            
            # Compare positions
            matched = 0
            mismatched = 0
            missing = 0
            unexpected = 0
            discrepancies = []
            
            # Check all internal positions
            for key, internal_pos in internal_positions_dict.items():
                if key in broker_positions_dict:
                    broker_pos = broker_positions_dict[key]
                    
                    # Compare quantities
                    if abs(internal_pos.quantity - broker_pos.quantity) > 0.01:
                        mismatched += 1
                        discrepancies.append({
                            "type": "quantity_mismatch",
                            "symbol": internal_pos.symbol,
                            "exchange": internal_pos.exchange,
                            "internal_quantity": internal_pos.quantity,
                            "broker_quantity": broker_pos.quantity,
                            "difference": internal_pos.quantity - broker_pos.quantity
                        })
                    else:
                        matched += 1
                        
                        # Update last reconciled timestamp
                        await self._update_position_reconciliation_status(
                            broker_id, internal_pos.symbol, internal_pos.exchange,
                            "matched", None
                        )
                else:
                    # Position missing in broker
                    missing += 1
                    discrepancies.append({
                        "type": "position_missing",
                        "symbol": internal_pos.symbol,
                        "exchange": internal_pos.exchange,
                        "internal_quantity": internal_pos.quantity,
                        "broker_quantity": 0
                    })
                    
                    await self._update_position_reconciliation_status(
                        broker_id, internal_pos.symbol, internal_pos.exchange,
                        "missing", {"reason": "Not found in broker"}
                    )
            
            # Check for unexpected positions in broker
            for key, broker_pos in broker_positions_dict.items():
                if key not in internal_positions_dict:
                    unexpected += 1
                    discrepancies.append({
                        "type": "unexpected_position",
                        "symbol": broker_pos.symbol,
                        "exchange": broker_pos.exchange,
                        "internal_quantity": 0,
                        "broker_quantity": broker_pos.quantity
                    })
                    
                    # Auto-correct: add to internal tracking
                    await self._add_internal_position(broker_id, broker_pos)
            
            # Determine status
            if mismatched == 0 and missing == 0 and unexpected == 0:
                status = "success"
            elif mismatched > 0 or missing > 0:
                status = "partial"
            else:
                status = "success"
            
            result = ReconciliationResult(
                broker_id=broker_id,
                timestamp=start_time,
                positions_matched=matched,
                positions_mismatched=mismatched,
                positions_missing=missing,
                positions_unexpected=unexpected,
                discrepancies=discrepancies,
                status=status
            )
            
            # Store reconciliation log
            await self._store_reconciliation_log(result)
            
            logger.info(
                f"Reconciliation complete for {broker_id}: "
                f"{matched} matched, {mismatched} mismatched, {missing} missing"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Reconciliation error for {broker_id}: {e}")
            return ReconciliationResult(
                broker_id=broker_id,
                timestamp=start_time,
                positions_matched=0,
                positions_mismatched=0,
                positions_missing=0,
                positions_unexpected=0,
                status="failed",
                error_message=str(e)
            )
    
    async def _get_internal_positions(self, broker_id: str) -> List[Any]:
        """Get internal positions from database."""
        if not self.db:
            return []
        
        try:
            from ..models import BrokerPosition
            
            positions = self.db.query(BrokerPosition).filter(
                BrokerPosition.connection_id == broker_id
            ).all()
            
            return positions
            
        except Exception as e:
            logger.error(f"Failed to fetch internal positions: {e}")
            return []
    
    async def _update_position_reconciliation_status(
        self,
        broker_id: str,
        symbol: str,
        exchange: str,
        status: str,
        discrepancy: Optional[Dict]
    ):
        """Update position reconciliation status in database."""
        if not self.db:
            return
        
        try:
            from ..models import BrokerPosition
            from datetime import datetime
            
            position = self.db.query(BrokerPosition).filter(
                BrokerPosition.connection_id == broker_id,
                BrokerPosition.symbol == symbol,
                BrokerPosition.exchange == exchange
            ).first()
            
            if position:
                position.last_reconciled_at = datetime.utcnow()
                position.reconciliation_status = status
                position.discrepancy = discrepancy
                
                self.db.commit()
                
        except Exception as e:
            logger.error(f"Failed to update reconciliation status: {e}")
            self.db.rollback()
    
    async def _add_internal_position(self, broker_id: str, position: Any):
        """Add a new position to internal tracking."""
        if not self.db:
            return
        
        try:
            from ..models import BrokerPosition, ProductType
            from uuid import uuid4
            from decimal import Decimal
            
            new_position = BrokerPosition(
                id=uuid4(),
                user_id=None,  # Would be set from broker_id
                connection_id=broker_id,
                symbol=position.symbol,
                exchange=position.exchange,
                product_type=ProductType(position.product_type.value) if hasattr(position.product_type, 'value') else ProductType.INTRADAY,
                quantity=Decimal(str(position.quantity)),
                average_price=Decimal(str(position.average_price)),
                last_price=Decimal(str(position.last_price)),
                pnl=Decimal(str(position.pnl)),
                pnl_percentage=Decimal(str(position.pnl_percentage)),
                reconciliation_status="auto_added",
                last_reconciled_at=datetime.utcnow(),
                created_at=datetime.utcnow()
            )
            
            self.db.add(new_position)
            self.db.commit()
            
            logger.info(f"Auto-added position {position.symbol} from broker reconciliation")
            
        except Exception as e:
            logger.error(f"Failed to add internal position: {e}")
            self.db.rollback()
    
    async def _store_reconciliation_log(self, result: ReconciliationResult):
        """Store reconciliation result in database."""
        if not self.db:
            return
        
        try:
            from ..models import ReconciliationLog
            from uuid import uuid4
            
            log = ReconciliationLog(
                id=uuid4(),
                user_id=None,  # Would be extracted from broker_id
                connection_id=result.broker_id,
                positions_matched=result.positions_matched,
                positions_mismatched=result.positions_mismatched,
                positions_missing=result.positions_missing,
                discrepancies=result.discrepancies,
                status=result.status,
                error_message=result.error_message,
                started_at=result.timestamp,
                completed_at=datetime.utcnow()
            )
            
            self.db.add(log)
            self.db.commit()
            
        except Exception as e:
            logger.error(f"Failed to store reconciliation log: {e}")
            self.db.rollback()
    
    async def _emit_reconciliation_alert(self, result: ReconciliationResult):
        """Emit alert for reconciliation discrepancies."""
        for callback in self._callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(result)
                else:
                    callback(result)
            except Exception as e:
                logger.error(f"Error in reconciliation callback: {e}")
    
    def on_discrepancy(self, callback):
        """Register callback for discrepancy alerts."""
        self._callbacks.append(callback)
    
    def get_last_result(self, broker_id: str) -> Optional[ReconciliationResult]:
        """Get last reconciliation result for a broker."""
        return self._last_results.get(broker_id)
    
    def get_all_results(self) -> Dict[str, ReconciliationResult]:
        """Get all last reconciliation results."""
        return self._last_results.copy()
