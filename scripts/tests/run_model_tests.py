#!/usr/bin/env python3
"""
Simple test runner for algo_builder models tests
"""
import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

try:
    # Try to import the models to verify they're accessible
    from services.algo_builder.models import (
        IndicatorType,
        CompareOperator,
        ConditionBlock,
        LogicGate,
        ConditionGroup,
        EntryRule,
        ExitRule,
        PositionSizingMethod,
        PositionSizing,
        MarketFilter,
        StrategySpec,
    )
    print("✓ All models imported successfully")
    
    # Try to create a simple valid model
    sizing = PositionSizing(
        method=PositionSizingMethod.PCT_CAPITAL,
        value=2.0,
        max_position_pct=5.0
    )
    print(f"✓ Created PositionSizing model: {sizing.method.value}")
    
    # Test the validator
    try:
        invalid_sizing = PositionSizing(
            method=PositionSizingMethod.PCT_CAPITAL,
            value=2.0,
            max_position_pct=15.0  # Should fail
        )
        print("✗ Validator failed - should have rejected max_position_pct > 10.0")
        sys.exit(1)
    except Exception as e:
        print(f"✓ Validator correctly rejected max_position_pct > 10.0: {str(e)[:50]}...")
    
    print("\n✓ All basic model tests passed!")
    print("\nTo run full test suite, use:")
    print("  python -m pytest tests/test_algo_builder_models.py -v")
    
except ImportError as e:
    print(f"✗ Import error: {e}")
    sys.exit(1)
except Exception as e:
    print(f"✗ Error: {e}")
    sys.exit(1)
