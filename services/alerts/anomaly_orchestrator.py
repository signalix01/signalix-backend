"""
Anomaly Detection Orchestrator

Coordinates all anomaly detectors and manages the complete detection pipeline:
1. Runs all 4 detectors (ZScore price, ZScore volume, CUSUM, IsolationForest) in parallel
2. Runs flash detector on tick buffer
3. Deduplicates events before emitting
4. Publishes to Redis pub/sub channel `anomalies:{instrument}`
5. Stores events to TimescaleDB

Requirements: 11.5, 11.7
Task: 32
"""

import asyncio
import logging
from typing import List, Optional
from datetime import datetime
import json
import uuid
import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select, insert
import numpy as np
import pandas as pd

from shared.config.settings import settings
from shared.database.models import AnomalyEvent, Base
from services.alerts.detectors.zscore import ZScoreDetector
from services.alerts.detectors.cusum import CUSUMDetector
from services.alerts.detectors.isolation_forest import IsolationForestDetector
from services.alerts.detectors.flash_detector import FlashDetector, TickData
from services.alerts.deduplication import get_dedup_service

logger = logging.getLogger(__name__)


class OHLCVBar:
    """
    Represents a single OHLCV bar (candlestick) data point.
    
    Attributes:
        timestamp: ISO timestamp string or datetime object
        open: Opening price
        high: Highest price
        low: Lowest price
        close: Closing price
        volume: Trading volume
        instrument: Instrument symbol
        asset_class: Asset class (equity, fo, crypto, etc.)
        exchange: Exchange name (NSE, BSE, etc.)
    """
    def __init__(
        self,
        timestamp: datetime,
        open: float,
        high: float,
        low: float,
        close: float,
        volume: float,
        instrument: str,
        asset_class: str = "equity",
        exchange: Optional[str] = None
    ):
        self.timestamp = timestamp
        self.open = open
        self.high = high
        self.low = low
        self.close = close
        self.volume = volume
        self.instrument = instrument
        self.asset_class = asset_class
        self.exchange = exchange
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization"""
        return {
            "timestamp": self.timestamp.isoformat() if isinstance(self.timestamp, datetime) else self.timestamp,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "instrument": self.instrument,
            "asset_class": self.asset_class,
            "exchange": self.exchange
        }
    
    def to_series(self) -> pd.Series:
        """Convert to pandas Series for detector compatibility"""
        return pd.Series({
            "timestamp": self.timestamp,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume
        })


class AnomalyOrchestrator:
    """
    Main orchestrator for anomaly detection pipeline.
    
    Coordinates all detectors, deduplication, and event publishing.
    Called on every new OHLCV bar for real-time anomaly detection.
    
    Requirements: 11.5, 11.7
    """
    
    def __init__(self):
        """Initialize the orchestrator with all detectors and connections"""
        # Initialize detectors
        self.zscore_detector = ZScoreDetector(
            window_size=20,
            alert_threshold=3.0,
            critical_threshold=4.0
        )
        self.cusum_detector = CUSUMDetector(h=5.0, k=0.5)
        self.isolation_forest_detector = IsolationForestDetector(
            contamination=0.02,
            n_estimators=100
        )
        self.flash_detector = FlashDetector(
            threshold_pct=5.0,
            window_minutes=5
        )
        
        # Redis connection for pub/sub and tick storage
        self.redis_url = settings.REDIS_URL
        self._redis_client: Optional[redis.Redis] = None
        
        # Database connection for event storage
        self.database_url = settings.DATABASE_URL
        self._db_engine = None
        self._async_session_maker = None
        
        # Deduplication service
        self._dedup_service = None
        
        logger.info("AnomalyOrchestrator initialized")
    
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
                logger.info("AnomalyOrchestrator Redis client connected")
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
                logger.info("AnomalyOrchestrator database engine created")
            except Exception as e:
                logger.error(f"Failed to create database engine: {e}")
                raise
        
        # Get deduplication service
        if self._dedup_service is None:
            from services.alerts.deduplication import get_dedup_service
            self._dedup_service = await get_dedup_service()
            logger.info("AnomalyOrchestrator deduplication service connected")
    
    async def disconnect(self):
        """Close all connections"""
        if self._redis_client:
            await self._redis_client.close()
            self._redis_client = None
            logger.info("AnomalyOrchestrator Redis client disconnected")
        
        if self._db_engine:
            await self._db_engine.dispose()
            self._db_engine = None
            self._async_session_maker = None
            logger.info("AnomalyOrchestrator database engine disposed")
    
    async def _get_historical_data(
        self,
        instrument: str,
        window_size: int = 90
    ) -> Optional[pd.DataFrame]:
        """
        Fetch historical OHLCV data for the instrument.
        
        This is used for detectors that need historical context
        (e.g., IsolationForest training).
        
        Args:
            instrument: Instrument symbol
            window_size: Number of bars to fetch (default: 90)
        
        Returns:
            DataFrame with OHLCV data or None if not available
        """
        # TODO: Implement actual data fetching from TimescaleDB
        # For now, return None - detectors will handle gracefully
        logger.debug(f"Historical data fetch not yet implemented for {instrument}")
        return None
    
    async def _get_tick_buffer(self, instrument: str) -> List[TickData]:
        """
        Fetch recent tick data from Redis for flash detection.
        
        Tick data is stored in Redis sorted sets with pattern: `ticks:{instrument}`
        Score: Unix timestamp in milliseconds
        Value: JSON-encoded tick data
        
        Args:
            instrument: Instrument symbol
        
        Returns:
            List of TickData objects from the last 10 minutes
        """
        if not self._redis_client:
            await self.connect()
        
        try:
            key = f"ticks:{instrument}"
            
            # Get all ticks from the sorted set (last 10 minutes)
            # Redis ZRANGEBYSCORE returns all items within score range
            now_ms = int(datetime.utcnow().timestamp() * 1000)
            ten_min_ago_ms = now_ms - (10 * 60 * 1000)
            
            tick_data = await self._redis_client.zrangebyscore(
                key,
                min=ten_min_ago_ms,
                max=now_ms,
                withscores=True
            )
            
            # Parse tick data
            ticks = []
            for tick_json, timestamp_ms in tick_data:
                try:
                    tick_dict = json.loads(tick_json)
                    tick = TickData(
                        timestamp=datetime.fromtimestamp(timestamp_ms / 1000),
                        price=tick_dict.get("price", 0.0),
                        volume=tick_dict.get("volume"),
                        instrument=instrument
                    )
                    ticks.append(tick)
                except (json.JSONDecodeError, KeyError, ValueError) as e:
                    logger.warning(f"Failed to parse tick data: {e}")
                    continue
            
            logger.debug(f"Fetched {len(ticks)} ticks for {instrument}")
            return ticks
            
        except Exception as e:
            logger.error(f"Failed to fetch tick buffer for {instrument}: {e}")
            return []
    
    async def _run_zscore_detectors(
        self,
        instrument: str,
        bar: OHLCVBar,
        historical_bars: List[OHLCVBar]
    ) -> List[AnomalyEvent]:
        """
        Run Z-score detectors on price and volume.
        
        Args:
            instrument: Instrument symbol
            bar: Current OHLCV bar
            historical_bars: List of recent historical bars (for rolling window)
        
        Returns:
            List of detected anomaly events
        """
        events = []
        
        try:
            # Need at least 20 bars for Z-score (window_size)
            if len(historical_bars) < 20:
                logger.debug(f"Insufficient historical data for Z-score: {len(historical_bars)} bars")
                return events
            
            # Prepare data arrays
            all_bars = historical_bars + [bar]
            prices = np.array([b.close for b in all_bars])
            volumes = np.array([b.volume for b in all_bars])
            timestamps = [b.timestamp.isoformat() if isinstance(b.timestamp, datetime) else b.timestamp 
                         for b in all_bars]
            
            # Run price spike detection
            price_events = self.zscore_detector.detect_price_spike(
                prices=prices,
                timestamps=timestamps,
                instrument=instrument,
                asset_class=bar.asset_class,
                exchange=bar.exchange
            )
            events.extend(price_events)
            
            # Run volume surge detection
            volume_events = self.zscore_detector.detect_volume_surge(
                volumes=volumes,
                timestamps=timestamps,
                instrument=instrument,
                asset_class=bar.asset_class,
                exchange=bar.exchange
            )
            events.extend(volume_events)
            
            logger.debug(f"Z-score detected {len(events)} anomalies for {instrument}")
            
        except Exception as e:
            logger.error(f"Error in Z-score detection for {instrument}: {e}")
        
        return events
    
    async def _run_cusum_detector(
        self,
        instrument: str,
        bar: OHLCVBar,
        historical_bars: List[OHLCVBar]
    ) -> List[AnomalyEvent]:
        """
        Run CUSUM detector for regime change detection.
        
        Args:
            instrument: Instrument symbol
            bar: Current OHLCV bar
            historical_bars: List of recent historical bars
        
        Returns:
            List of detected anomaly events
        """
        events = []
        
        try:
            # Need at least 20 bars for CUSUM
            if len(historical_bars) < 20:
                logger.debug(f"Insufficient historical data for CUSUM: {len(historical_bars)} bars")
                return events
            
            # Prepare data arrays
            all_bars = historical_bars + [bar]
            prices = np.array([b.close for b in all_bars])
            timestamps = [b.timestamp.isoformat() if isinstance(b.timestamp, datetime) else b.timestamp 
                         for b in all_bars]
            
            # Run CUSUM detection
            cusum_events = self.cusum_detector.detect_batch(
                series=prices,
                timestamps=timestamps,
                instrument=instrument,
                asset_class=bar.asset_class,
                exchange=bar.exchange,
                window_size=20
            )
            events.extend(cusum_events)
            
            logger.debug(f"CUSUM detected {len(events)} anomalies for {instrument}")
            
        except Exception as e:
            logger.error(f"Error in CUSUM detection for {instrument}: {e}")
        
        return events
    
    async def _run_isolation_forest_detector(
        self,
        instrument: str,
        bar: OHLCVBar,
        historical_bars: List[OHLCVBar]
    ) -> List[AnomalyEvent]:
        """
        Run Isolation Forest ML detector.
        
        Args:
            instrument: Instrument symbol
            bar: Current OHLCV bar
            historical_bars: List of recent historical bars
        
        Returns:
            List of detected anomaly events (0 or 1)
        """
        events = []
        
        try:
            # Need sufficient historical data for Isolation Forest
            if len(historical_bars) < 30:
                logger.debug(f"Insufficient historical data for Isolation Forest: {len(historical_bars)} bars")
                return events
            
            # Convert to DataFrame
            historical_df = pd.DataFrame([
                {
                    "timestamp": b.timestamp,
                    "open": b.open,
                    "high": b.high,
                    "low": b.low,
                    "close": b.close,
                    "volume": b.volume
                }
                for b in historical_bars
            ])
            
            # Run detection on current bar
            event = self.isolation_forest_detector.detect(
                bar=bar.to_series(),
                instrument=instrument,
                asset_class=bar.asset_class,
                exchange=bar.exchange,
                historical_data=historical_df
            )
            
            if event:
                events.append(event)
                logger.debug(f"Isolation Forest detected anomaly for {instrument}")
            
        except Exception as e:
            logger.error(f"Error in Isolation Forest detection for {instrument}: {e}")
        
        return events
    
    async def _run_flash_detector(
        self,
        instrument: str,
        bar: OHLCVBar
    ) -> List[AnomalyEvent]:
        """
        Run flash crash/rally detector on tick buffer.
        
        Args:
            instrument: Instrument symbol
            bar: Current OHLCV bar (for metadata)
        
        Returns:
            List of detected anomaly events (0 or 1)
        """
        events = []
        
        try:
            # Fetch tick buffer from Redis
            ticks = await self._get_tick_buffer(instrument)
            
            if len(ticks) < 2:
                logger.debug(f"Insufficient tick data for flash detection: {len(ticks)} ticks")
                return events
            
            # Run flash detection
            event = self.flash_detector.check_with_metadata(
                ticks=ticks,
                instrument=instrument,
                asset_class=bar.asset_class,
                exchange=bar.exchange,
                window_minutes=5
            )
            
            if event:
                events.append(event)
                logger.debug(f"Flash detector detected anomaly for {instrument}")
            
        except Exception as e:
            logger.error(f"Error in flash detection for {instrument}: {e}")
        
        return events
    
    async def _deduplicate_events(
        self,
        events: List[AnomalyEvent]
    ) -> List[AnomalyEvent]:
        """
        Deduplicate events using the deduplication service.
        
        Args:
            events: List of detected anomaly events
        
        Returns:
            List of events that should be emitted (not suppressed)
        """
        if not self._dedup_service:
            await self.connect()
        
        passed_events = []
        
        for event in events:
            try:
                should_suppress = await self._dedup_service.should_suppress(event)
                
                if not should_suppress:
                    passed_events.append(event)
                else:
                    logger.info(
                        f"Suppressed duplicate event: {event.instrument}:"
                        f"{event.anomaly_type.value} (severity: {event.severity.value})"
                    )
            except Exception as e:
                logger.error(f"Error in deduplication: {e}")
                # On error, don't suppress (fail open)
                passed_events.append(event)
        
        return passed_events
    
    async def _store_event_to_db(self, event: AnomalyEvent):
        """
        Store anomaly event to TimescaleDB.
        
        Args:
            event: AnomalyEvent to store
        """
        if not self._async_session_maker:
            await self.connect()
        
        try:
            async with self._async_session_maker() as session:
                # Convert Pydantic model to SQLAlchemy model
                db_event = AnomalyEvent(
                    id=event.id if event.id else uuid.uuid4(),
                    instrument=event.instrument,
                    asset_class=event.asset_class,
                    exchange=event.exchange,
                    anomaly_type=event.anomaly_type,
                    severity=event.severity,
                    detected_at=event.detected_at if event.detected_at else datetime.utcnow(),
                    description=event.description,
                    z_score=event.z_score,
                    price=event.price,
                    volume=event.volume,
                    raw_data=event.raw_data,
                    affected_instruments=event.affected_instruments if hasattr(event, 'affected_instruments') else None
                )
                
                session.add(db_event)
                await session.commit()
                
                logger.info(
                    f"Stored event to DB: {event.instrument}:{event.anomaly_type.value} "
                    f"(id: {db_event.id})"
                )
                
        except Exception as e:
            logger.error(f"Failed to store event to database: {e}")
            # Don't raise - continue with pub/sub even if DB fails
    
    async def _publish_event_to_redis(self, event: AnomalyEvent):
        """
        Publish anomaly event to Redis pub/sub channel.
        
        Channel pattern: `anomalies:{instrument}`
        
        Args:
            event: AnomalyEvent to publish
        """
        if not self._redis_client:
            await self.connect()
        
        try:
            channel = f"anomalies:{event.instrument}"
            
            # Serialize event to JSON
            event_data = {
                "id": str(event.id) if event.id else str(uuid.uuid4()),
                "instrument": event.instrument,
                "asset_class": event.asset_class,
                "exchange": event.exchange,
                "anomaly_type": event.anomaly_type.value,
                "severity": event.severity.value,
                "detected_at": event.detected_at.isoformat() if event.detected_at else datetime.utcnow().isoformat(),
                "description": event.description,
                "z_score": event.z_score,
                "price": event.price,
                "volume": event.volume,
                "raw_data": event.raw_data
            }
            
            # Publish to channel
            await self._redis_client.publish(channel, json.dumps(event_data))
            
            logger.info(
                f"Published event to Redis: {channel} "
                f"(type: {event.anomaly_type.value}, severity: {event.severity.value})"
            )
            
        except Exception as e:
            logger.error(f"Failed to publish event to Redis: {e}")
            # Don't raise - continue even if pub/sub fails
    
    async def process_bar(
        self,
        instrument: str,
        bar: OHLCVBar,
        historical_bars: Optional[List[OHLCVBar]] = None
    ) -> List[AnomalyEvent]:
        """
        Process a new OHLCV bar through the complete anomaly detection pipeline.
        
        This is the main entry point called on every new bar.
        
        Pipeline:
        1. Run all 4 detectors in parallel (ZScore price, ZScore volume, CUSUM, IsolationForest)
        2. Run flash detector on tick buffer
        3. Deduplicate events
        4. Store passed events to TimescaleDB
        5. Publish passed events to Redis pub/sub
        
        Args:
            instrument: Instrument symbol
            bar: Current OHLCV bar
            historical_bars: Optional list of recent historical bars (for context)
                           If not provided, will attempt to fetch from database
        
        Returns:
            List of anomaly events that were emitted (after deduplication)
        
        Requirements: 11.5, 11.7
        """
        # Ensure connections are established
        if not self._redis_client or not self._async_session_maker:
            await self.connect()
        
        logger.info(f"Processing bar for {instrument} at {bar.timestamp}")
        
        # Fetch historical data if not provided
        if historical_bars is None:
            historical_bars = []
            # TODO: Fetch from database
            logger.debug(f"No historical bars provided for {instrument}")
        
        try:
            # Run all detectors in parallel
            detector_tasks = [
                self._run_zscore_detectors(instrument, bar, historical_bars),
                self._run_cusum_detector(instrument, bar, historical_bars),
                self._run_isolation_forest_detector(instrument, bar, historical_bars),
                self._run_flash_detector(instrument, bar)
            ]
            
            # Wait for all detectors to complete
            detector_results = await asyncio.gather(*detector_tasks, return_exceptions=True)
            
            # Collect all detected events
            all_events = []
            for result in detector_results:
                if isinstance(result, Exception):
                    logger.error(f"Detector failed with exception: {result}")
                    continue
                if isinstance(result, list):
                    all_events.extend(result)
            
            logger.info(f"Detected {len(all_events)} total anomalies for {instrument}")
            
            # Deduplicate events
            passed_events = await self._deduplicate_events(all_events)
            
            logger.info(f"After deduplication: {len(passed_events)} events to emit for {instrument}")
            
            # Store and publish passed events
            for event in passed_events:
                # Store to database and publish to Redis in parallel
                await asyncio.gather(
                    self._store_event_to_db(event),
                    self._publish_event_to_redis(event),
                    return_exceptions=True
                )
            
            return passed_events
            
        except Exception as e:
            logger.error(f"Error in process_bar for {instrument}: {e}")
            return []


# Global orchestrator instance
_orchestrator: Optional[AnomalyOrchestrator] = None


async def get_orchestrator() -> AnomalyOrchestrator:
    """
    Get or create the global anomaly orchestrator instance.
    
    Returns:
        AnomalyOrchestrator instance
    """
    global _orchestrator
    
    if _orchestrator is None:
        _orchestrator = AnomalyOrchestrator()
        await _orchestrator.connect()
    
    return _orchestrator


async def close_orchestrator():
    """Close the global orchestrator connections"""
    global _orchestrator
    
    if _orchestrator:
        await _orchestrator.disconnect()
        _orchestrator = None
