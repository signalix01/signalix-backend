"""
Unit tests for SQL Pre-Filter Layer (without database dependency)

Tests the SQL query building logic without requiring a live database.

Requirements: 9.2
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio
import time

from services.screening.models import ScreeningCriteria
from services.screening.sql_filter import SQLPreFilter


@pytest.fixture
def mock_session():
    """Create mock database session"""
    session = AsyncMock()
    return session


@pytest.fixture
def sql_filter(mock_session):
    """Create SQLPreFilter instance with mock session"""
    return SQLPreFilter(mock_session)


@pytest.fixture
def test_universe():
    """Create test universe of symbols"""
    return [
        "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK",
        "SBIN", "BHARTIARTL", "ITC", "KOTAKBANK", "LT"
    ]


@pytest.mark.asyncio
async def test_filter_builds_correct_query_with_rsi(sql_filter, mock_session, test_universe):
    """
    Test that SQL pre-filter builds correct query with RSI bounds
    
    Validates: Requirement 9.2 - SQL query construction
    """
    # Setup mock result
    mock_result = MagicMock()
    mock_result.fetchall.return_value = [("RELIANCE",), ("TCS",), ("INFY",)]
    mock_session.execute = AsyncMock(return_value=mock_result)
    
    # Create criteria with RSI filter
    criteria = ScreeningCriteria(
        name="RSI Test",
        description="Test RSI filtering",
        asset_class=["equity"],
        min_rsi=30.0,
        max_rsi=70.0
    )
    
    # Execute filter
    result = await sql_filter.filter(criteria, test_universe)
    
    # Verify query was called
    assert mock_session.execute.called, "Session execute should be called"
    
    # Verify result
    assert result == ["RELIANCE", "TCS", "INFY"], "Should return filtered symbols"
    
    # Verify query parameters
    call_args = mock_session.execute.call_args
    query_params = call_args[0][1] if len(call_args[0]) > 1 else {}
    
    assert "min_rsi" in query_params, "Query should include min_rsi parameter"
    assert "max_rsi" in query_params, "Query should include max_rsi parameter"
    assert query_params["min_rsi"] == 30.0, "min_rsi should be 30.0"
    assert query_params["max_rsi"] == 70.0, "max_rsi should be 70.0"
    
    print("✓ RSI query building test passed")


@pytest.mark.asyncio
async def test_filter_builds_query_with_multiple_conditions(sql_filter, mock_session, test_universe):
    """
    Test that SQL pre-filter builds correct query with multiple conditions
    
    Validates: Requirement 9.2 - Complex query construction
    """
    # Setup mock result
    mock_result = MagicMock()
    mock_result.fetchall.return_value = [("RELIANCE",)]
    mock_session.execute = AsyncMock(return_value=mock_result)
    
    # Create criteria with multiple filters
    criteria = ScreeningCriteria(
        name="Complex Test",
        description="Test multiple filters",
        asset_class=["equity"],
        min_rsi=30.0,
        max_rsi=70.0,
        min_adx=20.0,
        min_volume_ratio=1.5,
        require_above_ema=200
    )
    
    # Execute filter
    result = await sql_filter.filter(criteria, test_universe)
    
    # Verify query was called
    assert mock_session.execute.called, "Session execute should be called"
    
    # Verify query parameters
    call_args = mock_session.execute.call_args
    query_params = call_args[0][1] if len(call_args[0]) > 1 else {}
    
    assert "min_rsi" in query_params, "Query should include min_rsi"
    assert "max_rsi" in query_params, "Query should include max_rsi"
    assert "min_adx" in query_params, "Query should include min_adx"
    assert "min_volume_ratio" in query_params, "Query should include min_volume_ratio"
    
    print("✓ Multiple conditions query building test passed")


@pytest.mark.asyncio
async def test_filter_handles_empty_universe(sql_filter, mock_session):
    """
    Test that SQL pre-filter handles empty universe correctly
    
    Validates: Edge case handling
    """
    criteria = ScreeningCriteria(
        name="Empty Test",
        description="Test empty universe",
        asset_class=["equity"],
        min_rsi=30.0
    )
    
    # Execute filter with empty universe
    result = await sql_filter.filter(criteria, [])
    
    # Verify no query was executed
    assert not mock_session.execute.called, "Should not execute query for empty universe"
    
    # Verify empty result
    assert result == [], "Should return empty list for empty universe"
    
    print("✓ Empty universe handling test passed")


@pytest.mark.asyncio
async def test_filter_respects_200_symbol_limit(sql_filter, mock_session, test_universe):
    """
    Test that SQL pre-filter limits results to 200 symbols
    
    Validates: Requirement 9.2 - Return up to 200 symbols
    """
    # Setup mock result with many symbols
    mock_symbols = [(f"SYMBOL{i:03d}",) for i in range(250)]
    mock_result = MagicMock()
    mock_result.fetchall.return_value = mock_symbols
    mock_session.execute = AsyncMock(return_value=mock_result)
    
    criteria = ScreeningCriteria(
        name="Limit Test",
        description="Test 200 symbol limit",
        asset_class=["equity"],
        min_rsi=30.0
    )
    
    # Execute filter
    result = await sql_filter.filter(criteria, test_universe)
    
    # Verify query includes LIMIT 200
    call_args = mock_session.execute.call_args
    query_text = str(call_args[0][0])
    
    assert "LIMIT 200" in query_text, "Query should include LIMIT 200"
    
    print("✓ 200 symbol limit test passed")


@pytest.mark.asyncio
async def test_filter_with_options_criteria(sql_filter, mock_session, test_universe):
    """
    Test SQL pre-filter with options-specific criteria
    
    Validates: Requirement 9.2 - Options filters (IV rank, PCR)
    """
    # Setup mock result
    mock_result = MagicMock()
    mock_result.fetchall.return_value = [("BANKNIFTY",)]
    mock_session.execute = AsyncMock(return_value=mock_result)
    
    # Create criteria with options filters
    criteria = ScreeningCriteria(
        name="Options Test",
        description="Test options filtering",
        asset_class=["fo"],
        min_iv_rank=60.0,
        max_iv_rank=90.0,
        min_pcr=0.8,
        max_pcr=1.4
    )
    
    # Execute filter
    result = await sql_filter.filter(criteria, test_universe)
    
    # Verify query parameters
    call_args = mock_session.execute.call_args
    query_params = call_args[0][1] if len(call_args[0]) > 1 else {}
    
    assert "min_iv_rank" in query_params, "Query should include min_iv_rank"
    assert "max_iv_rank" in query_params, "Query should include max_iv_rank"
    assert "min_pcr" in query_params, "Query should include min_pcr"
    assert "max_pcr" in query_params, "Query should include max_pcr"
    
    print("✓ Options criteria test passed")


@pytest.mark.asyncio
async def test_filter_with_fundamental_criteria(sql_filter, mock_session, test_universe):
    """
    Test SQL pre-filter with fundamental criteria
    
    Validates: Requirement 9.2 - Fundamental filters
    """
    # Setup mock result
    mock_result = MagicMock()
    mock_result.fetchall.return_value = [("RELIANCE",), ("TCS",)]
    mock_session.execute = AsyncMock(return_value=mock_result)
    
    # Create criteria with fundamental filters
    criteria = ScreeningCriteria(
        name="Fundamental Test",
        description="Test fundamental filtering",
        asset_class=["equity"],
        min_market_cap_cr=1000.0,
        max_pe_ratio=30.0,
        min_roe_pct=15.0,
        min_revenue_growth_pct=10.0,
        min_promoter_holding_pct=50.0
    )
    
    # Execute filter
    result = await sql_filter.filter(criteria, test_universe)
    
    # Verify query parameters
    call_args = mock_session.execute.call_args
    query_params = call_args[0][1] if len(call_args[0]) > 1 else {}
    
    assert "min_market_cap_cr" in query_params, "Query should include min_market_cap_cr"
    assert "max_pe_ratio" in query_params, "Query should include max_pe_ratio"
    assert "min_roe_pct" in query_params, "Query should include min_roe_pct"
    assert "min_revenue_growth_pct" in query_params, "Query should include min_revenue_growth_pct"
    assert "min_promoter_holding_pct" in query_params, "Query should include min_promoter_holding_pct"
    
    print("✓ Fundamental criteria test passed")


@pytest.mark.asyncio
async def test_filter_timeout_enforcement(sql_filter, mock_session, test_universe):
    """
    Test that SQL pre-filter enforces 5-second timeout
    
    Validates: Requirement 9.2 - 5-second timeout
    """
    # Setup mock to simulate slow query
    async def slow_execute(*args, **kwargs):
        await asyncio.sleep(6)  # Simulate 6-second query
        return MagicMock()
    
    mock_session.execute = slow_execute
    
    criteria = ScreeningCriteria(
        name="Timeout Test",
        description="Test timeout enforcement",
        asset_class=["equity"],
        min_rsi=30.0
    )
    
    # Execute filter and expect timeout
    with pytest.raises(asyncio.TimeoutError):
        await sql_filter.filter(criteria, test_universe)
    
    print("✓ Timeout enforcement test passed")


@pytest.mark.asyncio
async def test_filter_with_ema_position(sql_filter, mock_session, test_universe):
    """
    Test SQL pre-filter with EMA position requirement
    
    Validates: Requirement 9.2 - EMA filter
    """
    # Setup mock result
    mock_result = MagicMock()
    mock_result.fetchall.return_value = [("RELIANCE",), ("TCS",)]
    mock_session.execute = AsyncMock(return_value=mock_result)
    
    # Create criteria requiring price above 200 EMA
    criteria = ScreeningCriteria(
        name="EMA Test",
        description="Test EMA position filtering",
        asset_class=["equity"],
        require_above_ema=200
    )
    
    # Execute filter
    result = await sql_filter.filter(criteria, test_universe)
    
    # Verify query includes EMA condition
    call_args = mock_session.execute.call_args
    query_text = str(call_args[0][0])
    
    assert "ema_200" in query_text, "Query should reference ema_200 column"
    assert "close > ema_200" in query_text, "Query should check close > ema_200"
    
    print("✓ EMA position test passed")


@pytest.mark.asyncio
async def test_filter_with_breakout_criteria(sql_filter, mock_session, test_universe):
    """
    Test SQL pre-filter with price breakout criteria
    
    Validates: Requirement 9.2 - Breakout detection
    """
    # Setup mock result
    mock_result = MagicMock()
    mock_result.fetchall.return_value = [("RELIANCE",)]
    mock_session.execute = AsyncMock(return_value=mock_result)
    
    # Create criteria with 52-week high breakout
    criteria = ScreeningCriteria(
        name="Breakout Test",
        description="Test breakout filtering",
        asset_class=["equity"],
        price_breakout_days=52
    )
    
    # Execute filter
    result = await sql_filter.filter(criteria, test_universe)
    
    # Verify query includes breakout condition
    call_args = mock_session.execute.call_args
    query_text = str(call_args[0][0])
    
    assert "highest_high_52" in query_text, "Query should reference highest_high_52 column"
    assert "close >= highest_high_52" in query_text, "Query should check close >= highest_high_52"
    
    print("✓ Breakout criteria test passed")


@pytest.mark.asyncio
async def test_filter_orders_by_composite_score(sql_filter, mock_session, test_universe):
    """
    Test that SQL pre-filter orders results by composite_score DESC
    
    Validates: Requirement 9.2 - Return best matches first
    """
    # Setup mock result
    mock_result = MagicMock()
    mock_result.fetchall.return_value = [("RELIANCE",), ("TCS",)]
    mock_session.execute = AsyncMock(return_value=mock_result)
    
    criteria = ScreeningCriteria(
        name="Order Test",
        description="Test result ordering",
        asset_class=["equity"],
        min_rsi=30.0
    )
    
    # Execute filter
    result = await sql_filter.filter(criteria, test_universe)
    
    # Verify query includes ORDER BY
    call_args = mock_session.execute.call_args
    query_text = str(call_args[0][0])
    
    assert "ORDER BY composite_score DESC" in query_text, "Query should order by composite_score DESC"
    
    print("✓ Result ordering test passed")


# Run all tests
if __name__ == "__main__":
    print("=" * 80)
    print("SQL Pre-Filter Layer Unit Tests (No Database Required)")
    print("=" * 80)
    print()
    
    # Run pytest
    pytest.main([__file__, "-v", "-s"])
