# Migration 005: Screening Snapshot Materialized View

## Overview

This migration creates the `screening_snapshot` materialized view that enables fast SQL pre-filtering for the AI Screening Engine. The view joins the `instruments` table with the latest `ohlcv_1d` record per symbol and includes all pre-computed technical indicators.

## Requirements

- **Requirement 9.3**: AI Screening Engine — Multi-Layer Architecture
- **Requirement 16.1**: Data Retention & Performance

## What This Migration Does

1. **Creates Base Tables** (if they don't exist):
   - `instruments`: Stores instrument metadata (symbol, name, exchange, asset_class, etc.)
   - `ohlcv_1d`: Stores daily OHLCV data with technical indicators (as TimescaleDB hypertable)

2. **Creates Materialized View**:
   - `screening_snapshot`: Joins instruments with latest OHLCV data per symbol
   - Includes all technical indicators needed for screening:
     - RSI (14-period)
     - EMAs (21, 50, 200)
     - ADX (14-period)
     - ATR (14-period)
     - Volume ratio (current volume / 20-day average)
     - Above EMA 200 flag
     - IV Rank (for F&O instruments)
     - PCR (Put-Call Ratio for F&O)
     - Composite score (weighted combination of all indicators)

3. **Creates Indexes**:
   - Unique index on `symbol` for fast lookups
   - Performance indexes on common filter columns (RSI, ADX, volume_ratio, composite_score)

4. **Creates Refresh Function**:
   - `refresh_screening_snapshot()`: Function to refresh the materialized view

## Running the Migration

```bash
cd signalixai-backend
alembic upgrade head
```

## Post-Migration Steps

### 1. Initial Refresh

After running the migration, perform an initial refresh of the materialized view:

```sql
REFRESH MATERIALIZED VIEW CONCURRENTLY screening_snapshot;
```

### 2. Configure Automatic Refresh (TimescaleDB Continuous Aggregate)

If using TimescaleDB 2.0+, you can configure automatic refresh every 15 minutes:

**Option A: Using TimescaleDB Continuous Aggregate Policy**

```sql
-- Add a refresh policy to update every 15 minutes
SELECT add_continuous_aggregate_policy('screening_snapshot',
    start_offset => INTERVAL '1 hour',
    end_offset => INTERVAL '15 minutes',
    schedule_interval => INTERVAL '15 minutes'
);
```

**Option B: Using PostgreSQL pg_cron Extension**

If TimescaleDB continuous aggregates are not available, use pg_cron:

```sql
-- Install pg_cron extension (if not already installed)
CREATE EXTENSION IF NOT EXISTS pg_cron;

-- Schedule refresh every 15 minutes during market hours (9:00 AM - 4:00 PM IST)
SELECT cron.schedule(
    'refresh-screening-snapshot',
    '*/15 9-16 * * 1-5',  -- Every 15 minutes, 9 AM to 4 PM, Monday to Friday
    'REFRESH MATERIALIZED VIEW CONCURRENTLY screening_snapshot;'
);
```

**Option C: Using Application-Level Scheduler (Celery Beat)**

Add to your Celery beat schedule:

```python
# In your Celery configuration
from celery.schedules import crontab

beat_schedule = {
    'refresh-screening-snapshot': {
        'task': 'services.screening.tasks.refresh_screening_snapshot',
        'schedule': crontab(minute='*/15', hour='9-16', day_of_week='1-5'),
    },
}
```

And create the Celery task:

```python
# services/screening/tasks.py
from celery import shared_task
from sqlalchemy import text
from database import engine

@shared_task
def refresh_screening_snapshot():
    """Refresh the screening_snapshot materialized view"""
    with engine.connect() as conn:
        conn.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY screening_snapshot;"))
        conn.commit()
    return "screening_snapshot refreshed"
```

## Testing

Run the test script to verify the materialized view works correctly:

```bash
cd signalixai-backend
python tests/test_screening_snapshot.py
```

The test script will:
1. Verify the materialized view exists
2. Verify the unique index on symbol exists
3. Insert test data for 5 symbols
4. Refresh the materialized view
5. Verify all required indicator columns are present
6. Test SQL pre-filtering performance (should be < 500ms)
7. Verify the unique constraint on symbol

## Performance Expectations

According to Requirement 9.2, the SQL pre-filter layer should:
- Complete in < 500ms for 10,000 instruments
- Return up to 200 symbols passing filters

The materialized view with proper indexes should easily meet this requirement.

## Data Flow

```
┌─────────────┐     ┌──────────────┐
│ instruments │     │  ohlcv_1d    │
│             │     │ (hypertable) │
└──────┬──────┘     └──────┬───────┘
       │                   │
       │    JOIN (latest   │
       │     record per    │
       │      symbol)      │
       └────────┬──────────┘
                │
                ▼
    ┌───────────────────────┐
    │ screening_snapshot    │
    │ (materialized view)   │
    │                       │
    │ - Refreshed every     │
    │   15 minutes          │
    │ - Unique index on     │
    │   symbol              │
    │ - Performance indexes │
    │   on filter columns   │
    └───────────────────────┘
                │
                ▼
    ┌───────────────────────┐
    │ AI Screening Engine   │
    │ SQL Pre-Filter Layer  │
    │ (< 500ms for 10K)     │
    └───────────────────────┘
```

## Rollback

To rollback this migration:

```bash
alembic downgrade -1
```

This will:
- Drop the `screening_snapshot` materialized view
- Drop the `refresh_screening_snapshot()` function
- **Note**: Base tables (`instruments`, `ohlcv_1d`) are NOT dropped as they may be used elsewhere

## Troubleshooting

### Issue: Materialized view is empty

**Solution**: Ensure the `instruments` and `ohlcv_1d` tables have data, then refresh:

```sql
REFRESH MATERIALIZED VIEW CONCURRENTLY screening_snapshot;
```

### Issue: Refresh is slow

**Solution**: Ensure indexes exist on `ohlcv_1d`:

```sql
CREATE INDEX IF NOT EXISTS idx_ohlcv_1d_symbol_timestamp 
ON ohlcv_1d (symbol, timestamp DESC);
```

### Issue: "CONCURRENTLY" refresh fails

**Solution**: The CONCURRENTLY option requires a unique index. Ensure the unique index on symbol exists:

```sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_screening_snapshot_symbol 
ON screening_snapshot (symbol);
```

If the unique index cannot be created (due to duplicate symbols), use non-concurrent refresh:

```sql
REFRESH MATERIALIZED VIEW screening_snapshot;
```

## Related Files

- Migration: `alembic/versions/005_screening_snapshot_view.py`
- Test: `tests/test_screening_snapshot.py`
- Design: `.kiro/specs/Signalix_UX_.md/design_algo_backend.md`
- Requirements: `.kiro/specs/Signalix_UX_.md/requirements_algo_backend.md`

## Next Steps

After this migration:
1. Implement the SQL pre-filter layer in `services/screening/sql_filter.py` (Task 22)
2. Implement the TA-Lib scoring layer in `services/screening/ta_scorer.py` (Task 23)
3. Implement the AI scoring layer in `services/screening/ai_scorer.py` (Task 24)
