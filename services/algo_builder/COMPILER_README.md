# StrategyCompiler Documentation

## Overview

The `StrategyCompiler` converts `StrategySpec` JSON objects into executable Python class strings that inherit from `BaseStrategy`. The compiled code is designed for sandboxed execution with no filesystem or network access.

**Requirements**: 3.1, 3.2

## Features

### Core Functionality

1. **Strategy Compilation**: Converts StrategySpec JSON → executable Python class
2. **Syntax Validation**: Validates generated code using Python's `ast.parse()`
3. **Safe Execution**: Generated code uses only safe libraries (numpy, pandas, talib, math, datetime)
4. **Complete Implementation**: Generates all required methods for BaseStrategy

### Supported Operators

The compiler maps all `ConditionBlock` operators to Python expressions:

- **`>`** (GREATER): Standard comparison
- **`<`** (LESS): Standard comparison
- **`==`** (EQUALS): Standard comparison
- **`crosses_above`**: Uses `BaseStrategy.crosses_above()` helper
- **`crosses_below`**: Uses `BaseStrategy.crosses_below()` helper
- **`between`**: Uses `BaseStrategy.between()` helper with tuple bounds

### Position Sizing Methods

All position sizing methods from `PositionSizingMethod` enum are supported:

1. **`fixed_capital`**: Fixed amount per trade
2. **`pct_capital`**: Percentage of capital
3. **`kelly`**: Kelly Criterion (simplified)
4. **`atr_based`**: ATR-based position sizing (1% risk / ATR)
5. **`vol_adj`**: Volatility-adjusted sizing

### Market Filters

All market filter conditions are compiled:

- **`require_above_200ema`**: Only trade when price > 200 EMA
- **`min_adx`**: Only trade when ADX > threshold
- **`max_vix`**: Halt trading when VIX > threshold
- **`require_positive_breadth`**: Only trade when market breadth > 50%

### Exit Rules

All exit rule types are supported:

1. **`target`**: Target profit percentage
2. **`stop_loss`**: Stop loss percentage
3. **`trailing_sl`**: Trailing stop loss percentage
4. **`indicator`**: Indicator-based exit condition
5. **`time`**: Time-based exit (max hold candles)

## Usage

### Basic Usage

```python
from services.algo_builder.compiler import StrategyCompiler
from services.algo_builder.models import StrategySpec

# Create compiler instance
compiler = StrategyCompiler()

# Load or create a StrategySpec
spec = StrategySpec(**strategy_json)

# Compile to Python code
compiled_code = compiler.compile(spec)

# The compiled_code is a string containing a Python class
# that can be executed in a sandboxed environment
```

### Generated Code Structure

The compiler generates a complete Python class with this structure:

```python
import pandas as pd
import numpy as np
import talib
from datetime import datetime
import math
from services.algo_builder.base_strategy import BaseStrategy

class CompiledStrategy_<strategy_id>(BaseStrategy):
    """Compiled strategy: <name>"""
    name = "<name>"
    asset_class = "<asset_class>"
    strategy_id = "<strategy_id>"

    def __init__(self, data: pd.DataFrame, capital: float):
        super().__init__(data, capital)
        self.risk_per_trade = <risk_per_trade_pct> / 100
        self.max_daily_loss = <max_daily_loss_pct> / 100
        # Indicator setup...

    def compute_indicators(self):
        """Compute all technical indicators"""
        # Indicator computation...

    def market_filter_pass(self, bar_idx: int) -> bool:
        """Check if market filter conditions are met"""
        # Market filter logic...

    def should_enter_long(self, bar_idx: int) -> bool:
        """Check if long entry conditions are met"""
        # Entry logic for LONG...

    def should_enter_short(self, bar_idx: int) -> bool:
        """Check if short entry conditions are met"""
        # Entry logic for SHORT...

    def should_exit(self, position, bar_idx: int) -> tuple:
        """Check if exit conditions are met"""
        # Exit logic...

    def position_size(self, capital: float, price: float, atr: float) -> float:
        """Calculate position size"""
        # Position sizing logic...
```

## Testing

### Running Tests

The compiler includes comprehensive unit tests that validate:

1. All 8 strategy templates compile successfully
2. Generated code has valid Python syntax
3. All required methods are present
4. All operators are correctly mapped
5. All position sizing methods work
6. All market filters work
7. All exit rules work
8. Only safe libraries are used

To run tests:

```bash
# Using pytest (if available)
pytest services/algo_builder/test_compiler.py -v

# Using the standalone test runner
python services/algo_builder/run_compiler_tests.py
```

### Test Coverage

The test suite includes:

- **Template Compilation Tests**: Compiles all 8 strategy templates
- **Operator Tests**: Tests each ConditionBlock operator
- **Position Sizing Tests**: Tests each position sizing method
- **Market Filter Tests**: Tests each market filter condition
- **Exit Rule Tests**: Tests each exit rule type
- **Safety Tests**: Validates only safe libraries are used
- **Syntax Tests**: Validates generated Python syntax

## Security

### Sandboxed Execution

The compiled code is designed for sandboxed execution with:

