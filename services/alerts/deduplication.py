"""
Anomaly Event Deduplication Service

This module provides deduplication logic for anomaly events to prevent alert fatigue.
Events of the same type on the same instrument are suppressed within a 15-minute window,
UNLESS severity increases (e.g., medium → high is not suppressed).

Requirements: 11.8
Design: Service 4 - Anomaly & Alert Engine
"""
import logging
from typing import Optional
from datetime import datetime, timedelta
import redis.asyncio as redis
from shared.config.settings import settings
from shared.database.models import AnomalyEvent, AnomalySeverity

logger = logging.getLogger(__name__)


class DedupService:
    """
    Deduplication service for anomaly events.
    
    Uses Redis to track recent events and suppress duplicates within a 15-minute window.
    Allows severity escalation (medium → high is not suppressed).
    
    Key pattern: dedup:{instrument}:{anomaly_type}
    TTL: 15 minutes (900 seconds)
    
    Requirements: 11.8
    """
    
    # Deduplication window in seconds (15 minutes)
    DEDUP_WINDOW_SECONDS = 900
    
    # Severity ordering for escalation detection
    SEVERITY_ORDER = {
        AnomalySeverity.LOW: 1,
        AnomalySeverity.MEDIUM: 2,
        AnomalySeverity.HIGH: 3,
        AnomalySeverity.CRITICAL: 4
    }
    
    def __init__(self):
        """Initialize deduplication service"""
        self.redis_url = settings.REDIS_URL
        self._client: Optional[redis.Redis] = None
    
    async def connect(self):
        """Establish Redis connection"""
        if self._client is None:
            try:
                self._client = redis.from_url(
                    self.redis_url,
                    decode_responses=True,
                    max_connections=50,
                    socket_connect_timeout=5,
                    socket_timeout=5
                )
                # Test connection
                await self._client.ping()
                logger.info("DedupService Redis client connected successfully")
            except Exception as e:
                logger.error(f"Failed to connect to Redis: {e}")
                raise
    
    async def disconnect(self):
        """Close Redis connection"""
        if self._client:
            await self._client.close()
            self._client = None
            logger.info("DedupService Redis client disconnected")
    
    def _get_dedup_key(self, instrument: str, anomaly_type: str) -> str:
        """
        Generate Redis key for deduplication tracking.
        
        Args:
            instrument: Instrument symbol (e.g., "RELIANCE", "BTCUSDT")
            anomaly_type: Type of anomaly (e.g., "price_spike", "volume_surge")
            
        Returns:
            Redis key string
        """
        return f"dedup:{instrument}:{anomaly_type}"
    
    def _is_severity_increase(
        self,
        previous_severity: str,
        current_severity: AnomalySeverity
    ) -> bool:
        """
        Check if current severity is higher than previous severity.
        
        Args:
            previous_severity: Previous severity level (string)
            current_severity: Current severity level (enum)
            
        Returns:
            True if severity increased, False otherwise
        """
        try:
            # Convert string to enum for comparison
            prev_enum = AnomalySeverity(previous_severity)
            prev_level = self.SEVERITY_ORDER.get(prev_enum, 0)
            curr_level = self.SEVERITY_ORDER.get(current_severity, 0)
            
            return curr_level > prev_level
        except (ValueError, KeyError) as e:
            logger.warning(f"Invalid severity comparison: {e}")
            # If we can't determine, don't suppress (fail open)
            return True
    
    async def should_suppress(self, event: AnomalyEvent) -> bool:
        """
        Determine if an anomaly event should be suppressed due to deduplication.
        
        Logic:
        1. Check Redis for recent event of same type + instrument
        2. If found within 15-minute window:
           - If severity increased: DO NOT suppress (allow escalation)
           - If severity same or decreased: SUPPRESS
        3. If not found: DO NOT suppress (new event)
        
        Args:
            event: AnomalyEvent to check
            
        Returns:
            True if event should be suppressed, False if it should be emitted
            
        Requirements: 11.8
        """
        if not self._client:
            await self.connect()
        
        try:
            # Generate dedup key
            key = self._get_dedup_key(event.instrument, event.anomaly_type.value)
            
            # Check for existing event
            existing_data = await self._client.hgetall(key)
            
            if not existing_data:
                # No recent event found - do not suppress
                logger.info(
                    f"No recent event for {event.instrument}:{event.anomaly_type.value} - "
                    f"allowing event"
                )
                
                # Store this event for future deduplication
                await self._store_event(event)
                return False
            
            # Recent event exists - check severity
            previous_severity = existing_data.get('severity')
            
            if not previous_severity:
                # Malformed data - don't suppress (fail open)
                logger.warning(f"Malformed dedup data for key {key} - allowing event")
                await self._store_event(event)
                return False
            
            # Check if severity increased
            if self._is_severity_increase(previous_severity, event.severity):
                # Severity escalation - do not suppress
                logger.info(
                    f"Severity escalation detected for {event.instrument}:"
                    f"{event.anomaly_type.value} "
                    f"({previous_severity} → {event.severity.value}) - allowing event"
                )
                
                # Update stored event with new severity
                await self._store_event(event)
                return False
            
            # Same or lower severity - suppress
            logger.info(
                f"Suppressing duplicate event for {event.instrument}:"
                f"{event.anomaly_type.value} "
                f"(severity: {event.severity.value}, previous: {previous_severity})"
            )
            return True
            
        except Exception as e:
            logger.error(f"Error in deduplication check: {e}")
            # On error, don't suppress (fail open to avoid missing critical alerts)
            return False
    
    async def _store_event(self, event: AnomalyEvent):
        """
        Store event data in Redis for deduplication tracking.
        
        Args:
            event: AnomalyEvent to store
        """
        if not self._client:
            await self.connect()
        
        try:
            key = self._get_dedup_key(event.instrument, event.anomaly_type.value)
            
            # Store event metadata
            data = {
                'severity': event.severity.value,
                'detected_at': event.detected_at.isoformat() if event.detected_at else datetime.utcnow().isoformat(),
                'event_id': str(event.id) if event.id else 'unknown'
            }
            
            # Store with TTL
            await self._client.hset(key, mapping=data)
            await self._client.expire(key, self.DEDUP_WINDOW_SECONDS)
            
            logger.debug(
                f"Stored dedup data for {event.instrument}:{event.anomaly_type.value} "
                f"with {self.DEDUP_WINDOW_SECONDS}s TTL"
            )
            
        except Exception as e:
            logger.error(f"Failed to store dedup data: {e}")
            # Non-critical error - continue without storing
    
    async def clear_dedup_state(self, instrument: str, anomaly_type: str):
        """
        Clear deduplication state for a specific instrument and anomaly type.
        Useful for testing or manual intervention.
        
        Args:
            instrument: Instrument symbol
            anomaly_type: Type of anomaly
        """
        if not self._client:
            await self.connect()
        
        try:
            key = self._get_dedup_key(instrument, anomaly_type)
            await self._client.delete(key)
            logger.info(f"Cleared dedup state for {key}")
        except Exception as e:
            logger.error(f"Failed to clear dedup state: {e}")
    
    async def get_dedup_state(self, instrument: str, anomaly_type: str) -> Optional[dict]:
        """
        Get current deduplication state for debugging/monitoring.
        
        Args:
            instrument: Instrument symbol
            anomaly_type: Type of anomaly
            
        Returns:
            Dict with dedup state or None if not found
        """
        if not self._client:
            await self.connect()
        
        try:
            key = self._get_dedup_key(instrument, anomaly_type)
            data = await self._client.hgetall(key)
            
            if data:
                # Add TTL info
                ttl = await self._client.ttl(key)
                data['ttl_seconds'] = ttl
                return data
            return None
            
        except Exception as e:
            logger.error(f"Failed to get dedup state: {e}")
            return None


# Global dedup service instance
_dedup_service: Optional[DedupService] = None


async def get_dedup_service() -> DedupService:
    """
    Get or create the global deduplication service instance.
    
    Returns:
        DedupService instance
    """
    global _dedup_service
    
    if _dedup_service is None:
        _dedup_service = DedupService()
        await _dedup_service.connect()
    
    return _dedup_service


async def close_dedup_service():
    """Close the global deduplication service connection"""
    global _dedup_service
    
    if _dedup_service:
        await _dedup_service.disconnect()
        _dedup_service = None
