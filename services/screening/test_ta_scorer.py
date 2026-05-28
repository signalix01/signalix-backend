"""
Unit tests for TA-Lib Scoring Layer

Tests the TAScorer class that computes composite scores for screened instruments.

Requirements: 9.2
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
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
        name="Test Momentum Scanner",
        description="Test criteria for momentum stocks",
        asset_class=["equity"],
        min_rsi=30.0,
        max_rsi=70.0,
        min_adx=25.0,
        min_volume_ratio=1.5
    )


@pytest.fixture
def sample_ohlcv_data():
    """Create sample OHLCV data rows"""
    base_time = datetime.now()
    
    # Create 60 bars of data
    rows = []
    for i in range(60):
        row = MagicMock()
        row.symbol = "RELIANCE"
        row.timestamp = base_time - timedelta(days=i)
        row.open = 2400.0 + i
        row.high = 2450.0 + i
        row.low = 2380.0 + i
        row.close = 2420.0 + i
        row.volume = 1000000.0 * (1.5 if i == 0 else 1.0)  # Latest bar has high volume
        row.rsi_14 = 55.0
        row.ema_5 = 2425.0
        row.ema_9 = 2422.0
        row.ema_21 = 2418.0
        row.ema_50 = 2410.0
        row.ema_200 = 2380.0
        row.adx_14 = 32.5
        row.atr_14 = 45.2
        row.volume_ma_20 = 1000000.0
        row.exchange = "NSE"
        row.asset_class = "equity"
        rows.append(row)
    
    return rows


class TestTAScorer:
    """Test suite for TAScorer class"""
    
    @pytest.mark.asyncio
    async def test_score_empty_symbols(self, mock_session, sample_criteria):
        """Test scoring with empty symbols list"""
        scorer = TAScorer(mock_session)
        
        result = await scorer.score([], sample_criteria)
        
        assert result == []
        assert not mock_session.execute.called
    
    @pytest.mark.asyncio
    async def test_score_single_symbol_success(
        self,
        mock_session,
        sample_criteria,
        sample_ohlcv_data
    ):
        """Test scoring a single symbol with valid data"""
        # Mock database response
        mock_result = MagicMock()
        mock_result.fetchall.return_value = sample_ohlcv_data
        mock_session.execute.return_value = mock_result
        
        scorer = TAScorer(mock_session)
        
        result = await scorer.score(["RELIANCE"], sample_criteria)
        
        assert len(result) == 1
        assert isinstance(result[0], ScreenedInstrument)
        assert result[0].symbol == "RELIANCE"
        assert 0 <= result[0].score <= 100
        assert result[0].current_price == 2420.0
        assert result[0].exchange == "NSE"
        assert result[0].asset_class == "equity"
        assert len(result[0].reasons) > 0
        assert result[0].quick_stats is not None
    
    @pytest.mark.asyncio
    async def test_score_multiple_symbols(
        self,
        mock_session,
        sample_criteria,
        sample_ohlcv_data
    ):
        """Test scoring multiple symbols"""
        # Create data for multiple symbols
        symbols = ["RELIANCE", "TCS", "INFY"]
        
        async def mock_execute(query, params):
            mock_result = MagicMock()
            # Return data with symbol from params
            data = []
            for row in sample_ohlcv_data:
                new_row = MagicMock()
                for attr in dir(row):
                    if not attr.startswith('_'):
                        setattr(new_row, attr, getattr(row, attr))
                new_row.symbol = params["symbol"]
                data.append(new_row)
            mock_result.fetchall.return_value = data
            return mock_result
        
        mock_session.execute.side_effect = mock_execute
        
        scorer = TAScorer(mock_session)
        
        result = await scorer.score(symbols, sample_criteria)
        
        assert len(result) == 3
        assert all(isinstance(inst, ScreenedInstrument) for inst in result)
        assert {inst.symbol for inst in result} == set(symbols)
        # Results should be sorted by score descending
        scores = [inst.score for inst in result]
        assert scores == sorted(scores, reverse=True)
    
    @pytest.mark.asyncio
    async def test_score_insufficient_data(self, mock_session, sample_criteria):
        """Test scoring when symbol has insufficient data"""
        # Mock database response with only 5 bars (< 10 minimum)
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_session.execute.return_value = mock_result
        
        scorer = TAScorer(mock_session)
        
        result = await scorer.score(["NEWSTOCK"], sample_criteria)
        
        assert len(result) == 0
    
    @pytest.mark.asyncio
    async def test_score_missing_critical_data(
        self,
        mock_session,
        sample_criteria,
        sample_ohlcv_data
    ):
        """Test scoring when critical data (close, RSI) is missing"""
        # Set critical fields to None
        for row in sample_ohlcv_data:
            row.close = None
            row.rsi_14 = None
        
        mock_result = MagicMock()
        mock_result.fetchall.return_value = sample_ohlcv_data
        mock_session.execute.return_value = mock_result
        
        scorer = TAScorer(mock_session)
        
        result = await scorer.score(["BADDATA"], sample_criteria)
        
        assert len(result) == 0
    
    @pytest.mark.asyncio
    async def test_composite_score_calculation(
        self,
        mock_session,
        sample_criteria,
        sample_ohlcv_data
    ):
        """Test that composite score is calculated correctly"""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = sample_ohlcv_data
        mock_session.execute.return_value = mock_result
        
        scorer = TAScorer(mock_session)
        
        result = await scorer.score(["RELIANCE"], sample_criteria)
        
        assert len(result) == 1
        inst = result[0]
        
        # Composite score should be weighted average
        # score = (rsi_score * 0.30) + (volume_score * 0.30) + (trend_score * 0.25) + (momentum_score * 0.15)
        assert 0 <= inst.score <= 100
        assert 0 <= inst.technical_score <= 100
        assert 0 <= inst.momentum_score <= 100
        assert 0 <= inst.volume_score <= 100
        assert inst.fundamental_score == 0.0  # Not computed in TA layer
    
    @pytest.mark.asyncio
    async def test_quick_stats_populated(
        self,
        mock_session,
        sample_criteria,
        sample_ohlcv_data
    ):
        """Test that quick_stats dictionary is properly populated"""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = sample_ohlcv_data
        mock_session.execute.return_value = mock_result
        
        scorer = TAScorer(mock_session)
        
        result = await scorer.score(["RELIANCE"], sample_criteria)
        
        assert len(result) == 1
        stats = result[0].quick_stats
        
        # Check all expected fields are present
        assert "rsi" in stats
        assert "adx" in stats
        assert "atr" in stats
        assert "volume_ratio" in stats
        assert "ema_position" in stats
        assert "close" in stats
        assert "ema_5" in stats
        assert "ema_9" in stats
        assert "ema_21" in stats
        assert "ema_50" in stats
        assert "ema_200" in stats
        
        # Check values are reasonable
        assert stats["rsi"] == 55.0
        assert stats["adx"] == 32.5
        assert stats["volume_ratio"] == 1.5  # 1.5M / 1M
        assert stats["close"] == 2420.0
    
    @pytest.mark.asyncio
    async def test_reasons_generated(
        self,
        mock_session,
        sample_criteria,
        sample_ohlcv_data
    ):
        """Test that human-readable reasons are generated"""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = sample_ohlcv_data
        mock_session.execute.return_value = mock_result
        
        scorer = TAScorer(mock_session)
        
        result = await scorer.score(["RELIANCE"], sample_criteria)
        
        assert len(result) == 1
        reasons = result[0].reasons
        
        # Should have at least one reason
        assert len(reasons) > 0
        # All reasons should be non-empty strings
        assert all(isinstance(r, str) and len(r) > 0 for r in reasons)
    
    def test_compute_rsi_score_oversold(self):
        """Test RSI score computation for oversold conditions"""
        scorer = TAScorer(AsyncMock())
        criteria = ScreeningCriteria(
            name="Test",
            description="Test",
            asset_class=["equity"]
        )
        
        # RSI 25 (oversold) should get high score
        score = scorer._compute_rsi_score(25.0, criteria)
        assert score >= 70.0
        
        # RSI 30 (oversold threshold) should get good score
        score = scorer._compute_rsi_score(30.0, criteria)
        assert score >= 70.0
    
    def test_compute_rsi_score_overbought(self):
        """Test RSI score computation for overbought conditions"""
        scorer = TAScorer(AsyncMock())
        criteria = ScreeningCriteria(
            name="Test",
            description="Test",
            asset_class=["equity"]
        )
        
        # RSI 75 (overbought) should get high score
        score = scorer._compute_rsi_score(75.0, criteria)
        assert score >= 80.0
        
        # RSI 70 (overbought threshold) should get good score
        score = scorer._compute_rsi_score(70.0, criteria)
        assert score >= 80.0
    
    def test_compute_rsi_score_with_criteria_bounds(self):
        """Test RSI score computation with criteria bounds"""
        scorer = TAScorer(AsyncMock())
        criteria = ScreeningCriteria(
            name="Test",
            description="Test",
            asset_class=["equity"],
            min_rsi=40.0,
            max_rsi=60.0
        )
        
        # RSI within bounds should get high score
        score = scorer._compute_rsi_score(50.0, criteria)
        assert score >= 70.0
        
        # RSI outside bounds should get lower score
        score = scorer._compute_rsi_score(75.0, criteria)
        assert score < 70.0
    
    def test_compute_volume_score(self):
        """Test volume score computation"""
        scorer = TAScorer(AsyncMock())
        
        # Volume ratio 2.0 should get score 100
        score = scorer._compute_volume_score(2000000.0, 1000000.0)
        assert score == 100.0
        
        # Volume ratio 1.0 should get score 50
        score = scorer._compute_volume_score(1000000.0, 1000000.0)
        assert score == 50.0
        
        # Volume ratio 0.5 should get score 25
        score = scorer._compute_volume_score(500000.0, 1000000.0)
        assert score == 25.0
        
        # Missing data should get neutral score
        score = scorer._compute_volume_score(None, 1000000.0)
        assert score == 50.0
    
    def test_compute_trend_score_bullish_stack(self):
        """Test trend score for perfect bullish EMA stack"""
        scorer = TAScorer(AsyncMock())
        
        # Perfect bullish stack: close > ema_5 > ema_9 > ema_21 > ema_50 > ema_200
        score = scorer._compute_trend_score(
            close=2500.0,
            ema_5=2480.0,
            ema_9=2460.0,
            ema_21=2440.0,
            ema_50=2420.0,
            ema_200=2400.0
        )
        assert score == 100.0
    
    def test_compute_trend_score_bearish_stack(self):
        """Test trend score for bearish EMA stack"""
        scorer = TAScorer(AsyncMock())
        
        # Bearish stack: close < ema_5 < ema_9 < ema_21 < ema_50 < ema_200
        score = scorer._compute_trend_score(
            close=2300.0,
            ema_5=2320.0,
            ema_9=2340.0,
            ema_21=2360.0,
            ema_50=2380.0,
            ema_200=2400.0
        )
        assert score == 0.0
    
    def test_compute_momentum_score(self):
        """Test momentum score computation based on ADX"""
        scorer = TAScorer(AsyncMock())
        
        # ADX 50 should get score 100
        score = scorer._compute_momentum_score(50.0)
        assert score == 100.0
        
        # ADX 25 should get score 50
        score = scorer._compute_momentum_score(25.0)
        assert score == 50.0
        
        # ADX 0 should get score 0
        score = scorer._compute_momentum_score(0.0)
        assert score == 0.0
        
        # Missing ADX should get neutral score
        score = scorer._compute_momentum_score(None)
        assert score == 50.0
    
    def test_determine_ema_position(self):
        """Test EMA position determination"""
        scorer = TAScorer(AsyncMock())
        
        # Price above all EMAs
        pos = scorer._determine_ema_position(
            close=2500.0,
            ema_5=2480.0,
            ema_9=2460.0,
            ema_21=2440.0,
            ema_50=2420.0,
            ema_200=2400.0
        )
        assert pos == "above_all"
        
        # Price above 200 EMA only
        pos = scorer._determine_ema_position(
            close=2410.0,
            ema_5=2480.0,
            ema_9=2460.0,
            ema_21=2440.0,
            ema_50=2420.0,
            ema_200=2400.0
        )
        assert pos == "above_200"
        
        # Price below all EMAs
        pos = scorer._determine_ema_position(
            close=2300.0,
            ema_5=2480.0,
            ema_9=2460.0,
            ema_21=2440.0,
            ema_50=2420.0,
            ema_200=2400.0
        )
        assert pos == "below_all"
    
    def test_generate_reasons(self):
        """Test reason generation"""
        scorer = TAScorer(AsyncMock())
        criteria = ScreeningCriteria(
            name="Test Scanner",
            description="Test",
            asset_class=["equity"],
            min_rsi=30.0,
            max_rsi=70.0
        )
        
        reasons = scorer._generate_reasons(
            symbol="RELIANCE",
            rsi_14=55.0,
            volume_ratio=2.5,
            ema_position="above_all",
            adx_14=35.0,
            criteria=criteria
        )
        
        # Should have multiple reasons
        assert len(reasons) >= 3
        
        # Check for expected reason types
        reason_text = " ".join(reasons).lower()
        assert "rsi" in reason_text
        assert "volume" in reason_text
        assert "ema" in reason_text or "trend" in reason_text
        assert "adx" in reason_text or "trend" in reason_text
    
    @pytest.mark.asyncio
    async def test_score_handles_database_errors(
        self,
        mock_session,
        sample_criteria
    ):
        """Test that scoring handles database errors gracefully"""
        # Mock database to raise an exception
        mock_session.execute.side_effect = Exception("Database connection failed")
        
        scorer = TAScorer(mock_session)
        
        # Should not raise exception, just return empty list
        result = await scorer.score(["RELIANCE"], sample_criteria)
        
        assert len(result) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
