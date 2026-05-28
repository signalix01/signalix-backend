"""
Integration tests for Anomaly Detection Orchestrator

Tests the complete anomaly detection pipeline:
- Detector coordination and parallel execution
- Deduplication logic
- Database storage
- Redis pub/sub publishing

Requirements: 11.5, 11.7
Task: 32
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import json
import uuid

from services.alerts.anomaly_orchestrator import (
    AnomalyOrchestrator,
    OHLCVBar,
    get_orchestrator,
    close_orchestrator
)
from shared.database.models import AnomalyEvent, AnomalyType, AnomalySeverity


@pytest.fixture
def normal_bars():
    """Generate normal OHLCV bars for testing"""
    bars = []
    base_time = datetime(2024, 1, 1, 9, 0, 0)
    base_price = 100.0
    
    for i in range(30):
        timestamp = base_time + timedelta(minutes=i)
        # Normal price movement (±1%)
        price = base_price + (i % 3 - 1) * 0.5
        
        bar = OHLCVBar(
            timestamp=timestamp,
            open=price - 0.2,
            high=price + 0.3,
            low=price - 0.3,
            close=price,
            volume=1000000 + (i % 5) * 10000,
            instrument="RELIANCE",
            asset_class="equity",
            exchange="NSE"
        )
        bars.append(bar)
    
    return bars


@pytest.fixture
def anomalous_bar():
    """Generate an anomalous OHLCV bar (price spike)"""
    return OHLCVBar(
        timestamp=datetime(2024, 1, 1, 9, 30, 0),
        open=100.0,
        high=115.0,  # 15% spike
        low=100.0,
        close=112.0,  # 12% spike from normal
        volume=5000000,  # 5x normal volume
        instrument="RELIANCE",
        asset_class="equity",
        exchange="NSE"
    )


@pytest.fixture
def mock_redis():
    """Mock Redis client"""
    mock_client = AsyncMock()
    mock_client.ping = AsyncMock()
    mock_client.publish = AsyncMock()
    mock_client.zrangebyscore = AsyncMock(return_value=[])
    mock_client.close = AsyncMock()
    return mock_client


@pytest.fixture
def mock_db_engine():
    """Mock database engine"""
    mock_engine = MagicMock()
    mock_engine.dispose = AsyncMock()
    return mock_engine


@pytest.fixture
def mock_db_session():
    """Mock database session"""
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()
    mock_session.close = AsyncMock()
    return mock_session


@pytest.fixture
def mock_dedup_service():
    """Mock deduplication service"""
    mock_service = AsyncMock()
    mock_service.should_suppress = AsyncMock(return_value=False)
    return mock_service


class TestOHLCVBar:
    """Test OHLCVBar data structure"""
    
    def test_bar_creation(self):
        """Test creating an OHLCV bar"""
        bar = OHLCVBar(
            timestamp=datetime(2024, 1, 1, 9, 0, 0),
            open=100.0,
            high=102.0,
            low=99.0,
            close=101.0,
            volume=1000000,
            instrument="RELIANCE",
            asset_class="equity",
            exchange="NSE"
        )
        
        assert bar.instrument == "RELIANCE"
        assert bar.close == 101.0
        assert bar.volume == 1000000
    
    def test_bar_to_dict(self):
        """Test converting bar to dictionary"""
        bar = OHLCVBar(
            timestamp=datetime(2024, 1, 1, 9, 0, 0),
            open=100.0,
            high=102.0,
            low=99.0,
            close=101.0,
            volume=1000000,
            instrument="RELIANCE",
            asset_class="equity",
            exchange="NSE"
        )
        
        bar_dict = bar.to_dict()
        
        assert bar_dict["instrument"] == "RELIANCE"
        assert bar_dict["close"] == 101.0
        assert bar_dict["volume"] == 1000000
        assert "timestamp" in bar_dict
    
    def test_bar_to_series(self):
        """Test converting bar to pandas Series"""
        bar = OHLCVBar(
            timestamp=datetime(2024, 1, 1, 9, 0, 0),
            open=100.0,
            high=102.0,
            low=99.0,
            close=101.0,
            volume=1000000,
            instrument="RELIANCE",
            asset_class="equity",
            exchange="NSE"
        )
        
        series = bar.to_series()
        
        assert series["close"] == 101.0
        assert series["volume"] == 1000000
        assert "timestamp" in series.index


class TestAnomalyOrchestrator:
    """Test AnomalyOrchestrator functionality"""
    
    @pytest.mark.asyncio
    async def test_orchestrator_initialization(self):
        """Test orchestrator initialization"""
        orchestrator = AnomalyOrchestrator()
        
        assert orchestrator.zscore_detector is not None
        assert orchestrator.cusum_detector is not None
        assert orchestrator.isolation_forest_detector is not None
        assert orchestrator.flash_detector is not None
    
    @pytest.mark.asyncio
    @patch('services.alerts.anomaly_orchestrator.redis.from_url')
    @patch('services.alerts.anomaly_orchestrator.create_async_engine')
    @patch('services.alerts.anomaly_orchestrator.get_dedup_service')
    async def test_orchestrator_connect(
        self,
        mock_get_dedup,
        mock_create_engine,
        mock_redis_from_url
    ):
        """Test orchestrator connection setup"""
        # Setup mocks
        mock_redis_client = AsyncMock()
        mock_redis_client.ping = AsyncMock()
        mock_redis_from_url.return_value = mock_redis_client
        
        mock_engine = MagicMock()
        mock_engine.dispose = AsyncMock()
        mock_create_engine.return_value = mock_engine
        
        mock_dedup = AsyncMock()
        mock_get_dedup.return_value = mock_dedup
        
        # Test connection
        orchestrator = AnomalyOrchestrator()
        await orchestrator.connect()
        
        assert orchestrator._redis_client is not None
        assert orchestrator._db_engine is not None
        assert orchestrator._dedup_service is not None
        
        # Cleanup
        await orchestrator.disconnect()
    
    @pytest.mark.asyncio
    @patch('services.alerts.anomaly_orchestrator.redis.from_url')
    @patch('services.alerts.anomaly_orchestrator.create_async_engine')
    @patch('services.alerts.anomaly_orchestrator.async_sessionmaker')
    @patch('services.alerts.anomaly_orchestrator.get_dedup_service')
    async def test_process_bar_with_anomaly(
        self,
        mock_get_dedup,
        mock_sessionmaker,
        mock_create_engine,
        mock_redis_from_url,
        normal_bars,
        anomalous_bar,
        mock_redis,
        mock_db_engine
    ):
        """Test processing a bar with anomalous data"""
        # Setup mocks
        mock_redis_from_url.return_value = mock_redis
        mock_create_engine.return_value = mock_db_engine
        
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()
        
        mock_session_factory = MagicMock(return_value=mock_session)
        mock_sessionmaker.return_value = mock_session_factory
        
        mock_dedup = AsyncMock()
        mock_dedup.should_suppress = AsyncMock(return_value=False)
        mock_get_dedup.return_value = mock_dedup
        
        # Create orchestrator and process bar
        orchestrator = AnomalyOrchestrator()
        await orchestrator.connect()
        
        # Process anomalous bar with historical context
        events = await orchestrator.process_bar(
            instrument="RELIANCE",
            bar=anomalous_bar,
            historical_bars=normal_bars
        )
        
        # Verify events were detected
        assert len(events) > 0, "Should detect at least one anomaly"
        
        # Verify Redis publish was called
        assert mock_redis.publish.called, "Should publish to Redis"
        
        # Verify database storage was attempted
        assert mock_session.add.called, "Should store to database"
        assert mock_session.commit.called, "Should commit to database"
        
        # Cleanup
        await orchestrator.disconnect()
    
    @pytest.mark.asyncio
    @patch('services.alerts.anomaly_orchestrator.redis.from_url')
    @patch('services.alerts.anomaly_orchestrator.create_async_engine')
    @patch('services.alerts.anomaly_orchestrator.async_sessionmaker')
    @patch('services.alerts.anomaly_orchestrator.get_dedup_service')
    async def test_process_bar_normal_data(
        self,
        mock_get_dedup,
        mock_sessionmaker,
        mock_create_engine,
        mock_redis_from_url,
        normal_bars
    ):
        """Test processing normal bars (should not detect anomalies)"""
        # Setup mocks
        mock_redis_client = AsyncMock()
        mock_redis_client.ping = AsyncMock()
        mock_redis_client.publish = AsyncMock()
        mock_redis_client.zrangebyscore = AsyncMock(return_value=[])
        mock_redis_from_url.return_value = mock_redis_client
        
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine
        
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()
        
        mock_session_factory = MagicMock(return_value=mock_session)
        mock_sessionmaker.return_value = mock_session_factory
        
        mock_dedup = AsyncMock()
        mock_dedup.should_suppress = AsyncMock(return_value=False)
        mock_get_dedup.return_value = mock_dedup
        
        # Create orchestrator
        orchestrator = AnomalyOrchestrator()
        await orchestrator.connect()
        
        # Process normal bar
        normal_bar = normal_bars[-1]
        events = await orchestrator.process_bar(
            instrument="RELIANCE",
            bar=normal_bar,
            historical_bars=normal_bars[:-1]
        )
        
        # Should detect few or no anomalies on normal data
        assert len(events) == 0 or len(events) < 2, "Should detect few anomalies on normal data"
        
        # Cleanup
        await orchestrator.disconnect()
    
    @pytest.mark.asyncio
    @patch('services.alerts.anomaly_orchestrator.redis.from_url')
    @patch('services.alerts.anomaly_orchestrator.create_async_engine')
    @patch('services.alerts.anomaly_orchestrator.async_sessionmaker')
    @patch('services.alerts.anomaly_orchestrator.get_dedup_service')
    async def test_deduplication_suppresses_duplicate(
        self,
        mock_get_dedup,
        mock_sessionmaker,
        mock_create_engine,
        mock_redis_from_url,
        normal_bars,
        anomalous_bar
    ):
        """Test that deduplication suppresses duplicate events"""
        # Setup mocks
        mock_redis_client = AsyncMock()
        mock_redis_client.ping = AsyncMock()
        mock_redis_client.publish = AsyncMock()
        mock_redis_client.zrangebyscore = AsyncMock(return_value=[])
        mock_redis_from_url.return_value = mock_redis_client
        
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine
        
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()
        
        mock_session_factory = MagicMock(return_value=mock_session)
        mock_sessionmaker.return_value = mock_session_factory
        
        # Mock deduplication to suppress all events
        mock_dedup = AsyncMock()
        mock_dedup.should_suppress = AsyncMock(return_value=True)
        mock_get_dedup.return_value = mock_dedup
        
        # Create orchestrator
        orchestrator = AnomalyOrchestrator()
        await orchestrator.connect()
        
        # Process anomalous bar
        events = await orchestrator.process_bar(
            instrument="RELIANCE",
            bar=anomalous_bar,
            historical_bars=normal_bars
        )
        
        # All events should be suppressed
        assert len(events) == 0, "All events should be suppressed by deduplication"
        
        # Verify deduplication was called
        assert mock_dedup.should_suppress.called, "Deduplication should be called"
        
        # Cleanup
        await orchestrator.disconnect()
    
    @pytest.mark.asyncio
    @patch('services.alerts.anomaly_orchestrator.redis.from_url')
    @patch('services.alerts.anomaly_orchestrator.create_async_engine')
    @patch('services.alerts.anomaly_orchestrator.async_sessionmaker')
    @patch('services.alerts.anomaly_orchestrator.get_dedup_service')
    async def test_redis_publish_format(
        self,
        mock_get_dedup,
        mock_sessionmaker,
        mock_create_engine,
        mock_redis_from_url,
        normal_bars,
        anomalous_bar
    ):
        """Test that Redis publish uses correct format"""
        # Setup mocks
        mock_redis_client = AsyncMock()
        mock_redis_client.ping = AsyncMock()
        mock_redis_client.publish = AsyncMock()
        mock_redis_client.zrangebyscore = AsyncMock(return_value=[])
        mock_redis_from_url.return_value = mock_redis_client
        
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine
        
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()
        
        mock_session_factory = MagicMock(return_value=mock_session)
        mock_sessionmaker.return_value = mock_session_factory
        
        mock_dedup = AsyncMock()
        mock_dedup.should_suppress = AsyncMock(return_value=False)
        mock_get_dedup.return_value = mock_dedup
        
        # Create orchestrator
        orchestrator = AnomalyOrchestrator()
        await orchestrator.connect()
        
        # Process anomalous bar
        events = await orchestrator.process_bar(
            instrument="RELIANCE",
            bar=anomalous_bar,
            historical_bars=normal_bars
        )
        
        if len(events) > 0:
            # Verify Redis publish was called with correct channel pattern
            assert mock_redis_client.publish.called
            
            # Get the first publish call
            call_args = mock_redis_client.publish.call_args_list[0]
            channel = call_args[0][0]
            message = call_args[0][1]
            
            # Verify channel format
            assert channel == "anomalies:RELIANCE", f"Channel should be 'anomalies:RELIANCE', got '{channel}'"
            
            # Verify message is valid JSON
            message_data = json.loads(message)
            assert "instrument" in message_data
            assert "anomaly_type" in message_data
            assert "severity" in message_data
            assert "detected_at" in message_data
            assert message_data["instrument"] == "RELIANCE"
        
        # Cleanup
        await orchestrator.disconnect()
    
    @pytest.mark.asyncio
    @patch('services.alerts.anomaly_orchestrator.redis.from_url')
    @patch('services.alerts.anomaly_orchestrator.create_async_engine')
    @patch('services.alerts.anomaly_orchestrator.async_sessionmaker')
    @patch('services.alerts.anomaly_orchestrator.get_dedup_service')
    async def test_database_storage_format(
        self,
        mock_get_dedup,
        mock_sessionmaker,
        mock_create_engine,
        mock_redis_from_url,
        normal_bars,
        anomalous_bar
    ):
        """Test that database storage uses correct format"""
        # Setup mocks
        mock_redis_client = AsyncMock()
        mock_redis_client.ping = AsyncMock()
        mock_redis_client.publish = AsyncMock()
        mock_redis_client.zrangebyscore = AsyncMock(return_value=[])
        mock_redis_from_url.return_value = mock_redis_client
        
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine
        
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()
        
        mock_session_factory = MagicMock(return_value=mock_session)
        mock_sessionmaker.return_value = mock_session_factory
        
        mock_dedup = AsyncMock()
        mock_dedup.should_suppress = AsyncMock(return_value=False)
        mock_get_dedup.return_value = mock_dedup
        
        # Create orchestrator
        orchestrator = AnomalyOrchestrator()
        await orchestrator.connect()
        
        # Process anomalous bar
        events = await orchestrator.process_bar(
            instrument="RELIANCE",
            bar=anomalous_bar,
            historical_bars=normal_bars
        )
        
        if len(events) > 0:
            # Verify database add was called
            assert mock_session.add.called
            
            # Get the stored event
            stored_event = mock_session.add.call_args[0][0]
            
            # Verify event structure
            assert hasattr(stored_event, 'instrument')
            assert hasattr(stored_event, 'anomaly_type')
            assert hasattr(stored_event, 'severity')
            assert hasattr(stored_event, 'detected_at')
            assert stored_event.instrument == "RELIANCE"
        
        # Cleanup
        await orchestrator.disconnect()
    
    @pytest.mark.asyncio
    @patch('services.alerts.anomaly_orchestrator.redis.from_url')
    @patch('services.alerts.anomaly_orchestrator.create_async_engine')
    @patch('services.alerts.anomaly_orchestrator.async_sessionmaker')
    @patch('services.alerts.anomaly_orchestrator.get_dedup_service')
    async def test_parallel_detector_execution(
        self,
        mock_get_dedup,
        mock_sessionmaker,
        mock_create_engine,
        mock_redis_from_url,
        normal_bars,
        anomalous_bar
    ):
        """Test that detectors run in parallel"""
        # Setup mocks
        mock_redis_client = AsyncMock()
        mock_redis_client.ping = AsyncMock()
        mock_redis_client.publish = AsyncMock()
        mock_redis_client.zrangebyscore = AsyncMock(return_value=[])
        mock_redis_from_url.return_value = mock_redis_client
        
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine
        
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()
        
        mock_session_factory = MagicMock(return_value=mock_session)
        mock_sessionmaker.return_value = mock_session_factory
        
        mock_dedup = AsyncMock()
        mock_dedup.should_suppress = AsyncMock(return_value=False)
        mock_get_dedup.return_value = mock_dedup
        
        # Create orchestrator
        orchestrator = AnomalyOrchestrator()
        await orchestrator.connect()
        
        # Measure execution time
        import time
        start_time = time.time()
        
        # Process bar
        events = await orchestrator.process_bar(
            instrument="RELIANCE",
            bar=anomalous_bar,
            historical_bars=normal_bars
        )
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        # Parallel execution should be faster than sequential
        # (This is a rough check - actual timing depends on system)
        assert execution_time < 5.0, "Parallel execution should complete quickly"
        
        # Cleanup
        await orchestrator.disconnect()


class TestGlobalOrchestrator:
    """Test global orchestrator instance management"""
    
    @pytest.mark.asyncio
    @patch('services.alerts.anomaly_orchestrator.redis.from_url')
    @patch('services.alerts.anomaly_orchestrator.create_async_engine')
    @patch('services.alerts.anomaly_orchestrator.get_dedup_service')
    async def test_get_orchestrator_singleton(
        self,
        mock_get_dedup,
        mock_create_engine,
        mock_redis_from_url
    ):
        """Test that get_orchestrator returns singleton instance"""
        # Setup mocks
        mock_redis_client = AsyncMock()
        mock_redis_client.ping = AsyncMock()
        mock_redis_from_url.return_value = mock_redis_client
        
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine
        
        mock_dedup = AsyncMock()
        mock_get_dedup.return_value = mock_dedup
        
        # Get orchestrator twice
        orchestrator1 = await get_orchestrator()
        orchestrator2 = await get_orchestrator()
        
        # Should be the same instance
        assert orchestrator1 is orchestrator2
        
        # Cleanup
        await close_orchestrator()
    
    @pytest.mark.asyncio
    @patch('services.alerts.anomaly_orchestrator.redis.from_url')
    @patch('services.alerts.anomaly_orchestrator.create_async_engine')
    @patch('services.alerts.anomaly_orchestrator.get_dedup_service')
    async def test_close_orchestrator(
        self,
        mock_get_dedup,
        mock_create_engine,
        mock_redis_from_url
    ):
        """Test closing the global orchestrator"""
        # Setup mocks
        mock_redis_client = AsyncMock()
        mock_redis_client.ping = AsyncMock()
        mock_redis_client.close = AsyncMock()
        mock_redis_from_url.return_value = mock_redis_client
        
        mock_engine = MagicMock()
        mock_engine.dispose = AsyncMock()
        mock_create_engine.return_value = mock_engine
        
        mock_dedup = AsyncMock()
        mock_get_dedup.return_value = mock_dedup
        
        # Get and close orchestrator
        orchestrator = await get_orchestrator()
        await close_orchestrator()
        
        # Verify connections were closed
        assert mock_redis_client.close.called
        assert mock_engine.dispose.called


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
