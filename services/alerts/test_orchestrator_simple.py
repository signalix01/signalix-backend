"""
Simple integration test for Anomaly Detection Orchestrator

Tests the core functionality with minimal mocking.
Requirements: 11.5, 11.7
Task: 32
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import json

from services.alerts.anomaly_orchestrator import (
    AnomalyOrchestrator,
    OHLCVBar
)
from shared.database.models import AnomalyType, AnomalySeverity


@pytest.fixture
def normal_bars():
    """Generate normal OHLCV bars"""
    bars = []
    base_time = datetime(2024, 1, 1, 9, 0, 0)
    base_price = 100.0
    
    for i in range(30):
        timestamp = base_time + timedelta(minutes=i)
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
    """Generate an anomalous OHLCV bar"""
    return OHLCVBar(
        timestamp=datetime(2024, 1, 1, 9, 30, 0),
        open=100.0,
        high=115.0,
        low=100.0,
        close=112.0,  # 12% spike
        volume=5000000,  # 5x normal
        instrument="RELIANCE",
        asset_class="equity",
        exchange="NSE"
    )


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
        assert "timestamp" in bar_dict


class TestAnomalyOrchestrator:
    """Test AnomalyOrchestrator core functionality"""
    
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
    @patch('services.alerts.anomaly_orchestrator.async_sessionmaker')
    @patch('services.alerts.anomaly_orchestrator.get_dedup_service')
    async def test_process_bar_detects_anomaly(
        self,
        mock_get_dedup,
        mock_sessionmaker,
        mock_create_engine,
        mock_redis_from_url,
        normal_bars,
        anomalous_bar
    ):
        """Test that orchestrator detects anomalies in anomalous data"""
        # Setup mocks
        mock_redis_client = AsyncMock()
        mock_redis_client.ping = AsyncMock()
        mock_redis_client.publish = AsyncMock()
        mock_redis_client.zrangebyscore = AsyncMock(return_value=[])
        mock_redis_client.close = AsyncMock()
        mock_redis_from_url.return_value = mock_redis_client
        
        mock_engine = MagicMock()
        mock_engine.dispose = AsyncMock()
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
        
        # Verify anomalies were detected
        assert len(events) > 0, "Should detect at least one anomaly"
        
        # Verify event structure
        for event in events:
            assert hasattr(event, 'instrument')
            assert hasattr(event, 'anomaly_type')
            assert hasattr(event, 'severity')
            assert event.instrument == "RELIANCE"
        
        # Verify Redis publish was called
        assert mock_redis_client.publish.called
        
        # Verify database storage was attempted
        assert mock_session.add.called
        assert mock_session.commit.called
        
        # Cleanup
        await orchestrator.disconnect()
    
    @pytest.mark.asyncio
    @patch('services.alerts.anomaly_orchestrator.redis.from_url')
    @patch('services.alerts.anomaly_orchestrator.create_async_engine')
    @patch('services.alerts.anomaly_orchestrator.async_sessionmaker')
    @patch('services.alerts.anomaly_orchestrator.get_dedup_service')
    async def test_redis_publish_channel_format(
        self,
        mock_get_dedup,
        mock_sessionmaker,
        mock_create_engine,
        mock_redis_from_url,
        normal_bars,
        anomalous_bar
    ):
        """Test that Redis publish uses correct channel format"""
        # Setup mocks
        mock_redis_client = AsyncMock()
        mock_redis_client.ping = AsyncMock()
        mock_redis_client.publish = AsyncMock()
        mock_redis_client.zrangebyscore = AsyncMock(return_value=[])
        mock_redis_client.close = AsyncMock()
        mock_redis_from_url.return_value = mock_redis_client
        
        mock_engine = MagicMock()
        mock_engine.dispose = AsyncMock()
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
            # Verify Redis publish was called
            assert mock_redis_client.publish.called
            
            # Get the first publish call
            call_args = mock_redis_client.publish.call_args_list[0]
            channel = call_args[0][0]
            message = call_args[0][1]
            
            # Verify channel format: anomalies:{instrument}
            assert channel == "anomalies:RELIANCE"
            
            # Verify message is valid JSON
            message_data = json.loads(message)
            assert "instrument" in message_data
            assert "anomaly_type" in message_data
            assert "severity" in message_data
            assert message_data["instrument"] == "RELIANCE"
        
        # Cleanup
        await orchestrator.disconnect()
    
    @pytest.mark.asyncio
    @patch('services.alerts.anomaly_orchestrator.redis.from_url')
    @patch('services.alerts.anomaly_orchestrator.create_async_engine')
    @patch('services.alerts.anomaly_orchestrator.async_sessionmaker')
    @patch('services.alerts.anomaly_orchestrator.get_dedup_service')
    async def test_database_storage(
        self,
        mock_get_dedup,
        mock_sessionmaker,
        mock_create_engine,
        mock_redis_from_url,
        normal_bars,
        anomalous_bar
    ):
        """Test that events are stored to database"""
        # Setup mocks
        mock_redis_client = AsyncMock()
        mock_redis_client.ping = AsyncMock()
        mock_redis_client.publish = AsyncMock()
        mock_redis_client.zrangebyscore = AsyncMock(return_value=[])
        mock_redis_client.close = AsyncMock()
        mock_redis_from_url.return_value = mock_redis_client
        
        mock_engine = MagicMock()
        mock_engine.dispose = AsyncMock()
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
            assert stored_event.instrument == "RELIANCE"
            
            # Verify commit was called
            assert mock_session.commit.called
        
        # Cleanup
        await orchestrator.disconnect()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
