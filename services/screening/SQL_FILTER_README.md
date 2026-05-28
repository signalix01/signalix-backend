# SQL Pre-Filter Layer - Implementation Documentation

## Overview

The SQL Pre-Filter Layer is the first stage of the AI Screening Engine pipeline. It provides fast, SQL-based filtering against the `screening_snapshot` materialized view to quickly narrow down thousands of instruments to a manageable set (up to 200) that pass basic criteria.

**Requirements**: 9.2

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   AI Screening Engine                        │
│                                                              │
│  ┌────────────┐    ┌────────────┐    ┌────────────┐        │
│  │  Layer 1:  │───▶│  Layer 2:  │───▶│  Layer 3:  │        │
│  │ SQL Filter │    │ TA-Lib     │    │ Gemini AI  │        │
│  │ < 500ms    │    │ Scoring    │    │ Scoring    │        │
│  │ 10K → 200  │    │ < 10s      │    │ < 30s      │        │
│  └────────────┘    └────────────┘    └────────────┘        │
│         ▲                                                    │
│         │                                                    │
│  ┌──────┴──────────────────────────────────────────┐        │
│  │  screening_snapshot (TimescaleDB)               │        │
│  │  Materialized View (refreshed every 15 min)     │        │
│  └─────────────────────────────────────────────────┘        │
└─────────────────────────────────────────────────────────────┘
```

## Performance Targets

- **Query Execution**: < 500ms for 10,000 instruments
- **Timeout**: 5-second hard limit
- **Result Limit**: Maximum 200 symbols returned
- **Refresh Rate**: screening_snapshot refreshed every 15 minutes during market hours

## Implementation

### Core Class: `SQLPreFilter`

Located in: `signalixai-backend/services/screening/sql_filter.py`

```python
class SQLPreFilter:
    """
    SQL-based pre-filter for screening engine
    
    Queries the screening_snapshot materialized view to quickly filter
    thousands of instruments down to a manageable set (up to 200) that
    pass basic criteria.
    """
    
    async def filter(
        self,
        criteria: ScreeningCriteria,
        universe: List[str]
    ) -> List[str]:
        """
        Filter universe of symbols using SQL against screening_snapshot
        
        Returns up to 200 symbols that pass all filters.
        """
```

### Supported Filter Criteria

#### Technical Filters (All Markets)
- **RSI Bounds**: `min_rsi`, `max_rsi` (0-100)
- **EMA Position**: `require_above_ema` (e.g., 200 for 200-day EMA)
- **ADX**: `min_adx` (trending strength, 0-100)
- **Volume Ratio**: `min_volume_ratio` (vs 20-day average)
- **Price Breakout**: `price_breakout_days` (e.g., 52 for 52-week high)

#### Options-Specific Filters (F&O)
- **IV Rank**: `min_iv_rank`, `max_iv_rank` (0-100)
- **Put-Call Ratio**: `min_pcr`, `max_pcr`

#### Fundamental Filters (Equity Only)
- **Market Cap**: `min_market_cap_cr` (in crores)
- **P/E Ratio**: `max_pe_ratio`
- **ROE**: `min_roe_pct` (%)
- **Revenue Growth**: `min_revenue_growth_pct` (%)
- **Promoter Holding**: `min_promoter_holding_pct` (%)

#### Crypto-Specific Filters
- **Fear & Greed Index**: `min_fear_greed` (0-100)
- **Funding Rate**: `max_funding_rate`
- **On-Chain Netflow**: `min_on_chain_netflow_btc` (negative = bullish)

### Query Construction

The SQL pre-filter builds dynamic parameterized queries based on non-null criteria fields:

```sql
SELECT symbol 
FROM screening_snapshot 
WHERE symbol = ANY(:universe)
  AND rsi_14 >= :min_rsi
  AND rsi_14 <= :max_rsi
  AND close > ema_200
  AND adx_14 >= :min_adx
  AND volume_ratio >= :min_volume_ratio
