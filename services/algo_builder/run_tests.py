"""
Simple test runner for Strategy CRUD API
Runs basic validation tests without requiring pytest
"""
import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from services.algo_builder.models import StrategySpec, PositionSizing, MarketFilter, EntryRule, ExitRule, ConditionGroup, ConditionBlock
from datetime import datetime


def test_strategy_spec_validation():
    """Test StrategySpec validation"""
    print("\n=== Testing StrategySpec Validation ===")
    
    # Test 1: Valid strategy spec
    print("\n1. Testing valid strategy spec...")
    try:
        spec = StrategySpec(
            strategy_id="test_001",
            user_id="user_123",
            name="Test Strategy",
            description="A test strategy",
            asset_class="equity",
            instruments=["NIFTY", "BANKNIFTY"],
            entry_rules=[
                EntryRule(
                    direction="LONG",
                    condition_groups=[
                        ConditionGroup(
                            conditions=[
                                ConditionBlock(
                                    left_operand="rsi_14",
                                    operator="<",
                                    right_operand=30.0,
                                    time_frame="1D"
                                )
                            ],
                            gate="AND"
                        )
                    ],
                    confirmation_candles=1
                )
            ],
            exit_rules=[
                ExitRule(
                    exit_type="target",
                    target_pct=5.0
                )
            ],
            position_sizing=PositionSizing(
                method="pct_capital",
                value=5.0,
                max_position_pct=10.0,
                max_concurrent_positions=3
            ),
            market_filter=MarketFilter(
                require_above_200ema=False,
                min_adx=None,
                max_vix=None,
                require_positive_breadth=False
            ),
            indicators_config={"rsi_14": {"period": 14}},
            risk_per_trade_pct=1.0,
            max_daily_loss_pct=2.0,
            regime_awareness=True,
            status="draft",
            created_at=datetime.utcnow().isoformat(),
            updated_at=datetime.utcnow().isoformat()
        )
        print("✓ Valid strategy spec created successfully")
        print(f"  Strategy: {spec.name}")
        print(f"  Asset class: {spec.asset_class}")
        print(f"  Instruments: {', '.join(spec.instruments)}")
        print(f"  Entry rules: {len(spec.entry_rules)}")
        print(f"  Exit rules: {len(spec.exit_rules)}")
    except Exception as e:
        print(f"✗ Failed to create valid strategy spec: {e}")
        return False
    
    # Test 2: Empty entry rules (should fail)
    print("\n2. Testing empty entry rules (should fail)...")
    try:
        spec = StrategySpec(
            strategy_id="test_002",
            user_id="user_123",
            name="Invalid Strategy",
            description="Missing entry rules",
            asset_class="equity",
            instruments=["NIFTY"],
            entry_rules=[],  # Empty - should fail
            exit_rules=[
                ExitRule(exit_type="target", target_pct=5.0)
            ],
            position_sizing=PositionSizing(
                method="pct_capital",
                value=5.0,
                max_position_pct=10.0,
                max_concurrent_positions=3
            ),
            market_filter=MarketFilter(require_above_200ema=False),
            indicators_config={},
            risk_per_trade_pct=1.0,
            max_daily_loss_pct=2.0,
            regime_awareness=True,
            status="draft",
            created_at=datetime.utcnow().isoformat(),
            updated_at=datetime.utcnow().isoformat()
        )
        print("✗ Should have failed validation for empty entry rules")
        return False
    except ValueError as e:
        print(f"✓ Correctly rejected empty entry rules: {e}")
    
    # Test 3: Empty exit rules (should fail)
    print("\n3. Testing empty exit rules (should fail)...")
    try:
        spec = StrategySpec(
            strategy_id="test_003",
            user_id="user_123",
            name="Invalid Strategy",
            description="Missing exit rules",
            asset_class="equity",
            instruments=["NIFTY"],
            entry_rules=[
                EntryRule(
                    direction="LONG",
                    condition_groups=[
                        ConditionGroup(
                            conditions=[
                                ConditionBlock(
                                    left_operand="rsi_14",
                                    operator="<",
                                    right_operand=30.0,
                                    time_frame="1D"
                                )
                            ],
                            gate="AND"
                        )
                    ],
                    confirmation_candles=1
                )
            ],
            exit_rules=[],  # Empty - should fail
            position_sizing=PositionSizing(
                method="pct_capital",
                value=5.0,
                max_position_pct=10.0,
                max_concurrent_positions=3
            ),
            market_filter=MarketFilter(require_above_200ema=False),
            indicators_config={},
            risk_per_trade_pct=1.0,
            max_daily_loss_pct=2.0,
            regime_awareness=True,
            status="draft",
            created_at=datetime.utcnow().isoformat(),
            updated_at=datetime.utcnow().isoformat()
        )
        print("✗ Should have failed validation for empty exit rules")
        return False
    except ValueError as e:
        print(f"✓ Correctly rejected empty exit rules: {e}")
    
    # Test 4: Max position cap > 10% (should fail)
    print("\n4. Testing max_position_pct > 10% (should fail)...")
    try:
        spec = StrategySpec(
            strategy_id="test_004",
            user_id="user_123",
            name="Invalid Strategy",
            description="Max position too high",
            asset_class="equity",
            instruments=["NIFTY"],
            entry_rules=[
                EntryRule(
                    direction="LONG",
                    condition_groups=[
                        ConditionGroup(
                            conditions=[
                                ConditionBlock(
                                    left_operand="rsi_14",
                                    operator="<",
                                    right_operand=30.0,
                                    time_frame="1D"
                                )
                            ],
                            gate="AND"
                        )
                    ],
                    confirmation_candles=1
                )
            ],
            exit_rules=[
                ExitRule(exit_type="target", target_pct=5.0)
            ],
            position_sizing=PositionSizing(
                method="pct_capital",
                value=5.0,
                max_position_pct=15.0,  # > 10% - should fail
                max_concurrent_positions=3
            ),
            market_filter=MarketFilter(require_above_200ema=False),
            indicators_config={},
            risk_per_trade_pct=1.0,
            max_daily_loss_pct=2.0,
            regime_awareness=True,
            status="draft",
            created_at=datetime.utcnow().isoformat(),
            updated_at=datetime.utcnow().isoformat()
        )
        print("✗ Should have failed validation for max_position_pct > 10%")
        return False
    except ValueError as e:
        print(f"✓ Correctly rejected max_position_pct > 10%: {e}")
    
    # Test 5: All indicator types
    print("\n5. Testing all indicator types...")
    try:
        from services.algo_builder.models import IndicatorType
        indicators = [
            IndicatorType.RSI, IndicatorType.MACD, IndicatorType.EMA,
            IndicatorType.SMA, IndicatorType.BB, IndicatorType.ATR,
            IndicatorType.VWAP, IndicatorType.SUPERTREND, IndicatorType.ADX,
            IndicatorType.STOCH, IndicatorType.OBV, IndicatorType.PIVOT,
            IndicatorType.ICHIMOKU, IndicatorType.WILLIAMS_R, IndicatorType.CCI,
            IndicatorType.MFI
        ]
        print(f"✓ All {len(indicators)} indicator types defined:")
        for ind in indicators:
            print(f"  - {ind.value}")
    except Exception as e:
        print(f"✗ Failed to enumerate indicator types: {e}")
        return False
    
    # Test 6: All comparison operators
    print("\n6. Testing all comparison operators...")
    try:
        from services.algo_builder.models import CompareOperator
        operators = [
            CompareOperator.GREATER, CompareOperator.LESS,
            CompareOperator.CROSSES_ABOVE, CompareOperator.CROSSES_BELOW,
            CompareOperator.EQUALS, CompareOperator.BETWEEN
        ]
        print(f"✓ All {len(operators)} comparison operators defined:")
        for op in operators:
            print(f"  - {op.value}")
    except Exception as e:
        print(f"✗ Failed to enumerate comparison operators: {e}")
        return False
    
    # Test 7: All position sizing methods
    print("\n7. Testing all position sizing methods...")
    try:
        from services.algo_builder.models import PositionSizingMethod
        methods = [
            PositionSizingMethod.FIXED_CAPITAL,
            PositionSizingMethod.PCT_CAPITAL,
            PositionSizingMethod.KELLY_CRITERION,
            PositionSizingMethod.ATR_BASED,
            PositionSizingMethod.VOLATILITY_ADJUSTED
        ]
        print(f"✓ All {len(methods)} position sizing methods defined:")
        for method in methods:
            print(f"  - {method.value}")
    except Exception as e:
        print(f"✗ Failed to enumerate position sizing methods: {e}")
        return False
    
    print("\n=== All validation tests passed! ===")
    return True


