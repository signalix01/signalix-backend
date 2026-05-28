"""
Alert Delivery Engine
Orchestrates alert delivery across all channels with retry logic and offline queueing

Requirements: 13.2, 14.1, 14.2, 14.3, 14.4
"""
import logging
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime
import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, insert
import os

from shared.database.models import (
    AnomalyEvent,
    AlertRule,
    AlertDeliveryLog,
    AnomalySeverity
)
from services.alerts.channels import (
    InAppChannel,
    PushChannel,
    EmailChannel,
    SMSChannel,
    WhatsAppChannel,
    TelegramChannel,
    WebhookChannel,
)

logger = logging.getLogger(__name__)


class AlertDeliveryEngine:
    """
    Orchestrates alert delivery across all channels.
    
    Features:
    - CRITICAL alerts: concurrent delivery across all channels (asyncio.gather)
    - Non-critical alerts: sequential delivery to avoid overwhelming APIs
    - Retry logic: 3 retries with exponential backoff (30s, 2min, 10min)
    - Offline queue: stores alerts in Redis for offline users (max 100 per user)
    - Delivery logging: logs every attempt to alert_delivery_log table
    
    Requirements: 13.2, 14.1, 14.2, 14.3, 14.4
    """
    
    def __init__(self, db_session: AsyncSession, redis_client: redis.Redis):
        """
        Initialize delivery engine
        
        Args:
            db_session: SQLAlchemy async session
            redis_client: Async Redis client
        """
        self.db_session = db_session
        self.redis_client = redis_client
        
        # Initialize all delivery channels
        self.in_app_channel = InAppChannel(redis_client)
        self.push_channel = PushChannel()
        self.email_channel = EmailChannel()
        self.sms_channel = SMSChannel()
        self.whatsapp_channel = WhatsAppChannel()
        self.telegram_channel = TelegramChannel()
        self.webhook_channel = WebhookChannel()
        
        # Retry configuration (exponential backoff)
        self.retry_delays = [30, 120, 600]  # 30s, 2min, 10min
        self.max_retries = 3
    
    async def deliver(
        self,
        event: AnomalyEvent,
        matching_rules: List[AlertRule]
    ) -> Dict[str, Any]:
        """
        Deliver alert to all matching rules
        
        Args:
            event: AnomalyEvent instance
            matching_rules: List of AlertRule instances that matched this event
            
        Returns:
            dict with delivery summary
        """
        if not matching_rules:
            logger.info(f"No matching rules for event {event.id}, skipping delivery")
            return {
                "event_id": str(event.id),
                "rules_matched": 0,
                "deliveries_attempted": 0,
                "deliveries_successful": 0,
                "deliveries_failed": 0,
            }
        
        logger.info(f"Delivering event {event.id} to {len(matching_rules)} matching rules")
        
        # Determine if this is a critical alert
        is_critical = event.severity == AnomalySeverity.CRITICAL
        
        # Track delivery results
        total_attempted = 0
        total_successful = 0
        total_failed = 0
        
        # Deliver to each matching rule
        for rule in matching_rules:
            # Get user delivery preferences from rule
            user_id = str(rule.user_id)
            channels = rule.channels
            
            # Format alert for each channel
            delivery_tasks = []
            
            for channel in channels:
                delivery_tasks.append(
                    self._deliver_to_channel(
                        channel=channel,
                        user_id=user_id,
                        event=event,
                        rule=rule,
                        is_critical=is_critical
                    )
                )
            
            # Execute deliveries based on severity
            if is_critical:
                # CRITICAL: deliver concurrently to all channels
                logger.info(f"CRITICAL alert: delivering concurrently to {len(channels)} channels")
                results = await asyncio.gather(*delivery_tasks, return_exceptions=True)
            else:
                # Non-critical: deliver sequentially to avoid overwhelming APIs
                logger.info(f"Non-critical alert: delivering sequentially to {len(channels)} channels")
                results = []
                for task in delivery_tasks:
                    try:
                        result = await task
                        results.append(result)
                    except Exception as e:
                        logger.error(f"Delivery task failed: {str(e)}", exc_info=True)
                        results.append(e)
            
            # Process results
            for result in results:
                total_attempted += 1
                
                if isinstance(result, Exception):
                    logger.error(f"Delivery failed with exception: {str(result)}")
                    total_failed += 1
                elif isinstance(result, dict):
                    if result.get("status") == "sent":
                        total_successful += 1
                    elif result.get("status") == "failed":
                        total_failed += 1
                    # "skipped" doesn't count as success or failure
        
        summary = {
            "event_id": str(event.id),
            "rules_matched": len(matching_rules),
            "deliveries_attempted": total_attempted,
            "deliveries_successful": total_successful,
            "deliveries_failed": total_failed,
            "is_critical": is_critical,
            "timestamp": datetime.utcnow().isoformat(),
        }
        
        logger.info(f"Delivery complete: {summary}")
        return summary
    
    async def _deliver_to_channel(
        self,
        channel: str,
        user_id: str,
        event: AnomalyEvent,
        rule: AlertRule,
        is_critical: bool
    ) -> Dict[str, Any]:
        """
        Deliver alert to a specific channel with retry logic
        
        Args:
            channel: Channel name (in_app, push, email, etc.)
            user_id: User ID
            event: AnomalyEvent instance
            rule: AlertRule instance
            is_critical: Whether this is a critical alert
            
        Returns:
            dict with delivery result
        """
        attempt = 1
        last_error = None
        
        # Try delivery with retries
        while attempt <= self.max_retries:
            try:
                # Log delivery attempt
                await self._log_delivery_attempt(
                    event=event,
                    rule=rule,
                    channel=channel,
                    attempt=attempt,
                    status="pending"
                )
                
                # Attempt delivery
                result = await self._send_to_channel(
                    channel=channel,
                    user_id=user_id,
                    event=event,
                    rule=rule
                )
                
                # Check result
                if result.get("status") == "sent":
                    # Success - log and return
                    await self._log_delivery_attempt(
                        event=event,
                        rule=rule,
                        channel=channel,
                        attempt=attempt,
                        status="sent",
                        delivered_at=datetime.utcnow(),
                        detection_to_delivery_ms=self._calculate_latency(event)
                    )
                    
                    logger.info(f"Successfully delivered to {channel} for user {user_id} (attempt {attempt})")
                    return result
                
                elif result.get("status") == "skipped":
                    # Skipped (e.g., no email configured) - log and return
                    await self._log_delivery_attempt(
                        event=event,
                        rule=rule,
                        channel=channel,
                        attempt=attempt,
                        status="skipped",
                        error_message=result.get("reason")
                    )
                    
                    logger.info(f"Skipped delivery to {channel}: {result.get('reason')}")
                    return result
                
                elif result.get("status") == "failed":
                    # Failed - will retry
                    last_error = result.get("error", "Unknown error")
                    
                    await self._log_delivery_attempt(
                        event=event,
                        rule=rule,
                        channel=channel,
                        attempt=attempt,
                        status="failed",
                        error_message=last_error
                    )
                    
                    logger.warning(f"Delivery to {channel} failed (attempt {attempt}/{self.max_retries}): {last_error}")
                    
                    # If not last attempt, wait before retry (exponential backoff)
                    if attempt < self.max_retries:
                        delay = self.retry_delays[attempt - 1]
                        logger.info(f"Retrying in {delay} seconds...")
                        await asyncio.sleep(delay)
                    
                    attempt += 1
                    continue
                
                else:
                    # Unknown status
                    logger.error(f"Unknown delivery status: {result.get('status')}")
                    return result
            
            except Exception as e:
                last_error = str(e)
                logger.error(f"Exception during delivery to {channel} (attempt {attempt}): {last_error}", exc_info=True)
                
                await self._log_delivery_attempt(
                    event=event,
                    rule=rule,
                    channel=channel,
                    attempt=attempt,
                    status="failed",
                    error_message=last_error
                )
                
                # If not last attempt, wait before retry
                if attempt < self.max_retries:
                    delay = self.retry_delays[attempt - 1]
                    await asyncio.sleep(delay)
                
                attempt += 1
        
        # All retries exhausted
        logger.error(f"Failed to deliver to {channel} after {self.max_retries} attempts. Last error: {last_error}")
        
        return {
            "status": "failed",
            "channel": channel,
            "error": f"Failed after {self.max_retries} retries: {last_error}",
            "timestamp": datetime.utcnow().isoformat(),
        }
    
    async def _send_to_channel(
        self,
        channel: str,
        user_id: str,
        event: AnomalyEvent,
        rule: AlertRule
    ) -> Dict[str, Any]:
        """
        Send alert to specific channel
        
        Args:
            channel: Channel name
            user_id: User ID
            event: AnomalyEvent instance
            rule: AlertRule instance
            
        Returns:
            dict with delivery result
        """
        rule_id = str(rule.id)
        
        try:
            if channel == "in_app":
                return await self.in_app_channel.send(user_id, event, rule_id)
            
            elif channel == "push":
                # Get device tokens from user preferences (placeholder - implement user preferences service)
                device_tokens = await self._get_user_device_tokens(user_id)
                return await self.push_channel.send(user_id, event, rule_id, device_tokens)
            
            elif channel == "email":
                # Get email from user preferences
                email_address = await self._get_user_email(user_id)
                return await self.email_channel.send(user_id, event, rule_id, email_address)
            
            elif channel == "sms":
                # Get phone number from user preferences
                phone_number = await self._get_user_phone(user_id)
                return await self.sms_channel.send(user_id, event, rule_id, phone_number)
            
            elif channel == "whatsapp":
                # Get phone number from user preferences
                phone_number = await self._get_user_phone(user_id)
                return await self.whatsapp_channel.send(user_id, event, rule_id, phone_number)
            
            elif channel == "telegram":
                # Get Telegram chat ID from user preferences
                chat_id = await self._get_user_telegram_chat_id(user_id)
                return await self.telegram_channel.send(user_id, event, rule_id, chat_id)
            
            elif channel == "webhook":
                # Get webhook config from rule
                webhook_url = rule.webhook_url
                webhook_secret = rule.webhook_secret
                return await self.webhook_channel.send(user_id, event, rule_id, webhook_url, webhook_secret)
            
            else:
                logger.error(f"Unknown channel: {channel}")
                return {
                    "status": "failed",
                    "channel": channel,
                    "error": f"Unknown channel: {channel}",
                    "timestamp": datetime.utcnow().isoformat(),
                }
        
        except Exception as e:
            logger.error(f"Error sending to {channel}: {str(e)}", exc_info=True)
            return {
                "status": "failed",
                "channel": channel,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }
    
    async def _log_delivery_attempt(
        self,
        event: AnomalyEvent,
        rule: AlertRule,
        channel: str,
        attempt: int,
        status: str,
        delivered_at: Optional[datetime] = None,
        error_message: Optional[str] = None,
        detection_to_delivery_ms: Optional[int] = None
    ) -> None:
        """
        Log delivery attempt to database
        
        Args:
            event: AnomalyEvent instance
            rule: AlertRule instance
            channel: Channel name
            attempt: Attempt number
            status: Delivery status (pending, sent, failed, skipped)
            delivered_at: Delivery timestamp (if successful)
            error_message: Error message (if failed)
            detection_to_delivery_ms: Latency in milliseconds
        """
        try:
            log_entry = AlertDeliveryLog(
                anomaly_event_id=event.id,
                alert_rule_id=rule.id,
                user_id=rule.user_id,
                channel=channel,
                status=status,
                attempt_number=attempt,
                delivered_at=delivered_at,
                error_message=error_message,
                detection_to_delivery_ms=detection_to_delivery_ms,
                created_at=datetime.utcnow()
            )
            
            self.db_session.add(log_entry)
            await self.db_session.commit()
            
        except Exception as e:
            logger.error(f"Failed to log delivery attempt: {str(e)}", exc_info=True)
            # Don't raise - logging failure shouldn't stop delivery
    
    def _calculate_latency(self, event: AnomalyEvent) -> int:
        """
        Calculate latency from detection to delivery in milliseconds
        
        Args:
            event: AnomalyEvent instance
            
        Returns:
            Latency in milliseconds
        """
        if event.detected_at:
            delta = datetime.utcnow() - event.detected_at
            return int(delta.total_seconds() * 1000)
        return 0
    
    # ============================================================================
    # User Preferences Helpers (Placeholder - implement user preferences service)
    # ============================================================================
    
    async def _get_user_device_tokens(self, user_id: str) -> List[str]:
        """
        Get user's FCM device tokens
        
        TODO: Implement user preferences service
        For now, returns empty list (push notifications will be skipped)
        """
        # Placeholder - implement user preferences lookup
        return []
    
    async def _get_user_email(self, user_id: str) -> Optional[str]:
        """
        Get user's email address
        
        TODO: Implement user preferences service
        For now, returns None (email will be skipped)
        """
        # Placeholder - implement user preferences lookup
        return None
    
    async def _get_user_phone(self, user_id: str) -> Optional[str]:
        """
        Get user's phone number
        
        TODO: Implement user preferences service
        For now, returns None (SMS/WhatsApp will be skipped)
        """
        # Placeholder - implement user preferences lookup
        return None
    
    async def _get_user_telegram_chat_id(self, user_id: str) -> Optional[str]:
        """
        Get user's Telegram chat ID
        
        TODO: Implement user preferences service
        For now, returns None (Telegram will be skipped)
        """
        # Placeholder - implement user preferences lookup
        return None