ORDER BY composite_score DESC
LIMIT 200
```

**Key Features**:
- ✅ Parameterized queries (SQL injection safe)
- ✅ Dynamic WHERE clause construction
- ✅ Only includes non-null criteria
- ✅ Orders by composite_score DESC (best matches first)
- ✅ Hard limit of 200 results

### Timeout Handling

All queries are wrapped with a 5-second timeout using `asyncio.wait_for`:

```python
result = await asyncio.wait_for(
    self.session.execute(query, params),
    timeout=5.0
)
```

If a query exceeds 5 seconds, an `asyncio.TimeoutError` is raised.

## Usage Example

```python
from services.screening.sql_filter import SQLPreFilter
from services.screening.models import ScreeningCriteria

# Create criteria
criteria = ScreeningCriteria(
    name="Oversold Reversal Scanner",
    description="Find oversold stocks with strong fundamentals",
    asset_class=["equity"],
    min_rsi=20.0,
    max_rsi=35.0,
    require_above_ema=200,
    min_volume_ratio=1.5,
    min_market_cap_cr=1000.0
)

# Define universe
universe = ["RELIANCE", "TCS", "INFY", "HDFCBANK", ...]  # NSE 100

# Execute filter
async with AsyncSessionLocal() as session:
    sql_filter = SQLPreFilter(session)
    filtered_symbols = await sql_filter.filter(criteria, universe)
    
    print(f"Filtered {len(universe)} symbols down to {len(filtered_symbols)}")
    # Output: Filtered 100 symbols down to 15
```

## Testing

### Unit Tests (No Database Required)

Located in: `signalixai-backend/services/screening/test_sql_filter_unit.py`

Run with:
```bash
pytest signalixai-backend/services/screening/test_sql_filter_unit.py -v
```

**Test Coverage**:
- ✅ RSI bounds filtering
- ✅ Multiple combined conditions
- ✅ Empty universe handling
- ✅ 200 symbol limit enforcement
- ✅ Options-specific criteria
- ✅ Fundamental criteria
- ✅ Timeout enforcement
- ✅ EMA position filtering
- ✅ Breakout detection
- ✅ Result ordering by composite_score

**All 10 tests passed** ✓

### Integration Tests (Requires Database)

Located in: `signalixai-backend/services/screening/test_sql_filter.py`

Run with:
```bash
pytest signalixai-backend/services/screening/test_sql_filter.py -v
```

**Prerequisites**:
- PostgreSQL/TimescaleDB running
- `screening_snapshot` materialized view created
- Sample data populated

## Database Schema

### screening_snapshot Materialized View

Expected columns:
```sql
CREATE MATERIALIZED VIEW screening_snapshot AS
SELECT 
    symbol,
    exchange,
    close,
    -- Technical indicators
    rsi_14,
    ema_21, ema_50, ema_200,
    adx_14,
    volume_ratio,
    atr_14,
    -- Breakout detection
    highest_high_5, highest_high_10, highest_high_20, highest_high_52,
    -- Options data (F&O only)
    iv_rank,
    pcr,
    -- Fundamental data (equity only)
    market_cap_cr,
    pe_ratio,
    roe_pct,
    revenue_growth_pct,
    promoter_holding_pct,
    -- Crypto data
    fear_greed_index,
    funding_rate,
    on_chain_netflow_btc,
    -- Composite score
    composite_score
FROM ...
WITH DATA;

