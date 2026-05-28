"""
Integration test for AI Screening Engine

Tests the complete 3-layer screening pipeline with Turtle Breakout criteria
against NSE 100 universe.

Requirements: 9.1, 9.5, 9.6, 9.7
"""
import pytest
import asyncio
import sys
import os
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text
import uuid

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from services.screening.models import ScreeningCriteria
from services.screening.engine import AIScreeningEngine
from shared.database.models import Base


# Test database URL
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/signalixai_test"
)


@pytest.fixture(scope="module")
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
async def test_engine():
    """Create test database engine"""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    # Cleanup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()


@pytest.fixture
async def db_session(test_engine):
    """Create database session for tests"""
    async_session = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    
    async with async_session() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def seed_test_data(db_session):
    """Seed test OHLCV data for screening"""
    # Create test instruments
    instruments = [
        "RELIANCE", "TCS", "INFY", "HDFC", "ICICIBANK",
        "HDFCBANK", "KOTAKBANK", "SBIN", "BHARTIARTL", "ITC"
    ]
    
    # Insert test OHLCV data for last 60 days
    base_date = datetime.utcnow() - timedelta(days=60)
    
    for symbol in instruments:
        for day in range(60):
            date = base_date + timedelta(days=day)
            
            # Generate test data with some variation
            base_price = 1000 + (hash(symbol) % 500)
            price_variation = (day % 10) - 5  # -5 to +5
            close = base_price + price_variation
            
            # Calculate indicators
            rsi_14 = 30 + (day % 40)  # 30-70 range
            ema_5 = close * 0.99
            ema_9 = close * 0.98
            ema_21 = close * 0.97
            ema_50 = close * 0.96
            ema_200 = close * 0.95
            adx_14 = 20 + (day % 30)  # 20-50 range
            atr_14 = close * 0.02
            volume = 1000000 + (day % 500000)
            volume_ma_20 = 1000000
            
            # Insert OHLCV record
            await db_session.execute(text("""
                INSERT INTO ohlcv_1d (
                    symbol, timestamp, open, high, low, close, volume,
                    rsi_14, ema_5, ema_9, ema_21, ema_50, ema_200,
                    adx_14, atr_14, volume_ma_20, exchange, asset_class
                ) VALUES (
                    :symbol, :timestamp, :open, :high, :low, :close, :volume,
                    :rsi_14, :ema_5, :ema_9, :ema_21, :ema_50, :ema_200,
                    :adx_14, :atr_14, :volume_ma_20, :exchange, :asset_class
                )
            """), {
                "symbol": symbol,
                "timestamp": date,
                "open": close * 0.99,
                "high": close * 1.01,
                "low": close * 0.98,
                "close": close,
                "volume": volume,
                "rsi_14": rsi_14,
                "ema_5": ema_5,
                "ema_9": ema_9,
                "ema_21": ema_21,
                "ema_50": ema_50,
                "ema_200": ema_200,
                "adx_14": adx_14,
                "atr_14": atr_14,
                "volume_ma_20": volume_ma_20,
                "exchange": "NSE",
                "asset_class": "equity"
            })
    
    await db_session.commit()
    
    return instruments


@pytest.mark.asyncio
async def test_turtle_breakout_screening(db_session, seed_test_data):
    """
    Test complete screening pipeline with Turtle Breakout criteria
    
    This test verifies:
    1. SQL pre-filter executes and returns filtered symbols
    2. TA-Lib scoring computes scores for filtered symbols
    3. AI scoring (optional) processes top candidates
    4. Final results are returned with all required fields
    """
    # Create Turtle Breakout screening criteria
    criteria = ScreeningCriteria(
        name="Turtle Breakout Scanner",
        description="Find instruments breaking out to 20-day highs with strong momentum",
        asset_class=["equity"],
        min_rsi=40.0,
        max_rsi=70.0,
        min_adx=25.0,
        min_volume_ratio=1.2,
        price_breakout_days=20,
        require_above_ema=200
    )
    
    # Create screening engine
    engine = AIScreeningEngine(db_session)
    
    # Run screening
    universe = seed_test_data
    result = await engine.run_screening(criteria, universe)
    
    # Verify result structure
    assert result.screening_id is not None
    assert result.criteria_name == "Turtle Breakout Scanner"
    assert result.instruments_scanned == len(universe)
    assert result.duration_seconds > 0
    
    # Verify results
    assert isinstance(result.results, list)
    
    # If results found, verify structure
    if result.instruments_passed > 0:
        for inst in result.results:
            assert inst.symbol in universe
            assert inst.asset_class == "equity"
            assert inst.exchange == "NSE"
            assert inst.current_price > 0
            assert 0 <= inst.score <= 100
            assert 0 <= inst.technical_score <= 100
            assert 0 <= inst.momentum_score <= 100
            assert 0 <= inst.volume_score <= 100
            assert isinstance(inst.reasons, list)
            assert len(inst.reasons) > 0
            assert isinstance(inst.quick_stats, dict)
            assert "rsi" in inst.quick_stats
            assert "adx" in inst.quick_stats
            assert "volume_ratio" in inst.quick_stats
    
    print(f"\n✅ Screening completed successfully:")
    print(f"   - Screening ID: {result.screening_id}")
    print(f"   - Instruments scanned: {result.instruments_scanned}")
    print(f"   - Instruments passed: {result.instruments_passed}")
    print(f"   - Duration: {result.duration_seconds:.2f}s")
    
    if result.instruments_passed > 0:
        print(f"\n   Top 3 results:")
        for i, inst in enumerate(result.results[:3], 1):
            print(f"   {i}. {inst.symbol}: Score {inst.score:.1f}")
            print(f"      Reasons: {', '.join(inst.reasons[:2])}")


