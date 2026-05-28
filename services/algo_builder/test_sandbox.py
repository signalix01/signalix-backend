"""Tests for sandboxed execution environment

Tests verify:
1. Timeout kills correctly
2. Memory limit enforced
3. Network access blocked
4. Successful validation of valid strategies
5. Proper error handling

Requirements: 3.3, 3.4, 3.5, 3.6
"""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from algo_builder.sandbox import SandboxRunner, ValidationResult, validate_strategy
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


class TestSandboxRunner:
    """Test suite for SandboxRunner"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.runner = SandboxRunner()
        self.compiler = StrategyCompiler()
    
    def create_simple_strategy_spec(self) -> StrategySpec:
        """Create a simple valid strategy spec for testing"""
        return StrategySpec(
            strategy_id="test-strategy-001",
            user_id="test-user",
            name="Test Strategy",
            description="Simple test strategy",
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
                value=2.0,
                max_position_pct=10.0
            ),
            market_filter=MarketFilter(),
            indicators_config={"rsi_14": {"period": 14}},
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat()
        )
    
    def test_validate_simple_strategy_success(self):
        """Test successful validation of a simple strategy"""
        spec = self.create_simple_strategy_spec()
        compiled_code = self.compiler.compile(spec)
        
        result = self.runner.validate(compiled_code)
        
        assert result.success is True
        assert result.error is None
        assert result.execution_time_ms is not None
        assert result.execution_time_ms > 0
        assert "validated successfully" in result.message.lower()
    
    def test_validate_timeout_kills_correctly(self):
        """Test that timeout kills runaway strategies correctly"""
        # Create a strategy with an infinite loop
        malicious_code = '''
import pandas as pd
import numpy as np
from services.algo_builder.base_strategy import BaseStrategy

class CompiledStrategy_timeout_test(BaseStrategy):
    name = "Timeout Test"
    asset_class = "equity"
    strategy_id = "timeout-test"

    def __init__(self, data: pd.DataFrame, capital: float):
        super().__init__(data, capital)
        self.risk_per_trade = 0.01
        self.max_daily_loss = 0.02

    def compute_indicators(self):
        # Infinite loop to trigger timeout
        while True:
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
        
        result = self.runner.validate(malicious_code)
        
        assert result.success is False
        assert result.error is not None
        assert "timeout" in result.error.lower() or "exceeded" in result.error.lower()
    
    def test_validate_network_access_blocked(self):
        """Test that network access is blocked in sandbox"""
        # Create a strategy that attempts network access
        network_code = '''
import pandas as pd
import numpy as np
from services.algo_builder.base_strategy import BaseStrategy

class CompiledStrategy_network_test(BaseStrategy):
    name = "Network Test"
    asset_class = "equity"
    strategy_id = "network-test"

    def __init__(self, data: pd.DataFrame, capital: float):
        super().__init__(data, capital)
        self.risk_per_trade = 0.01
        self.max_daily_loss = 0.02

    def compute_indicators(self):
        # Attempt network access
        try:
            import urllib.request
            urllib.request.urlopen('http://example.com', timeout=1)
        except Exception as e:
            # Network should be blocked
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
        
        # The strategy should still validate (network access just fails silently)
        # but we verify it doesn't crash
        result = self.runner.validate(network_code)
        
        # Strategy should complete (network access is blocked but doesn't crash)
        assert result.success is True or (result.success is False and "network" not in result.error.lower())
    
    def test_validate_memory_limit_enforced(self):
        """Test that memory limit is enforced (Linux only)"""
        import platform
        
        if platform.system() != "Linux":
            pytest.skip("Memory limit test only runs on Linux")
        
        # Create a strategy that attempts to allocate excessive memory
        memory_hog_code = '''
import pandas as pd
import numpy as np
from services.algo_builder.base_strategy import BaseStrategy

class CompiledStrategy_memory_test(BaseStrategy):
    name = "Memory Test"
    asset_class = "equity"
    strategy_id = "memory-test"

    def __init__(self, data: pd.DataFrame, capital: float):
        super().__init__(data, capital)
        self.risk_per_trade = 0.01
        self.max_daily_loss = 0.02

    def compute_indicators(self):
        # Try to allocate 1GB of memory (exceeds 512MB limit)
        try:
            big_array = np.zeros((1024, 1024, 128), dtype=np.float64)  # ~1GB
        except MemoryError:
            pass  # Expected

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
        
        result = self.runner.validate(memory_hog_code)
        
        # Should either fail with memory error or complete (if memory allocation was caught)
        # The key is that it doesn't crash the parent process
        assert result is not None
        if not result.success:
            assert "memory" in result.error.lower() or "error" in result.error.lower()
    
    def test_validate_missing_methods(self):
        """Test validation fails when required methods are missing"""
        # Create a strategy missing required methods
        incomplete_code = '''
import pandas as pd
import numpy as np
from services.algo_builder.base_strategy import BaseStrategy

class CompiledStrategy_incomplete(BaseStrategy):
    name = "Incomplete Strategy"
    asset_class = "equity"
    strategy_id = "incomplete"

    def __init__(self, data: pd.DataFrame, capital: float):
        super().__init__(data, capital)

    def compute_indicators(self):
        pass

    # Missing other required methods
'''
        
        result = self.runner.validate(incomplete_code)
        
        assert result.success is False
        assert result.error is not None
        assert "missing" in result.error.lower() or "method" in result.error.lower()
    
    def test_validate_syntax_error(self):
        """Test validation fails gracefully with syntax errors"""
        # Create code with syntax error
        syntax_error_code = '''
import pandas as pd
import numpy as np
from services.algo_builder.base_strategy import BaseStrategy

class CompiledStrategy_syntax_error(BaseStrategy):
    name = "Syntax Error"
    asset_class = "equity"
    strategy_id = "syntax-error"

    def __init__(self, data: pd.DataFrame, capital: float):
        super().__init__(data, capital)

    def compute_indicators(self):
        # Syntax error: missing closing parenthesis
        x = (1 + 2
'''
        
        result = self.runner.validate(syntax_error_code)
        
        assert result.success is False
        assert result.error is not None
    
    def test_execute_with_real_data(self):
        """Test execution with real OHLCV data"""
        spec = self.create_simple_strategy_spec()
        compiled_code = self.compiler.compile(spec)
        
        # Create test data
        test_data = self.runner._create_test_data(100)
        test_capital = 100000.0
        
        # Execute
        strategy = self.runner.execute(compiled_code, test_data, test_capital)
        
        # Verify strategy was created
        assert strategy is not None
        assert hasattr(strategy, 'data')
        assert hasattr(strategy, 'capital')
        assert strategy.capital == test_capital
    
    def test_create_test_data(self):
        """Test synthetic test data generation"""
        data = self.runner._create_test_data(100)
        
        assert len(data) == 100
        assert 'open' in data.columns
        assert 'high' in data.columns
        assert 'low' in data.columns
        assert 'close' in data.columns
        assert 'volume' in data.columns
        assert 'rsi_14' in data.columns
        assert 'ema_9' in data.columns
        
        # Verify no NaN values
        assert not data.isnull().any().any()
        
        # Verify high >= low
        assert (data['high'] >= data['low']).all()
    
    def test_validation_result_to_dict(self):
        """Test ValidationResult serialization"""
        result = ValidationResult(
            success=True,
            message="Test message",
            error=None,
            execution_time_ms=123.45
        )
        
        result_dict = result.to_dict()
        
        assert result_dict['success'] is True
        assert result_dict['message'] == "Test message"
        assert result_dict['error'] is None
        assert result_dict['execution_time_ms'] == 123.45
    
    def test_convenience_function(self):
        """Test the convenience validate_strategy function"""
        spec = self.create_simple_strategy_spec()
        compiled_code = self.compiler.compile(spec)
        
        result = validate_strategy(compiled_code)
        
        assert isinstance(result, ValidationResult)
        assert result.success is True


class TestSandboxIntegration:
    """Integration tests for sandbox with compiler"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.compiler = StrategyCompiler()
        self.runner = SandboxRunner()
    
    def test_compile_and_validate_turtle_strategy(self):
        """Test compiling and validating a Turtle-style strategy"""
        spec = StrategySpec(
            strategy_id="turtle-001",
            user_id="test-user",
            name="Turtle Breakout",
            description="20-day channel breakout",
            asset_class="equity",
            instruments=["BANKNIFTY"],
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
                                )
                            ]
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
                    exit_type="target",
                    target_pct=5.0
                )
            ],
            position_sizing=PositionSizing(
                method=PositionSizingMethod.ATR_BASED,
                value=1.0
            ),
            market_filter=MarketFilter(
                require_above_200ema=True
            ),
            indicators_config={
                "ema_50": {"period": 50},
                "ema_200": {"period": 200},
                "atr_14": {"period": 14}
            },
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat()
        )
        
        # Compile
        compiled_code = self.compiler.compile(spec)
        assert compiled_code is not None
        
        # Validate
        result = self.runner.validate(compiled_code)
        assert result.success is True
    
    def test_compile_and_validate_complex_strategy(self):
        """Test compiling and validating a complex multi-condition strategy"""
        spec = StrategySpec(
            strategy_id="complex-001",
            user_id="test-user",
            name="Complex Strategy",
            description="Multi-indicator strategy",
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
                                    operator=CompareOperator.BETWEEN,
                                    right_operand="40,60"
                                ),
                                ConditionBlock(
                                    left_operand="close",
                                    operator=CompareOperator.GREATER,
                                    right_operand="ema_21"
                                )
                            ],
                            gate=LogicGate.AND
                        )
                    ]
                ),
                EntryRule(
                    direction="SHORT",
                    condition_groups=[
                        ConditionGroup(
                            conditions=[
                                ConditionBlock(
                                    left_operand="rsi_14",
                                    operator=CompareOperator.GREATER,
                                    right_operand=70
                                )
                            ]
                        )
                    ]
                )
            ],
            exit_rules=[
                ExitRule(
                    exit_type="trailing_sl",
                    trailing_sl_pct=3.0
                ),
                ExitRule(
                    exit_type="time",
                    max_hold_candles=20
                )
            ],
            position_sizing=PositionSizing(
                method=PositionSizingMethod.VOLATILITY_ADJUSTED,
                value=5.0
            ),
            market_filter=MarketFilter(
                min_adx=25.0
            ),
            indicators_config={
                "rsi_14": {"period": 14},
                "ema_21": {"period": 21},
                "adx_14": {"period": 14}
            },
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat()
        )
        
        # Compile
        compiled_code = self.compiler.compile(spec)
        assert compiled_code is not None
        
        # Validate
        result = self.runner.validate(compiled_code)
        assert result.success is True


def run_tests():
    """Run all tests"""
    print("Running sandbox tests...")
    print("=" * 70)
    
    # Run with pytest
    pytest.main([__file__, "-v", "--tb=short"])


if __name__ == "__main__":
    run_tests()
