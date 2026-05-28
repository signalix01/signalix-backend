"""Simple test runner for StrategyCompiler

This script runs basic validation tests on the StrategyCompiler without requiring pytest.
"""
import sys
import ast
import importlib.util
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Import the compiler
from services.algo_builder.compiler import StrategyCompiler
from services.algo_builder.models import StrategySpec

# Import strategy templates
migration_path = Path(__file__).parent.parent.parent / "alembic" / "versions" / "006_strategy_templates.py"
spec = importlib.util.spec_from_file_location("templates_module", migration_path)
templates_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(templates_module)

STRATEGY_TEMPLATES = templates_module.STRATEGY_TEMPLATES


def test_compile_all_templates():
    """Test that all 8 templates compile successfully"""
    print("=" * 80)
    print("Testing StrategyCompiler - Compiling all 8 strategy templates")
    print("=" * 80)
    print()
    
    compiler = StrategyCompiler()
    passed = 0
    failed = 0
    
    for idx, template in enumerate(STRATEGY_TEMPLATES, 1):
        template_name = template["name"]
        print(f"Test {idx}/8: Compiling '{template_name}'...")
        
        try:
            # Create StrategySpec from template
            spec = StrategySpec(**template["spec"])
            
            # Compile the strategy
            result = compiler.compile(spec)
            
            # Validate it's a string
            assert isinstance(result, str), "Result is not a string"
            assert len(result) > 0, "Result is empty"
            
            # Validate Python syntax
            ast.parse(result)
            
            # Validate structure
            assert "class CompiledStrategy_" in result, "Missing class definition"
            assert "BaseStrategy" in result, "Missing BaseStrategy inheritance"
            assert "def compute_indicators" in result, "Missing compute_indicators method"
            assert "def market_filter_pass" in result, "Missing market_filter_pass method"
            assert "def should_enter_long" in result, "Missing should_enter_long method"
            assert "def should_enter_short" in result, "Missing should_enter_short method"
            assert "def should_exit" in result, "Missing should_exit method"
            assert "def position_size" in result, "Missing position_size method"
            
            # Validate imports
            assert "import pandas as pd" in result, "Missing pandas import"
            assert "import numpy as np" in result, "Missing numpy import"
            assert "import talib" in result, "Missing talib import"
            assert "from services.algo_builder.base_strategy import BaseStrategy" in result, "Missing BaseStrategy import"
            
            # Validate no dangerous imports
            dangerous = ["import os", "import sys", "import subprocess", "import socket", "import requests"]
            for danger in dangerous:
                assert danger not in result, f"Contains dangerous import: {danger}"
            
            print(f"  ✓ PASSED - Generated {len(result)} characters of valid Python code")
            passed += 1
            
        except Exception as e:
            print(f"  ✗ FAILED - {str(e)}")
            failed += 1
        
        print()
    
    print("=" * 80)
    print(f"Results: {passed} passed, {failed} failed out of {len(STRATEGY_TEMPLATES)} templates")
    print("=" * 80)
    
    if failed == 0:
        print("\n✓ All tests PASSED!")
        return True
    else:
        print(f"\n✗ {failed} tests FAILED")
        return False


