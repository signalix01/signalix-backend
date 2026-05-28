"""
Action Center Service

Semi-automated queue for orders requiring manual approval.
Mirrors OpenAlgo's action_center_service.py functionality.

Requirements: Semi-auto order approval system
"""

import asyncio
from typing import Optional, Dict, Any, List, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
from uuid import uuid4
import logging

logger = logging.getLogger(__name__)


class ActionStatus(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    EXECUTED = "executed"
    CANCELLED = "cancelled"


class ActionPriority(Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class ActionItem:
    """Action item in the queue"""
    id: str
    order_request: Dict[str, Any]
    broker_id: str
    user_id: str
    status: ActionStatus
    priority: ActionPriority
    created_at: datetime
    expires_at: Optional[datetime]
    approved_at: Optional[datetime] = None
    approved_by: Optional[str] = None
    rejection_reason: Optional[str] = None
    execution_result: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class ActionCenter:
    """
    Action Center for semi-automated order approval.
    
    Features:
    - Queue for orders awaiting approval
    - Priority-based processing
    - Auto-expiry of pending actions
    - Risk rule validation
    - Audit trail
    """
    
    DEFAULT_EXPIRY_MINUTES = 5
    
    def __init__(self, order_manager=None, db_session=None):
        """
        Initialize action center.
        
        Args:
            order_manager: OrderManager instance for executing approved orders
            db_session: Database session for persistence
        """
        self.order_manager = order_manager
        self.db = db_session
        self._actions: Dict[str, ActionItem] = {}
        self._lock = asyncio.Lock()
        self._callbacks: List[Callable] = []
        self._cleanup_task: Optional[asyncio.Task] = None
        
    async def start(self):
        """Start the action center background tasks."""
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("Action Center started")
    
    async def stop(self):
        """Stop the action center."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        logger.info("Action Center stopped")
    
    async def submit_order_for_approval(
        self,
        broker_id: str,
        user_id: str,
        order_request: Dict[str, Any],
        priority: ActionPriority = ActionPriority.MEDIUM,
        expiry_minutes: Optional[int] = None,
        risk_checks: Optional[Dict[str, Any]] = None
    ) -> ActionItem:
        """
        Submit an order for manual approval.
        
        Args:
            broker_id: Broker connection ID
            user_id: User ID requesting the order
            order_request: Order details
            priority: Action priority level
            expiry_minutes: Minutes until auto-expiry (default: 5)
            risk_checks: Risk validation results
            
        Returns:
            ActionItem with the assigned action ID
        """
        async with self._lock:
            action_id = str(uuid4())
            now = datetime.utcnow()
            
            expiry = now + timedelta(
                minutes=expiry_minutes or self.DEFAULT_EXPIRY_MINUTES
            )
            
            action = ActionItem(
                id=action_id,
                order_request=order_request,
                broker_id=broker_id,
                user_id=user_id,
                status=ActionStatus.PENDING,
                priority=priority,
                created_at=now,
                expires_at=expiry,
                metadata={
                    "risk_checks": risk_checks or {},
                    "submitted_at": now.isoformat()
                }
            )
            
            self._actions[action_id] = action
            
            logger.info(
                f"Action {action_id} submitted for approval by user {user_id}"
            )
            
            # Notify callbacks
            await self._notify_subscribers("submitted", action)
            
            return action
    
    async def approve_action(
        self,
        action_id: str,
        approved_by: str,
        notes: Optional[str] = None
    ) -> Optional[ActionItem]:
        """
        Approve an action and execute the order.
        
        Args:
            action_id: Action ID to approve
            approved_by: User ID approving the action
            notes: Optional approval notes
            
        Returns:
            Updated ActionItem or None if not found
        """
        async with self._lock:
            action = self._actions.get(action_id)
            if not action:
                logger.warning(f"Action {action_id} not found for approval")
                return None
            
            if action.status != ActionStatus.PENDING:
                logger.warning(f"Action {action_id} is not pending (status: {action.status})")
                return None
            
            if datetime.utcnow() > action.expires_at:
                action.status = ActionStatus.EXPIRED
                logger.warning(f"Action {action_id} expired before approval")
                return action
            
            # Update action status
            action.status = ActionStatus.APPROVED
            action.approved_at = datetime.utcnow()
            action.approved_by = approved_by
            action.metadata["approval_notes"] = notes
            
            logger.info(f"Action {action_id} approved by {approved_by}")
            
            # Execute the order
            if self.order_manager:
                try:
                    from .order_manager import OrderRequest
                    
                    order_req = OrderRequest(
                        symbol=action.order_request["symbol"],
                        exchange=action.order_request.get("exchange", "NSE"),
                        action=action.order_request["action"],
                        order_type=action.order_request["order_type"],
                        product_type=action.order_request.get("product_type", "INTRADAY"),
                        quantity=action.order_request["quantity"],
                        price=action.order_request.get("price"),
                        trigger_price=action.order_request.get("trigger_price"),
                        validity=action.order_request.get("validity", "DAY"),
                        tag="action_center"
                    )
                    
                    result = await self.order_manager.place_order(
                        action.broker_id,
                        order_req
                    )
                    
                    if result.success:
                        action.status = ActionStatus.EXECUTED
                        action.execution_result = {
                            "order_id": result.order_id,
                            "broker_order_id": result.broker_order_id,
                            "status": result.status,
                            "executed_at": datetime.utcnow().isoformat()
                        }
                        logger.info(f"Action {action_id} executed successfully")
                    else:
                        action.execution_result = {
                            "error": result.message,
                            "failed_at": datetime.utcnow().isoformat()
                        }
                        logger.error(f"Action {action_id} execution failed: {result.message}")
                    
                except Exception as e:
                    action.execution_result = {
                        "error": str(e),
                        "failed_at": datetime.utcnow().isoformat()
                    }
                    logger.exception(f"Action {action_id} execution error: {e}")
            else:
                # Demo mode
                action.status = ActionStatus.APPROVED
                action.execution_result = {"demo": True}
            
            await self._notify_subscribers("approved", action)
            return action
    
    async def reject_action(
        self,
        action_id: str,
        rejected_by: str,
        reason: str
    ) -> Optional[ActionItem]:
        """
        Reject an action.
        
        Args:
            action_id: Action ID to reject
            rejected_by: User ID rejecting the action
            reason: Rejection reason
            
        Returns:
            Updated ActionItem or None if not found
        """
        async with self._lock:
            action = self._actions.get(action_id)
            if not action:
                return None
            
            if action.status != ActionStatus.PENDING:
                return None
            
            action.status = ActionStatus.REJECTED
            action.rejection_reason = reason
            action.metadata["rejected_by"] = rejected_by
            action.metadata["rejected_at"] = datetime.utcnow().isoformat()
            
            logger.info(f"Action {action_id} rejected by {rejected_by}: {reason}")
            
            await self._notify_subscribers("rejected", action)
            return action
    
    async def cancel_action(self, action_id: str, cancelled_by: str) -> bool:
        """
        Cancel a pending action (by the submitter).
        
        Args:
            action_id: Action ID to cancel
            cancelled_by: User ID cancelling the action
            
        Returns:
            True if cancelled successfully
        """
        async with self._lock:
            action = self._actions.get(action_id)
            if not action:
                return False
            
            if action.status != ActionStatus.PENDING:
                return False
            
            if action.user_id != cancelled_by:
                return False  # Can only cancel own actions
            
            action.status = ActionStatus.CANCELLED
            action.metadata["cancelled_by"] = cancelled_by
            action.metadata["cancelled_at"] = datetime.utcnow().isoformat()
            
            logger.info(f"Action {action_id} cancelled by {cancelled_by}")
            return True
    
    async def get_action(self, action_id: str) -> Optional[ActionItem]:
        """Get action details by ID."""
        return self._actions.get(action_id)
    
    async def list_pending_actions(
        self,
        broker_id: Optional[str] = None,
        user_id: Optional[str] = None,
        priority: Optional[ActionPriority] = None
    ) -> List[ActionItem]:
        """
        List pending actions with optional filtering.
        
        Args:
            broker_id: Filter by broker
            user_id: Filter by user
            priority: Filter by priority level
            
        Returns:
            List of pending ActionItems
        """
        actions = []
        for action in self._actions.values():
            if action.status != ActionStatus.PENDING:
                continue
            
            if broker_id and action.broker_id != broker_id:
                continue
            
            if user_id and action.user_id != user_id:
                continue
            
            if priority and action.priority != priority:
                continue
            
            actions.append(action)
        
        # Sort by priority (highest first), then by creation time
        return sorted(actions, key=lambda a: (-a.priority.value, a.created_at))
    
    async def get_action_stats(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        """Get action center statistics."""
        stats = {
            "pending": 0,
            "approved": 0,
            "rejected": 0,
            "expired": 0,
            "executed": 0,
            "cancelled": 0,
            "total": len(self._actions)
        }
        
        for action in self._actions.values():
            if user_id and action.user_id != user_id:
                continue
            
            stats[action.status.value] += 1
        
        stats["awaiting_approval"] = stats["pending"]
        
        return stats
    
    def on_action_update(self, callback: Callable):
        """Subscribe to action updates."""
        self._callbacks.append(callback)
    
    async def _notify_subscribers(self, event: str, action: ActionItem):
        """Notify subscribers of action updates."""
        for callback in self._callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(event, action)
                else:
                    callback(event, action)
            except Exception as e:
                logger.error(f"Error in action callback: {e}")
    
    async def _cleanup_loop(self):
        """Background task to clean up expired actions."""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute
                
                async with self._lock:
                    now = datetime.utcnow()
                    expired = []
                    
                    for action_id, action in self._actions.items():
                        if (
                            action.status == ActionStatus.PENDING and
                            now > action.expires_at
                        ):
                            action.status = ActionStatus.EXPIRED
                            expired.append(action_id)
                            logger.info(f"Action {action_id} auto-expired")
                    
                    if expired:
                        await self._notify_subscribers("expired", None)
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup loop error: {e}")
    
    def action_to_dict(self, action: ActionItem) -> Dict[str, Any]:
        """Convert action to dictionary for API responses."""
        return {
            "id": action.id,
            "status": action.status.value,
            "priority": action.priority.value,
            "priority_label": action.priority.name,
            "broker_id": action.broker_id,
            "user_id": action.user_id,
            "order_request": action.order_request,
            "created_at": action.created_at.isoformat(),
            "expires_at": action.expires_at.isoformat() if action.expires_at else None,
            "approved_at": action.approved_at.isoformat() if action.approved_at else None,
            "approved_by": action.approved_by,
            "rejection_reason": action.rejection_reason,
            "execution_result": action.execution_result,
            "metadata": action.metadata
        }
