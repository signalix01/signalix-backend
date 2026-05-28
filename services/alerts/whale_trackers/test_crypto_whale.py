"""
Integration tests for Crypto Whale Tracker

Tests:
1. Mock Glassnode API with 600 BTC inflow
2. Verify CRITICAL event generated
3. Test AI interpretation generation
4. Test caching behavior
5. Test whale transfer detection
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
import json

from services.alerts.whale_trackers.crypto_whale import CryptoWhaleTracker
from shared.database.models import AnomalyType, AnomalySeverity


@pytest.fixture
def mock_redis_client():
    """Mock Redis client for testing"""
    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.setex = AsyncMock()
    return redis_mock


@pytest.fixture
def crypto_tracker(mock_redis_client):
    """Create CryptoWhaleTracker instance with mocked dependencies"""
    return CryptoWhaleTracker(
        glassnode_api_key="test_api_key",
        anthropic_api_key="test_anthropic_key",
        redis_client=mock_redis_client,
        timeout_seconds=30
    )


@pytest.fixture
def mock_glassnode_inflow_response():
    """Mock Glassnode API response for exchange inflow (600 BTC)"""
    return [
        {
            "t": int(datetime.utcnow().timestamp()),
            "v": 600.0  # 600 BTC inflow
        }
    ]


@pytest.fixture
def mock_glassnode_outflow_response():
    """Mock Glassnode API response for exchange outflow (100 BTC)"""
    return [
        {
            "t": int(datetime.utcnow().timestamp()),
            "v": 100.0  # 100 BTC outflow
        }
    ]


@pytest.fixture
def mock_glassnode_large_txn_response():
    """Mock Glassnode API response for large transactions"""
    return [
        {
            "t": int(datetime.utcnow().timestamp()),
            "v": 75  # 75 large transactions
        }
    ]


class TestCryptoWhaleTracker:
    """Test suite for CryptoWhaleTracker"""
    
    @pytest.mark.asyncio
    async def test_fetch_exchange_inflow_success(
        self,
        crypto_tracker,
        mock_glassnode_inflow_response
    ):
        """Test successful fetch of exchange inflow data"""
        with patch('httpx.AsyncClient') as mock_client:
            # Setup mock response
            mock_response = MagicMock()
            mock_response.json.return_value = mock_glassnode_inflow_response
            mock_response.raise_for_status = MagicMock()
            
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )
            
            # Fetch data
            result = await crypto_tracker.fetch_exchange_inflow("BTC")
            
            # Assertions
            assert result is not None
            assert result["asset"] == "BTC"
            assert result["metric"] == "exchange_inflow"
            assert result["value_btc"] == 600.0
            assert "timestamp" in result
    
    @pytest.mark.asyncio
    async def test_fetch_exchange_outflow_success(
        self,
        crypto_tracker,
        mock_glassnode_outflow_response
    ):
        """Test successful fetch of exchange outflow data"""
        with patch('httpx.AsyncClient') as mock_client:
            # Setup mock response
            mock_response = MagicMock()
            mock_response.json.return_value = mock_glassnode_outflow_response
            mock_response.raise_for_status = MagicMock()
            
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )
            
            # Fetch data
            result = await crypto_tracker.fetch_exchange_outflow("BTC")
            
            # Assertions
            assert result is not None
            assert result["asset"] == "BTC"
            assert result["metric"] == "exchange_outflow"
            assert result["value_btc"] == 100.0
    
    @pytest.mark.asyncio
    async def test_fetch_large_transactions_success(
        self,
        crypto_tracker,
        mock_glassnode_large_txn_response
    ):
        """Test successful fetch of large transaction data"""
        with patch('httpx.AsyncClient') as mock_client:
            # Setup mock response
            mock_response = MagicMock()
            mock_response.json.return_value = mock_glassnode_large_txn_response
            mock_response.raise_for_status = MagicMock()
            
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )
            
            # Fetch data
            result = await crypto_tracker.fetch_large_transactions("BTC")
            
            # Assertions
            assert result is not None
            assert result["asset"] == "BTC"
            assert result["metric"] == "large_transactions"
            assert result["count"] == 75
    
    @pytest.mark.asyncio
    async def test_detect_netflow_anomaly_critical_inflow(self, crypto_tracker):
        """
        Test detection of CRITICAL netflow anomaly with 600 BTC inflow.
        
        This is the main integration test specified in the task:
        - Mock Glassnode API with 600 BTC inflow
        - Verify CRITICAL event generated
        """
        # Mock data: 600 BTC inflow, 100 BTC outflow = 500 BTC net inflow
        inflow_data = {
            "timestamp": int(datetime.utcnow().timestamp()),
            "value_btc": 600.0,
            "asset": "BTC",
            "metric": "exchange_inflow"
        }
        
        outflow_data = {
            "timestamp": int(datetime.utcnow().timestamp()),
            "value_btc": 100.0,
            "asset": "BTC",
            "metric": "exchange_outflow"
        }
        
        large_txn_data = {
            "timestamp": int(datetime.utcnow().timestamp()),
            "count": 75,
            "asset": "BTC",
            "metric": "large_transactions"
        }
        
        # Mock AI interpretation
        with patch.object(
            crypto_tracker,
            'generate_ai_interpretation',
            return_value="Potential sell pressure signal"
        ):
            # Detect anomaly
            events = await crypto_tracker.detect_netflow_anomaly(
                "BTC",
                inflow_data,
                outflow_data,
                large_txn_data
            )
        
        # Assertions
        assert len(events) == 1
        event = events[0]
        
        # Verify event properties
        assert event.instrument == "BTC/USD"
        assert event.asset_class == "crypto"
        assert event.exchange == "AGGREGATE"
        assert event.anomaly_type == AnomalyType.WHALE_MOVEMENT
        assert event.severity == AnomalySeverity.CRITICAL  # 500 BTC netflow >= 500 threshold
        assert "Large exchange inflow detected" in event.description
        assert "500.00 BTC" in event.description
        assert "Potential sell pressure signal" in event.description
        
        # Verify raw data
        assert event.raw_data["detection_type"] == "exchange_netflow"
        assert event.raw_data["asset"] == "BTC"
        assert event.raw_data["inflow_btc"] == 600.0
        assert event.raw_data["outflow_btc"] == 100.0
        assert event.raw_data["netflow_btc"] == 500.0
        assert event.raw_data["direction"] == "inflow"
        assert event.raw_data["large_txn_count"] == 75
        assert event.raw_data["threshold_btc"] == 500.0
    
    @pytest.mark.asyncio
    async def test_detect_netflow_anomaly_high_outflow(self, crypto_tracker):
        """Test detection of HIGH severity netflow anomaly with large outflow (accumulation)"""
        # Mock data: 100 BTC inflow, 1200 BTC outflow = -1100 BTC net outflow
        inflow_data = {
            "timestamp": int(datetime.utcnow().timestamp()),
            "value_btc": 100.0,
            "asset": "BTC",
            "metric": "exchange_inflow"
        }
        
        outflow_data = {
            "timestamp": int(datetime.utcnow().timestamp()),
            "value_btc": 1200.0,
            "asset": "BTC",
            "metric": "exchange_outflow"
        }
        
        large_txn_data = None
        
        # Mock AI interpretation
        with patch.object(
            crypto_tracker,
            'generate_ai_interpretation',
            return_value="Accumulation detected"
        ):
            # Detect anomaly
            events = await crypto_tracker.detect_netflow_anomaly(
                "BTC",
                inflow_data,
                outflow_data,
                large_txn_data
            )
        
        # Assertions
        assert len(events) == 1
        event = events[0]
        
        assert event.severity == AnomalySeverity.HIGH  # 1100 BTC >= 1000 threshold
        assert event.raw_data["direction"] == "outflow"
        assert event.raw_data["netflow_btc"] == -1100.0
        assert "Accumulation detected" in event.description
    
    @pytest.mark.asyncio
    async def test_detect_netflow_anomaly_below_threshold(self, crypto_tracker):
        """Test that netflow below threshold does not generate event"""
        # Mock data: 250 BTC inflow, 100 BTC outflow = 150 BTC net inflow (below 500 threshold)
        inflow_data = {
            "timestamp": int(datetime.utcnow().timestamp()),
            "value_btc": 250.0,
            "asset": "BTC",
            "metric": "exchange_inflow"
        }
        
        outflow_data = {
            "timestamp": int(datetime.utcnow().timestamp()),
            "value_btc": 100.0,
            "asset": "BTC",
            "metric": "exchange_outflow"
        }
        
        large_txn_data = None
        
        # Detect anomaly
        events = await crypto_tracker.detect_netflow_anomaly(
            "BTC",
            inflow_data,
            outflow_data,
            large_txn_data
        )
        
        # Assertions - no events should be generated
        assert len(events) == 0
    
    @pytest.mark.asyncio
    async def test_detect_whale_transfers_high_activity(self, crypto_tracker):
        """Test detection of whale transfers based on high transaction count"""
        large_txn_data = {
            "timestamp": int(datetime.utcnow().timestamp()),
            "count": 150,  # High whale activity
            "asset": "BTC",
            "metric": "large_transactions"
        }
        
        # Mock AI interpretation
        with patch.object(
            crypto_tracker,
            'generate_ai_interpretation',
            return_value="Significant whale movement detected"
        ):
            # Detect whale transfers
            events = await crypto_tracker.detect_whale_transfers("BTC", large_txn_data)
        
        # Assertions
        assert len(events) == 1
        event = events[0]
        
        assert event.instrument == "BTC/USD"
        assert event.asset_class == "crypto"
        assert event.exchange == "BLOCKCHAIN"
        assert event.anomaly_type == AnomalyType.WHALE_MOVEMENT
        assert event.severity == AnomalySeverity.HIGH  # 150 >= 100 threshold
        assert "150 large transactions" in event.description
        assert event.raw_data["detection_type"] == "whale_transfers"
        assert event.raw_data["large_txn_count"] == 150
    
    @pytest.mark.asyncio
    async def test_detect_whale_transfers_below_threshold(self, crypto_tracker):
        """Test that low transaction count does not generate event"""
        large_txn_data = {
            "timestamp": int(datetime.utcnow().timestamp()),
            "count": 30,  # Below 50 threshold
            "asset": "BTC",
            "metric": "large_transactions"
        }
        
        # Detect whale transfers
        events = await crypto_tracker.detect_whale_transfers("BTC", large_txn_data)
        
        # Assertions - no events should be generated
        assert len(events) == 0
    
    @pytest.mark.asyncio
    async def test_generate_ai_interpretation_with_anthropic(self, crypto_tracker):
        """Test AI interpretation generation with Anthropic API"""
        try:
            import anthropic
        except ImportError:
            pytest.skip("anthropic module not installed")
        
        with patch('services.alerts.whale_trackers.crypto_whale.anthropic') as mock_anthropic:
            # Setup mock response
            mock_message = MagicMock()
            mock_message.content = [
                MagicMock(text="Large exchange inflow suggests potential sell pressure as whales move coins to exchanges. Monitor for price impact.")
            ]
            
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_message
            mock_anthropic.return_value = mock_client
            
            # Generate interpretation
            interpretation = await crypto_tracker.generate_ai_interpretation(
                "BTC",
                500.0,
                "inflow",
                75
            )
            
            # Assertions
            assert interpretation is not None
            assert len(interpretation) > 0
            assert "sell pressure" in interpretation.lower() or "exchange" in interpretation.lower()
    
    @pytest.mark.asyncio
    async def test_generate_ai_interpretation_fallback(self):
        """Test AI interpretation fallback when Anthropic API is not available"""
        # Create tracker without Anthropic API key
        tracker = CryptoWhaleTracker(
            glassnode_api_key="test_api_key",
            anthropic_api_key=None
        )
        
        # Generate interpretation for inflow
        interpretation_inflow = await tracker.generate_ai_interpretation(
            "BTC",
            500.0,
            "inflow",
            None
        )
        
        # Generate interpretation for outflow
        interpretation_outflow = await tracker.generate_ai_interpretation(
            "BTC",
            -500.0,
            "outflow",
            None
        )
        
        # Assertions - should use fallback messages
        assert interpretation_inflow == "Potential sell pressure signal"
        assert interpretation_outflow == "Accumulation detected"
    
    @pytest.mark.asyncio
    async def test_caching_behavior(self, crypto_tracker, mock_glassnode_inflow_response):
        """Test that API responses are cached in Redis"""
        with patch('httpx.AsyncClient') as mock_client:
            # Setup mock response
            mock_response = MagicMock()
            mock_response.json.return_value = mock_glassnode_inflow_response
            mock_response.raise_for_status = MagicMock()
            
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )
            
            # First fetch - should call API and cache
            result1 = await crypto_tracker.fetch_exchange_inflow("BTC")
            
            # Verify Redis setex was called
            crypto_tracker.redis_client.setex.assert_called_once()
            
            # Verify data is in in-memory cache
            cache_key = "inflow_BTC"
            assert cache_key in crypto_tracker._cache
    
    @pytest.mark.asyncio
    async def test_poll_crypto_whale_activity_integration(
        self,
        crypto_tracker,
        mock_glassnode_inflow_response,
        mock_glassnode_outflow_response,
        mock_glassnode_large_txn_response
    ):
        """
        Integration test: Poll crypto whale activity with mocked Glassnode API.
        
        This test simulates the full polling flow:
        1. Fetch inflow, outflow, and large transaction data
        2. Detect netflow anomalies
        3. Detect whale transfers
        4. Return all events
        """
        with patch('httpx.AsyncClient') as mock_client:
            # Setup mock responses for all three endpoints
            def mock_get(url, **kwargs):
                mock_response = MagicMock()
                mock_response.raise_for_status = MagicMock()
                
                if "transfers_volume_to_exchanges_sum" in url:
                    mock_response.json.return_value = mock_glassnode_inflow_response
                elif "transfers_volume_from_exchanges_sum" in url:
                    mock_response.json.return_value = mock_glassnode_outflow_response
                elif "count_above_value_usd_sum" in url:
                    mock_response.json.return_value = mock_glassnode_large_txn_response
                
                return mock_response
            
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=mock_get
            )
            
            # Mock AI interpretation
            with patch.object(
                crypto_tracker,
                'generate_ai_interpretation',
                return_value="Potential sell pressure signal"
            ):
                # Poll whale activity
                events = await crypto_tracker.poll_crypto_whale_activity(["BTC"])
            
            # Assertions
            assert len(events) >= 1  # Should have at least netflow event
            
            # Check netflow event
            netflow_events = [e for e in events if e.raw_data.get("detection_type") == "exchange_netflow"]
            assert len(netflow_events) == 1
            assert netflow_events[0].severity == AnomalySeverity.CRITICAL
            
            # Check whale transfer event
            whale_events = [e for e in events if e.raw_data.get("detection_type") == "whale_transfers"]
            assert len(whale_events) == 1
            assert whale_events[0].severity == AnomalySeverity.MEDIUM  # 75 txns is between 50-100 threshold
    
    @pytest.mark.asyncio
    async def test_poll_multiple_assets(
        self,
        crypto_tracker,
        mock_glassnode_inflow_response,
        mock_glassnode_outflow_response,
        mock_glassnode_large_txn_response
    ):
        """Test polling multiple assets (BTC and ETH)"""
        with patch('httpx.AsyncClient') as mock_client:
            # Setup mock responses
            def mock_get(url, **kwargs):
                mock_response = MagicMock()
                mock_response.raise_for_status = MagicMock()
                
                if "transfers_volume_to_exchanges_sum" in url:
                    mock_response.json.return_value = mock_glassnode_inflow_response
                elif "transfers_volume_from_exchanges_sum" in url:
                    mock_response.json.return_value = mock_glassnode_outflow_response
                elif "count_above_value_usd_sum" in url:
                    mock_response.json.return_value = mock_glassnode_large_txn_response
                
                return mock_response
            
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=mock_get
            )
            
            # Mock AI interpretation
            with patch.object(
                crypto_tracker,
                'generate_ai_interpretation',
                return_value="Whale activity detected"
            ):
                # Poll both BTC and ETH
                events = await crypto_tracker.poll_crypto_whale_activity(["BTC", "ETH"])
            
            # Assertions - should have events for both assets
            btc_events = [e for e in events if "BTC" in e.instrument]
            eth_events = [e for e in events if "ETH" in e.instrument]
            
            assert len(btc_events) >= 1
            assert len(eth_events) >= 1
    
    def test_initialization_without_api_keys(self):
        """Test tracker initialization without API keys"""
        tracker = CryptoWhaleTracker()
        
        # Should initialize but log warnings
        assert tracker.glassnode_api_key is None or tracker.glassnode_api_key == ""
        assert tracker.anthropic_api_key is None or tracker.anthropic_api_key == ""
    
    @pytest.mark.asyncio
    async def test_api_error_handling(self, crypto_tracker):
        """Test graceful handling of API errors"""
        with patch('httpx.AsyncClient') as mock_client:
            # Setup mock to raise HTTP error
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=Exception("API Error")
            )
            
            # Fetch should return None on error
            result = await crypto_tracker.fetch_exchange_inflow("BTC")
            
            assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