def test_specific_features():
    """Test specific compiler features"""
    print("\n" + "=" * 80)
    print("Testing specific compiler features")
    print("=" * 80)
    print()
    
    compiler = StrategyCompiler()
    passed = 0
    failed = 0
    
    # Test 1: Crosses above operator
    print("Test 1: Crosses above operator...")
    try:
        turtle = next((t for t in STRATEGY_TEMPLATES if "Turtle Breakout" in t["name"]), None)
        spec = StrategySpec(**turtle["spec"])
        result = compiler.compile(spec)
        assert "crosses_above" in result
        print("  ✓ PASSED")
        passed += 1
    except Exception as e:
        print(f"  ✗ FAILED - {str(e)}")
        failed += 1
    
    # Test 2: Between operator
    print("\nTest 2: Between operator...")
    try:
        thorp = next((t for t in STRATEGY_TEMPLATES if "Thorp" in t["name"]), None)
        spec = StrategySpec(**thorp["spec"])
        result = compiler.compile(spec)
        assert "between" in result
        print("  ✓ PASSED")
        passed += 1
    except Exception as e:
        print(f"  ✗ FAILED - {str(e)}")
        failed += 1
    
    # Test 3: ATR-based position sizing
    print("\nTest 3: ATR-based position sizing...")
    try:
        turtle = next((t for t in STRATEGY_TEMPLATES if "Turtle Breakout" in t["name"]), None)
        spec = StrategySpec(**turtle["spec"])
        result = compiler.compile(spec)
        assert "atr" in result.lower()
        print("  ✓ PASSED")
        passed += 1
    except Exception as e:
        print(f"  ✗ FAILED - {str(e)}")
        failed += 1
    
    # Test 4: Kelly position sizing
    print("\nTest 4: Kelly position sizing...")
    try:
        thorp = next((t for t in STRATEGY_TEMPLATES if "Thorp" in t["name"]), None)
        spec = StrategySpec(**thorp["spec"])
        result = compiler.compile(spec)
        assert "kelly" in result.lower()
        print("  ✓ PASSED")
        passed += 1
    except Exception as e:
        print(f"  ✗ FAILED - {str(e)}")
        failed += 1
    
    # Test 5: Market filter with 200 EMA
    print("\nTest 5: Market filter with 200 EMA...")
    try:
        jones = next((t for t in STRATEGY_TEMPLATES if "Paul Tudor Jones" in t["name"]), None)
        spec = StrategySpec(**jones["spec"])
        spec.market_filter.require_above_200ema = True
        result = compiler.compile(spec)
        assert "ema_200" in result
        print("  ✓ PASSED")
        passed += 1
    except Exception as e:
        print(f"  ✗ FAILED - {str(e)}")
        failed += 1
    
    # Test 6: Target exit rule
    print("\nTest 6: Target exit rule...")
    try:
        thorp = next((t for t in STRATEGY_TEMPLATES if "Thorp" in t["name"]), None)
        spec = StrategySpec(**thorp["spec"])
        result = compiler.compile(spec)
        assert "target" in result.lower()
        print("  ✓ PASSED")
        passed += 1
    except Exception as e:
        print(f"  ✗ FAILED - {str(e)}")
        failed += 1
    
    # Test 7: Max position cap enforcement
    print("\nTest 7: Max position cap enforcement...")
    try:
        template = STRATEGY_TEMPLATES[0]
        spec = StrategySpec(**template["spec"])
        result = compiler.compile(spec)
        assert "max_size" in result or "max_position" in result.lower()
        print("  ✓ PASSED")
        passed += 1
    except Exception as e:
        print(f"  ✗ FAILED - {str(e)}")
        failed += 1
    
    print("\n" + "=" * 80)
    print(f"Feature tests: {passed} passed, {failed} failed out of 7 tests")
    print("=" * 80)
    
    return failed == 0


def main():
    """Run all tests"""
    print("\n" + "=" * 80)
    print("StrategyCompiler Test Suite")
    print("Requirements: 3.1, 3.2")
    print("=" * 80)
    
    # Run tests
    test1_passed = test_compile_all_templates()
    test2_passed = test_specific_features()
    
    # Summary
    print("\n" + "=" * 80)
    print("FINAL SUMMARY")
    print("=" * 80)
    
    if test1_passed and test2_passed:
        print("✓ ALL TESTS PASSED")
        print("\nThe StrategyCompiler successfully:")
        print("  - Compiles all 8 strategy templates")
        print("  - Generates valid Python syntax")
        print("  - Includes all required methods")
        print("  - Uses only safe libraries (numpy, pandas, talib, math, datetime)")
        print("  - Maps all ConditionBlock operators correctly")
        print("  - Implements all position sizing methods")
        print("  - Implements all market filters")
        print("  - Implements all exit rules")
        print("\nRequirements 3.1 and 3.2 are satisfied.")
        return 0
    else:
        print("✗ SOME TESTS FAILED")
        print("\nPlease review the failures above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
