"""
Validation script for strategy templates
Tests that all 8 strategy templates pass StrategySpec Pydantic validation

Requirements: 2.1, 2.2, 2.3
"""
import sys
from pathlib import Path
import importlib.util

# Add services to path
sys.path.insert(0, str(Path(__file__).parent))

from services.algo_builder.models import StrategySpec

# Import the templates from the migration file
migration_path = Path(__file__).parent / "alembic" / "versions" / "006_strategy_templates.py"
spec = importlib.util.spec_from_file_location("templates_module", migration_path)
templates_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(templates_module)

STRATEGY_TEMPLATES = templates_module.STRATEGY_TEMPLATES


def test_all_templates():
    """Test all 8 strategy templates"""
    print("="*70)
    print("STRATEGY TEMPLATES VALIDATION TEST")
    print("="*70)
    print()
    
    total_tests = 0
    passed_tests = 0
    failed_tests = []
    
    # Test 1: Verify count
    print("Test 1: Verify template count")
    total_tests += 1
    if len(STRATEGY_TEMPLATES) == 8:
        print(f"✓ Found {len(STRATEGY_TEMPLATES)} templates (expected 8)")
        passed_tests += 1
    else:
        print(f"✗ Found {len(STRATEGY_TEMPLATES)} templates (expected 8)")
        failed_tests.append("Template count mismatch")
    print()
    
    # Test 2: Verify all expected names
    print("Test 2: Verify template names")
    expected_names = [
        "Turtle Breakout (Richard Dennis)",
        "Volatility Mean Reversion (Edward Thorp)",
        "Macro Momentum (Paul Tudor Jones)",
        "SuperTrend + EMA Cross",
        "BankNifty Iron Condor (PR Sundar)",
        "Concentrated Trend (Stanley Druckenmiller)",
        "Value Momentum (Rakesh Jhunjhunwala)",
        "Crypto Accumulation"
    ]
    
    template_names = [t["name"] for t in STRATEGY_TEMPLATES]
    for expected_name in expected_names:
        total_tests += 1
        if expected_name in template_names:
            print(f"✓ {expected_name}")
            passed_tests += 1
        else:
            print(f"✗ {expected_name} NOT FOUND")
            failed_tests.append(f"Missing template: {expected_name}")
    print()
    
    # Test 3: Validate each template's StrategySpec
    print("Test 3: Validate StrategySpec for each template")
    for template in STRATEGY_TEMPLATES:
        total_tests += 1
        template_name = template["name"]
        
        try:
            # Validate with Pydantic
            spec = StrategySpec(**template["spec"])
            
            # Additional validations
            assert spec.strategy_id is not None
            assert spec.name is not None
            assert spec.asset_class in ["equity", "fo", "crypto", "forex", "commodity"]
            assert len(spec.entry_rules) >= 1, "Must have at least 1 entry rule"
            assert len(spec.exit_rules) >= 1, "Must have at least 1 exit rule"
            assert spec.position_sizing is not None
            assert spec.position_sizing.max_position_pct <= 10.0, "Max position must be <= 10%"
            assert spec.market_filter is not None
            assert spec.indicators_config is not None
            assert len(spec.indicators_config) > 0, "Must have indicators configured"
            
            print(f"✓ {template_name}")
            print(f"  - Asset class: {spec.asset_class}")
            print(f"  - Entry rules: {len(spec.entry_rules)}")
            print(f"  - Exit rules: {len(spec.exit_rules)}")
            print(f"  - Position sizing: {spec.position_sizing.method}")
            print(f"  - Indicators: {len(spec.indicators_config)}")
            passed_tests += 1
            
        except Exception as e:
            print(f"✗ {template_name}: {str(e)}")
            failed_tests.append(f"{template_name}: {str(e)}")
        print()
    
    # Test 4: Verify required fields
    print("Test 4: Verify required fields in templates")
    required_fields = ["id", "name", "description", "methodology_attribution", "use_cases", "spec"]
    
    for template in STRATEGY_TEMPLATES:
        total_tests += 1
        template_name = template["name"]
        missing_fields = [f for f in required_fields if f not in template]
        
        if not missing_fields:
            print(f"✓ {template_name}: All required fields present")
            passed_tests += 1
        else:
            print(f"✗ {template_name}: Missing fields: {', '.join(missing_fields)}")
            failed_tests.append(f"{template_name}: Missing {', '.join(missing_fields)}")
    print()
    
    # Test 5: Specific template validations
    print("Test 5: Specific template validations")
    
    # Turtle Breakout
    total_tests += 1
    turtle = next((t for t in STRATEGY_TEMPLATES if "Turtle Breakout" in t["name"]), None)
    if turtle:
        spec = StrategySpec(**turtle["spec"])
        if (spec.asset_class == "equity" and 
            spec.position_sizing.method == "atr_based" and
            "highest_high_20" in spec.indicators_config):
            print("✓ Turtle Breakout: Correct configuration")
            passed_tests += 1
        else:
            print("✗ Turtle Breakout: Configuration mismatch")
            failed_tests.append("Turtle Breakout configuration")
    else:
        print("✗ Turtle Breakout: Template not found")
        failed_tests.append("Turtle Breakout not found")
    
    # Thorp Volatility
    total_tests += 1
    thorp = next((t for t in STRATEGY_TEMPLATES if "Thorp" in t["name"]), None)
    if thorp:
        spec = StrategySpec(**thorp["spec"])
        if (spec.asset_class == "fo" and 
            spec.position_sizing.method == "kelly" and
            "iv_rank" in spec.indicators_config):
            print("✓ Thorp Volatility: Correct configuration")
            passed_tests += 1
        else:
            print("✗ Thorp Volatility: Configuration mismatch")
            failed_tests.append("Thorp Volatility configuration")
    else:
        print("✗ Thorp Volatility: Template not found")
        failed_tests.append("Thorp Volatility not found")
    
    # Jones Momentum
    total_tests += 1
    jones = next((t for t in STRATEGY_TEMPLATES if "Paul Tudor Jones" in t["name"]), None)
    if jones:
        spec = StrategySpec(**jones["spec"])
        if (spec.market_filter.require_above_200ema == True and
            "ema_200" in spec.indicators_config):
            print("✓ Jones Momentum: Correct configuration")
            passed_tests += 1
        else:
            print("✗ Jones Momentum: Configuration mismatch")
            failed_tests.append("Jones Momentum configuration")
    else:
        print("✗ Jones Momentum: Template not found")
        failed_tests.append("Jones Momentum not found")
    
    # SuperTrend
    total_tests += 1
    supertrend = next((t for t in STRATEGY_TEMPLATES if "SuperTrend" in t["name"]), None)
    if supertrend:
        spec = StrategySpec(**supertrend["spec"])
        if ("supertrend" in spec.indicators_config and
            "ema_9" in spec.indicators_config and
            "ema_21" in spec.indicators_config):
            print("✓ SuperTrend + EMA Cross: Correct configuration")
            passed_tests += 1
        else:
            print("✗ SuperTrend + EMA Cross: Configuration mismatch")
            failed_tests.append("SuperTrend configuration")
    else:
        print("✗ SuperTrend + EMA Cross: Template not found")
        failed_tests.append("SuperTrend not found")
    
    # BankNifty Iron Condor
    total_tests += 1
    iron_condor = next((t for t in STRATEGY_TEMPLATES if "Iron Condor" in t["name"]), None)
    if iron_condor:
        spec = StrategySpec(**iron_condor["spec"])
        if (spec.asset_class == "fo" and
            "BANKNIFTY" in spec.instruments and
            "iv_rank" in spec.indicators_config):
            print("✓ BankNifty Iron Condor: Correct configuration")
            passed_tests += 1
        else:
            print("✗ BankNifty Iron Condor: Configuration mismatch")
            failed_tests.append("Iron Condor configuration")
    else:
        print("✗ BankNifty Iron Condor: Template not found")
        failed_tests.append("Iron Condor not found")
    
    # Druckenmiller Trend
    total_tests += 1
    druckenmiller = next((t for t in STRATEGY_TEMPLATES if "Druckenmiller" in t["name"]), None)
    if druckenmiller:
        spec = StrategySpec(**druckenmiller["spec"])
        if (spec.market_filter.min_adx == 30.0 and
            spec.position_sizing.max_concurrent_positions == 1):
            print("✓ Druckenmiller Concentrated Trend: Correct configuration")
            passed_tests += 1
        else:
            print("✗ Druckenmiller Concentrated Trend: Configuration mismatch")
            failed_tests.append("Druckenmiller configuration")
    else:
        print("✗ Druckenmiller Concentrated Trend: Template not found")
        failed_tests.append("Druckenmiller not found")
    
    # Value Momentum
    total_tests += 1
    value_momentum = next((t for t in STRATEGY_TEMPLATES if "Jhunjhunwala" in t["name"]), None)
    if value_momentum:
        spec = StrategySpec(**value_momentum["spec"])
        if (spec.market_filter.require_above_200ema == True and
            spec.market_filter.require_positive_breadth == True):
            print("✓ Value Momentum: Correct configuration")
            passed_tests += 1
        else:
            print("✗ Value Momentum: Configuration mismatch")
            failed_tests.append("Value Momentum configuration")
    else:
        print("✗ Value Momentum: Template not found")
        failed_tests.append("Value Momentum not found")
    
    # Crypto Accumulation
    total_tests += 1
    crypto = next((t for t in STRATEGY_TEMPLATES if "Crypto" in t["name"]), None)
    if crypto:
        spec = StrategySpec(**crypto["spec"])
        if (spec.asset_class == "crypto" and
            spec.market_filter.require_above_200ema == True):
            print("✓ Crypto Accumulation: Correct configuration")
            passed_tests += 1
        else:
            print("✗ Crypto Accumulation: Configuration mismatch")
            failed_tests.append("Crypto Accumulation configuration")
    else:
        print("✗ Crypto Accumulation: Template not found")
        failed_tests.append("Crypto Accumulation not found")
    
    print()
    
    # Summary
    print("="*70)
    print("TEST SUMMARY")
    print("="*70)
    print(f"Total tests: {total_tests}")
    print(f"Passed: {passed_tests}")
    print(f"Failed: {len(failed_tests)}")
    print()
    
    if failed_tests:
        print("Failed tests:")
        for failure in failed_tests:
            print(f"  - {failure}")
        print()
        print("✗ VALIDATION FAILED")
        return False
    else:
        print("✓ ALL TESTS PASSED")
        print()
        print("All 8 strategy templates:")
        print("  1. Load successfully")
        print("  2. Pass StrategySpec Pydantic validation")
        print("  3. Have all required fields")
        print("  4. Have correct configurations")
        print()
        print("Requirements validated: 2.1, 2.2, 2.3")
        return True


if __name__ == "__main__":
    try:
        success = test_all_templates()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
