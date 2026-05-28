"""
Unit tests for AI Scorer

Tests the Gemini 2.5 Flash AI scoring layer with mocked API responses.
Verifies JSON parsing handles all response variations.

Requirements: 9.2, 9.8
"""
import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from services.screening.ai_scorer import AIScorer
from services.screening.models import ScreeningCriteria, ScreenedInstrument


@pytest.fixture
def sample_criteria():
    """Sample screening criteria"""
    return ScreeningCriteria(
        name="Oversold Reversal Scanner",
        description="Find oversold stocks showing reversal signals",
        asset_class=["equity"],
        min_rsi=20.0,
        max_rsi=35.0,
        require_above_ema=200,
        min_volume_ratio=1.5
    )


@pytest.fixture
def sample_instruments():
    """Sample screened instruments"""
    return [
        ScreenedInstrument(
            symbol="RELIANCE",
            asset_class="equity",
            exchange="NSE",
            current_price=2450.50,
            score=85.5,
            technical_score=82.0,
            fundamental_score=88.0,
            momentum_score=78.0,
            volume_score=92.0,
            reasons=["RSI oversold at 28.5", "Volume 2.3x average"],
            quick_stats={
                "rsi": 28.5,
                "ema_position": "above_200",
                "volume_ratio": 2.3,
                "atr": 45.2,
                "adx": 32.5
            }
        ),
        ScreenedInstrument(
            symbol="TCS",
            asset_class="equity",
            exchange="NSE",
            current_price=3650.75,
            score=78.2,
            technical_score=75.0,
            fundamental_score=85.0,
            momentum_score=72.0,
            volume_score=80.0,
            reasons=["RSI at 32.1", "Price above 200 EMA"],
            quick_stats={
                "rsi": 32.1,
                "ema_position": "above_200",
                "volume_ratio": 1.8,
                "atr": 52.3,
                "adx": 28.0
            }
        )
    ]


class TestAIScorerInitialization:
    """Test AI scorer initialization"""
    
    def test_init_with_api_key(self):
        """Test initialization with explicit API key"""
        scorer = AIScorer(api_key="test-api-key")
        assert scorer.api_key == "test-api-key"
        assert scorer.enabled is True
    
    def test_init_without_api_key(self):
        """Test initialization without API key"""
        with patch.dict('os.environ', {}, clear=True):
            scorer = AIScorer()
            assert scorer.enabled is False
    
    def test_init_with_env_var(self):
        """Test initialization with environment variable"""
        with patch.dict('os.environ', {'GOOGLE_API_KEY': 'env-api-key'}):
            scorer = AIScorer()
            assert scorer.api_key == "env-api-key"
            assert scorer.enabled is True


