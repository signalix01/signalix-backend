# Vectorised Backtesting Engine

## Overview

The Vectorised Backtesting Engine provides fast, efficient backtesting using vectorbt for signal-to-result computation. This engine can backtest 10+ years of daily data in seconds using vectorised operations.

## Features

- **Fast Execution**: Vectorised operations for 10+ years in < 10 seconds
- **Comprehensive Metrics**: All performance, risk, and trade statistics
- **Transaction Costs**: Accurate modeling of brokerage, STT, and GST
- **Kelly Criterion**: Optimal position sizing calculation
- **Trade Analysis**: Complete trade list with entry/exit details
- **Equity Curve**: Daily portfolio value tracking
- **Drawdown Analysis**: Maximum and average drawdown metrics

## Installation

### Prerequisites

```bash
# Install required packages
pip install -r requirements.txt
```

### Dependencies

- `vectorbt==0.26.2` - Vectorised backtesting library
- `TA-Lib==0.4.28` - Technical analysis indicators
- `pandas>=2.1.4` - Data manipulation
- `numpy>=1.26.3` - Numerical operations

### TA-Lib Installation

**Windows:**
```bash
pip install TA-Lib
```

**Linux/Mac:**
```bash
# Install system library first
sudo apt-get install ta-lib  # Ubuntu/Debian
brew install ta-lib          # macOS

# Then install Python wrapper
pip install TA-Lib
```

## Quick Start

### 1. Basic Usage

```python
from services.backtesting.vectorised_engine import VectorisedEngine
from services.backtesting.models import BacktestConfig, BacktestMode
from services.backtesting.data_pipeline import BacktestDataPipeline

# Fetch data
pipeline = BacktestDataPipeline()
data = await pipeline.get_backtest_data(
    instrument="BANKNIFTY",
    start="2019-01-01",
    end="2023-12-31",
    timeframe="1D",
    asset_class="NSE_EQUITY"
)

# Configure backtest
config = BacktestConfig(
    strategy_spec=my_strategy,
    instrument="BANKNIFTY",
    start_date="2019-01-01",
    end_date="2023-12-31",
    initial_capital=100000.0,
    mode=BacktestMode.VECTORISED
)

# Run backtest
engine = VectorisedEngine()
result = engine.run(spec=my_strategy, data=data, config=config)

# Access results
print(f"Total Return: {result.total_return_pct:.2f}%")
print(f"Sharpe Ratio: {result.sharpe_ratio:.2f}")
print(f"Total Trades: {result.total_trades}")
```

### 2. Running the Example

```bash
# Run the complete example
python services/backtesting/example_vectorised_backtest.py

# Run the test suite
python services/backtesting/run_vectorised_test.py
```

## Configuration

### BacktestConfig Parameters

```python
BacktestConfig(
    strategy_spec: StrategySpec,      # Strategy specification
    instrument: str,                   # Symbol/ticker
    start_date: str,                   # ISO date (YYYY-MM-DD)
    end_date: str,                     # ISO date (YYYY-MM-DD)
    initial_capital: float,            # Initial capital in Rs/USD
    mode: BacktestMode,                # VECTORISED or EVENT_DRIVEN
    
    # Transaction costs
    slippage_value: float = 0.05,      # 0.05% slippage
    brokerage_pct: float = 0.03,       # 0.03% brokerage
    brokerage_fixed: float = 20.0,     # Rs 20 per order
    stt_rate: float = 0.025,           # 0.025% STT
    gst_rate: float = 18.0,            # 18% GST on brokerage
    
    # Validation settings
    run_walk_forward: bool = True,
    run_monte_carlo: bool = False,
    run_regime_analysis: bool = True
)
```

### Transaction Cost Models

**Angel One Intraday:**
- Brokerage: 0.03%
- STT: 0.025%
- GST: 18% on brokerage

**Zerodha Equity Delivery:**
- Brokerage: Rs 20 per order (flat)
- STT: 0.1%
- GST: 18% on brokerage

**Zerodha Intraday:**
- Brokerage: 0.03% or Rs 20 (whichever is lower)
- STT: 0.025%
- GST: 18% on brokerage

## Results

### BacktestResult Fields

**Performance Metrics:**
- `total_return_pct`: Total return percentage
- `cagr_pct`: Compound Annual Growth Rate
- `sharpe_ratio`: Risk-adjusted return (target: > 1.5)
- `sortino_ratio`: Downside risk-adjusted return (target: > 2.0)
- `calmar_ratio`: CAGR / Max Drawdown

**Drawdown Metrics:**
- `max_drawdown_pct`: Maximum drawdown (alert if > 15%)
- `avg_drawdown_pct`: Average drawdown
- `max_drawdown_duration_days`: Longest drawdown period

**Trade Statistics:**
- `total_trades`: Number of trades
- `win_rate_pct`: Percentage of winning trades
- `avg_win_pct`: Average winning trade return
- `avg_loss_pct`: Average losing trade return
- `profit_factor`: Gross profit / Gross loss (target: > 1.5)
- `expectancy_per_trade`: Expected profit per trade
- `avg_hold_days`: Average holding period
- `max_consecutive_losses`: Maximum losing streak

