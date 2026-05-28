"""
Integration Tests for F&O Whale Tracker

Tests the options chain fetcher, OI change detection, IV spike detection,
large premium trade detection, and Redis snapshot storage.

Requirements: 12.1
"""

import pytest
import asyncio
from datetime import datetime, time
from unittest.mock import AsyncMock, patch, MagicMock
from typing import List, Dict, Any

from services.alerts.whale_trackers.fo_whale import FOWhaleTracker
from shared.database.models import AnomalyEvent, AnomalyType, AnomalySeverity


class TestFOWhaleTracker:
    """Test suite for F&O Whale Tracker"""
    
    @pytest.fixture
    def tracker(self):
        """Create a tracker instance for testing"""
        return FOWhaleTracker(
            angel_one_api_key="test_api_key",
            angel_one_api_base_url="https://test-angel.com",
            redis_client=None,  # Use in-memory cache for tests
            timeout_seconds=10
        )
    
    @pytest.fixture
    def mock_options_chain(self):
        """Mock options chain data from Angel One"""
        return {
            "strikes": [
                {
                    "strike": 24000,
                    "CE": {
                        "lastPrice": 150.50,
                        "openInterest": 75000,  # 75,000 contracts = 1,500 lots (50 lot size)
                        "impliedVolatility": 18.5,
                        "volume": 25000
                    },
                    "PE": {
                        "lastPrice": 120.25,
                        "openInterest": 60000,  # 60,000 contracts = 1,200 lots
                        "impliedVolatility": 17.2,
                        "volume": 18000
                    }
                },
                {
                    "strike": 24500,
                    "CE": {
                        "lastPrice": 95.75,
                        "openInterest": 120000,  # 120,000 contracts = 2,400 lots
                        "impliedVolatility": 19.8,
                        "volume": 45000
                    },
                    "PE": {
                        "lastPrice": 180.00,
                        "openInterest": 90000,  # 90,000 contracts = 1,800 lots
                        "impliedVolatility": 20.5,
                        "volume": 30000
                    }
                }
            ]
        }
    
    @pytest.fixture
    def mock_options_chain_with_oi_change(self):
        """Mock options chain with significant OI change (1,500 lot increase)"""
        return {
            "strikes": [
                {
                    "strike": 24000,
                    "CE": {
                        "lastPrice": 150.50,
                        "openInterest": 150000,  # Increased from 75,000 to 150,000 = 1,500 lot increase
                        "impliedVolatility": 18.5,
                        "volume": 25000
                    },
                    "PE": {
                        "lastPrice": 120.25,
                        "openInterest": 60000,
                        "impliedVolatility": 17.2,
                        "volume": 18000
                    }
                }
            ]
        }
    
    @pytest.fixture
    def mock_options_chain_with_iv_spike(self):
        """Mock options chain with significant IV spike (25% increase)"""
        return {
            "strikes": [
                {
                    "strike": 24000,
                    "CE": {
                        "lastPrice": 150.50,
                        "openInterest": 75000,
                        "impliedVolatility": 23.125,  # Increased from 18.5 to 23.125 = 25% spike
                        "volume": 25000
                    },
                    "PE": {
                        "lastPrice": 120.25,
                        "openInterest": 60000,
                        "impliedVolatility": 17.2,
                        "volume": 18000
                    }
                }
            ]
        }
    
    # Test 1: Options Chain Fetcher
    @pytest.mark.asyncio
    async def test_fetch_options_chain_success(self, tracker, mock_options_chain):
        """Test successful options chain fetching"""
        mock_response_data = {
            "status": True,
            "data": mock_options_chain
        }
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_response_data
            mock_response.raise_for_status = MagicMock()
            
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )
            
            chain = await tracker.fetch_options_chain("NIFTY", "2024-01-25")
            
            assert chain is not None
            assert "strikes" in chain
            assert len(chain["strikes"]) == 2
            assert chain["strikes"][0]["strike"] == 24000
    
    @pytest.mark.asyncio
    async def test_fetch_options_chain_http_error(self, tracker):
        """Test options chain fetching with HTTP error"""
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=Exception("Connection error")
            )
            
            chain = await tracker.fetch_options_chain("NIFTY", "2024-01-25")
            
            assert chain is None
    
    # Test 2: Lot Size Retrieval
    def test_get_lot_size(self, tracker):
        """Test lot size retrieval for various symbols"""
        assert tracker._get_lot_size("NIFTY") == 50
        assert tracker._get_lot_size("BANKNIFTY") == 15
        assert tracker._get_lot_size("FINNIFTY") == 40
        assert tracker._get_lot_size("UNKNOWN") == 50  # Default
    
    # Test 3: Premium Calculation
    def test_calculate_premium_cr(self, tracker):
        """Test premium calculation in Crores"""
        # 100 lots @ Rs 150 with lot size 50 = 100 * 150 * 50 = Rs 7,50,000 = Rs 0.075 Cr
        premium_cr = tracker._calculate_premium_cr(150.0, 100, 50)
        assert abs(premium_cr - 0.075) < 0.001
        
        # 500 lots @ Rs 200 with lot size 15 = 500 * 200 * 15 = Rs 15,00,000 = Rs 0.15 Cr
        premium_cr = tracker._calculate_premium_cr(200.0, 500, 15)
        assert abs(premium_cr - 0.15) < 0.001
        
        # 1000 lots @ Rs 100 with lot size 50 = 1000 * 100 * 50 = Rs 50,00,000 = Rs 0.5 Cr
        premium_cr = tracker._calculate_premium_cr(100.0, 1000, 50)
        assert abs(premium_cr - 0.5) < 0.001
    
    # Test 4: OI Change Event Generation - Qualifying Change
    def test_generate_oi_change_event_qualifying(self, tracker):
        """Test event generation for qualifying OI change (>= 1,000 lots)"""
        event = tracker._generate_oi_change_event(
            symbol="NIFTY",
            strike=24000,
            option_type="CE",
            expiry="2024-01-25",
            current_oi=150000,
            previous_oi=75000,
            oi_change_lots=1500,  # 1,500 lots increase
            price=150.50,
            lot_size=50
        )
        
        assert event is not None
        assert event.instrument == "NIFTY"
        assert event.asset_class == "fo"
        assert event.exchange == "NFO"
        assert event.anomaly_type == AnomalyType.OPTIONS_UNUSUAL
        assert event.severity in [AnomalySeverity.MEDIUM, AnomalySeverity.HIGH]
        assert event.price == 150.50
        assert "buildup" in event.description.lower()
        assert "1,500 lots" in event.description
        
        # Check raw data
        assert event.raw_data["detection_type"] == "oi_change"
        assert event.raw_data["oi_change_lots"] == 1500
        assert event.raw_data["direction"] == "buildup"
    
    # Test 5: OI Change Event Generation - Below Threshold
    def test_generate_oi_change_event_below_threshold(self, tracker):
        """Test that OI changes below threshold don't generate events"""
        event = tracker._generate_oi_change_event(
            symbol="NIFTY",
            strike=24000,
            option_type="CE",
            expiry="2024-01-25",
            current_oi=75500,
            previous_oi=75000,
            oi_change_lots=10,  # Only 10 lots (below 1,000 threshold)
            price=150.50,
            lot_size=50
        )
        
        assert event is None
    
    # Test 6: OI Change Event Generation - Unwinding
    def test_generate_oi_change_event_unwinding(self, tracker):
        """Test event generation for OI unwinding (negative change)"""
        event = tracker._generate_oi_change_event(
            symbol="BANKNIFTY",
            strike=48000,
            option_type="PE",
            expiry="2024-01-25",
            current_oi=30000,
            previous_oi=60000,
            oi_change_lots=-2000,  # 2,000 lots decrease
            price=200.00,
            lot_size=15
        )
        
        assert event is not None
        assert "unwinding" in event.description.lower()
        assert event.raw_data["direction"] == "unwinding"
        assert event.raw_data["oi_change_lots"] == -2000
    
    # Test 7: IV Spike Event Generation - Qualifying Spike
    def test_generate_iv_spike_event_qualifying(self, tracker):
        """Test event generation for qualifying IV spike (>= 20%)"""
        event = tracker._generate_iv_spike_event(
            symbol="NIFTY",
            strike=24000,
            option_type="CE",
            expiry="2024-01-25",
            current_iv=23.125,
            previous_iv=18.5,
            iv_change_pct=25.0,  # 25% spike
            price=150.50,
            oi=75000
        )
        
        assert event is not None
        assert event.instrument == "NIFTY"
        assert event.anomaly_type == AnomalyType.OPTIONS_UNUSUAL
        assert event.severity in [AnomalySeverity.MEDIUM, AnomalySeverity.HIGH]
        assert "spike" in event.description.lower()
        assert "25.0%" in event.description
        
        # Check raw data
        assert event.raw_data["detection_type"] == "iv_spike"
        assert event.raw_data["iv_change_pct"] == 25.0
        assert event.raw_data["direction"] == "spike"
    
    # Test 8: IV Spike Event Generation - Below Threshold
    def test_generate_iv_spike_event_below_threshold(self, tracker):
        """Test that IV changes below threshold don't generate events"""
        event = tracker._generate_iv_spike_event(
            symbol="NIFTY",
            strike=24000,
            option_type="CE",
            expiry="2024-01-25",
            current_iv=19.5,
            previous_iv=18.5,
            iv_change_pct=5.4,  # Only 5.4% (below 20% threshold)
            price=150.50,
            oi=75000
        )
        
        assert event is None
    
    # Test 9: Large Premium Event Generation - Qualifying Trade
    def test_generate_large_premium_event_qualifying(self, tracker):
        """Test event generation for large premium trade (>= Rs 5 Cr)"""
        event = tracker._generate_large_premium_event(
            symbol="NIFTY",
            strike=24000,
            option_type="CE",
            expiry="2024-01-25",
            price=100.0,
            quantity_lots=1000,  # 1,000 lots @ Rs 100 with lot size 50 = Rs 5 Cr
            lot_size=50,
            premium_cr=5.0,
            oi=75000,
            iv=18.5
        )
        
        assert event is not None
        assert event.instrument == "NIFTY"
        assert event.anomaly_type == AnomalyType.WHALE_MOVEMENT
        assert event.severity in [AnomalySeverity.MEDIUM, AnomalySeverity.HIGH]
        assert "5.00 Cr" in event.description
        assert "1,000 lots" in event.description
        
        # Check raw data
        assert event.raw_data["detection_type"] == "large_premium"
        assert event.raw_data["premium_cr"] == 5.0
    
    # Test 10: Large Premium Event Generation - Below Threshold
    def test_generate_large_premium_event_below_threshold(self, tracker):
        """Test that premium trades below threshold don't generate events"""
        event = tracker._generate_large_premium_event(
            symbol="NIFTY",
            strike=24000,
            option_type="CE",
            expiry="2024-01-25",
            price=50.0,
            quantity_lots=100,  # 100 lots @ Rs 50 with lot size 50 = Rs 0.25 Cr
            lot_size=50,
            premium_cr=0.25,
            oi=75000,
            iv=18.5
        )
        
        assert event is None
    
    # Test 11: Severity Levels Based on OI Change Magnitude
    def test_oi_change_severity_levels(self, tracker):
        """Test that severity levels are assigned correctly based on OI change magnitude"""
        # Medium severity: 1,000-2,500 lots
        event = tracker._generate_oi_change_event(
            "NIFTY", 24000, "CE", "2024-01-25",
            current_oi=125000, previous_oi=75000,
            oi_change_lots=1000, price=150.0, lot_size=50
        )
        assert event.severity == AnomalySeverity.MEDIUM
        
        # High severity: 2,500-5,000 lots
        event = tracker._generate_oi_change_event(
            "NIFTY", 24000, "CE", "2024-01-25",
            current_oi=200000, previous_oi=75000,
            oi_change_lots=2500, price=150.0, lot_size=50
        )
        assert event.severity == AnomalySeverity.HIGH
        
        # Critical severity: >= 5,000 lots
        event = tracker._generate_oi_change_event(
            "NIFTY", 24000, "CE", "2024-01-25",
            current_oi=325000, previous_oi=75000,
            oi_change_lots=5000, price=150.0, lot_size=50
        )
        assert event.severity == AnomalySeverity.CRITICAL
    
    # Test 12: Severity Levels Based on IV Spike Magnitude
    def test_iv_spike_severity_levels(self, tracker):
        """Test that severity levels are assigned correctly based on IV spike magnitude"""
        # Medium severity: 20-35%
        event = tracker._generate_iv_spike_event(
            "NIFTY", 24000, "CE", "2024-01-25",
            current_iv=24.0, previous_iv=20.0,
            iv_change_pct=20.0, price=150.0, oi=75000
        )
        assert event.severity == AnomalySeverity.MEDIUM
        
        # High severity: 35-50%
        event = tracker._generate_iv_spike_event(
            "NIFTY", 24000, "CE", "2024-01-25",
            current_iv=27.0, previous_iv=20.0,
            iv_change_pct=35.0, price=150.0, oi=75000
        )
        assert event.severity == AnomalySeverity.HIGH
        
        # Critical severity: >= 50%
        event = tracker._generate_iv_spike_event(
            "NIFTY", 24000, "CE", "2024-01-25",
            current_iv=30.0, previous_iv=20.0,
            iv_change_pct=50.0, price=150.0, oi=75000
        )
        assert event.severity == AnomalySeverity.CRITICAL
    
    # Test 13: Market Hours Check
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
        
        # Monday 4:00 PM - after market close
        monday_4pm = datetime(2024, 1, 15, 16, 0, 0)
        assert tracker.is_market_hours(monday_4pm) is False
        
        # Saturday - not a trading day
        saturday = datetime(2024, 1, 13, 10, 0, 0)  # Saturday
        assert tracker.is_market_hours(saturday) is False
    
    # Test 14: Integration Test - Mock Options Chain with 1,500-lot OI Change
    @pytest.mark.asyncio
    async def test_analyze_options_chain_with_oi_change(
        self, tracker, mock_options_chain, mock_options_chain_with_oi_change
    ):
        """Integration test: Mock options chain with 1,500-lot OI change, verify event generated"""
        # First poll - establish baseline
        with patch.object(tracker, 'fetch_options_chain', return_value=mock_options_chain):
            events = await tracker.analyze_options_chain("NIFTY", "2024-01-25")
            # First poll should not generate OI change events (no previous data)
            oi_events = [e for e in events if e.raw_data.get("detection_type") == "oi_change"]
            assert len(oi_events) == 0
        
        # Second poll - with OI change
        with patch.object(tracker, 'fetch_options_chain', return_value=mock_options_chain_with_oi_change):
            events = await tracker.analyze_options_chain("NIFTY", "2024-01-25")
            # Should generate OI change event for 24000 CE (1,500 lot increase)
            oi_events = [e for e in events if e.raw_data.get("detection_type") == "oi_change"]
            assert len(oi_events) >= 1
            
            # Verify the event details
            event = oi_events[0]
            assert event.instrument == "NIFTY"
            assert event.raw_data["strike"] == 24000
            assert event.raw_data["option_type"] == "CE"
            assert event.raw_data["oi_change_lots"] == 1500
            assert "1,500 lots" in event.description
    
    # Test 15: Integration Test - Mock Options Chain with IV Spike
    @pytest.mark.asyncio
    async def test_analyze_options_chain_with_iv_spike(
        self, tracker, mock_options_chain, mock_options_chain_with_iv_spike
    ):
        """Integration test: Mock options chain with 25% IV spike, verify event generated"""
        # First poll - establish baseline
        with patch.object(tracker, 'fetch_options_chain', return_value=mock_options_chain):
            events = await tracker.analyze_options_chain("NIFTY", "2024-01-25")
            # First poll should not generate IV spike events (no previous data)
            iv_events = [e for e in events if e.raw_data.get("detection_type") == "iv_spike"]
            assert len(iv_events) == 0
        
        # Second poll - with IV spike
        with patch.object(tracker, 'fetch_options_chain', return_value=mock_options_chain_with_iv_spike):
            events = await tracker.analyze_options_chain("NIFTY", "2024-01-25")
            # Should generate IV spike event for 24000 CE (25% spike)
            iv_events = [e for e in events if e.raw_data.get("detection_type") == "iv_spike"]
            assert len(iv_events) >= 1
            
            # Verify the event details
            event = iv_events[0]
            assert event.instrument == "NIFTY"
            assert event.raw_data["strike"] == 24000
            assert event.raw_data["option_type"] == "CE"
            assert abs(event.raw_data["iv_change_pct"] - 25.0) < 0.1
            assert "25" in event.description  # Should mention 25% change
    
    # Test 16: OI and IV Snapshot Storage and Retrieval
    @pytest.mark.asyncio
    async def test_oi_iv_snapshot_storage(self, tracker):
        """Test OI and IV snapshot storage and retrieval (in-memory)"""
        option_key = "NIFTY_24000_CE_2024-01-25"
        
        # Store OI
        await tracker._store_current_oi(option_key, 75000.0)
        
        # Retrieve OI
        oi = await tracker._get_previous_oi(option_key)
        assert oi == 75000.0
        
        # Store IV
        await tracker._store_current_iv(option_key, 18.5)
        
        # Retrieve IV
        iv = await tracker._get_previous_iv(option_key)
        assert iv == 18.5
        
        # Non-existent key should return None
        oi = await tracker._get_previous_oi("NONEXISTENT_KEY")
        assert oi is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