-- Refresh policy
CREATE POLICY refresh_screening_snapshot
ON screening_snapshot
FOR REFRESH
SCHEDULE INTERVAL '15 minutes';
```

## Utility Methods

### Get Available Columns

```python
columns = await sql_filter.get_available_columns()
print(columns)
# ['symbol', 'rsi_14', 'adx_14', 'volume_ratio', ...]
```

### Get Snapshot Statistics

```python
stats = await sql_filter.get_snapshot_stats()
print(stats)
# {
#   'total_symbols': 2000,
#   'symbols_by_exchange': {'NSE': 1800, 'BSE': 200}
# }
```

## Performance Optimization

### Indexes

Ensure the following indexes exist on `screening_snapshot`:

```sql
CREATE UNIQUE INDEX idx_screening_snapshot_symbol ON screening_snapshot(symbol);
CREATE INDEX idx_screening_snapshot_rsi ON screening_snapshot(rsi_14);
CREATE INDEX idx_screening_snapshot_adx ON screening_snapshot(adx_14);
CREATE INDEX idx_screening_snapshot_volume_ratio ON screening_snapshot(volume_ratio);
CREATE INDEX idx_screening_snapshot_composite_score ON screening_snapshot(composite_score DESC);
```

### Query Optimization Tips

1. **Use composite indexes** for frequently combined filters
2. **Refresh materialized view** during off-market hours when possible
3. **Partition by exchange** if dealing with > 10K symbols
4. **Monitor query execution time** using PostgreSQL's `EXPLAIN ANALYZE`

## Error Handling

### Timeout Errors

```python
try:
    result = await sql_filter.filter(criteria, universe)
except asyncio.TimeoutError:
    logger.error("SQL pre-filter timeout exceeded 5 seconds")
    # Fallback: return empty list or retry with simpler criteria
```

### Database Errors

```python
try:
    result = await sql_filter.filter(criteria, universe)
except Exception as e:
    logger.error(f"SQL pre-filter failed: {str(e)}")
    # Fallback: skip SQL layer and proceed to TA-Lib layer
```

## Logging

The SQL pre-filter logs the following events:

- **Query Built**: Logs criteria name, universe size, number of conditions
- **Query Completed**: Logs input/output sizes, filter ratio, duration
- **Timeout**: Logs criteria name, universe size, timeout duration
- **Error**: Logs criteria name, universe size, error message

Example log output:
```
INFO: SQL pre-filter query built
  criteria_name: "Oversold Reversal Scanner"
  universe_size: 100
  num_conditions: 5
  has_rsi_filter: True
  has_ema_filter: True

INFO: SQL pre-filter completed
  criteria_name: "Oversold Reversal Scanner"
  input_universe_size: 100
  output_symbols_count: 15
  filter_ratio: 15.0%
```

## Integration with Screening Engine

The SQL pre-filter is the first layer in the screening pipeline:

```python
# Layer 1: SQL Pre-Filter (< 500ms)
sql_filtered = await sql_filter.filter(criteria, universe)

# Layer 2: TA-Lib Scoring (< 10s)
scored = await ta_scorer.score(sql_filtered, criteria)

# Layer 3: AI Scoring (< 30s)
ai_scored = await ai_scorer.score(scored[:50], criteria)
```

## Future Enhancements

1. **Query Caching**: Cache frequent query patterns in Redis
2. **Adaptive Timeout**: Adjust timeout based on universe size
3. **Query Hints**: Add PostgreSQL query hints for complex filters
4. **Parallel Execution**: Split large universes into batches
5. **Real-time Updates**: Subscribe to screening_snapshot changes via LISTEN/NOTIFY

## References

- **Requirements**: Section 9.2 (AI Screening Engine — Multi-Layer Architecture)
- **Design Document**: `.kiro/specs/Signalix_UX_.md/design_algo_backend.md`
- **Tasks**: Task 22 in `.kiro/specs/Signalix_UX_.md/tasks_algo_backend.md`

## Support

For issues or questions:
1. Check test output: `pytest signalixai-backend/services/screening/test_sql_filter_unit.py -v`
2. Review logs for timeout or error messages
3. Verify `screening_snapshot` view exists and is populated
4. Check database connection and permissions

---

**Status**: ✅ Implemented and Tested  
**Last Updated**: 2025-01-15  
**Version**: 1.0.0