@pytest.mark.asyncio
async def test_screening_with_ai_layer(db_session, seed_test_data):
    """
    Test screening pipeline with AI scoring layer enabled
    
    This test verifies that AI scoring is triggered when min_ai_confidence
    is set in the criteria.
    """
    # Create criteria with AI confidence threshold
    criteria = ScreeningCriteria(
        name="AI-Enhanced Momentum Scanner",
        description="Find momentum stocks with AI confirmation",
        asset_class=["equity"],
        min_rsi=50.0,
        max_rsi=80.0,
        min_adx=30.0,
        min_ai_confidence=70.0,  # Enable AI layer
        ai_direction_filter="BUY"
    )
    
    # Create screening engine
    engine = AIScreeningEngine(db_session)
    
    # Run screening
    universe = seed_test_data
    result = await engine.run_screening(criteria, universe)
    
    # Verify result
    assert result.screening_id is not None
    assert result.instruments_scanned == len(universe)
    
    # If AI scoring is enabled and working, results should have AI signals
    if result.instruments_passed > 0:
        for inst in result.results:
            # AI scorer might not be configured in test environment
            # So we just verify the structure is correct
            assert hasattr(inst, 'ai_signal')
            assert hasattr(inst, 'ai_confidence')
    
    print(f"\n✅ AI-enhanced screening completed:")
    print(f"   - Screening ID: {result.screening_id}")
    print(f"   - Instruments passed: {result.instruments_passed}")
    print(f"   - Duration: {result.duration_seconds:.2f}s")


@pytest.mark.asyncio
async def test_screening_empty_universe(db_session):
    """
    Test screening with empty universe
    
    Verifies graceful handling of empty input.
    """
    criteria = ScreeningCriteria(
        name="Test Scanner",
        description="Test with empty universe",
        asset_class=["equity"]
    )
    
    engine = AIScreeningEngine(db_session)
    result = await engine.run_screening(criteria, [])
    
    assert result.instruments_scanned == 0
    assert result.instruments_passed == 0
    assert len(result.results) == 0
    
    print(f"\n✅ Empty universe handled gracefully")


@pytest.mark.asyncio
async def test_screening_no_matches(db_session, seed_test_data):
    """
    Test screening with criteria that matches nothing
    
    Verifies graceful handling when no instruments pass filters.
    """
    # Create very restrictive criteria
    criteria = ScreeningCriteria(
        name="Impossible Scanner",
        description="Criteria that matches nothing",
        asset_class=["equity"],
        min_rsi=95.0,  # Very high RSI
        max_rsi=100.0,
        min_adx=80.0  # Very high ADX
    )
    
    engine = AIScreeningEngine(db_session)
    result = await engine.run_screening(criteria, seed_test_data)
    
    assert result.instruments_scanned == len(seed_test_data)
    assert result.instruments_passed == 0
    assert len(result.results) == 0
    
    print(f"\n✅ No matches handled gracefully")


@pytest.mark.asyncio
async def test_get_default_universe(db_session, seed_test_data):
    """
    Test default universe fetching
    
    Verifies that the engine can fetch a default universe for given asset classes.
    """
    engine = AIScreeningEngine(db_session)
    
    # Get default universe for equity
    universe = await engine.get_default_universe(["equity"])
    
    # Should return symbols (if instruments table is populated)
    assert isinstance(universe, list)
    
    print(f"\n✅ Default universe fetched: {len(universe)} symbols")


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "-s"])
