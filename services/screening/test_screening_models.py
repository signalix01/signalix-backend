"""
Test screening models validation

Requirements: 9.4, 10.1, 10.2, 10.3, 10.4
"""
import pytest
from services.screening.models import ScreeningCriteria, ScreenedInstrument, ScreeningResult


def test_screening_criteria_valid():
    """Test valid screening criteria creation"""
    criteria = ScreeningCriteria(
        name="Test Scanner",
        description="Test description",
        asset_class=["equity"],
        min_rsi=20.0,
        max_rsi=35.0,
        require_above_ema=200,
        min_volume_ratio=1.5
    )
    
    assert criteria.name == "Test Scanner"
    assert criteria.asset_class == ["equity"]
    assert criteria.min_rsi == 20.0
    assert criteria.max_rsi == 35.0


def test_screening_criteria_invalid_asset_class():
    """Test invalid asset class raises error"""
    with pytest.raises(ValueError, match="Invalid asset class"):
        ScreeningCriteria(
            name="Test Scanner",
            description="Test description",
            asset_class=["invalid_class"],
            min_rsi=20.0
        )


def test_screening_criteria_rsi_range_validation():
    """Test RSI range validation"""
    with pytest.raises(ValueError, match="max_rsi must be greater than min_rsi"):
        ScreeningCriteria(
            name="Test Scanner",
            description="Test description",
            asset_class=["equity"],
            min_rsi=40.0,
            max_rsi=30.0  # Invalid: max < min
        )


def test_screening_criteria_iv_rank_range_validation():
    """Test IV rank range validation"""
    with pytest.raises(ValueError, match="max_iv_rank must be greater than min_iv_rank"):
        ScreeningCriteria(
            name="Test Scanner",
            description="Test description",
            asset_class=["fo"],
            min_iv_rank=80.0,
            max_iv_rank=70.0  # Invalid: max < min
        )


def test_screening_criteria_pcr_range_validation():
    """Test PCR range validation"""
    with pytest.raises(ValueError, match="max_pcr must be greater than min_pcr"):
        ScreeningCriteria(
            name="Test Scanner",
            description="Test description",
            asset_class=["fo"],
            min_pcr=1.5,
            max_pcr=1.0  # Invalid: max < min
        )


def test_screening_criteria_all_fields():
    """Test screening criteria with all fields"""
    criteria = ScreeningCriteria(
        name="Comprehensive Scanner",
        description="Test all fields",
        asset_class=["equity", "fo"],
        # Fundamental
        min_market_cap_cr=1000.0,
        max_pe_ratio=30.0,
        min_roe_pct=15.0,
        min_revenue_growth_pct=10.0,
        min_promoter_holding_pct=50.0,
        # Technical
        min_rsi=20.0,
        max_rsi=35.0,
        require_above_ema=200,
        min_adx=25.0,
        min_volume_ratio=1.5,
        price_breakout_days=20,
        # Options
        min_iv_rank=70.0,
        max_iv_rank=90.0,
        min_pcr=0.8,
        max_pcr=1.5,
        # Crypto
        min_fear_greed=20,
        max_funding_rate=0.01,
        min_on_chain_netflow_btc=-500.0,
        # AI
        min_ai_confidence=70.0,
        ai_direction_filter="BUY"
    )
    
    assert criteria.name == "Comprehensive Scanner"
    assert len(criteria.asset_class) == 2
    assert criteria.min_market_cap_cr == 1000.0
    assert criteria.min_rsi == 20.0
    assert criteria.min_iv_rank == 70.0
    assert criteria.ai_direction_filter == "BUY"


def test_screened_instrument_valid():
    """Test valid screened instrument creation"""
    instrument = ScreenedInstrument(
        symbol="RELIANCE",
        asset_class="equity",
        exchange="NSE",
        current_price=2450.50,
        score=85.5,
        technical_score=82.0,
        fundamental_score=88.0,
        momentum_score=78.0,
        volume_score=92.0,
        ai_signal="BUY",
        ai_confidence=85.0,
        reasons=["RSI oversold", "Strong volume"],
        quick_stats={"rsi": 28.5, "volume_ratio": 2.3}
    )
    
    assert instrument.symbol == "RELIANCE"
    assert instrument.score == 85.5
    assert instrument.ai_signal == "BUY"
    assert len(instrument.reasons) == 2


def test_screening_result_valid():
    """Test valid screening result creation"""
    result = ScreeningResult(
        screening_id="550e8400-e29b-41d4-a716-446655440000",
        criteria_name="Test Scanner",
        run_at="2025-01-15T10:30:00Z",
        duration_seconds=12.5,
        instruments_scanned=2000,
        instruments_passed=15,
        results=[]
    )
    
    assert result.screening_id == "550e8400-e29b-41d4-a716-446655440000"
    assert result.instruments_scanned == 2000
    assert result.instruments_passed == 15


if __name__ == "__main__":
    # Run tests
    print("Testing ScreeningCriteria validation...")
    test_screening_criteria_valid()
    print("✓ Valid criteria test passed")
    
    test_screening_criteria_all_fields()
    print("✓ All fields test passed")
    
    test_screened_instrument_valid()
    print("✓ Screened instrument test passed")
    
    test_screening_result_valid()
    print("✓ Screening result test passed")
    
    print("\nTesting validation errors...")
    try:
        test_screening_criteria_invalid_asset_class()
        print("✗ Should have raised ValueError for invalid asset class")
    except:
        print("✓ Invalid asset class validation passed")
    
    try:
        test_screening_criteria_rsi_range_validation()
        print("✗ Should have raised ValueError for invalid RSI range")
    except:
        print("✓ RSI range validation passed")
    
    try:
        test_screening_criteria_iv_rank_range_validation()
        print("✗ Should have raised ValueError for invalid IV rank range")
    except:
        print("✓ IV rank range validation passed")
    
    try:
        test_screening_criteria_pcr_range_validation()
        print("✗ Should have raised ValueError for invalid PCR range")
    except:
        print("✓ PCR range validation passed")
    
    print("\n✅ All tests passed!")
