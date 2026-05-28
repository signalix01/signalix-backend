"""
Integration test for TA-Lib Scoring Layer

Tests the TAScorer with 20 instruments to verify:
- Composite score is between 0-100
- Reasons are non-empty
- All required fields are populated

Requirements: 9.2
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession

from services.screening.ta_scorer import TAScorer
from services.screening.models import ScreeningCriteria, ScreenedInstrument


@pytest.fixture
def mock_session():
    """Create a mock async database session"""
    session = AsyncMock(spec=AsyncSession)
    return session


@pytest.fixture
def sample_criteria():
    """Create sample screening criteria"""
    return ScreeningCriteria(
        name="Integration Test Scanner",
        description="Test criteria for 20 instruments",
        asset_class=["equity"],
        min_rsi=25.0,
        max_rsi=75.0,
        min_adx=20.0,
        min_volume_ratio=1.2
    )


def create_mock_ohlcv_data(symbol: str, rsi: float, adx: float, volume_ratio: float):
    """
    Create mock OHLCV data for a symbol with specific indicator values
    
    Args:
        symbol: Symbol name
        rsi: RSI value to use
        adx: ADX value to use
        volume_ratio: Volume ratio to use
    
    Returns:
        List of mock row objects
    """
    base_time = datetime.now()
    base_price = 1000.0 + (hash(symbol) % 1000)  # Deterministic price based on symbol
    
    rows = []
    for i in range(60):
        row = MagicMock()
        row.symbol = symbol
        row.timestamp = base_time - timedelta(days=i)
        row.open = base_price + i
        row.high = base_price + i + 20
        row.low = base_price + i - 20
        row.close = base_price + i + 5
        row.volume = 1000000.0 * (volume_ratio if i == 0 else 1.0)
        row.rsi_14 = rsi
        row.ema_5 = base_price + i + 10
        row.ema_9 = base_price + i + 8
        row.ema_21 = base_price + i + 5
        row.ema_50 = base_price + i
        row.ema_200 = base_price + i - 50
        row.adx_14 = adx
        row.atr_14 = 25.0
        row.volume_ma_20 = 1000000.0
        row.exchange = "NSE"
        row.asset_class = "equity"
        rows.append(row)
    
    return rows


@pytest.mark.asyncio
async def test_score_20_instruments(mock_session, sample_criteria):
    """
    Integration test: Score 20 instruments and verify all requirements
    
    Requirements tested:
    - Composite score between 0-100
    - Reasons non-empty
    - All fields populated correctly
    """
    # Create 20 test symbols with varying characteristics
    test_symbols = [
        ("RELIANCE", 55.0, 32.5, 2.0),   # Strong momentum
        ("TCS", 45.0, 28.0, 1.5),        # Moderate momentum
        ("INFY", 65.0, 35.0, 2.5),       # High momentum, high RSI
        ("HDFC", 30.0, 22.0, 1.8),       # Oversold
        ("ICICIBANK", 70.0, 38.0, 2.2),  # Overbought
        ("SBIN", 50.0, 25.0, 1.3),       # Neutral
        ("WIPRO", 40.0, 30.0, 1.6),      # Moderate
        ("AXISBANK", 60.0, 33.0, 2.1),   # Good momentum
        ("HCLTECH", 35.0, 26.0, 1.4),    # Slightly oversold
        ("BHARTIARTL", 75.0, 40.0, 2.8), # Very strong
        ("ITC", 48.0, 24.0, 1.2),        # Weak trend
        ("LT", 52.0, 29.0, 1.7),         # Moderate
        ("MARUTI", 42.0, 27.0, 1.5),     # Moderate
        ("SUNPHARMA", 58.0, 31.0, 1.9),  # Good
        ("TATAMOTORS", 68.0, 36.0, 2.3), # Strong
        ("TATASTEEL", 38.0, 23.0, 1.4),  # Moderate
        ("TECHM", 62.0, 34.0, 2.0),      # Strong
        ("TITAN", 72.0, 37.0, 2.4),      # Very strong
        ("ULTRACEMCO", 46.0, 28.0, 1.6), # Moderate
        ("ASIANPAINT", 54.0, 30.0, 1.8)  # Good
    ]
    
    symbols = [s[0] for s in test_symbols]
    
    # Mock database responses for each symbol
    async def mock_execute(query, params):
        symbol = params["symbol"]
        # Find the test data for this symbol
        for test_symbol, rsi, adx, vol_ratio in test_symbols:
            if test_symbol == symbol:
                mock_result = MagicMock()
                mock_result.fetchall.return_value = create_mock_ohlcv_data(
                    symbol, rsi, adx, vol_ratio
                )
                return mock_result
        
        # Symbol not found - return empty
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        return mock_result
    
    mock_session.execute.side_effect = mock_execute
    
    # Create scorer and score all 20 instruments
    scorer = TAScorer(mock_session)
    results = await scorer.score(symbols, sample_criteria)
    
    # Verify we got results for all 20 instruments
    assert len(results) == 20, f"Expected 20 results, got {len(results)}"
    
    # Verify all results are ScreenedInstrument objects
    assert all(isinstance(r, ScreenedInstrument) for r in results), \
        "All results should be ScreenedInstrument objects"
    
    # Verify all symbols are present
    result_symbols = {r.symbol for r in results}
    assert result_symbols == set(symbols), \
        f"Missing symbols: {set(symbols) - result_symbols}"
    
    # Test each instrument
    for inst in results:
        # Requirement: Composite score between 0-100
        assert 0 <= inst.score <= 100, \
            f"{inst.symbol}: Score {inst.score} not in range 0-100"
        
        # Requirement: Reasons non-empty
        assert len(inst.reasons) > 0, \
            f"{inst.symbol}: Reasons list is empty"
        
        # Verify all reasons are non-empty strings
        assert all(isinstance(r, str) and len(r) > 0 for r in inst.reasons), \
            f"{inst.symbol}: Invalid reasons format"
        
        # Verify component scores are in valid range
        assert 0 <= inst.technical_score <= 100, \
            f"{inst.symbol}: Technical score {inst.technical_score} out of range"
        assert 0 <= inst.momentum_score <= 100, \
            f"{inst.symbol}: Momentum score {inst.momentum_score} out of range"
        assert 0 <= inst.volume_score <= 100, \
            f"{inst.symbol}: Volume score {inst.volume_score} out of range"
        assert inst.fundamental_score == 0.0, \
            f"{inst.symbol}: Fundamental score should be 0.0 in TA layer"
        
        # Verify quick_stats is populated
        assert inst.quick_stats is not None, \
            f"{inst.symbol}: quick_stats is None"
        assert "rsi" in inst.quick_stats, \
            f"{inst.symbol}: RSI missing from quick_stats"
        assert "adx" in inst.quick_stats, \
            f"{inst.symbol}: ADX missing from quick_stats"
        assert "volume_ratio" in inst.quick_stats, \
            f"{inst.symbol}: volume_ratio missing from quick_stats"
        assert "ema_position" in inst.quick_stats, \
            f"{inst.symbol}: ema_position missing from quick_stats"
        
        # Verify metadata fields
        assert inst.symbol in symbols, \
            f"Unknown symbol: {inst.symbol}"
        assert inst.asset_class == "equity", \
            f"{inst.symbol}: Wrong asset class"
        assert inst.exchange == "NSE", \
            f"{inst.symbol}: Wrong exchange"
        assert inst.current_price > 0, \
            f"{inst.symbol}: Invalid current price"
        
        # Verify AI fields are None (computed in AI layer)
        assert inst.ai_signal is None, \
            f"{inst.symbol}: ai_signal should be None in TA layer"
        assert inst.ai_confidence is None, \
            f"{inst.symbol}: ai_confidence should be None in TA layer"
    
    # Verify results are sorted by score (descending)
    scores = [inst.score for inst in results]
    assert scores == sorted(scores, reverse=True), \
        "Results should be sorted by score in descending order"
    
    # Verify score distribution is reasonable
    # Should have variation in scores
    high_scores = [s for s in scores if s >= 70]
    medium_scores = [s for s in scores if 40 <= s < 70]
    low_scores = [s for s in scores if s < 40]
    
    # At least some variation in scores
    assert len(set(scores)) > 1, "Scores should have variation"
    assert max(scores) - min(scores) > 10, "Score range should be > 10 points"
    
    # Print summary for manual verification
    print("\n=== Integration Test Summary ===")
    print(f"Total instruments scored: {len(results)}")
    print(f"Score range: {min(scores):.1f} - {max(scores):.1f}")
    print(f"Average score: {sum(scores)/len(scores):.1f}")
    print(f"High scores (≥70): {len(high_scores)}")
    print(f"Medium scores (40-70): {len(medium_scores)}")
    print(f"Low scores (<40): {len(low_scores)}")
    print("\nTop 5 instruments:")
    for i, inst in enumerate(results[:5], 1):
        print(f"{i}. {inst.symbol}: {inst.score:.1f} - {inst.reasons[0]}")


@pytest.mark.asyncio
async def test_score_performance_20_instruments(mock_session, sample_criteria):
    """
    Test that scoring 20 instruments completes in reasonable time
    
    Performance target: < 10 seconds for 200 instruments
    For 20 instruments: should complete in < 1 second
    """
    import time
    
    # Create 20 test symbols
    symbols = [f"STOCK{i:02d}" for i in range(1, 21)]
    
    # Mock database responses
    async def mock_execute(query, params):
        mock_result = MagicMock()
        mock_result.fetchall.return_value = create_mock_ohlcv_data(
            params["symbol"], 50.0, 30.0, 1.5
        )
        return mock_result
    
    mock_session.execute.side_effect = mock_execute
    
    # Measure execution time
    scorer = TAScorer(mock_session)
    start_time = time.time()
    results = await scorer.score(symbols, sample_criteria)
    elapsed_time = time.time() - start_time
    
    # Verify results
    assert len(results) == 20
    
    # Verify performance
    assert elapsed_time < 1.0, \
        f"Scoring 20 instruments took {elapsed_time:.2f}s, expected < 1.0s"
    
    print(f"\n=== Performance Test ===")
    print(f"Scored 20 instruments in {elapsed_time:.3f} seconds")
    print(f"Average time per instrument: {elapsed_time/20*1000:.1f}ms")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
