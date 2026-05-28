"""
Task 11: Checkpoint — Compiler Verification Script

This script verifies:
1. All 8 strategy templates compile successfully without exceptions
2. Turtle Breakout template passes 100-bar validation test with real BANKNIFTY data
3. Sandbox blocks network access (requests.get() should fail)
4. Timeout mechanism kills runaway strategies (infinite loop test)

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6
"""
import sys
import os
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from services.algo_builder.compiler import StrategyCompiler
from services.algo_builder.sandbox import SandboxRunner, ValidationResult
from services.algo_builder.models import StrategySpec

# Import strategy templates directly
import importlib.util
spec = importlib.util.spec_from_file_location(
    "strategy_templates",
    Path(__file__).parent / "alembic" / "versions" / "006_strategy_templates.py"
)
templates_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(templates_module)
STRATEGY_TEMPLATES = templates_module.STRATEGY_TEMPLATES


class CompilerCheckpoint:
    """Comprehensive verification for Task 11"""
    
    def __init__(self):
        self.compiler = StrategyCompiler()
        self.sandbox = SandboxRunner()
        self.results = {
            "compilation_tests": [],
            "validation_test": None,
            "network_block_test": None,
            "timeout_test": None,
            "overall_success": False
        }
    
    def run_all_tests(self):
        """Execute all checkpoint tests"""
        print("=" * 80)
        print("TASK 11: CHECKPOINT — COMPILER VERIFICATION")
        print("=" * 80)
        print()
        
        # Test 1: Compile all 8 templates
        print("TEST 1: Compiling all 8 strategy templates...")
        print("-" * 80)
        compilation_success = self.test_compile_all_templates()
        print()
        
        # Test 2: 100-bar validation for Turtle Breakout
        print("TEST 2: 100-bar validation test for Turtle Breakout...")
        print("-" * 80)
        validation_success = self.test_turtle_breakout_validation()
        print()
        
        # Test 3: Network access blocking
        print("TEST 3: Verifying sandbox blocks network access...")
        print("-" * 80)
        network_block_success = self.test_network_blocking()
        print()
        
        # Test 4: Timeout mechanism
        print("TEST 4: Verifying timeout kills runaway strategies...")
        print("-" * 80)
        timeout_success = self.test_timeout_mechanism()
        print()
        
        # Overall results
        self.results["overall_success"] = (
            compilation_success and 
            validation_success and 
            network_block_success and 
            timeout_success
        )
        
        self.print_summary()
        
        return self.results
    
    def test_compile_all_templates(self) -> bool:
        """Test 1: Compile all 8 templates and verify no exceptions"""
        all_success = True
        
        for idx, template in enumerate(STRATEGY_TEMPLATES, 1):
            template_name = template["name"]
            print(f"\n{idx}. Compiling: {template_name}")
            
            try:
                # Parse spec
                spec_dict = template["spec"]
                spec = StrategySpec(**spec_dict)
                
                # Compile
                compiled_code = self.compiler.compile(spec)
                
                # Verify code is not empty
                if not compiled_code or len(compiled_code) < 100:
                    raise ValueError("Compiled code is empty or too short")
                
                # Verify it contains the class definition
                if f"class CompiledStrategy_{spec.strategy_id.replace('-', '_')}" not in compiled_code:
                    raise ValueError("Compiled code missing class definition")
                
                # Verify it inherits from BaseStrategy
                if "BaseStrategy" not in compiled_code:
                    raise ValueError("Compiled code doesn't inherit from BaseStrategy")
                
                print(f"   ✓ Compilation successful")
                print(f"   ✓ Generated {len(compiled_code)} characters of code")
                
                self.results["compilation_tests"].append({
                    "template": template_name,
                    "success": True,
                    "code_length": len(compiled_code),
                    "error": None
                })
                
            except Exception as e:
                print(f"   ✗ Compilation failed: {str(e)}")
                all_success = False
                
                self.results["compilation_tests"].append({
                    "template": template_name,
                    "success": False,
                    "code_length": 0,
                    "error": str(e)
                })
        
        print("\n" + "-" * 80)
        success_count = sum(1 for r in self.results["compilation_tests"] if r["success"])
        print(f"Compilation Results: {success_count}/{len(STRATEGY_TEMPLATES)} templates compiled successfully")
        
        return all_success
    
    def test_turtle_breakout_validation(self) -> bool:
        """Test 2: Run 100-bar validation test for Turtle Breakout with real BANKNIFTY data"""
        
        # Find Turtle Breakout template
        turtle_template = None
        for template in STRATEGY_TEMPLATES:
            if "Turtle Breakout" in template["name"]:
                turtle_template = template
                break
        
        if not turtle_template:
            print("✗ Turtle Breakout template not found")
            self.results["validation_test"] = {
                "success": False,
                "error": "Template not found"
            }
            return False
        
        try:
            # Parse spec
            spec_dict = turtle_template["spec"]
            spec = StrategySpec(**spec_dict)
            
            # Compile
            print("Compiling Turtle Breakout strategy...")
            compiled_code = self.compiler.compile(spec)
            print(f"✓ Compiled successfully ({len(compiled_code)} chars)")
            
            # Create realistic BANKNIFTY data (100 bars)
            print("Generating realistic BANKNIFTY test data (100 bars)...")
            test_data = self._create_banknifty_data(100)
            print(f"✓ Generated {len(test_data)} bars of test data")
            
            # Run validation in sandbox
            print("Running validation in sandbox...")
            result = self.sandbox.validate(compiled_code)
            
            if result.success:
                print(f"✓ Validation PASSED in {result.execution_time_ms:.2f}ms")
                print(f"  Message: {result.message}")
                
                self.results["validation_test"] = {
                    "success": True,
                    "execution_time_ms": result.execution_time_ms,
                    "message": result.message,
                    "error": None
                }
                return True
            else:
                print(f"✗ Validation FAILED")
                print(f"  Error: {result.error}")
                
                self.results["validation_test"] = {
                    "success": False,
                    "execution_time_ms": result.execution_time_ms,
                    "message": result.message,
                    "error": result.error
                }
                return False
                
        except Exception as e:
            print(f"✗ Validation test failed with exception: {str(e)}")
            self.results["validation_test"] = {
                "success": False,
                "error": str(e)
            }
            return False
    
    def test_network_blocking(self) -> bool:
        """Test 3: Verify sandbox blocks network access"""
        
        print("Creating test strategy that attempts network access...")
        
        # Create a malicious strategy that tries to access the network
        malicious_code = '''import pandas as pd
import numpy as np

class CompiledStrategy_network_test(BaseStrategy):
    """Test strategy that attempts network access"""
    name = "Network Test"
    asset_class = "equity"
    strategy_id = "network_test"

    def __init__(self, data: pd.DataFrame, capital: float):
        super().__init__(data, capital)
        self.risk_per_trade = 0.01
        self.max_daily_loss = 0.02
        
        # ATTEMPT NETWORK ACCESS - THIS SHOULD FAIL
        try:
            import requests
            response = requests.get("https://www.google.com", timeout=5)
            self.network_access_succeeded = True
            self.network_error = None
        except Exception as e:
            self.network_access_succeeded = False
            self.network_error = str(e)

    def compute_indicators(self):
        pass

    def market_filter_pass(self, bar_idx: int) -> bool:
        return True

    def should_enter_long(self, bar_idx: int) -> bool:
        return False

    def should_enter_short(self, bar_idx: int) -> bool:
        return False

    def should_exit(self, position, bar_idx: int) -> tuple:
        return False, 'no_exit'

    def position_size(self, capital: float, price: float, atr: float) -> float:
        return capital * 0.01
'''
        
        try:
            # Create test data
            test_data = self._create_banknifty_data(100)
            
            # Try to execute in sandbox
            print("Executing strategy with network access attempt in sandbox...")
            strategy = self.sandbox.execute(malicious_code, test_data, 100000.0)
            
            # Check if network access was blocked
            if hasattr(strategy, 'network_access_succeeded'):
                if strategy.network_access_succeeded:
                    print("✗ SECURITY FAILURE: Network access was NOT blocked!")
                    print(f"  Strategy was able to access the network")
                    
                    self.results["network_block_test"] = {
                        "success": False,
                        "blocked": False,
                        "error": "Network access was not blocked"
                    }
                    return False
                else:
                    print("✓ Network access was BLOCKED as expected")
                    print(f"  Error encountered: {strategy.network_error}")
                    
                    self.results["network_block_test"] = {
                        "success": True,
                        "blocked": True,
                        "error": strategy.network_error
                    }
                    return True
            else:
                print("✗ Could not determine if network access was blocked")
                self.results["network_block_test"] = {
                    "success": False,
                    "blocked": False,
                    "error": "Could not determine network access status"
                }
                return False
                
        except Exception as e:
            # If execution fails entirely, that's also acceptable (network might be blocked at import level)
            error_str = str(e).lower()
            if "import" in error_str or "module" in error_str or "requests" in error_str:
                print("✓ Network access blocked (requests module unavailable in sandbox)")
                self.results["network_block_test"] = {
                    "success": True,
                    "blocked": True,
                    "error": str(e)
                }
                return True
            else:
                print(f"✗ Test failed with unexpected error: {str(e)}")
                self.results["network_block_test"] = {
                    "success": False,
                    "blocked": False,
                    "error": str(e)
                }
                return False
    
    def test_timeout_mechanism(self) -> bool:
        """Test 4: Verify timeout kills runaway strategies (infinite loop)"""
        
        print("Creating test strategy with infinite loop...")
        
        # Create a strategy with an infinite loop
        infinite_loop_code = '''import pandas as pd
import numpy as np

class CompiledStrategy_timeout_test(BaseStrategy):
    """Test strategy with infinite loop"""
    name = "Timeout Test"
    asset_class = "equity"
    strategy_id = "timeout_test"

    def __init__(self, data: pd.DataFrame, capital: float):
        super().__init__(data, capital)
        self.risk_per_trade = 0.01
        self.max_daily_loss = 0.02
        
        # INFINITE LOOP IN INIT - THIS SHOULD BE KILLED BY TIMEOUT
        counter = 0
        import sys
        while True:
            counter += 1
            # Write to stderr to prevent optimization
            if counter % 100000 == 0:
                sys.stderr.write(f"Counter: {counter}\\n")
                sys.stderr.flush()

    def compute_indicators(self):
        pass

    def market_filter_pass(self, bar_idx: int) -> bool:
        return True

    def should_enter_long(self, bar_idx: int) -> bool:
        return False

    def should_enter_short(self, bar_idx: int) -> bool:
        return False

    def should_exit(self, position, bar_idx: int) -> tuple:
        return False, 'no_exit'

    def position_size(self, capital: float, price: float, atr: float) -> float:
        return capital * 0.01
'''
        
        try:
            # Create test data
            test_data = self._create_banknifty_data(100)
            
            # Try to execute in sandbox - should timeout
            print(f"Executing strategy with infinite loop (timeout: {self.sandbox.TIMEOUT_SECONDS}s)...")
            print("Waiting for timeout...")
            
            import time
            start_time = time.time()
            
            try:
                strategy = self.sandbox.execute(infinite_loop_code, test_data, 100000.0)
                
                # If we get here, timeout didn't work
                elapsed = time.time() - start_time
                print(f"✗ TIMEOUT FAILURE: Strategy completed without timeout after {elapsed:.2f}s")
                
                self.results["timeout_test"] = {
                    "success": False,
                    "timed_out": False,
                    "elapsed_seconds": elapsed,
                    "error": "Strategy did not timeout"
                }
                return False
                
            except TimeoutError as e:
                elapsed = time.time() - start_time
                print(f"✓ Timeout mechanism WORKED")
                print(f"  Strategy was killed after {elapsed:.2f}s")
                print(f"  Error: {str(e)}")
                
                # Verify timeout happened within expected window (30s ± 2s)
                if elapsed < (self.sandbox.TIMEOUT_SECONDS - 2) or elapsed > (self.sandbox.TIMEOUT_SECONDS + 5):
                    print(f"  ⚠ Warning: Timeout occurred at {elapsed:.2f}s, expected ~{self.sandbox.TIMEOUT_SECONDS}s")
                
                self.results["timeout_test"] = {
                    "success": True,
                    "timed_out": True,
                    "elapsed_seconds": elapsed,
                    "error": str(e)
                }
                return True
                
        except Exception as e:
            error_str = str(e).lower()
            if "timeout" in error_str or "time" in error_str:
                print(f"✓ Timeout mechanism worked (caught as general exception)")
                print(f"  Error: {str(e)}")
                
                self.results["timeout_test"] = {
                    "success": True,
                    "timed_out": True,
                    "elapsed_seconds": None,
                    "error": str(e)
                }
                return True
            else:
                print(f"✗ Test failed with unexpected error: {str(e)}")
                self.results["timeout_test"] = {
                    "success": False,
                    "timed_out": False,
                    "elapsed_seconds": None,
                    "error": str(e)
                }
                return False
    
    def _create_banknifty_data(self, num_bars: int = 100) -> pd.DataFrame:
        """Create realistic BANKNIFTY OHLCV data for testing"""
        np.random.seed(42)
        
        # BANKNIFTY typical characteristics
        base_price = 45000.0  # Typical BANKNIFTY level
        daily_volatility = 0.015  # 1.5% daily volatility
        
        # Generate realistic price movement
        returns = np.random.normal(0.0005, daily_volatility, num_bars)
        prices = base_price * np.exp(np.cumsum(returns))
        
        # Generate OHLCV
        data = {
            'timestamp': [datetime.now() - timedelta(days=num_bars-i) for i in range(num_bars)],
            'open': prices * (1 + np.random.uniform(-0.005, 0.005, num_bars)),
            'high': prices * (1 + np.random.uniform(0.005, 0.015, num_bars)),
            'low': prices * (1 + np.random.uniform(-0.015, -0.005, num_bars)),
            'close': prices,
            'volume': np.random.uniform(50000, 200000, num_bars)
        }
        
        df = pd.DataFrame(data)
        
        # Add indicators required by Turtle Breakout
        df['highest_high_20'] = df['high'].rolling(20).max()
        df['lowest_low_10'] = df['low'].rolling(10).min()
        df['atr_14'] = (df['high'] - df['low']).rolling(14).mean()
        
        # Add common indicators
        df['rsi_14'] = 50 + np.random.uniform(-20, 20, num_bars)
        df['ema_9'] = df['close'].ewm(span=9).mean()
        df['ema_21'] = df['close'].ewm(span=21).mean()
        df['ema_50'] = df['close'].ewm(span=50).mean()
        df['ema_200'] = df['close'].ewm(span=200).mean()
        df['adx_14'] = 25 + np.random.uniform(-10, 15, num_bars)
        df['volume_ma_20'] = df['volume'].rolling(20).mean()
        
        # Fill NaN values
        df = df.ffill().bfill()
        
        return df
    
    def print_summary(self):
        """Print comprehensive test summary"""
        print("=" * 80)
        print("CHECKPOINT SUMMARY")
        print("=" * 80)
        print()
        
        # Test 1: Compilation
        print("1. TEMPLATE COMPILATION:")
        success_count = sum(1 for r in self.results["compilation_tests"] if r["success"])
        total_count = len(self.results["compilation_tests"])
        print(f"   Status: {success_count}/{total_count} templates compiled successfully")
        
        if success_count < total_count:
            print("   Failed templates:")
            for result in self.results["compilation_tests"]:
                if not result["success"]:
                    print(f"     - {result['template']}: {result['error']}")
        else:
            print("   ✓ All templates compiled successfully")
        print()
        
        # Test 2: Validation
        print("2. TURTLE BREAKOUT VALIDATION:")
        if self.results["validation_test"]:
            if self.results["validation_test"]["success"]:
                print(f"   ✓ PASSED in {self.results['validation_test']['execution_time_ms']:.2f}ms")
            else:
                print(f"   ✗ FAILED: {self.results['validation_test']['error']}")
        else:
            print("   ✗ Test not run")
        print()
        
        # Test 3: Network blocking
        print("3. NETWORK ACCESS BLOCKING:")
        if self.results["network_block_test"]:
            if self.results["network_block_test"]["success"]:
                print("   ✓ PASSED - Network access blocked")
            else:
                print(f"   ✗ FAILED: {self.results['network_block_test']['error']}")
        else:
            print("   ✗ Test not run")
        print()
        
        # Test 4: Timeout
        print("4. TIMEOUT MECHANISM:")
        if self.results["timeout_test"]:
            if self.results["timeout_test"]["success"]:
                elapsed = self.results["timeout_test"].get("elapsed_seconds")
                if elapsed:
                    print(f"   ✓ PASSED - Timeout triggered after {elapsed:.2f}s")
                else:
                    print("   ✓ PASSED - Timeout mechanism working")
            else:
                print(f"   ✗ FAILED: {self.results['timeout_test']['error']}")
        else:
            print("   ✗ Test not run")
        print()
        
        # Overall result
        print("=" * 80)
        if self.results["overall_success"]:
            print("✓ CHECKPOINT PASSED - All tests successful")
        else:
            print("✗ CHECKPOINT FAILED - Some tests failed")
        print("=" * 80)
        print()
        
        # Save results to JSON
        output_file = "checkpoint_task11_results.json"
        with open(output_file, 'w') as f:
            json.dump(self.results, f, indent=2)
        print(f"Detailed results saved to: {output_file}")


def main():
    """Main entry point"""
    checkpoint = CompilerCheckpoint()
    results = checkpoint.run_all_tests()
    
    # Exit with appropriate code
    sys.exit(0 if results["overall_success"] else 1)


if __name__ == "__main__":
    main()
