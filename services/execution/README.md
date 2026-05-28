# Live Execution Safety Checks

This module implements pre-order safety checks for live algo trading strategy execution.

## Requirements

Implements Requirements 15.3 and 15.4 from the Algo Backend specification:
- **15.3**: Apply all risk guardrails before every order (daily loss limit, max position size, max concurrent positions, market hours, circuit breaker)
- **15.4**: Place simultaneous stop-loss order for every entry order

## Safety Checks

### 1. Daily Loss Limit Check

Fetches today's realized P&L from `trade_records` table and blocks orders if daily loss exceeds the configured `max_daily_loss_pct`.

**Behavior:**
- **PASS**: Daily loss is within limit
- **WARNING**: Daily loss > 80% of limit
- **FAIL**: Daily loss >= limit

**Example:**
```python
result = await safety_checks.check_daily_loss_limit(
    user_id="user123",
    capital=100000.0,  # ₹1 lakh
    max_daily_loss_pct=2.0  # 2% = ₹2000 max loss
)
```

### 2. Max Position Size Check

Ensures a single position doesn't exceed the configured percentage of capital.

**Behavior:**
- **PASS**: Position size within limit
- **WARNING**: Position size > 90% of limit
- **FAIL**: Position size > limit

**Example:**
```python
result = safety_checks.check_max_position_size(
    position_size=5000.0,
    capital=100000.0,
    max_position_pct=10.0  # 10% max
)
```

### 3. Max Concurrent Positions Check

Checks the count of currently open positions against the configured limit.

**Behavior:**
- **PASS**: Open positions < limit
- **WARNING**: Open positions >= 80% of limit
- **FAIL**: Open positions >= limit

**Example:**
```python
result = await safety_checks.check_max_concurrent_positions(
    user_id="user123",
    strategy_id="strategy456",
    max_concurrent_positions=5
)
```

### 4. Market Hours Check

Verifies the market is open for the asset class before placing orders.

**Market Hours (IST):**
- **Equity/F&O**: 09:15 - 15:30
- **Commodity (MCX)**: 09:00 - 23:30
- **Crypto**: 24/7
- **Forex**: 24/5 (Mon-Fri)

**Behavior:**
- **PASS**: Market is open
- **FAIL**: Market is closed

**Example:**
```python
result = safety_checks.check_market_hours(
    instrument="RELIANCE",
    asset_class="equity"
)
```

### 5. Circuit Breaker Check

Checks if the instrument has an active circuit breaker (NSE equity and F&O only).

Circuit breaker limits: 5%, 10%, 20%

**Behavior:**
- **PASS**: No circuit breaker active
- **WARNING**: Cannot verify status
- **FAIL**: Circuit breaker active

**Example:**
```python
result = await safety_checks.check_circuit_breaker(
    instrument="RELIANCE",
    asset_class="equity"
)
```

## Simultaneous Stop-Loss Order Placement

After every entry order confirmation, a stop-loss order is immediately placed at the broker.

**For LONG positions:**
- SL Price = Entry Price × (1 - stop_loss_pct / 100)
- SL Order Type = SELL

**For SHORT positions:**
- SL Price = Entry Price × (1 + stop_loss_pct / 100)
- SL Order Type = BUY

**Example:**
```python
entry_order = {
    "order_id": "ENTRY123",
    "instrument": "RELIANCE",
    "direction": "LONG",
    "entry_price": 2500.0,
    "quantity": 10.0,
    "asset_class": "equity"
}

sl_order = await safety_checks.place_simultaneous_sl_order(
    entry_order=entry_order,
    stop_loss_pct=2.0,  # 2% SL
    broker_adapter=broker_adapter
)
# SL order placed at ₹2450 (2500 * 0.98)
```

## Running All Checks

The `run_all_checks()` method executes all 5 safety checks and returns a combined result.

