"""
Integration Tests for US Equity Whale Tracker

Tests the dark pool print fetcher, options sweep fetcher, event generation,
and threshold validation logic.

Requirements: 12.1
"""

import pytest
import asyncio
from datetime import datetime, time
from unittest.mock import AsyncMock, patch, MagicMock
from typing import List

from services.alerts.whale_trackers.us_equity_whale import USEquityWhaleTracker
from shared.database.models import AnomalyEvent, AnomalyType, AnomalySeverity


class TestUSEquityWhaleTracker:
    """Test suite for US Equity Whale Tracker"""
    
    @pytest.fixture
    def tracker(self):
        """Create a tracker instance for testing"""
        return USEquityWhaleTracker(
            unusual_whales_api_key="test_uw_key",
            polygon_api_key="test_polygon_key",
            timeout_seconds=10
        )
    
    @pytest.fixture
    def mock_dark_pool_trade(self):
        """Mock dark pool trade data"""
        return {
            "ticker": "AAPL",
            "size": 100000,
            "price": 175.50,
            "timestamp": "2024-01-15T14:30:00Z",
            "venue": "DARK_POOL_X"
        }
    
    @pytest.fixture
    def mock_options_sweep(self):
        """Mock options sweep data"""
        return {
            "ticker": "TSLA",
            "contracts": 5000,
            "premium": 2500000,  # $2.5M
            "strike": 250.00,
            "expiry": "2024-02-16",
            "type": "CALL",
            "sentiment": "BULLISH",
            "timestamp": "2024-01-15T14:30:00Z"
        }
    
    # Test 1: Unusual Whales Dark Pool Fetcher
    @pytest.mark.asyncio
    async def test_fetch_unusual_whales_dark_pool_success(self, tracker):
        """Test successful Unusual Whales dark pool fetching"""
        mock_response_data = {
            "data": [
                {"ticker": "AAPL", "size": 100000, "price": 175.50},
                {"ticker": "MSFT", "size": 50000, "price": 380.00}
            ]
        }
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_response_data
            mock_response.raise_for_status = MagicMock()
            
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )
            
            trades = await tracker.fetch_unusual_whales_dark_pool()
            
            assert len(trades) == 2
            assert trades[0]["ticker"] == "AAPL"
            assert trades[1]["ticker"] == "MSFT"
    
    @pytest.mark.asyncio
    async def test_fetch_unusual_whales_dark_pool_http_error(self, tracker):
        """Test Unusual Whales dark pool fetching with HTTP error"""
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=Exception("Connection error")
            )
            
            trades = await tracker.fetch_unusual_whales_dark_pool()
            
            assert trades == []
    
    # Test 2: Unusual Whales Options Flow Fetcher
    @pytest.mark.asyncio
    async def test_fetch_unusual_whales_options_flow_success(self, tracker):
        """Test successful Unusual Whales options flow fetching"""
        mock_response_data = {
            "data": [
                {"ticker": "TSLA", "contracts": 5000, "premium": 2500000},
                {"ticker": "NVDA", "contracts": 3000, "premium": 1800000}
            ]
        }
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_response_data
            mock_response.raise_for_status = MagicMock()
            
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )
            
            sweeps = await tracker.fetch_unusual_whales_options_flow()
            
            assert len(sweeps) == 2
            assert sweeps[0]["ticker"] == "TSLA"
            assert sweeps[1]["ticker"] == "NVDA"
    
    # Test 3: Polygon.io Block Trades Fetcher
    @pytest.mark.asyncio
    async def test_fetch_polygon_block_trades_success(self, tracker):
        """Test successful Polygon.io block trades fetching"""
        mock_response_data = {
            "results": [
                {"T": "AAPL", "s": 100000, "p": 175.50},
                {"T": "GOOGL", "s": 20000, "p": 140.00}
            ]
        }
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_response_data
            mock_response.raise_for_status = MagicMock()
            
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )
            
            trades = await tracker.fetch_polygon_block_trades()
            
            assert len(trades) == 2
            assert trades[0]["T"] == "AAPL"
            assert trades[1]["T"] == "GOOGL"
    
    # Test 4: Trade Value Calculation
    def test_calculate_trade_value_usd(self, tracker):
        """Test trade value calculation in USD"""
        # 100,000 shares @ $175.50 = $17,550,000
        value_usd = tracker._calculate_trade_value_usd(100000, 175.50)
        assert abs(value_usd - 17_550_000) < 0.01
        
        # 50,000 shares @ $380.00 = $19,000,000
        value_usd = tracker._calculate_trade_value_usd(50000, 380.00)
        assert abs(value_usd - 19_000_000) < 0.01
    
    # Test 5: Dark Pool Event Generation - Qualifying Trade
    def test_generate_dark_pool_event_qualifying(self, tracker, mock_dark_pool_trade):
        """Test event generation for qualifying dark pool print (>= $10M)"""
        event = tracker._generate_dark_pool_event(mock_dark_pool_trade, source="unusual_whales")
        
        assert event is not None
        assert event.instrument == "AAPL"
        assert event.asset_class == "us_equity"
        assert event.exchange == "DARK_POOL_X"
        assert event.anomaly_type == AnomalyType.WHALE_MOVEMENT
        assert event.severity in [AnomalySeverity.MEDIUM, AnomalySeverity.HIGH, AnomalySeverity.CRITICAL]
        assert event.price == 175.50
        assert event.volume == 100000
        assert "AAPL" in event.description
        assert "100,000 shares" in event.description
        assert "$175.50" in event.description
        
        # Check raw data
        assert event.raw_data["trade_type"] == "dark_pool"
        assert event.raw_data["value_usd"] >= 10_000_000
    
    # Test 6: Dark Pool Event Generation - Below Threshold
    def test_generate_dark_pool_event_below_threshold(self, tracker):
        """Test that dark pool trades below threshold don't generate events"""
        small_trade = {
            "ticker": "SMALLCAP",
            "size": 10000,
            "price": 50.00,
            "timestamp": "2024-01-15T14:30:00Z",
            "venue": "DARK_POOL"
        }
        
        event = tracker._generate_dark_pool_event(small_trade, source="unusual_whales")
        
        # Trade value = 10,000 * $50 = $500,000 (below $10M threshold)
        assert event is None
    
    # Test 7: Dark Pool Event Generation - Deduplication
    def test_generate_dark_pool_event_deduplication(self, tracker, mock_dark_pool_trade):
        """Test that duplicate dark pool trades are not generated twice"""
        # First call should generate event
        event1 = tracker._generate_dark_pool_event(mock_dark_pool_trade, source="unusual_whales")
        assert event1 is not None
        
        # Second call with same trade should return None (deduplicated)
        event2 = tracker._generate_dark_pool_event(mock_dark_pool_trade, source="unusual_whales")
        assert event2 is None
    
    # Test 8: Options Sweep Event Generation - Qualifying Sweep
    def test_generate_options_sweep_event_qualifying(self, tracker, mock_options_sweep):
        """Test event generation for qualifying options sweep (>= $1M)"""
        event = tracker._generate_options_sweep_event(mock_options_sweep)
        
        assert event is not None
        assert event.instrument == "TSLA"
        assert event.asset_class == "us_equity"
        assert event.exchange == "OPTIONS"
        assert event.anomaly_type == AnomalyType.OPTIONS_UNUSUAL
        assert event.severity in [AnomalySeverity.MEDIUM, AnomalySeverity.HIGH, AnomalySeverity.CRITICAL]
        assert event.price == 250.00
        assert event.volume == 5000
        assert "TSLA" in event.description
        assert "5,000 CALL contracts" in event.description
        assert "$250.00 strike" in event.description
        assert "BULLISH" in event.description
        
        # Check raw data
        assert event.raw_data["trade_type"] == "options_sweep"
        assert event.raw_data["premium"] >= 1_000_000
    
    # Test 9: Options Sweep Event Generation - Below Threshold
    def test_generate_options_sweep_event_below_threshold(self, tracker):
        """Test that options sweeps below threshold don't generate events"""
        small_sweep = {
            "ticker": "SMALLCAP",
            "contracts": 100,
            "premium": 50000,  # $50k (below $1M threshold)
            "strike": 100.00,
            "expiry": "2024-02-16",
            "type": "PUT",
            "sentiment": "BEARISH",
            "timestamp": "2024-01-15T14:30:00Z"
        }
        
        event = tracker._generate_options_sweep_event(small_sweep)
        
        assert event is None
    
    # Test 10: Options Sweep Event Generation - Deduplication
    def test_generate_options_sweep_event_deduplication(self, tracker, mock_options_sweep):
        """Test that duplicate options sweeps are not generated twice"""
        # First call should generate event
        event1 = tracker._generate_options_sweep_event(mock_options_sweep)
        assert event1 is not None
        
        # Second call with same sweep should return None (deduplicated)
        event2 = tracker._generate_options_sweep_event(mock_options_sweep)
        assert event2 is None
    
    # Test 11: Market Hours Check
    def test_is_market_hours(self, tracker):
        """Test market hours detection"""
        # Monday 10:00 AM - should be market hours
        monday_10am = datetime(2024, 1, 15, 10, 0, 0)  # Monday
        assert tracker.is_market_hours(monday_10am) is True
        
        # Monday 3:00 PM - should be market hours
        monday_3pm = datetime(2024, 1, 15, 15, 0, 0)
        assert tracker.is_market_hours(monday_3pm) is True
        
        # Monday 9:00 AM - before market open
        monday_9am = datetime(2024, 1, 15, 9, 0, 0)
        assert tracker.is_market_hours(monday_9am) is False
        
        # Monday 5:00 PM - after market close
        monday_5pm = datetime(2024, 1, 15, 17, 0, 0)
        assert tracker.is_market_hours(monday_5pm) is False
        
        # Saturday - not a trading day
        saturday = datetime(2024, 1, 13, 10, 0, 0)  # Saturday
        assert tracker.is_market_hours(saturday) is False
    
    # Test 12: Integration Test - Mock Unusual Whales API and Verify Event
    @pytest.mark.asyncio
    async def test_poll_dark_pool_prints_integration(self, tracker, mock_dark_pool_trade):
        """Integration test: Mock Unusual Whales API, verify event generated for qualifying trade"""
        mock_response_data = {"data": [mock_dark_pool_trade]}
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_response_data
            mock_response.raise_for_status = MagicMock()
            
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )
            
            events = await tracker.poll_dark_pool_prints()
            
            # Should generate 1 event for the qualifying trade
            assert len(events) == 1
            
            event = events[0]
            assert event.instrument == "AAPL"
            assert event.anomaly_type == AnomalyType.WHALE_MOVEMENT
            assert event.exchange == "DARK_POOL_X"
            assert "100,000 shares" in event.description
    
    # Test 13: Integration Test - Multiple Trades, Mixed Thresholds
    @pytest.mark.asyncio
    async def test_poll_dark_pool_prints_mixed_thresholds(self, tracker):
        """Integration test: Multiple trades with some above and below threshold"""
        mock_trades = [
            # Qualifying trade ($17.55M)
            {"ticker": "AAPL", "size": 100000, "price": 175.50, 
             "timestamp": "2024-01-15T14:30:00Z", "venue": "DARK_POOL_X"},
            # Below threshold ($500k)
            {"ticker": "SMALLCAP", "size": 10000, "price": 50.00,
             "timestamp": "2024-01-15T14:31:00Z", "venue": "DARK_POOL_Y"},
            # Qualifying trade ($19M)
            {"ticker": "MSFT", "size": 50000, "price": 380.00,
             "timestamp": "2024-01-15T14:32:00Z", "venue": "DARK_POOL_Z"}
        ]
        
        mock_response_data = {"data": mock_trades}
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_response_data
            mock_response.raise_for_status = MagicMock()
            
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )
            
            events = await tracker.poll_dark_pool_prints()
            
            # Should generate 2 events (only for qualifying trades)
            assert len(events) == 2
            
            tickers = [e.instrument for e in events]
            assert "AAPL" in tickers
            assert "MSFT" in tickers
            assert "SMALLCAP" not in tickers
    
    # Test 14: Integration Test - Options Sweeps
    @pytest.mark.asyncio
    async def test_poll_options_sweeps_integration(self, tracker, mock_options_sweep):
        """Integration test: Mock Unusual Whales options API, verify event generated"""
        mock_response_data = {"data": [mock_options_sweep]}
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_response_data
            mock_response.raise_for_status = MagicMock()
            
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )
            
            events = await tracker.poll_options_sweeps()
            
            # Should generate 1 event for the qualifying sweep
            assert len(events) == 1
            
            event = events[0]
            assert event.instrument == "TSLA"
            assert event.anomaly_type == AnomalyType.OPTIONS_UNUSUAL
            assert event.exchange == "OPTIONS"
            assert "5,000 CALL contracts" in event.description
    
    # Test 15: Severity Levels Based on Trade Size
    def test_severity_levels_by_trade_size(self):
        """Test that severity levels are assigned correctly based on trade size"""
        # Create a fresh tracker for this test to avoid deduplication issues
        tracker = USEquityWhaleTracker(unusual_whales_api_key="test_key")
        
        # Medium severity: $10M-$50M
        # 100,000 shares @ $150 = $15M
        medium_trade = {
            "ticker": "TEST1",
            "size": 100000,
            "price": 150.00,
            "timestamp": "2024-01-15T14:30:00Z",
            "venue": "DARK_POOL"
        }
        event = tracker._generate_dark_pool_event(medium_trade, source="unusual_whales")
        assert event is not None
        assert event.severity == AnomalySeverity.MEDIUM
        
        # High severity: $50M-$100M
        # 200,000 shares @ $300 = $60M
        high_trade = {
            "ticker": "TEST2",
            "size": 200000,
            "price": 300.00,
            "timestamp": "2024-01-15T14:31:00Z",
            "venue": "DARK_POOL"
        }
        event = tracker._generate_dark_pool_event(high_trade, source="unusual_whales")
        assert event is not None
        assert event.severity == AnomalySeverity.HIGH
        
        # Critical severity: >= $100M
        # 500,000 shares @ $250 = $125M
        critical_trade = {
            "ticker": "TEST3",
            "size": 500000,
            "price": 250.00,
            "timestamp": "2024-01-15T14:32:00Z",
            "venue": "DARK_POOL"
        }
        event = tracker._generate_dark_pool_event(critical_trade, source="unusual_whales")
        assert event is not None
        assert event.severity == AnomalySeverity.CRITICAL
    
    # Test 16: Options Severity Levels
    def test_options_severity_levels(self):
        """Test that severity levels are assigned correctly for options sweeps"""
        tracker = USEquityWhaleTracker(unusual_whales_api_key="test_key")
        
        # Medium severity: $1M-$5M
        medium_sweep = {
            "ticker": "TEST1",
            "contracts": 2000,
            "premium": 2_000_000,  # $2M
            "strike": 100.00,
            "expiry": "2024-02-16",
            "type": "CALL",
            "sentiment": "BULLISH",
            "timestamp": "2024-01-15T14:30:00Z"
        }
        event = tracker._generate_options_sweep_event(medium_sweep)
        assert event is not None
        assert event.severity == AnomalySeverity.MEDIUM
        
        # High severity: $5M-$10M
        high_sweep = {
            "ticker": "TEST2",
            "contracts": 5000,
            "premium": 7_000_000,  # $7M
            "strike": 150.00,
            "expiry": "2024-02-16",
            "type": "PUT",
            "sentiment": "BEARISH",
            "timestamp": "2024-01-15T14:31:00Z"
        }
        event = tracker._generate_options_sweep_event(high_sweep)
        assert event is not None
        assert event.severity == AnomalySeverity.HIGH
        
        # Critical severity: >= $10M
        critical_sweep = {
            "ticker": "TEST3",
            "contracts": 10000,
            "premium": 15_000_000,  # $15M
            "strike": 200.00,
            "expiry": "2024-02-16",
            "type": "CALL",
            "sentiment": "BULLISH",
            "timestamp": "2024-01-15T14:32:00Z"
        }
        event = tracker._generate_options_sweep_event(critical_sweep)
        assert event is not None
        assert event.severity == AnomalySeverity.CRITICAL
    
    # Test 17: No API Keys Configured
    def test_no_api_keys_configured(self):
        """Test tracker behavior when no API keys are configured"""
        tracker = USEquityWhaleTracker()
        
        assert tracker.use_unusual_whales is False
        assert tracker.use_polygon is False
    
    # Test 18: Polygon.io Fallback
    @pytest.mark.asyncio
    async def test_polygon_fallback(self):
        """Test that Polygon.io is used as fallback when Unusual Whales is not available"""
        # Create tracker with only Polygon.io key
        tracker = USEquityWhaleTracker(polygon_api_key="test_polygon_key")
        
        assert tracker.use_unusual_whales is False
        assert tracker.use_polygon is True
        
        mock_trades = [
            {"T": "AAPL", "s": 100000, "p": 175.50, "t": "2024-01-15T14:30:00Z"}
        ]
        
        mock_response_data = {"results": mock_trades}
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_response_data
            mock_response.raise_for_status = MagicMock()
            
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )
            
            events = await tracker.poll_dark_pool_prints()
            
            # Should generate 1 event using Polygon.io data
            assert len(events) == 1
            assert events[0].instrument == "AAPL"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
