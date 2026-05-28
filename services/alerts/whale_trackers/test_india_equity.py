"""
Integration Tests for India Equity Whale Tracker

Tests the NSE block deal fetcher, BSE bulk deal fetcher, NSDL FII/DII fetcher,
event generation, and instrument correlation logic.

Requirements: 12.1, 12.3, 12.4
"""

import pytest
import asyncio
from datetime import datetime, time
from unittest.mock import AsyncMock, patch, MagicMock
from typing import List

from services.alerts.whale_trackers.india_equity import IndiaEquityWhaleTracker
from shared.database.models import AnomalyEvent, AnomalyType, AnomalySeverity


class TestIndiaEquityWhaleTracker:
    """Test suite for India Equity Whale Tracker"""
    
    @pytest.fixture
    def tracker(self):
        """Create a tracker instance for testing"""
        return IndiaEquityWhaleTracker(
            nse_api_base_url="https://test-nse.com",
            bse_api_base_url="https://test-bse.com",
            nsdl_api_base_url="https://test-nsdl.com",
            timeout_seconds=10
        )
    
    @pytest.fixture
    def mock_nse_block_deal(self):
        """Mock NSE block deal data"""
        return {
            "symbol": "HDFCBANK",
            "quantity": 500000,
            "price": 1650.50,
            "client_name": "ABC Mutual Fund",
            "deal_type": "BUY",
            "trade_date": "2024-01-15"
        }
    
    @pytest.fixture
    def mock_bse_bulk_deal(self):
        """Mock BSE bulk deal data"""
        return {
            "scrip_code": "RELIANCE",
            "qty": 200000,
            "trade_price": 2450.75,
            "buyer": "XYZ Investment Trust",
            "type": "SELL",
            "date": "2024-01-15"
        }
    
    @pytest.fixture
    def mock_fii_dii_data(self):
        """Mock NSDL FII/DII data"""
        return {
            "date": "2024-01-15",
            "fii_net": 250.50,  # Rs 250.50 Cr net buying
            "dii_net": -150.25,  # Rs 150.25 Cr net selling
            "fii_gross_buy": 1500.00,
            "fii_gross_sell": 1249.50,
            "dii_gross_buy": 800.00,
            "dii_gross_sell": 950.25
        }
    
    # Test 1: NSE Block Deal Fetcher
    @pytest.mark.asyncio
    async def test_fetch_nse_block_deals_success(self, tracker):
        """Test successful NSE block deal fetching"""
        mock_response_data = {
            "data": [
                {"symbol": "HDFCBANK", "quantity": 500000, "price": 1650.50},
                {"symbol": "RELIANCE", "quantity": 300000, "price": 2450.00}
            ]
        }
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_response_data
            mock_response.raise_for_status = MagicMock()
            
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )
            
            deals = await tracker.fetch_nse_block_deals()
            
            assert len(deals) == 2
            assert deals[0]["symbol"] == "HDFCBANK"
            assert deals[1]["symbol"] == "RELIANCE"
    
    @pytest.mark.asyncio
    async def test_fetch_nse_block_deals_http_error(self, tracker):
        """Test NSE block deal fetching with HTTP error"""
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=Exception("Connection error")
            )
            
            deals = await tracker.fetch_nse_block_deals()
            
            assert deals == []
    
    # Test 2: BSE Bulk Deal Fetcher
    @pytest.mark.asyncio
    async def test_fetch_bse_bulk_deals_success(self, tracker):
        """Test successful BSE bulk deal fetching"""
        mock_response_data = [
            {"scrip_code": "RELIANCE", "qty": 200000, "trade_price": 2450.75},
            {"scrip_code": "TCS", "qty": 150000, "trade_price": 3650.00}
        ]
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_response_data
            mock_response.raise_for_status = MagicMock()
            
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )
            
            deals = await tracker.fetch_bse_bulk_deals()
            
            assert len(deals) == 2
            assert deals[0]["scrip_code"] == "RELIANCE"
    
    # Test 3: NSDL FII/DII Fetcher
    @pytest.mark.asyncio
    async def test_fetch_nsdl_fii_dii_success(self, tracker, mock_fii_dii_data):
        """Test successful NSDL FII/DII data fetching"""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_fii_dii_data
            mock_response.raise_for_status = MagicMock()
            
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )
            
            data = await tracker.fetch_nsdl_fii_dii_data()
            
            assert data is not None
            assert data["fii_net"] == 250.50
            assert data["dii_net"] == -150.25
    
    # Test 4: Deal Value Calculation
    def test_calculate_deal_value_cr(self, tracker):
        """Test deal value calculation in Crores"""
        # 500,000 shares @ Rs 1,650.50 = Rs 82,52,50,000 = Rs 82.525 Cr
        value_cr = tracker._calculate_deal_value_cr(500000, 1650.50)
        assert abs(value_cr - 82.525) < 0.001
        
        # 200,000 shares @ Rs 2,450.75 = Rs 49,01,50,000 = Rs 49.015 Cr
        value_cr = tracker._calculate_deal_value_cr(200000, 2450.75)
        assert abs(value_cr - 49.015) < 0.001
    
    # Test 5: Instrument Correlation
    def test_get_affected_instruments(self, tracker):
        """Test instrument correlation mapping"""
        # HDFC Bank should affect BANKNIFTY and NIFTY50
        affected = tracker._get_affected_instruments("HDFCBANK")
        assert "BANKNIFTY" in affected
        assert "NIFTY50" in affected
        
        # TCS should affect NIFTY50 and NIFTYIT
        affected = tracker._get_affected_instruments("TCS")
        assert "NIFTY50" in affected
        assert "NIFTYIT" in affected
        
        # Unknown stock should return empty list
        affected = tracker._get_affected_instruments("UNKNOWN")
        assert affected == []
    
    # Test 6: Block Deal Event Generation - Qualifying Deal
    def test_generate_block_deal_event_qualifying(self, tracker, mock_nse_block_deal):
        """Test event generation for qualifying NSE block deal (>= Rs 10 Cr)"""
        event = tracker._generate_block_deal_event(mock_nse_block_deal, exchange="NSE")
        
        assert event is not None
        assert event.instrument == "HDFCBANK"
        assert event.asset_class == "equity"
        assert event.exchange == "NSE"
        assert event.anomaly_type == AnomalyType.WHALE_MOVEMENT
        assert event.severity in [AnomalySeverity.MEDIUM, AnomalySeverity.HIGH, AnomalySeverity.CRITICAL]
        assert event.price == 1650.50
        assert event.volume == 500000
        assert "BANKNIFTY" in event.affected_instruments
        assert "NIFTY50" in event.affected_instruments
        assert "ABC Mutual Fund" in event.description
        assert "buying" in event.description.lower()
        
        # Check raw data
        assert event.raw_data["deal_type"] == "block_deal"
        assert event.raw_data["value_cr"] > 10.0
    
    # Test 7: Block Deal Event Generation - Below Threshold
    def test_generate_block_deal_event_below_threshold(self, tracker):
        """Test that deals below threshold don't generate events"""
        small_deal = {
            "symbol": "SMALLCAP",
            "quantity": 10000,
            "price": 50.00,
            "client_name": "Small Investor",
            "deal_type": "BUY"
        }
        
        event = tracker._generate_block_deal_event(small_deal, exchange="NSE")
        
        # Deal value = 10,000 * 50 = Rs 5,00,000 = Rs 0.05 Cr (below Rs 10 Cr threshold)
        assert event is None
    
    # Test 8: Block Deal Event Generation - Deduplication
    def test_generate_block_deal_event_deduplication(self, tracker, mock_nse_block_deal):
        """Test that duplicate deals are not generated twice"""
        # First call should generate event
        event1 = tracker._generate_block_deal_event(mock_nse_block_deal, exchange="NSE")
        assert event1 is not None
        
        # Second call with same deal should return None (deduplicated)
        event2 = tracker._generate_block_deal_event(mock_nse_block_deal, exchange="NSE")
        assert event2 is None
    
    # Test 9: FII/DII Event Generation - Qualifying Activity
    def test_generate_fii_dii_event_qualifying(self, tracker, mock_fii_dii_data):
        """Test event generation for qualifying FII/DII activity (>= Rs 100 Cr)"""
        events = tracker._generate_fii_dii_event(mock_fii_dii_data)
        
        # Should generate 2 events: one for FII, one for DII
        assert len(events) == 2
        
        # Check FII event
        fii_event = next(e for e in events if e.raw_data["flow_type"] == "fii")
        assert fii_event.instrument == "NIFTY50"
        assert fii_event.anomaly_type == AnomalyType.INSTITUTIONAL_FLOW
        assert fii_event.severity in [AnomalySeverity.HIGH, AnomalySeverity.CRITICAL]
        assert "FII buying" in fii_event.description
        assert "250.50 Cr" in fii_event.description
        assert "BANKNIFTY" in fii_event.affected_instruments
        
        # Check DII event
        dii_event = next(e for e in events if e.raw_data["flow_type"] == "dii")
        assert dii_event.instrument == "NIFTY50"
        assert dii_event.anomaly_type == AnomalyType.INSTITUTIONAL_FLOW
        assert "DII selling" in dii_event.description
        assert "150.25 Cr" in dii_event.description
    
    # Test 10: FII/DII Event Generation - Below Threshold
    def test_generate_fii_dii_event_below_threshold(self, tracker):
        """Test that FII/DII activity below threshold doesn't generate events"""
        small_activity = {
            "date": "2024-01-15",
            "fii_net": 50.0,  # Rs 50 Cr (below Rs 100 Cr threshold)
            "dii_net": 30.0   # Rs 30 Cr (below Rs 100 Cr threshold)
        }
        
        events = tracker._generate_fii_dii_event(small_activity)
        
        assert len(events) == 0
    
    # Test 11: FII/DII Event Generation - Deduplication
    def test_generate_fii_dii_event_deduplication(self, tracker, mock_fii_dii_data):
        """Test that FII/DII data for same date is not processed twice"""
        # First call should generate events
        events1 = tracker._generate_fii_dii_event(mock_fii_dii_data)
        assert len(events1) == 2
        
        # Second call with same date should return empty (deduplicated)
        events2 = tracker._generate_fii_dii_event(mock_fii_dii_data)
        assert len(events2) == 0
    
    # Test 12: Market Hours Check
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
    
    # Test 13: FII/DII Polling Time Check
    def test_should_poll_fii_dii(self, tracker):
        """Test FII/DII polling time detection"""
        # Monday 5:00 PM - after NSDL publish time
        monday_5pm = datetime(2024, 1, 15, 17, 0, 0)  # Monday
        assert tracker.should_poll_fii_dii(monday_5pm) is True
        
        # Monday 4:00 PM - before NSDL publish time
        monday_4pm = datetime(2024, 1, 15, 16, 0, 0)
        assert tracker.should_poll_fii_dii(monday_4pm) is False
        
        # Saturday - not a trading day
        saturday = datetime(2024, 1, 13, 17, 0, 0)  # Saturday
        assert tracker.should_poll_fii_dii(saturday) is False
    
    # Test 14: Integration Test - Mock NSE API and Verify Event
    @pytest.mark.asyncio
    async def test_poll_nse_block_deals_integration(self, tracker, mock_nse_block_deal):
        """Integration test: Mock NSE API, verify event generated for qualifying deal"""
        mock_response_data = {"data": [mock_nse_block_deal]}
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_response_data
            mock_response.raise_for_status = MagicMock()
            
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )
            
            events = await tracker.poll_nse_block_deals()
            
            # Should generate 1 event for the qualifying deal
            assert len(events) == 1
            
            event = events[0]
            assert event.instrument == "HDFCBANK"
            assert event.anomaly_type == AnomalyType.WHALE_MOVEMENT
            assert event.exchange == "NSE"
            assert "BANKNIFTY" in event.affected_instruments
            assert "ABC Mutual Fund" in event.description
    
    # Test 15: Integration Test - Multiple Deals, Mixed Thresholds
    @pytest.mark.asyncio
    async def test_poll_nse_block_deals_mixed_thresholds(self, tracker):
        """Integration test: Multiple deals with some above and below threshold"""
        mock_deals = [
            # Qualifying deal (Rs 82.525 Cr)
            {"symbol": "HDFCBANK", "quantity": 500000, "price": 1650.50, 
             "client_name": "Big Fund", "deal_type": "BUY"},
            # Below threshold (Rs 0.5 Cr)
            {"symbol": "SMALLCAP", "quantity": 10000, "price": 50.00,
             "client_name": "Small Investor", "deal_type": "BUY"},
            # Qualifying deal (Rs 49.015 Cr)
            {"symbol": "RELIANCE", "quantity": 200000, "price": 2450.75,
             "client_name": "Another Fund", "deal_type": "SELL"}
        ]
        
        mock_response_data = {"data": mock_deals}
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_response_data
            mock_response.raise_for_status = MagicMock()
            
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )
            
            events = await tracker.poll_nse_block_deals()
            
            # Should generate 2 events (only for qualifying deals)
            assert len(events) == 2
            
            symbols = [e.instrument for e in events]
            assert "HDFCBANK" in symbols
            assert "RELIANCE" in symbols
            assert "SMALLCAP" not in symbols
    
    # Test 16: Severity Levels Based on Deal Size
    def test_severity_levels_by_deal_size(self):
        """Test that severity levels are assigned correctly based on deal size"""
        # Create a fresh tracker for this test to avoid deduplication issues
        tracker = IndiaEquityWhaleTracker()
        
        # Medium severity: Rs 10-50 Cr
        # 100,000 shares @ Rs 3,000 = Rs 30,00,00,000 = Rs 30 Cr
        medium_deal = {
            "symbol": "TEST1",
            "quantity": 100000,
            "price": 3000.00,  # Rs 30 Cr
            "client_name": "Fund A",
            "deal_type": "BUY"
        }
        event = tracker._generate_block_deal_event(medium_deal, exchange="NSE")
        assert event is not None
        assert event.severity == AnomalySeverity.MEDIUM
        
        # High severity: Rs 50-100 Cr
        # 300,000 shares @ Rs 2,000 = Rs 60,00,00,000 = Rs 60 Cr
        high_deal = {
            "symbol": "TEST2",
            "quantity": 300000,
            "price": 2000.00,  # Rs 60 Cr
            "client_name": "Fund B",
            "deal_type": "BUY"
        }
        event = tracker._generate_block_deal_event(high_deal, exchange="NSE")
        assert event is not None
        assert event.severity == AnomalySeverity.HIGH
        
        # Critical severity: >= Rs 100 Cr
        # 1,000,000 shares @ Rs 1,500 = Rs 150,00,00,000 = Rs 150 Cr
        critical_deal = {
            "symbol": "TEST3",
            "quantity": 1000000,
            "price": 1500.00,  # Rs 150 Cr
            "client_name": "Fund C",
            "deal_type": "BUY"
        }
        event = tracker._generate_block_deal_event(critical_deal, exchange="NSE")
        assert event is not None
        assert event.severity == AnomalySeverity.CRITICAL


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
