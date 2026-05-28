"""
Alert Matching Engine

Matches anomaly events against user-defined alert rules to determine which alerts
should be delivered to which users.

Key features:
- Matches events against rule filters (instruments, asset_class, anomaly_type, severity)
- Implements quiet hours check using IST timezone
- Implements rate limit check using Redis counter
- CRITICAL severity events bypass quiet hours AND rate limits

Requirements: 13.2, 13.3, 13.4, 13.5
Task: 39
"""

import logging
from typing import List, Optional
from datetime import datetime, time
import pytz
import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select

from shared.config.settings import settings
from shared.database.models import AlertRule, AnomalyEvent, AnomalySeverity

logger = logging.getLogger(__name__)


class AlertMatcher:
    """
    Matches anomaly events against alert rules to determine delivery.
    
    Implements:
    - Rule matching based on instruments, asset_class, anomaly_type, severity
    - Quiet hours check (IST timezone)
    - Rate limit check (Redis counter)
    - CRITICAL severity bypass for quiet hours and rate limits
    
    Requirements: 13.2, 13.3, 13.4, 13.5
    """
    
    def __init__(self):
        """Initialize the alert matcher with database and Redis connections"""
        self.redis_url = settings.REDIS_URL
        self._redis_client: Optional[redis.Redis] = None
        
        self.database_url = settings.DATABASE_URL
        self._db_engine = None
        self._async_session_maker = None
        
        # IST timezone for quiet hours
        self.ist_tz = pytz.timezone('Asia/Kolkata')
        
        logger.info("AlertMatcher initialized")
    
    async def connect(self):
        """Establish connections to Redis and database"""
        # Connect to Redis
        if self._redis_client is None:
            try:
                self._redis_client = redis.from_url(
                    self.redis_url,
                    decode_responses=True,
                    max_connections=50,
                    socket_connect_timeout=5,
                    socket_timeout=5
                )
                await self._redis_client.ping()
                logger.info("AlertMatcher Redis client connected")
            except Exception as e:
                logger.error(f"Failed to connect to Redis: {e}")
                raise
        
        # Connect to database
        if self._db_engine is None:
            try:
                self._db_engine = create_async_engine(
                    self.database_url,
                    echo=False,
                    pool_pre_ping=True
                )
                self._async_session_maker = async_sessionmaker(
                    self._db_engine,
                    class_=AsyncSession,
                    expire_on_commit=False
                )
                logger.info("AlertMatcher database engine created")
            except Exception as e:
                logger.error(f"Failed to create database engine: {e}")
                raise
    
    async def disconnect(self):
        """Close all connections"""
        if self._redis_client:
            await self._redis_client.close()
            self._redis_client = None
            logger.info("AlertMatcher Redis client disconnected")
        
        if self._db_engine:
            await self._db_engine.dispose()
            self._db_engine = None
            self._async_session_maker = None
            logger.info("AlertMatcher database engine disposed")
    
    def _is_in_quiet_hours(self, rule: AlertRule, current_time: Optional[datetime] = None) -> bool:
        """
        Check if current time is within the rule's quiet hours (IST timezone).
        
        Args:
            rule: AlertRule to check
            current_time: Optional datetime to check (defaults to now in IST)
        
        Returns:
            True if in quiet hours, False otherwise
        
        Requirements: 13.3
        """
        # If no quiet hours configured, not in quiet hours
        if not rule.quiet_hours_start or not rule.quiet_hours_end:
            return False
        
        # Get current time in IST
        if current_time is None:
            current_time = datetime.now(self.ist_tz)
        elif current_time.tzinfo is None:
            # If naive datetime, assume UTC and convert to IST
            current_time = pytz.utc.localize(current_time).astimezone(self.ist_tz)
        else:
            # Convert to IST
            current_time = current_time.astimezone(self.ist_tz)
        
        current_time_only = current_time.time()
        
        # Parse quiet hours
        try:
            start_hour, start_minute = map(int, rule.quiet_hours_start.split(':'))
            end_hour, end_minute = map(int, rule.quiet_hours_end.split(':'))
            
            quiet_start = time(start_hour, start_minute)
            quiet_end = time(end_hour, end_minute)
        except (ValueError, AttributeError) as e:
            logger.error(f"Invalid quiet hours format for rule {rule.id}: {e}")
            return False
        
        # Check if current time is in quiet hours
        # Handle case where quiet hours span midnight (e.g., 22:00 to 08:00)
        if quiet_start <= quiet_end:
            # Normal case: quiet hours within same day (e.g., 08:00 to 18:00)
            in_quiet_hours = quiet_start <= current_time_only <= quiet_end
        else:
            # Spans midnight: quiet hours cross day boundary (e.g., 22:00 to 08:00)
            in_quiet_hours = current_time_only >= quiet_start or current_time_only <= quiet_end
        
        if in_quiet_hours:
            logger.debug(
                f"Rule {rule.id} is in quiet hours: {rule.quiet_hours_start} - {rule.quiet_hours_end} "
                f"(current time: {current_time_only.strftime('%H:%M')} IST)"
            )
        
        return in_quiet_hours
    
    async def _check_rate_limit(self, user_id: str, rule: AlertRule) -> bool:
        """
        Check if the user has exceeded their rate limit for this hour.
        
        Uses Redis counter with key pattern: `alert_rate:{user_id}:{hour}`
        Counter expires after 1 hour.
        
        Args:
            user_id: User ID to check
            rule: AlertRule with max_alerts_per_hour setting
        
        Returns:
            True if rate limit exceeded, False otherwise
        
        Requirements: 13.5
        """
        if not self._redis_client:
            await self.connect()
        
        try:
            # Get current hour in UTC for consistent rate limiting
            now = datetime.utcnow()
            hour_key = now.strftime('%Y-%m-%d-%H')
            
            # Redis key for rate limiting
            rate_key = f"alert_rate:{user_id}:{hour_key}"
            
            # Get current count
            current_count = await self._redis_client.get(rate_key)
            current_count = int(current_count) if current_count else 0
            
            # Check if limit exceeded
            if current_count >= rule.max_alerts_per_hour:
                logger.warning(
                    f"Rate limit exceeded for user {user_id}: "
                    f"{current_count}/{rule.max_alerts_per_hour} alerts this hour"
                )
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking rate limit for user {user_id}: {e}")
            # On error, don't block alerts (fail open)
            return False
    
    async def _increment_rate_counter(self, user_id: str):
        """
        Increment the rate limit counter for the user.
        
        Args:
            user_id: User ID to increment counter for
        """
        if not self._redis_client:
            await self.connect()
        
        try:
            # Get current hour in UTC
            now = datetime.utcnow()
            hour_key = now.strftime('%Y-%m-%d-%H')
            
            # Redis key for rate limiting
            rate_key = f"alert_rate:{user_id}:{hour_key}"
            
            # Increment counter
            await self._redis_client.incr(rate_key)
            
            # Set expiry to 1 hour (3600 seconds) if this is the first increment
            await self._redis_client.expire(rate_key, 3600)
            
            logger.debug(f"Incremented rate counter for user {user_id}: {rate_key}")
            
        except Exception as e:
            logger.error(f"Error incrementing rate counter for user {user_id}: {e}")
    
    def _matches_instrument_filter(self, event: AnomalyEvent, rule: AlertRule) -> bool:
        """
        Check if event instrument matches rule's instrument filter.
        
        Args:
            event: AnomalyEvent to check
            rule: AlertRule with instruments filter
        
        Returns:
            True if matches, False otherwise
        """
        # "ALL" matches all instruments
        if "ALL" in rule.instruments:
            return True
        
        # Check if event instrument is in rule's instrument list
        return event.instrument in rule.instruments
    
    def _matches_asset_class_filter(self, event: AnomalyEvent, rule: AlertRule) -> bool:
        """
        Check if event asset class matches rule's asset class filter.
        
        Args:
            event: AnomalyEvent to check
            rule: AlertRule with asset_classes filter
        
        Returns:
            True if matches, False otherwise
        """
        return event.asset_class in rule.asset_classes
    
    def _matches_anomaly_type_filter(self, event: AnomalyEvent, rule: AlertRule) -> bool:
        """
        Check if event anomaly type matches rule's anomaly type filter.
        
        Args:
            event: AnomalyEvent to check
            rule: AlertRule with anomaly_types filter
        
        Returns:
            True if matches, False otherwise
        """
        # Convert enum to string for comparison
        event_type = event.anomaly_type.value if hasattr(event.anomaly_type, 'value') else str(event.anomaly_type)
        return event_type in rule.anomaly_types
    
    def _matches_severity_filter(self, event: AnomalyEvent, rule: AlertRule) -> bool:
        """
        Check if event severity meets rule's minimum severity threshold.
        
        Severity hierarchy: LOW < MEDIUM < HIGH < CRITICAL
        
        Args:
            event: AnomalyEvent to check
            rule: AlertRule with min_severity threshold
        
        Returns:
            True if event severity >= rule min_severity, False otherwise
        """
        # Define severity order
        severity_order = {
            AnomalySeverity.LOW: 1,
            AnomalySeverity.MEDIUM: 2,
            AnomalySeverity.HIGH: 3,
            AnomalySeverity.CRITICAL: 4
        }
        
        # Get severity values
        event_severity = event.severity if isinstance(event.severity, AnomalySeverity) else AnomalySeverity(event.severity)
        rule_min_severity = rule.min_severity if isinstance(rule.min_severity, AnomalySeverity) else AnomalySeverity(rule.min_severity)
        
        event_level = severity_order.get(event_severity, 0)
        rule_level = severity_order.get(rule_min_severity, 0)
        
        return event_level >= rule_level
    
    async def find_matching_rules(
        self,
        event: AnomalyEvent,
        current_time: Optional[datetime] = None
    ) -> List[AlertRule]:
        """
        Find all alert rules that match the given anomaly event.
        
        Matching criteria:
        1. Rule must be enabled
        2. Event instrument must match rule's instruments filter (or "ALL")
        3. Event asset_class must match rule's asset_classes filter
        4. Event anomaly_type must be in rule's anomaly_types filter
        5. Event severity must be >= rule's min_severity
        6. If not CRITICAL: must not be in quiet hours
        7. If not CRITICAL: must not exceed rate limit
        
        CRITICAL severity events bypass quiet hours AND rate limits.
        
        Args:
            event: AnomalyEvent to match against rules
            current_time: Optional datetime for testing (defaults to now)
        
        Returns:
            List of matching AlertRule objects
        
        Requirements: 13.2, 13.3, 13.4, 13.5
        """
        if not self._async_session_maker:
            await self.connect()
        
        logger.info(
            f"Finding matching rules for event: {event.instrument}:{event.anomaly_type.value} "
            f"(severity: {event.severity.value})"
        )
        
        # Check if event is CRITICAL severity
        is_critical = event.severity == AnomalySeverity.CRITICAL
        
        try:
            async with self._async_session_maker() as session:
                # Query all enabled rules
                query = select(AlertRule).where(AlertRule.enabled == True)
                result = await session.execute(query)
                all_rules = result.scalars().all()
                
                logger.debug(f"Found {len(all_rules)} enabled rules to check")
                
                matching_rules = []
                
                for rule in all_rules:
                    # Check basic filters
                    if not self._matches_instrument_filter(event, rule):
                        logger.debug(f"Rule {rule.id} ({rule.name}): instrument filter failed")
                        continue
                    
                    if not self._matches_asset_class_filter(event, rule):
                        logger.debug(f"Rule {rule.id} ({rule.name}): asset class filter failed")
                        continue
                    
                    if not self._matches_anomaly_type_filter(event, rule):
                        logger.debug(f"Rule {rule.id} ({rule.name}): anomaly type filter failed")
                        continue
                    
                    if not self._matches_severity_filter(event, rule):
                        logger.debug(f"Rule {rule.id} ({rule.name}): severity filter failed")
                        continue
                    
                    # CRITICAL events bypass quiet hours and rate limits
                    if is_critical:
                        logger.info(
                            f"Rule {rule.id} ({rule.name}): matched (CRITICAL event - bypassing quiet hours and rate limits)"
                        )
                        matching_rules.append(rule)
                        continue
                    
                    # Check quiet hours for non-CRITICAL events
                    if self._is_in_quiet_hours(rule, current_time):
                        logger.info(
                            f"Rule {rule.id} ({rule.name}): blocked by quiet hours "
                            f"({rule.quiet_hours_start} - {rule.quiet_hours_end} IST)"
                        )
                        continue
                    
                    # Check rate limit for non-CRITICAL events
                    rate_limit_exceeded = await self._check_rate_limit(str(rule.user_id), rule)
                    if rate_limit_exceeded:
                        logger.info(
                            f"Rule {rule.id} ({rule.name}): blocked by rate limit "
                            f"(max {rule.max_alerts_per_hour}/hour)"
                        )
                        continue
                    
                    # Rule matched all criteria
                    logger.info(f"Rule {rule.id} ({rule.name}): matched")
                    matching_rules.append(rule)
                    
                    # Increment rate counter for this user
                    await self._increment_rate_counter(str(rule.user_id))
                
                logger.info(
                    f"Found {len(matching_rules)} matching rules for event "
                    f"{event.instrument}:{event.anomaly_type.value}"
                )
                
                return matching_rules
                
        except Exception as e:
            logger.error(f"Error finding matching rules: {e}")
            return []


# Global matcher instance
_matcher: Optional[AlertMatcher] = None


async def get_matcher() -> AlertMatcher:
    """
    Get or create the global alert matcher instance.
    
    Returns:
        AlertMatcher instance
    """
    global _matcher
    
    if _matcher is None:
        _matcher = AlertMatcher()
        await _matcher.connect()
    
    return _matcher


async def close_matcher():
    """Close the global matcher connections"""
    global _matcher
    
    if _matcher:
        await _matcher.disconnect()
        _matcher = None
