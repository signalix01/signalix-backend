"""
Churn Signal Detection Service
Detects early churn signals and triggers retention actions

Requirements: 11.7, 11.8
"""
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import logging

logger = logging.getLogger(__name__)


class ChurnSignalDetectionService:
    """
    Detect early churn signals and trigger proactive retention
    
    Monitors:
    - Login frequency drop >50% vs prior 7 days
    - Key feature usage stopped
    - Support ticket patterns
    - Billing page visits increased
    """
    
    def __init__(self):
        """Initialize churn detection service"""
        self.churn_signals: Dict[str, List[Dict[str, Any]]] = {}
        self.user_sessions: Dict[str, List[Dict[str, Any]]] = {}
        self.feature_usage: Dict[str, Dict[str, Any]] = {}
    
    async def detect_churn_signals(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Run all churn detection checks for a user
        
        Args:
            user_id: User ID to check
            
        Returns:
            List of detected churn signals
        """
        try:
            signals = []
            
            # Check login frequency
            login_signal = await self.check_login_frequency(user_id)
            if login_signal:
                signals.append(login_signal)
            
            # Check feature usage
            usage_signal = await self.check_feature_usage(user_id)
            if usage_signal:
                signals.append(usage_signal)
            
            # Check support patterns
            support_signal = await self.check_support_pattern(user_id)
            if support_signal:
                signals.append(support_signal)
            
            # Check billing page visits
            billing_signal = await self.check_billing_visits(user_id)
            if billing_signal:
                signals.append(billing_signal)
            
            # Store signals
            if signals:
                if user_id not in self.churn_signals:
                    self.churn_signals[user_id] = []
                self.churn_signals[user_id].extend(signals)
                
                logger.info(
                    f"Churn signals detected",
                    extra={
                        "user_id": user_id,
                        "signal_count": len(signals),
                        "signal_types": [s["signal_type"] for s in signals]
                    }
                )
                
                # Trigger retention actions
                await self.trigger_retention_actions(user_id, signals)
            
            return signals
            
        except Exception as e:
            logger.error(
                f"Failed to detect churn signals",
                extra={"user_id": user_id, "error": str(e)}
            )
            return []
    
    async def check_login_frequency(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Detect drop in login frequency
        
        Compares last 7 days vs previous 7 days.
        Triggers if drop >50%.
        
        Args:
            user_id: User ID
            
        Returns:
            Signal dict if detected, None otherwise
        """
        try:
            # Get login history (would query database in production)
            recent_logins = await self._get_login_history(user_id, days=7)
            previous_logins = await self._get_login_history(user_id, days=7, offset=7)
            
            recent_count = len(recent_logins)
            previous_count = len(previous_logins)
            
            # Need baseline to compare
            if previous_count == 0:
                return None
            
            # Calculate drop percentage
            drop_percentage = ((previous_count - recent_count) / previous_count) * 100
            
            # Trigger if drop >50%
            if drop_percentage > 50:
                strength = "high" if drop_percentage > 75 else "medium"
                
                logger.info(
                    f"Login frequency drop detected",
                    extra={
                        "user_id": user_id,
                        "recent_logins": recent_count,
                        "previous_logins": previous_count,
                        "drop_percentage": drop_percentage,
                        "strength": strength
                    }
                )
                
                return {
                    "signal_type": "login_frequency_drop",
                    "signal_strength": strength,
                    "signal_value": {
                        "recent_logins": recent_count,
                        "previous_logins": previous_count,
                        "drop_percentage": round(drop_percentage, 2)
                    },
                    "detected_at": datetime.utcnow().isoformat()
                }
            
            return None
            
        except Exception as e:
            logger.error(
                f"Failed to check login frequency",
                extra={"user_id": user_id, "error": str(e)}
            )
            return None
    
    async def check_feature_usage(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Detect stopped feature usage
        
        Checks if key features haven't been used in last 7 days
        but were used in previous 7 days.
        
        Args:
            user_id: User ID
            
        Returns:
            Signal dict if detected, None otherwise
        """
        try:
            # Key features to monitor
            key_features = [
                "analysis_run",
                "signal_viewed",
                "watchlist_updated",
                "risk_check"
            ]
            
            stopped_features = []
            
            for feature in key_features:
                recent_usage = await self._get_feature_usage(user_id, feature, days=7)
                previous_usage = await self._get_feature_usage(user_id, feature, days=7, offset=7)
                
                # Feature was used before but not recently
                if previous_usage > 0 and recent_usage == 0:
                    stopped_features.append({
                        "feature": feature,
                        "previous_usage": previous_usage
                    })
            
            # Trigger if any key feature stopped
            if stopped_features:
                strength = "high" if len(stopped_features) >= 3 else "medium"
                
                logger.info(
                    f"Feature usage stopped detected",
                    extra={
                        "user_id": user_id,
                        "stopped_features": [f["feature"] for f in stopped_features],
                        "strength": strength
                    }
                )
                
                return {
                    "signal_type": "feature_usage_stopped",
                    "signal_strength": strength,
                    "signal_value": {
                        "stopped_features": stopped_features,
                        "count": len(stopped_features)
                    },
                    "detected_at": datetime.utcnow().isoformat()
                }
            
            return None
            
        except Exception as e:
            logger.error(
                f"Failed to check feature usage",
                extra={"user_id": user_id, "error": str(e)}
            )
            return None
    
    async def check_support_pattern(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Detect support ticket pattern changes
        
        Triggers if:
        - Support tickets spike then stop (frustration)
        - Multiple unresolved tickets
        
        Args:
            user_id: User ID
            
        Returns:
            Signal dict if detected, None otherwise
        """
        try:
            # Get support ticket history
            recent_tickets = await self._get_support_tickets(user_id, days=14)
            previous_tickets = await self._get_support_tickets(user_id, days=14, offset=14)
            
            recent_count = len(recent_tickets)
            previous_count = len(previous_tickets)
            
            # Check for spike then stop pattern
            if previous_count >= 3 and recent_count == 0:
                logger.info(
                    f"Support ticket spike-stop pattern detected",
                    extra={
                        "user_id": user_id,
                        "previous_tickets": previous_count,
                        "recent_tickets": recent_count
                    }
                )
                
                return {
                    "signal_type": "support_ticket_spike_stop",
                    "signal_strength": "high",
                    "signal_value": {
                        "previous_tickets": previous_count,
                        "recent_tickets": recent_count,
                        "pattern": "spike_then_stop"
                    },
                    "detected_at": datetime.utcnow().isoformat()
                }
            
            # Check for unresolved tickets
            unresolved = [t for t in recent_tickets if t.get("status") != "resolved"]
            if len(unresolved) >= 2:
                logger.info(
                    f"Multiple unresolved tickets detected",
                    extra={
                        "user_id": user_id,
                        "unresolved_count": len(unresolved)
                    }
                )
                
                return {
                    "signal_type": "unresolved_support_tickets",
                    "signal_strength": "medium",
                    "signal_value": {
                        "unresolved_count": len(unresolved),
                        "ticket_ids": [t["id"] for t in unresolved]
                    },
                    "detected_at": datetime.utcnow().isoformat()
                }
            
            return None
            
        except Exception as e:
            logger.error(
                f"Failed to check support pattern",
                extra={"user_id": user_id, "error": str(e)}
            )
            return None
    
    async def check_billing_visits(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Detect increased billing page visits
        
        Triggers if billing/subscription page visits increased
        significantly (potential cancel intent).
        
        Args:
            user_id: User ID
            
        Returns:
            Signal dict if detected, None otherwise
        """
        try:
            # Get billing page visit history
            recent_visits = await self._get_page_visits(
                user_id,
                pages=["/settings/billing", "/subscription", "/settings/cancel"],
                days=7
            )
            previous_visits = await self._get_page_visits(
                user_id,
                pages=["/settings/billing", "/subscription", "/settings/cancel"],
                days=7,
                offset=7
            )
            
            recent_count = len(recent_visits)
            previous_count = len(previous_visits)
            
            # Trigger if visits increased significantly
            if recent_count >= 3 and recent_count > previous_count * 2:
                logger.info(
                    f"Billing page visits increased",
                    extra={
                        "user_id": user_id,
                        "recent_visits": recent_count,
                        "previous_visits": previous_count
                    }
                )
                
                return {
                    "signal_type": "billing_page_visits_increased",
                    "signal_strength": "high",
                    "signal_value": {
                        "recent_visits": recent_count,
                        "previous_visits": previous_count,
                        "pages_visited": list(set([v["page"] for v in recent_visits]))
                    },
                    "detected_at": datetime.utcnow().isoformat()
                }
            
            return None
            
        except Exception as e:
            logger.error(
                f"Failed to check billing visits",
                extra={"user_id": user_id, "error": str(e)}
            )
            return None
    
    async def trigger_retention_actions(
        self,
        user_id: str,
        signals: List[Dict[str, Any]]
    ) -> None:
        """
        Trigger retention actions based on churn signals
        
        Actions:
        - Send proactive retention email
        - Assign to customer success team
        - Offer discount or pause
        - Schedule check-in call
        
        Args:
            user_id: User ID
            signals: List of detected signals
        """
        try:
            # Determine action based on signal strength
            high_strength_signals = [s for s in signals if s["signal_strength"] == "high"]
            
            if high_strength_signals:
                # High priority - immediate action
                logger.info(
                    f"Triggering high-priority retention actions",
                    extra={
                        "user_id": user_id,
                        "signal_count": len(high_strength_signals)
                    }
                )
                
                # Send proactive retention email
                await self._send_retention_email(user_id, signals)
                
                # Assign to customer success
                await self._assign_to_customer_success(user_id, signals)
                
                # Offer proactive discount
                await self._offer_proactive_discount(user_id)
            else:
                # Medium priority - monitor and email
                logger.info(
                    f"Triggering medium-priority retention actions",
                    extra={"user_id": user_id}
                )
                
                # Send gentle check-in email
                await self._send_checkin_email(user_id, signals)
            
        except Exception as e:
            logger.error(
                f"Failed to trigger retention actions",
                extra={"user_id": user_id, "error": str(e)}
            )
    
    # Helper methods (would integrate with actual services in production)
    
    async def _get_login_history(
        self,
        user_id: str,
        days: int,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get login history for user"""
        # TODO: Query actual database
        # Placeholder: return empty list
        return []
    
    async def _get_feature_usage(
        self,
        user_id: str,
        feature: str,
        days: int,
        offset: int = 0
    ) -> int:
        """Get feature usage count"""
        # TODO: Query actual database
        return 0
    
    async def _get_support_tickets(
        self,
        user_id: str,
        days: int,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get support tickets"""
        # TODO: Query actual database
        return []
    
    async def _get_page_visits(
        self,
        user_id: str,
        pages: List[str],
        days: int,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get page visit history"""
        # TODO: Query actual analytics database
        return []
    
    async def _send_retention_email(
        self,
        user_id: str,
        signals: List[Dict[str, Any]]
    ) -> None:
        """Send proactive retention email"""
        logger.info(
            f"Retention email sent",
            extra={"user_id": user_id}
        )
        # TODO: Send via email service
    
    async def _send_checkin_email(
        self,
        user_id: str,
        signals: List[Dict[str, Any]]
    ) -> None:
        """Send check-in email"""
        logger.info(
            f"Check-in email sent",
            extra={"user_id": user_id}
        )
        # TODO: Send via email service
    
    async def _assign_to_customer_success(
        self,
        user_id: str,
        signals: List[Dict[str, Any]]
    ) -> None:
        """Assign user to customer success team"""
        logger.info(
            f"Assigned to customer success",
            extra={"user_id": user_id}
        )
        # TODO: Create task in CRM
    
    async def _offer_proactive_discount(self, user_id: str) -> None:
        """Offer proactive discount"""
        logger.info(
            f"Proactive discount offered",
            extra={"user_id": user_id}
        )
        # TODO: Create discount offer


# Global churn detection service instance
churn_detection_service = ChurnSignalDetectionService()