class TestAIScorerScoring:
    """Test AI scoring functionality"""
    
    @pytest.mark.asyncio
    async def test_score_disabled_scorer(self, sample_instruments, sample_criteria):
        """Test scoring with disabled scorer returns instruments unchanged"""
        scorer = AIScorer(api_key=None)
        result = await scorer.score(sample_instruments, sample_criteria)
        
        assert len(result) == len(sample_instruments)
        assert result[0].ai_signal is None
        assert result[0].ai_confidence is None
    
    @pytest.mark.asyncio
    async def test_score_empty_list(self, sample_criteria):
        """Test scoring with empty instruments list"""
        scorer = AIScorer(api_key="test-key")
        result = await scorer.score([], sample_criteria)
        
        assert len(result) == 0
    
    @pytest.mark.asyncio
    async def test_score_success(self, sample_instruments, sample_criteria):
        """Test successful scoring with mocked Gemini API"""
        scorer = AIScorer(api_key="test-key")
        
        # Mock Gemini API response
        mock_response = Mock()
        mock_response.text = json.dumps([
            {
                "symbol": "RELIANCE",
                "signal": "BUY",
                "confidence": 85,
                "reason": "Strong oversold reversal with high volume"
            },
            {
                "symbol": "TCS",
                "signal": "HOLD",
                "confidence": 60,
                "reason": "Mixed signals, waiting for confirmation"
            }
        ])
        mock_response.usage_metadata = Mock(
            prompt_token_count=1500,
            candidates_token_count=300
        )
        
        scorer.model.generate_content = Mock(return_value=mock_response)
        
        result = await scorer.score(sample_instruments, sample_criteria)
        
        assert len(result) == 2
        assert result[0].symbol == "RELIANCE"
        assert result[0].ai_signal == "BUY"
        assert result[0].ai_confidence == 85.0
        assert "AI: Strong oversold reversal with high volume" in result[0].reasons
        
        assert result[1].symbol == "TCS"
        assert result[1].ai_signal == "HOLD"
        assert result[1].ai_confidence == 60.0
    
    @pytest.mark.asyncio
    async def test_score_api_failure_graceful_degradation(
        self,
        sample_instruments,
        sample_criteria
    ):
        """Test graceful degradation when API call fails"""
        scorer = AIScorer(api_key="test-key")
        
        # Mock API failure
        scorer.model.generate_content = Mock(side_effect=Exception("API Error"))
        
        result = await scorer.score(sample_instruments, sample_criteria)
        
        # Should return instruments unchanged
        assert len(result) == len(sample_instruments)
        assert result[0].ai_signal is None
        assert result[0].ai_confidence is None
    
    @pytest.mark.asyncio
    async def test_score_limits_to_50_instruments(self, sample_criteria):
        """Test that scoring limits to top 50 instruments"""
        # Create 60 instruments
        instruments = []
        for i in range(60):
            instruments.append(
                ScreenedInstrument(
                    symbol=f"STOCK{i}",
                    asset_class="equity",
                    exchange="NSE",
                    current_price=100.0 + i,
                    score=90.0 - i,
                    technical_score=85.0,
                    fundamental_score=80.0,
                    momentum_score=75.0,
                    volume_score=70.0,
                    reasons=["Test reason"],
                    quick_stats={"rsi": 50.0}
                )
            )
        
        scorer = AIScorer(api_key="test-key")
        
        # Mock response for 50 instruments
        mock_scores = [
            {"symbol": f"STOCK{i}", "signal": "BUY", "confidence": 80, "reason": "Test"}
            for i in range(50)
        ]
        mock_response = Mock()
        mock_response.text = json.dumps(mock_scores)
        mock_response.usage_metadata = Mock(
            prompt_token_count=2000,
            candidates_token_count=500
        )
        
        scorer.model.generate_content = Mock(return_value=mock_response)
        
        result = await scorer.score(instruments, sample_criteria)
        
        # Should only score first 50
        assert len(result) == 50
        assert result[0].ai_signal == "BUY"


class TestAIScorerPromptBuilding:
    """Test prompt building functionality"""
    
    def test_build_batch_prompt(self, sample_instruments, sample_criteria):
        """Test batch prompt construction"""
        scorer = AIScorer(api_key="test-key")
        prompt = scorer._build_batch_prompt(sample_instruments, sample_criteria)
        
        # Verify prompt contains key elements
        assert "Signalix" in prompt
        assert sample_criteria.name in prompt
        assert sample_criteria.description in prompt
        assert "RELIANCE" in prompt
        assert "TCS" in prompt
        assert "BUY" in prompt
        assert "SELL" in prompt
        assert "HOLD" in prompt
        assert "confidence" in prompt
        assert "JSON" in prompt
    
    def test_build_batch_prompt_includes_all_data(
        self,
        sample_instruments,
        sample_criteria
    ):
        """Test that prompt includes all instrument data"""
        scorer = AIScorer(api_key="test-key")
        prompt = scorer._build_batch_prompt(sample_instruments, sample_criteria)
        
        # Verify all instruments included
        for inst in sample_instruments:
            assert inst.symbol in prompt
            assert str(inst.current_price) in prompt
            assert str(inst.score) in prompt


