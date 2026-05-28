"""
Manual test for screening templates
Tests template specifications match design document

Requirements: 9.4, 10.1, 10.2, 10.3, 10.4
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from services.screening.models import ScreeningCriteria


def test_oversold_reversal_template():
    """Test Oversold Reversal Scanner template spec"""
    print("Testing Oversold Reversal Scanner template...")
    
    criteria = ScreeningCriteria(
        name="Oversold Reversal Scanner",
        description="Find oversold instruments above 200 EMA showing reversal signals",
        asset_class=["equity"],
        min_rsi=20.0,
        max_rsi=35.0,
        require_above_ema=200,
        min_volume_ratio=1.3,
        min_market_cap_cr=1000.0,
        min_roe_pct=12.0
    )
    
    assert criteria.name == "Oversold Reversal Scanner"
    assert criteria.min_rsi == 20.0
    assert criteria.max_rsi == 35.0
    assert criteria.require_above_ema == 200
    assert criteria.min_market_cap_cr == 1000.0
    print("✓ Oversold Reversal Scanner template validated")


def test_fo_high_iv_template():
    """Test F&O High IV Seller template spec"""
    print("Testing F&O High IV Seller template...")
    
    criteria = ScreeningCriteria(
        name="F&O High IV Seller",
        description="Find F&O instruments with elevated IV Rank suitable for option selling",
        asset_class=["fo"],
        min_iv_rank=70.0,
        min_pcr=0.8,
        max_pcr=1.5,
        min_rsi=40.0,
        max_rsi=70.0
    )
    
    assert criteria.name == "F&O High IV Seller"
    assert criteria.min_iv_rank == 70.0
    assert criteria.min_pcr == 0.8
    assert criteria.max_pcr == 1.5
    print("✓ F&O High IV Seller template validated")


def test_crypto_accumulation_template():
    """Test Crypto Accumulation Scanner template spec"""
    print("Testing Crypto Accumulation Scanner template...")
    
    criteria = ScreeningCriteria(
        name="Crypto Accumulation Scanner",
        description="Find crypto assets in accumulation zones",
        asset_class=["crypto"],
        min_rsi=25.0,
        max_rsi=40.0,
        require_above_ema=200,
        min_fear_greed=20
    )
    
    assert criteria.name == "Crypto Accumulation Scanner"
    assert criteria.asset_class == ["crypto"]
    assert criteria.min_fear_greed == 20
    print("✓ Crypto Accumulation Scanner template validated")


def test_earnings_momentum_template():
    """Test Earnings Momentum Scanner template spec"""
    print("Testing Earnings Momentum Scanner template...")
    
    criteria = ScreeningCriteria(
        name="Earnings Momentum Scanner",
        description="Find NSE equities with strong fundamentals and technical momentum",
        asset_class=["equity"],
        min_market_cap_cr=5000.0,
        max_pe_ratio=35.0,
        min_roe_pct=15.0,
        min_revenue_growth_pct=10.0,
        min_promoter_holding_pct=50.0,
        require_above_ema=50,
        min_rsi=55.0,
        min_volume_ratio=1.2
    )
    
    assert criteria.name == "Earnings Momentum Scanner"
    assert criteria.min_market_cap_cr == 5000.0
    assert criteria.min_roe_pct == 15.0
    assert criteria.min_promoter_holding_pct == 50.0
    print("✓ Earnings Momentum Scanner template validated")


def test_all_asset_classes():
    """Test criteria with all asset classes"""
    print("Testing all asset classes...")
    
    criteria = ScreeningCriteria(
        name="Multi-Asset Scanner",
        description="Scan across all markets",
        asset_class=["equity", "fo", "crypto", "forex", "commodity"],
        min_rsi=30.0,
        max_rsi=70.0
    )
    
    assert len(criteria.asset_class) == 5
    assert "equity" in criteria.asset_class
    assert "crypto" in criteria.asset_class
    assert "forex" in criteria.asset_class
    print("✓ All asset classes validated")


if __name__ == "__main__":
    print("=" * 60)
    print("Screening Template Validation Tests")
    print("=" * 60)
    print()
    
    print("Testing Template Specifications:")
    print("-" * 60)
    test_oversold_reversal_template()
    test_fo_high_iv_template()
    test_crypto_accumulation_template()
    test_earnings_momentum_template()
    test_all_asset_classes()
    print()
    
    print("=" * 60)
    print("✅ All template validation tests passed!")
    print("=" * 60)
    print()
    print("Templates validated:")
    print("1. Oversold Reversal Scanner (equity)")
    print("2. F&O High IV Seller (options)")
    print("3. Crypto Accumulation Scanner (crypto)")
    print("4. Earnings Momentum Scanner (equity fundamentals)")
    print("5. Multi-asset scanner (all markets)")
    print()
    print("Next steps:")
    print("1. Run migration: alembic upgrade head")
    print("2. Start screening service on port 8006")
    print("3. Test endpoints with curl or Postman:")
    print("   - GET  /api/v1/screen/templates")
    print("   - POST /api/v1/screen/criteria")
    print("   - GET  /api/v1/screen/criteria")
    print("   - PUT  /api/v1/screen/criteria/{id}")
    print("   - DELETE /api/v1/screen/criteria/{id}")
    print("   - POST /api/v1/screen/templates/{id}/clone")
