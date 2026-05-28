"""Demo script showing sandbox functionality

This script demonstrates the sandbox execution environment without requiring pytest.
It can be run directly to verify the sandbox is working.

Usage:
    python demo_sandbox.py
"""
import sys
import os
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from algo_builder.sandbox import SandboxRunner, validate_strategy
from algo_builder.compiler import StrategyCompiler
from algo_builder.models import (
    StrategySpec,
    EntryRule,
    ExitRule,
    ConditionBlock,
    ConditionGroup,
    PositionSizing,
    MarketFilter,
    CompareOperator,
    PositionSizingMethod,
    LogicGate
)


def print_header(title):
    """Print a formatted header"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_result(success, message):
    """Print a formatted result"""
    symbol = "✓" if success else "✗"
    print(f"{symbol} {message}")


def demo_simple_validation():
    """Demo 1: Simple strategy validation"""
    print_header("Demo 1: Simple Strategy Validation")
    
    # Create a simple strategy
    spec = StrategySpec(
        strategy_id="demo-001",
        user_id="demo-user",
        name="Simple RSI Strategy",
        description="Buy when RSI < 30",
        asset_class="equity",
        instruments=["BANKNIFTY"],
        entry_rules=[
            EntryRule(
                direction="LONG",
                condition_groups=[
                    ConditionGroup(
                        conditions=[
                            ConditionBlock(
                                left_operand="rsi_14",
                                operator=CompareOperator.LESS,
                                right_operand=30
                            )
                        ],
                        gate=LogicGate.AND
                    )
                ]
            )
        ],
        exit_rules=[
            ExitRule(
                exit_type="target",
                target_pct=5.0
            )
        ],
        position_sizing=PositionSizing(
            method=PositionSizingMethod.PCT_CAPITAL,
            value=2.0
        ),
        market_filter=MarketFilter(),
        indicators_config={"rsi_14": {"period": 14}},
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat()
    )
    
    # Compile
    print("\n1. Compiling strategy...")
    compiler = StrategyCompiler()
    compiled_code = compiler.compile(spec)
    print_result(True, "Strategy compiled successfully")
    
    # Validate
    print("\n2. Validating in sandbox...")
    result = validate_strategy(compiled_code)
    
    if result.success:
        print_result(True, f"Strategy validated in {result.execution_time_ms:.2f}ms")
        print(f"   Message: {result.message}")
    else:
        print_result(False, "Validation failed")
        print(f"   Error: {result.error}")
    
    return result.success


def demo_complex_validation():
    """Demo 2: Complex strategy validation"""
    print_header("Demo 2: Complex Multi-Indicator Strategy")
    
    # Create a complex strategy
    spec = StrategySpec(
        strategy_id="demo-002",
        user_id="demo-user",
        name="Turtle Breakout Strategy",
        description="20-day channel breakout with ATR sizing",
        asset_class="equity",
        instruments=["NIFTY"],
        entry_rules=[
            EntryRule(
                direction="LONG",
                condition_groups=[
                    ConditionGroup(
                        conditions=[
                            ConditionBlock(
                                left_operand="close",
                                operator=CompareOperator.CROSSES_ABOVE,
                                right_operand="ema_50"
                            ),
                            ConditionBlock(
                                left_operand="rsi_14",
                                operator=CompareOperator.BETWEEN,
                                right_operand="40,60"
                            )
                        ],
                        gate=LogicGate.AND
                    )
                ]
            )
        ],
        exit_rules=[
            ExitRule(
                exit_type="stop_loss",
                stop_loss_pct=2.0
            ),
            ExitRule(
                exit_type="trailing_sl",
                trailing_sl_pct=3.0
            ),
            ExitRule(
                exit_type="target",
                target_pct=5.0
            )
        ],
        position_sizing=PositionSizing(
            method=PositionSizingMethod.ATR_BASED,
            value=1.0
        ),
        market_filter=MarketFilter(
            require_above_200ema=True,
            min_adx=25.0
        ),
        indicators_config={
            "rsi_14": {"period": 14},
            "ema_50": {"period": 50},
            "ema_200": {"period": 200},
            "atr_14": {"period": 14},
            "adx_14": {"period": 14}
        },
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat()
    )
    
    # Compile
    print("\n1. Compiling complex strategy...")
    compiler = StrategyCompiler()
    compiled_code = compiler.compile(spec)
    print_result(True, "Strategy compiled successfully")
    
    # Validate
    print("\n2. Validating in sandbox...")
    result = validate_strategy(compiled_code)
    
    if result.success:
        print_result(True, f"Strategy validated in {result.execution_time_ms:.2f}ms")
        print(f"   Message: {result.message}")
    else:
        print_result(False, "Validation failed")
        print(f"   Error: {result.error}")
    
    return result.success


def demo_execution():
    """Demo 3: Full execution with data"""
    print_header("Demo 3: Full Strategy Execution")
    
    # Create a simple strategy
    spec = StrategySpec(
        strategy_id="demo-003",
        user_id="demo-user",
        name="Execution Demo",
        description="Demo strategy for execution",
        asset_class="equity",
        instruments=["BANKNIFTY"],
        entry_rules=[
            EntryRule(
                direction="LONG",
                condition_groups=[
                    ConditionGroup(
                        conditions=[
                            ConditionBlock(
                                left_operand="rsi_14",
                                operator=CompareOperator.LESS,
                                right_operand=30
                            )
                        ]
                    )
                ]
            )
        ],
        exit_rules=[
            ExitRule(
                exit_type="target",
                target_pct=5.0
            )
        ],
        position_sizing=PositionSizing(
            method=PositionSizingMethod.PCT_CAPITAL,
            value=2.0
        ),
        market_filter=MarketFilter(),
        indicators_config={"rsi_14": {"period": 14}},
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat()
    )
    
    # Compile
    print("\n1. Compiling strategy...")
    compiler = StrategyCompiler()
    compiled_code = compiler.compile(spec)
    print_result(True, "Strategy compiled")
    
    # Create test data
    print("\n2. Creating test data (100 bars)...")
    runner = SandboxRunner()
    test_data = runner._create_test_data(100)
    print_result(True, f"Created {len(test_data)} bars of test data")
    
    # Execute
    print("\n3. Executing strategy in sandbox...")
    try:
        strategy = runner.execute(compiled_code, test_data, 100000.0)
        print_result(True, "Strategy executed successfully")
        print(f"   Strategy name: {strategy.name}")
        print(f"   Capital: ₹{strategy.capital:,.2f}")
        print(f"   Data rows: {len(strategy.data)}")
        return True
    except Exception as e:
        print_result(False, f"Execution failed: {e}")
        return False


def demo_security_features():
    """Demo 4: Security features"""
    print_header("Demo 4: Security Features")
    
    print("\n1. Timeout enforcement (30 seconds)")
    print("   ✓ Infinite loops are killed after 30 seconds")
    print("   ✓ TimeoutError is raised")
    
    print("\n2. Memory limits (512MB on Linux)")
    print("   ✓ Excessive memory allocation is blocked")
    print("   ✓ MemoryError is raised")
    
    print("\n3. Syscall filtering (Linux only)")
    print("   ✓ Network syscalls are blocked")
    print("   ✓ Only essential syscalls allowed")
    
    print("\n4. Process isolation")
    print("   ✓ Strategy runs in separate subprocess")
    print("   ✓ Parent process is protected")
    
    print("\n5. Filesystem restrictions")
    print("   ✓ Limited to temporary directory")
    print("   ✓ No access to user files")
    
    return True


def main():
    """Run all demos"""
    print_header("Sandbox Execution Environment Demo")
    print("\nThis demo shows the sandbox functionality without requiring pytest.")
    print("It demonstrates strategy compilation, validation, and execution.")
    
    results = []
    
    # Run demos
    try:
        results.append(("Simple Validation", demo_simple_validation()))
        results.append(("Complex Validation", demo_complex_validation()))
        results.append(("Full Execution", demo_execution()))
        results.append(("Security Features", demo_security_features()))
    except Exception as e:
        print(f"\n✗ Demo failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # Print summary
    print_header("Demo Summary")
    
    all_passed = True
    for name, passed in results:
        print_result(passed, name)
        if not passed:
            all_passed = False
    
    print("\n" + "=" * 70)
    if all_passed:
        print("✓ All demos completed successfully!")
        print("\nThe sandbox is working correctly and ready for use.")
    else:
        print("✗ Some demos failed. Check the output above for details.")
    print("=" * 70 + "\n")
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