class TestAIScorerResponseParsing:
    """Test JSON response parsing"""
    
    def test_parse_clean_json(self):
        """Test parsing clean JSON array"""
        scorer = AIScorer(api_key="test-key")
        response_text = json.dumps([
            {"symbol": "RELIANCE", "signal": "BUY", "confidence": 85, "reason": "Test"}
        ])
        
        result = scorer._parse_response(response_text)
        
        assert len(result) == 1
        assert result[0]["symbol"] == "RELIANCE"
        assert result[0]["signal"] == "BUY"
        assert result[0]["confidence"] == 85
    
    def test_parse_json_with_markdown_code_block(self):
        """Test parsing JSON wrapped in markdown code blocks"""
        scorer = AIScorer(api_key="test-key")
        response_text = """Here is the analysis:

```json
[
  {"symbol": "RELIANCE", "signal": "BUY", "confidence": 85, "reason": "Test"}
]
```

That's my analysis."""
        
        result = scorer._parse_response(response_text)
        
        assert len(result) == 1
        assert result[0]["symbol"] == "RELIANCE"
    
    def test_parse_json_with_generic_code_block(self):
        """Test parsing JSON in generic code blocks"""
        scorer = AIScorer(api_key="test-key")
        response_text = """```
[
  {"symbol": "TCS", "signal": "HOLD", "confidence": 60, "reason": "Test"}
]
```"""
        
        result = scorer._parse_response(response_text)
        
        assert len(result) == 1
        assert result[0]["symbol"] == "TCS"
    
    def test_parse_json_with_extra_text(self):
        """Test parsing JSON with extra text before/after"""
        scorer = AIScorer(api_key="test-key")
        response_text = """Here are my recommendations:

[
  {"symbol": "RELIANCE", "signal": "BUY", "confidence": 85, "reason": "Test"},
  {"symbol": "TCS", "signal": "HOLD", "confidence": 60, "reason": "Test"}
]

These are based on technical analysis."""
        
        result = scorer._parse_response(response_text)
        
        assert len(result) == 2
        assert result[0]["symbol"] == "RELIANCE"
        assert result[1]["symbol"] == "TCS"
    
    def test_parse_invalid_json_raises_error(self):
        """Test that invalid JSON raises ValueError"""
        scorer = AIScorer(api_key="test-key")
        response_text = "This is not JSON at all"
        
        with pytest.raises(ValueError):
            scorer._parse_response(response_text)


class TestAIScorerMerging:
    """Test merging AI scores with instruments"""
    
    def test_merge_ai_scores(self, sample_instruments):
        """Test merging AI scores into instruments"""
        scorer = AIScorer(api_key="test-key")
        
        ai_scores = [
            {
                "symbol": "RELIANCE",
                "signal": "BUY",
                "confidence": 85,
                "reason": "Strong buy signal"
            },
            {
                "symbol": "TCS",
                "signal": "HOLD",
                "confidence": 60,
                "reason": "Wait for confirmation"
            }
        ]
        
        result = scorer._merge_ai_scores(sample_instruments, ai_scores)
        
        assert result[0].symbol == "RELIANCE"
        assert result[0].ai_signal == "BUY"
        assert result[0].ai_confidence == 85.0
        assert "AI: Strong buy signal" in result[0].reasons
        
        assert result[1].symbol == "TCS"
        assert result[1].ai_signal == "HOLD"
        assert result[1].ai_confidence == 60.0
    
    def test_merge_ai_scores_missing_symbol(self, sample_instruments):
        """Test merging when AI score missing for a symbol"""
        scorer = AIScorer(api_key="test-key")
        
        ai_scores = [
            {
                "symbol": "RELIANCE",
                "signal": "BUY",
                "confidence": 85,
                "reason": "Strong buy signal"
            }
            # TCS missing
        ]
        
        result = scorer._merge_ai_scores(sample_instruments, ai_scores)
        
        # RELIANCE should have AI scores
        assert result[0].ai_signal == "BUY"
        
        # TCS should not have AI scores
        assert result[1].ai_signal is None
        assert result[1].ai_confidence is None


class TestAIScorerCostCalculation:
    """Test cost calculation"""
    
    def test_calculate_cost(self):
        """Test cost calculation for Gemini API"""
        scorer = AIScorer(api_key="test-key")
        
        # Test with sample token counts
        input_tokens = 1500
        output_tokens = 300
        
        cost = scorer._calculate_cost(input_tokens, output_tokens)
        
        # Expected: (1500/1M * 0.15) + (300/1M * 0.60)
        # = 0.000225 + 0.00018 = 0.000405
        expected_cost = 0.000405
        
        assert abs(cost - expected_cost) < 0.000001
    
    def test_calculate_cost_large_batch(self):
        """Test cost calculation for large batch (50 instruments)"""
        scorer = AIScorer(api_key="test-key")
        
        # Typical token counts for 50 instruments
        input_tokens = 5000
        output_tokens = 1000
        
        cost = scorer._calculate_cost(input_tokens, output_tokens)
        
        # Expected: (5000/1M * 0.15) + (1000/1M * 0.60)
        # = 0.00075 + 0.0006 = 0.00135
        expected_cost = 0.00135
        
        assert abs(cost - expected_cost) < 0.000001
        
        # Verify cost is under $0.002 target
        assert cost < 0.002


