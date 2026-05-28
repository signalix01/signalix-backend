"""
Dunning Service
Automated payment retry and recovery

Requirements: 11.6
"""
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import logging

logger = logging.getLogger(__name__)


class DunningService:
    """
    Automated payment retry and recovery service
    
    Implements smart retry logic with dunning email sequence:
    - Day 0: Immediate retry + payment failed email
    - Day 3: Retry + reminder email
    - Day 7: Retry + urgent warning email
    - Day 10: Final retry + final notice email
    """
    
    # Retry schedule configuration
    RETRY_SCHEDULE = [
        {"day": 0, "action": "immediate_retry", "email_template": "payment_failed"},
        {"day": 3, "action": "retry_and_email", "email_template": "payment_retry_day_3"},
        {"day": 7, "action": "retry_and_email", "email_template": "payment_retry_day_7"},
        {"day": 10, "action": "final_retry_and_email", "email_template": "payment_final_notice"},
    ]
    
    # Card expiry alert schedule (days before expiry)
    CARD_EXPIRY_ALERTS = [30, 15, 7]
    
    def __init__(self):
        """Initialize dunning service"""
        self.payment_failures: Dict[str, Dict[str, Any]] = {}
        self.retry_attempts: Dict[str, List[Dict[str, Any]]] = {}
    
    async def handle_payment_failure(
        self,
        user_id: str,
        subscription_id: str,
        amount: float,
        currency: str,
        failure_reason: str
    ) -> Dict[str, Any]:
        """
        Handle initial payment failure
        
        This method:
        1. Records the failure
        2. Attempts immediate retry
        3. Schedules dunning sequence if retry fails
        4. Sends initial failure email
        
        Args:
            user_id: User ID
            subscription_id: Subscription ID
            amount: Payment amount
            currency: Currency code
            failure_reason: Reason for failure
            
        Returns:
            Dict with failure_id and retry result
        """
        try:
            # Record failure
            failure_id = f"failure_{int(datetime.utcnow().timestamp() * 1000)}"
            failure = {
                "id": failure_id,
                "user_id": user_id,
                "subscription_id": subscription_id,
                "amount": amount,
                "currency": currency,
                "failure_reason": failure_reason,
                "failed_at": datetime.utcnow().isoformat(),
                "retry_count": 0,
                "status": "pending",
                "recovered": False
            }
            self.payment_failures[failure_id] = failure
            self.retry_attempts[failure_id] = []
            
            logger.info(
                f"Payment failure recorded",
                extra={
                    "failure_id": failure_id,
                    "user_id": user_id,
                    "subscription_id": subscription_id,
                    "amount": amount,
                    "currency": currency,
                    "reason": failure_reason
                }
            )
            
            # Immediate retry
            retry_result = await self.retry_payment(failure_id)
            
            if retry_result["success"]:
                # Payment recovered on first retry
                failure["status"] = "recovered"
                failure["recovered"] = True
                failure["recovered_at"] = datetime.utcnow().isoformat()
                
                logger.info(
                    f"Payment recovered on immediate retry",
                    extra={"failure_id": failure_id, "user_id": user_id}
                )
                
                # Send recovery email
                await self._send_email(
                    user_id=user_id,
                    template="payment_recovered",
                    context={}
                )
                
                return {
                    "failure_id": failure_id,
                    "recovered": True,
                    "retry_result": retry_result
                }
            
            # Schedule dunning sequence
            await self._schedule_dunning_sequence(failure_id)
            
            # Send initial failure email
            next_retry_date = datetime.utcnow() + timedelta(days=3)
            await self._send_email(
                user_id=user_id,
                template="payment_failed",
                context={
                    "amount": amount,
                    "currency": currency,
                    "retry_date": next_retry_date.strftime("%B %d, %Y"),
                    "update_card_url": f"{self._get_dashboard_url()}/settings/billing"
                }
            )
            
            return {
                "failure_id": failure_id,
                "recovered": False,
                "retry_result": retry_result,
                "dunning_scheduled": True
            }
            
        except Exception as e:
            logger.error(
                f"Failed to handle payment failure",
                extra={
                    "user_id": user_id,
                    "subscription_id": subscription_id,
                    "error": str(e)
                }
            )
            raise
    
    async def retry_payment(self, failure_id: str) -> Dict[str, Any]:
        """
        Attempt to retry payment
        
        Args:
            failure_id: Payment failure ID
            
        Returns:
            Dict with success status and details
        """
        try:
            failure = self.payment_failures.get(failure_id)
            if not failure:
                return {"success": False, "reason": "failure_not_found"}
            
            # Record retry attempt
            retry_attempt = {
                "attempted_at": datetime.utcnow().isoformat(),
                "retry_number": failure["retry_count"] + 1
            }
            
            # TODO: Implement actual payment retry logic with Stripe/Razorpay
            # For now, simulate retry (would fail in real implementation)
            retry_success = False  # Simulated failure
            
            if retry_success:
                retry_attempt["result"] = "success"
                failure["status"] = "recovered"
                failure["recovered"] = True
                failure["recovered_at"] = datetime.utcnow().isoformat()
                
                logger.info(
                    f"Payment retry successful",
                    extra={
                        "failure_id": failure_id,
                        "user_id": failure["user_id"],
                        "retry_number": retry_attempt["retry_number"]
                    }
                )
                
                return {"success": True, "retry_number": retry_attempt["retry_number"]}
            else:
                retry_attempt["result"] = "failed"
                failure["retry_count"] += 1
                
                logger.info(
                    f"Payment retry failed",
                    extra={
                        "failure_id": failure_id,
                        "user_id": failure["user_id"],
                        "retry_number": retry_attempt["retry_number"]
                    }
                )
                
                return {
                    "success": False,
                    "reason": "payment_declined",
                    "retry_number": retry_attempt["retry_number"]
                }
            
        except Exception as e:
            logger.error(
                f"Payment retry error",
                extra={"failure_id": failure_id, "error": str(e)}
            )
            return {"success": False, "reason": str(e)}
        finally:
            if failure_id in self.retry_attempts:
                self.retry_attempts[failure_id].append(retry_attempt)
    
    async def execute_dunning_step(self, failure_id: str, step: Dict[str, Any]) -> None:
        """
        Execute a dunning sequence step
        
        Args:
            failure_id: Payment failure ID
            step: Dunning step configuration
        """
        try:
            failure = self.payment_failures.get(failure_id)
            if not failure:
                logger.warning(f"Failure not found for dunning step: {failure_id}")
                return
            
            # Skip if already recovered or cancelled
            if failure["status"] in ["recovered", "cancelled"]:
                logger.info(
                    f"Skipping dunning step - status: {failure['status']}",
                    extra={"failure_id": failure_id}
                )
                return
            
            logger.info(
                f"Executing dunning step",
                extra={
                    "failure_id": failure_id,
                    "user_id": failure["user_id"],
                    "day": step["day"],
                    "action": step["action"]
                }
            )
            
            # Retry payment
            retry_result = await self.retry_payment(failure_id)
            
            if retry_result["success"]:
                # Payment recovered
                await self._send_email(
                    user_id=failure["user_id"],
                    template="payment_recovered",
                    context={}
                )
                return
            
            # Send dunning email
            if step["action"].endswith("_and_email"):
                days_remaining = 10 - step["day"]
                await self._send_email(
                    user_id=failure["user_id"],
                    template=step["email_template"],
                    context={
                        "retry_count": failure["retry_count"],
                        "days_remaining": days_remaining,
                        "amount": failure["amount"],
                        "currency": failure["currency"],
                        "update_card_url": f"{self._get_dashboard_url()}/settings/billing"
                    }
                )
            
            # Check if final attempt
            if step["day"] == 10:
                failure["status"] = "failed"
                
                logger.warning(
                    f"Payment recovery failed after all retries",
                    extra={
                        "failure_id": failure_id,
                        "user_id": failure["user_id"],
                        "total_retries": failure["retry_count"]
                    }
                )
                
                # Cancel subscription for non-payment
                await self._cancel_subscription_for_nonpayment(
                    user_id=failure["user_id"],
                    subscription_id=failure["subscription_id"]
                )
                
                # Send final cancellation notice
                await self._send_email(
                    user_id=failure["user_id"],
                    template="subscription_cancelled_nonpayment",
                    context={
                        "amount": failure["amount"],
                        "currency": failure["currency"],
                        "reactivate_url": f"{self._get_dashboard_url()}/subscription/reactivate"
                    }
                )
            
        except Exception as e:
            logger.error(
                f"Failed to execute dunning step",
                extra={
                    "failure_id": failure_id,
                    "step_day": step["day"],
                    "error": str(e)
                }
            )
    
    async def check_card_expiry(self, user_id: str, card_expiry_date: datetime) -> None:
        """
        Check card expiry and send alerts
        
        Args:
            user_id: User ID
            card_expiry_date: Card expiration date
        """
        try:
            days_until_expiry = (card_expiry_date - datetime.utcnow()).days
            
            # Check if alert should be sent
            if days_until_expiry in self.CARD_EXPIRY_ALERTS:
                logger.info(
                    f"Sending card expiry alert",
                    extra={
                        "user_id": user_id,
                        "days_until_expiry": days_until_expiry
                    }
                )
                
                await self._send_email(
                    user_id=user_id,
                    template="card_expiry_alert",
                    context={
                        "days_until_expiry": days_until_expiry,
                        "expiry_date": card_expiry_date.strftime("%B %Y"),
                        "update_card_url": f"{self._get_dashboard_url()}/settings/billing"
                    }
                )
        
        except Exception as e:
            logger.error(
                f"Failed to check card expiry",
                extra={"user_id": user_id, "error": str(e)}
            )
    
    async def _schedule_dunning_sequence(self, failure_id: str) -> None:
        """
        Schedule automated retry attempts
        
        Args:
            failure_id: Payment failure ID
        """
        try:
            failure = self.payment_failures.get(failure_id)
            if not failure:
                return
            
            # Schedule steps (skip day 0 as it's already done)
            for step in self.RETRY_SCHEDULE[1:]:
                execute_at = datetime.fromisoformat(failure["failed_at"]) + timedelta(days=step["day"])
                
                # TODO: Schedule task with rq or similar job queue
                # For now, just log
                logger.info(
                    f"Dunning step scheduled",
                    extra={
                        "failure_id": failure_id,
                        "user_id": failure["user_id"],
                        "day": step["day"],
                        "execute_at": execute_at.isoformat()
                    }
                )
        
        except Exception as e:
            logger.error(
                f"Failed to schedule dunning sequence",
                extra={"failure_id": failure_id, "error": str(e)}
            )
    
    async def _send_email(
        self,
        user_id: str,
        template: str,
        context: Dict[str, Any]
    ) -> None:
        """
        Send email via email service
        
        Args:
            user_id: User ID
            template: Email template name
            context: Template context
        """
        try:
            # TODO: Integrate with actual email service
            logger.info(
                f"Email sent",
                extra={
                    "user_id": user_id,
                    "template": template
                }
            )
        except Exception as e:
            logger.error(
                f"Failed to send email",
                extra={
                    "user_id": user_id,
                    "template": template,
                    "error": str(e)
                }
            )
    
    async def _cancel_subscription_for_nonpayment(
        self,
        user_id: str,
        subscription_id: str
    ) -> None:
        """
        Cancel subscription due to non-payment
        
        Args:
            user_id: User ID
            subscription_id: Subscription ID
        """
        try:
            # TODO: Cancel subscription in payment provider
            logger.info(
                f"Subscription cancelled for non-payment",
                extra={
                    "user_id": user_id,
                    "subscription_id": subscription_id
                }
            )
        except Exception as e:
            logger.error(
                f"Failed to cancel subscription",
                extra={
                    "user_id": user_id,
                    "subscription_id": subscription_id,
                    "error": str(e)
                }
            )
    
    def _get_dashboard_url(self) -> str:
        """Get dashboard URL from settings"""
        # TODO: Get from settings
        return "https://signalixai.com/dashboard"
    
    def get_failure_stats(self) -> Dict[str, Any]:
        """
        Get dunning statistics
        
        Returns:
            Dict with dunning stats
        """
        total_failures = len(self.payment_failures)
        recovered = sum(1 for f in self.payment_failures.values() if f["recovered"])
        pending = sum(1 for f in self.payment_failures.values() if f["status"] == "pending")
        failed = sum(1 for f in self.payment_failures.values() if f["status"] == "failed")
        
        recovery_rate = (recovered / total_failures * 100) if total_failures > 0 else 0
        
        return {
            "total_failures": total_failures,
            "recovered": recovered,
            "pending": pending,
            "failed": failed,
            "recovery_rate": round(recovery_rate, 2)
        }


# Global dunning service instance
dunning_service = DunningService()