def test_router_imports():
    """Test that router imports work"""
    print("\n=== Testing Router Imports ===")
    
    try:
        from services.algo_builder.router import router
        print("✓ Router imported successfully")
        
        # Check endpoints
        routes = [route.path for route in router.routes]
        print(f"✓ Router has {len(routes)} routes:")
        for route in routes:
            print(f"  - {route}")
        
        expected_routes = [
            "/api/v1/algo/strategies",
            "/api/v1/algo/strategies/{strategy_id}",
            "/api/v1/algo/templates",
            "/api/v1/algo/templates/{template_id}/clone",
            "/api/v1/algo/health"
        ]
        
        for expected in expected_routes:
            if any(expected in route for route in routes):
                print(f"✓ Found expected route: {expected}")
            else:
                print(f"✗ Missing expected route: {expected}")
                return False
        
        return True
        
    except Exception as e:
        print(f"✗ Failed to import router: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests"""
    print("=" * 60)
    print("Strategy CRUD API - Test Suite")
    print("=" * 60)
    
    results = []
    
    # Test 1: Model validation
    results.append(("Model Validation", test_strategy_spec_validation()))
    
    # Test 2: Router imports
    results.append(("Router Imports", test_router_imports()))
    
    # Print summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print(f"\n❌ {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