**Risk Metrics:**
- `kelly_fraction`: Optimal position size (Kelly Criterion)
- `half_kelly`: Conservative position size (Half-Kelly)

**Data:**
- `trades`: List of all trades with details
- `equity_curve`: Daily portfolio values
- `drawdown_curve`: Daily drawdown percentages

## Performance Targets

Based on the Trader Council principles:

| Metric | Target | Rationale |
|--------|--------|-----------|
| Sharpe Ratio | > 1.5 | Acceptable risk-adjusted returns |
| Sortino Ratio | > 2.0 | Good downside risk management |
| Max Drawdown | < 15% | Druckenmiller's risk limit |
| Profit Factor | > 1.5 | Sustainable edge |
| Win Rate | > 40% | Trend-following baseline |

## Examples

### Example 1: Turtle Breakout Strategy

```python
# See: example_vectorised_backtest.py
# Implements Richard Dennis's Turtle Trading System
# Entry: Price above 50 EMA
# Exit: 2% stop loss
# Results: Sharpe > 0, positive CAGR on trending data
```

### Example 2: RSI Mean Reversion

```python
# Entry: RSI crosses above 30 (oversold)
# Exit: RSI crosses below 70 (overbought)
# Position Size: 10% of capital
# Results: Works well in ranging markets
```

## Testing

### Unit Tests

```bash
# Run pytest tests (requires pytest)
pytest services/backtesting/test_vectorised_engine.py -v

# Run standalone test
python services/backtesting/run_vectorised_test.py
```

### Test Coverage

- ✅ Engine initialization
- ✅ Complete backtest execution
- ✅ Sharpe ratio calculation
- ✅ Trade list generation
- ✅ Kelly Criterion calculation
- ✅ Transaction cost application
- ✅ Equity curve extraction
- ✅ Drawdown analysis

## Integration

### With Data Pipeline

```python
from services.backtesting.data_pipeline import BacktestDataPipeline

pipeline = BacktestDataPipeline(db_connection=db, redis_client=redis)
data = await pipeline.get_backtest_data(
    instrument="BANKNIFTY",
    start="2019-01-01",
    end="2023-12-31",
    timeframe="1D",
    asset_class="NSE_EQUITY"
)
```

### With Strategy Compiler

```python
from services.algo_builder.compiler import StrategyCompiler

compiler = StrategyCompiler()
compiled_code = compiler.compile(strategy_spec)

# The vectorised engine will use the compiled strategy
# for signal generation in future versions
```

### With Database

```python
from shared.database.models import BacktestResult as DBBacktestResult

# Store result in database
db_result = DBBacktestResult(
    strategy_id=result.strategy_id,
    instrument=result.instrument,
    total_return_pct=result.total_return_pct,
    sharpe_ratio=result.sharpe_ratio,
    # ... other fields
)
await db.add(db_result)
```

## Limitations

### Current Limitations

1. **Signal Generation**: Simplified implementation; full StrategyCompiler integration pending
2. **Fixed Brokerage**: Not yet incorporated per-trade (only percentage-based)
3. **Slippage**: Not modeled in vectorised mode (use event-driven for realism)
4. **Partial Fills**: Not modeled (use event-driven engine)
5. **Intraday Data**: Currently optimized for daily data

### When to Use Event-Driven Engine

Use the event-driven engine (Task 15) for:
- Realistic slippage modeling
- Partial fill simulation
- Overnight gap risk
- Circuit breaker simulation
- F&O lot-size rounding
- High-frequency strategies

## Troubleshooting

### vectorbt Not Installed

**Error:**
```
WARNING:root:vectorbt not installed. Install with: pip install vectorbt
```

**Solution:**
```bash
pip install vectorbt
```

### TA-Lib Import Error

**Error:**
```
ModuleNotFoundError: No module named 'talib'
```

**Solution:**
```bash
# Windows
pip install TA-Lib

# Linux
sudo apt-get install ta-lib
pip install TA-Lib

# macOS
brew install ta-lib
pip install TA-Lib
```

### Memory Issues

**Error:**
```
MemoryError: Unable to allocate array
```

**Solution:**
- Reduce date range
- Use smaller timeframe
- Increase system memory
- Use event-driven engine for large datasets

## References

### Design Documents

- `design_algo_backend.md`: Complete architecture specification
- `requirements_algo_backend.md`: Detailed requirements
- `tasks_algo_backend.md`: Implementation tasks

### Related Tasks

- Task 12: Data Pipeline (completed)
- Task 13: SuperTrend Indicator (completed)
- Task 14: Vectorised Engine (this task)
- Task 15: Event-Driven Engine (next)
- Task 16: Walk-Forward Validation (next)
- Task 17: Monte Carlo Simulation (next)
- Task 18: Regime Analysis (next)

### External Resources

- [vectorbt Documentation](https://vectorbt.dev/)
- [TA-Lib Documentation](https://mrjbq7.github.io/ta-lib/)
- [Kelly Criterion](https://en.wikipedia.org/wiki/Kelly_criterion)
- [Sharpe Ratio](https://en.wikipedia.org/wiki/Sharpe_ratio)

## Support

For issues or questions:
1. Check the troubleshooting section
2. Review the example code
3. Run the test suite
4. Check the design documents

## License

Part of the Signalix platform. All rights reserved.
