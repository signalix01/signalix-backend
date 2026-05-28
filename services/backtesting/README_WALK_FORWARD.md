# Walk-Forward Validation

## Overview

Walk-forward validation is a critical technique for detecting overfitting in trading strategies. It implements Edward Thorp's principle: *"A strategy not tested on unseen data is a curve-fit fantasy."*

This module splits historical data into three non-overlapping periods and runs the strategy on each independently to assess robustness.

## Implementation

### Module: `walk_forward.py`

**Location:** `signalixai-backend/services/backtesting/walk_forward.py`

**Key Components:**

1. **WalkForwardResult** - Pydantic model containing:
   - `train`: BacktestResult for training period (70%)
   - `validation`: BacktestResult for validation period (15%)
   - `test`: BacktestResult for test period (15%)
   - `consistency_score`: 0.0-1.0 metric measuring performance consistency
   - `is_robust`: Boolean flag indicating if strategy passes robustness checks
   - `warnings`: List of warning messages
   - `overfitting_detected`: Boolean flag for suspected overfitting

2. **WalkForwardValidator** - Main validation class with methods:
   - `validate()`: Runs complete walk-forward validation
   - `_split_data()`: Splits data into three periods by index
   - `_run_period()`: Runs backtest on a single period
   - `_compute_consistency_score()`: Calculates consistency metric

## Data Split

The validator splits data into three non-overlapping periods:

```
|<-------- 70% Train -------->|<-- 15% Validate -->|<-- 15% Test -->|
```

- **Train Period (70%)**: Used to develop/optimize the strategy
- **Validation Period (15%)**: Used to validate parameter choices
- **Test Period (15%)**: Out-of-sample data - the true test of robustness

## Consistency Score

The consistency score measures how well the strategy performs across all three periods:

**Formula:**
```python
if all periods have positive returns:
    degradation = abs((train_sharpe - test_sharpe) / train_sharpe)
    consistency_score = max(0, 1 - degradation)
else:
    consistency_score = 0.0
```

**Interpretation:**
- `1.0`: Perfect consistency (no degradation from train to test)
- `0.7-1.0`: Good consistency (acceptable strategy)
- `< 0.7`: Poor consistency (likely overfitting)
- `0.0`: At least one period has negative returns

## Warning Flags

### Low Consistency Warning
**Trigger:** `consistency_score < 0.7`

**Message:** *"This strategy shows inconsistent performance across time periods. Consider simplifying the entry rules to avoid overfitting."*

### Overfitting Detection
**Trigger:** `train_sharpe > 2.0 AND test_sharpe < 0.5`

**Message:** *"CRITICAL: Highly suspected overfitting detected. Train period Sharpe > 2.0 but test period Sharpe < 0.5. This strategy is likely curve-fit to historical data."*

## Robustness Criteria

A strategy is considered **robust** if ALL of the following are true:
1. `consistency_score >= 0.7`
2. `test_sharpe_ratio > 1.0`
3. `overfitting_detected == False`

## Usage Example

```python
from services.backtesting.walk_forward import WalkForwardValidator
from services.backtesting.vectorised_engine import VectorisedEngine

# Initialize
validator = WalkForwardValidator()
engine = VectorisedEngine()

# Run validation
result = validator.validate(
    engine=engine,
    spec=strategy_spec,
    data=historical_data,
    config=backtest_config
)

# Check results
print(f"Consistency Score: {result.consistency_score:.3f}")
print(f"Is Robust: {result.is_robust}")

# Access individual period results
print(f"Train Return: {result.train.total_return_pct:.2f}%")
print(f"Validation Return: {result.validation.total_return_pct:.2f}%")
print(f"Test Return: {result.test.total_return_pct:.2f}%")

# Check warnings
for warning in result.warnings:
    print(f"⚠️  {warning}")
```

## Integration with Backtesting Engine

The walk-forward validator works with both backtesting engines:

1. **Vectorised Engine** (fast, for quick validation)
2. **Event-Driven Engine** (realistic, for final validation)

Simply pass the appropriate engine to the `validate()` method.

## Configuration

Walk-forward validation is controlled by `BacktestConfig` parameters:

```python
config = BacktestConfig(
    # ... other config ...
    run_walk_forward=True,      # Enable walk-forward validation
    wf_train_pct=0.70,          # 70% for training
    wf_validate_pct=0.15,       # 15% for validation
    wf_test_pct=0.15            # 15% for testing
)
```

## Testing

**Test File:** `test_walk_forward.py`

**Test Coverage:**
1. ✅ Validator initialization
2. ✅ Data split verification (70/15/15)
3. ✅ Three separate result objects returned
4. ✅ Consistency score calculation
5. ✅ Low consistency warning generation
6. ✅ Overfitting detection logic
7. ✅ Robustness check criteria

**Run Tests:**
```bash
# Run all tests
pytest signalixai-backend/services/backtesting/test_walk_forward.py -v

# Run specific test
pytest signalixai-backend/services/backtesting/test_walk_forward.py::test_walk_forward_three_separate_results -v

# Run with manual test script
python signalixai-backend/services/backtesting/test_walk_forward.py
```

## Requirements Satisfied

This implementation satisfies **Requirements 6.1-6.6**:

- ✅ **6.1**: Data split into train (70%), validate (15%), test (15%)
- ✅ **6.2**: Strategy run independently on each period
- ✅ **6.3**: Consistency score computed using specified formula
- ✅ **6.4**: Warning flag when consistency_score < 0.7
- ✅ **6.5**: Overfitting flag when train_sharpe > 2.0 AND test_sharpe < 0.5
- ✅ **6.6**: Test period result displayed as "headline" result

## Design Philosophy

This implementation follows the **Trader Council** principles:

- **Edward Thorp**: Mathematical rigor - every strategy must prove itself on unseen data
- **Richard Dennis**: Systematic approach - automated detection of curve-fitting
- **Stanley Druckenmiller**: Risk management - flag strategies before they lose money

## Performance

- **Vectorised Mode**: ~3x slower than single backtest (runs 3 separate backtests)
- **Event-Driven Mode**: ~3x slower than single backtest
- **Memory**: Minimal overhead (data is split by reference, not copied)

## Future Enhancements

Potential improvements for future versions:

1. **Rolling Walk-Forward**: Multiple train/test windows instead of single split
2. **Anchored Walk-Forward**: Expanding training window instead of fixed
3. **Monte Carlo Walk-Forward**: Combine with Monte Carlo simulation
4. **Regime-Aware Split**: Split by market regime instead of time
5. **Adaptive Thresholds**: Machine learning to determine optimal consistency thresholds

## References

- Thorp, E. (1966). *Beat the Dealer*
- Pardo, R. (2008). *The Evaluation and Optimization of Trading Strategies*
- Aronson, D. (2006). *Evidence-Based Technical Analysis*

---

**Status:** ✅ Implemented and Tested  
**Task:** Task 16 - Phase 5  
**Date:** 2024