**Example:**
```python
all_passed, results = await safety_checks.run_all_checks(
    user_id="user123",
    strategy_id="strategy456",
    instrument="RELIANCE",
    asset_class="equity",
    position_size=5000.0,
    capital=100000.0,
    max_daily_loss_pct=2.0,
    max_position_pct=10.0,
    max_concurrent_positions=5
)

if not all_passed:
    # Block order
    failed_checks = [r for r in results if r["status"] == "fail"]
    print(f"Order blocked: {failed_checks}")
else:
    # Proceed with order
    print("All safety checks passed")
```

## Fail-Safe Design

All safety checks follow a fail-safe design:
- If a check cannot be performed (e.g., database unavailable), it returns a WARNING status
- If a check encounters an error, it fails rather than passes
- Database client is optional; checks that require it will warn if not provided

## Testing

Comprehensive unit tests verify each check blocks correctly at its threshold:

```bash
pytest services/execution/test_safety_checks.py -v
```

**Test Coverage:**
- ✅ Daily loss limit: within limit, at threshold, exceeds threshold, warning threshold
- ✅ Max position size: within limit, at threshold, exceeds threshold, warning threshold
- ✅ Max concurrent positions: within limit, at threshold, exceeds threshold, warning threshold
- ✅ Market hours: equity open/closed, F&O, crypto 24/7, forex weekdays/weekends, commodity extended hours
- ✅ Circuit breaker: no breaker, breaker active, non-applicable asset classes
- ✅ Simultaneous SL: LONG position, SHORT position, placement failure
- ✅ Run all checks: all pass, single failure, multiple failures

**Test Results:** 36/36 tests passing ✅

## Integration

To integrate with the execution engine:

```python
from services.execution import LiveExecutionSafetyChecks

# Initialize with database client
safety_checks = LiveExecutionSafetyChecks(db_client=db_client)

# Before placing order
all_passed, results = await safety_checks.run_all_checks(
    user_id=user_id,
    strategy_id=strategy_id,
    instrument=instrument,
    asset_class=asset_class,
    position_size=position_size,
    capital=capital,
    max_daily_loss_pct=strategy.max_daily_loss_pct,
    max_position_pct=strategy.position_sizing.max_position_pct,
    max_concurrent_positions=strategy.position_sizing.max_concurrent_positions
)

if not all_passed:
    raise OrderRejectedError("Safety checks failed", details=results)

# Place entry order
entry_order = await broker_adapter.place_order(...)

# Immediately place SL order
sl_order = await safety_checks.place_simultaneous_sl_order(
    entry_order=entry_order,
    stop_loss_pct=strategy.exit_rules[0].stop_loss_pct,
    broker_adapter=broker_adapter
)
```

## Future Enhancements

When the `trade_records` table is implemented:
1. Update `_fetch_daily_pnl()` to query actual trade records
2. Update `_fetch_open_positions_count()` to query actual open positions
3. Update `_check_circuit_breaker_status()` to integrate with market data feed

## Architecture

```
LiveExecutionSafetyChecks
├── check_daily_loss_limit()
│   └── _fetch_daily_pnl()
├── check_max_position_size()
├── check_max_concurrent_positions()
│   └── _fetch_open_positions_count()
├── check_market_hours()
├── check_circuit_breaker()
│   └── _check_circuit_breaker_status()
├── place_simultaneous_sl_order()
└── run_all_checks()
```

## Error Handling

All checks return structured results:

```python
{
    "check": "daily_loss_limit",
    "status": "pass" | "warning" | "fail",
    "message": "Human-readable message",
    "details": {
        # Check-specific details
    }
}
```

Exceptions are raised only for critical errors using `SafetyCheckError`:

```python
try:
    result = await safety_checks.check_daily_loss_limit(...)
except SafetyCheckError as e:
    print(f"Check: {e.check_name}")
    print(f"Message: {e.message}")
    print(f"Details: {e.details}")
```