- **No filesystem access**: No `os`, `sys`, `subprocess` imports
- **No network access**: No `socket`, `requests`, `urllib`, `http` imports
- **30-second timeout**: Execution time limit
- **512MB memory limit**: Memory usage limit

### Safe Libraries Only

The compiler only generates imports for:

- `pandas` - Data manipulation
- `numpy` - Numerical operations
- `talib` - Technical analysis
- `datetime` - Date/time operations
- `math` - Mathematical functions
- `BaseStrategy` - Strategy base class

## Examples

### Example 1: Turtle Breakout Strategy

```python
# Turtle Breakout template compiles to:
# - Entry: price crosses_above highest_high_20
# - Exit: price crosses_below lowest_low_10
# - Sizing: atr_based

spec = StrategySpec(**turtle_template["spec"])
code = compiler.compile(spec)

# Generated code includes:
# - crosses_above('close', 'highest_high_20', bar_idx)
# - crosses_below('close', 'lowest_low_10', bar_idx)
# - ATR-based position sizing logic
```

### Example 2: Thorp Volatility Strategy

```python
# Thorp template compiles to:
# - Entry: iv_rank > 70 AND rsi_14 between 40,70
# - Exit: target 50% OR time 21 candles
# - Sizing: kelly

spec = StrategySpec(**thorp_template["spec"])
code = compiler.compile(spec)

# Generated code includes:
# - get_value('iv_rank', bar_idx) > 70
# - between('rsi_14', (40, 70), bar_idx)
# - Kelly Criterion position sizing
# - Target and time-based exits
```

### Example 3: Paul Tudor Jones Momentum

```python
# Jones template compiles to:
# - Entry: close > ema_200 AND rsi_14 crosses_above 50
# - Market Filter: require_above_200ema = True
# - Exit: rsi_14 < 40 OR close < ema_200

spec = StrategySpec(**jones_template["spec"])
code = compiler.compile(spec)

# Generated code includes:
# - Market filter checking ema_200
# - crosses_above('rsi_14', 50, bar_idx)
# - Multiple exit conditions
```

## Implementation Details

### Private Methods

The compiler uses several private methods to generate code sections:

1. **`_compile_indicators()`**: Generates indicator initialization code
2. **`_render_indicators()`**: Generates indicator computation code
3. **`_compile_entry_rules()`**: Converts entry rules to Python expressions
4. **`_compile_condition()`**: Maps ConditionBlock operators to Python
5. **`_compile_exit_rules()`**: Converts exit rules to Python code
6. **`_compile_position_sizing()`**: Generates position sizing logic
7. **`_compile_market_filter()`**: Generates market filter logic

### Operator Mapping

The `_compile_condition()` method maps operators as follows:

```python
# Simple comparisons
">" → "self.get_value('left', bar_idx) > self.get_value('right', bar_idx)"
"<" → "self.get_value('left', bar_idx) < self.get_value('right', bar_idx)"
"==" → "self.get_value('left', bar_idx) == self.get_value('right', bar_idx)"

# Special operators
"crosses_above" → "self.crosses_above('left', 'right', bar_idx)"
"crosses_below" → "self.crosses_below('left', 'right', bar_idx)"
"between" → "self.between('left', (lower, upper), bar_idx)"
```

### Position Sizing Logic

Each position sizing method generates different code:

```python
# fixed_capital
size = <value>

# pct_capital
size = capital * (<value> / 100)

# kelly
kelly_fraction = <value>
size = capital * kelly_fraction

# atr_based
risk_amount = capital * self.risk_per_trade
size = risk_amount / atr if atr > 0 else capital * 0.01

# vol_adj
base_size = capital * (<value> / 100)
vol_adjustment = avg_atr / atr if atr > 0 else 1.0
size = base_size * vol_adjustment
```

All methods enforce the maximum position cap:

```python
max_size = capital * (max_position_pct / 100)
size = min(size, max_size)
```

## Validation

The compiler validates generated code by:

1. **Syntax Check**: Uses `ast.parse()` to validate Python syntax
2. **Structure Check**: Ensures all required methods are present
3. **Import Check**: Ensures only safe libraries are imported
4. **Logic Check**: Ensures conditions compile to valid expressions

If validation fails, the compiler raises:

- `SyntaxError`: If generated code has syntax errors
- `ValueError`: If the spec is invalid

## Future Enhancements

Potential future improvements:

1. **Optimization**: Optimize generated code for performance
2. **Type Hints**: Add type hints to generated code
3. **Documentation**: Generate docstrings for compiled methods
4. **Validation**: Add runtime validation of indicator availability
5. **Debugging**: Add debug logging to generated code

## Related Files

- `compiler.py`: Main compiler implementation
- `test_compiler.py`: Comprehensive unit tests
- `run_compiler_tests.py`: Standalone test runner
- `base_strategy.py`: Base class for compiled strategies
- `models.py`: Pydantic models for StrategySpec
- `006_strategy_templates.py`: 8 pre-built strategy templates

## Requirements Satisfied

This implementation satisfies:

- **Requirement 3.1**: StrategyCompiler converts StrategySpec to Python class string
- **Requirement 3.2**: Compiled code implements all required methods and uses only safe libraries