class TestAIScorerIntegration:
    """Integration tests with realistic scenarios"""
    
    @pytest.mark.asyncio
    async def test_full_scoring_pipeline(self, sample_instruments, sample_criteria):
        """Test complete scoring pipeline end-to-end"""
        scorer = AIScorer(api_key="test-key")
        
        # Mock realistic Gemini response
        mock_response = Mock()
        mock_response.text = """```json
[
  {
    "symbol": "RELIANCE",
    "signal": "BUY",
    "confidence": 85,
    "reason": "Strong oversold reversal signal with high volume confirmation and price above 200 EMA."
  },
  {
    "symbol": "TCS",
    "signal": "HOLD",
    "confidence": 55,
    "reason": "Mixed signals - RSI neutral but volume declining, waiting for clearer direction."
  }
]
```"""
        mock_response.usage_metadata = Mock(
            prompt_token_count=1500,
            candidates_token_count=300
        )
        
        scorer.model.generate_content = Mock(return_value=mock_response)
        
        result = await scorer.score(sample_instruments, sample_criteria)
        
        # Verify complete pipeline
        assert len(result) == 2
        
        # Verify RELIANCE
        assert result[0].symbol == "RELIANCE"
        assert result[0].ai_signal == "BUY"
        assert result[0].ai_confidence == 85.0
        assert len(result[0].reasons) == 3  # 2 original + 1 AI
        
        # Verify TCS
        assert result[1].symbol == "TCS"
        assert result[1].ai_signal == "HOLD"
        assert result[1].ai_confidence == 55.0
    
    @pytest.mark.asyncio
    async def test_all_signal_types(self, sample_criteria):
        """Test handling of all signal types: BUY, SELL, HOLD"""
        instruments = [
            ScreenedInstrument(
                symbol="BUY_STOCK",
                asset_class="equity",
                exchange="NSE",
                current_price=100.0,
                score=90.0,
                technical_score=85.0,
                fundamental_score=88.0,
                momentum_score=80.0,
                volume_score=95.0,
                reasons=["Test"],
                quick_stats={"rsi": 25.0}
            ),
            ScreenedInstrument(
                symbol="SELL_STOCK",
                asset_class="equity",
                exchange="NSE",
                current_price=200.0,
                score=85.0,
                technical_score=80.0,
                fundamental_score=82.0,
                momentum_score=75.0,
                volume_score=90.0,
                reasons=["Test"],
                quick_stats={"rsi": 75.0}
            ),
            ScreenedInstrument(
                symbol="HOLD_STOCK",
                asset_class="equity",
                exchange="NSE",
                current_price=150.0,
                score=70.0,
                technical_score=68.0,
                fundamental_score=72.0,
                momentum_score=65.0,
                volume_score=75.0,
                reasons=["Test"],
                quick_stats={"rsi": 50.0}
            )
        ]
        
        scorer = AIScorer(api_key="test-key")
        
        mock_response = Mock()
        mock_response.text = json.dumps([
            {"symbol": "BUY_STOCK", "signal": "BUY", "confidence": 90, "reason": "Strong buy"},
            {"symbol": "SELL_STOCK", "signal": "SELL", "confidence": 85, "reason": "Strong sell"},
            {"symbol": "HOLD_STOCK", "signal": "HOLD", "confidence": 50, "reason": "Neutral"}
        ])
        mock_response.usage_metadata = Mock(
            prompt_token_count=1200,
            candidates_token_count=250
        )
        
        scorer.model.generate_content = Mock(return_value=mock_response)
        
        result = await scorer.score(instruments, sample_criteria)
        
        assert result[0].ai_signal == "BUY"
        assert result[1].ai_signal == "SELL"
        assert result[2].ai_signal == "HOLD"
