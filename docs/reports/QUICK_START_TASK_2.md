# Quick Start: Task 2 - screening_snapshot Materialized View

## What Was Done

Created the `screening_snapshot` materialized view for fast SQL pre-filtering in the AI Screening Engine.

## Files Created

1. **Migration**: `alembic/versions/005_screening_snapshot_view.py`
2. **Test**: `tests/test_screening_snapshot.py`
3. **Runner**: `run_migration_005.py`
4. **Docs**: `alembic/versions/README_005.md`
5. **Summary**: `TASK_2_IMPLEMENTATION_SUMMARY.md`

## Quick Deploy (3 Steps)

### Step 1: Run Migration

```bash
cd signalixai-backend

# Option A: Using Alembic
alembic upgrade head

# Option B: Using standalone script
python run_migration_005.py
```

### Step 2: Initial Refresh

Connect to your database and run:

```sql
REFRESH MATERIALIZED VIEW CONCURRENTLY screening_snapshot;
```

### Step 3: Configure Auto-Refresh (Choose One)

**Option A: TimescaleDB (Recommended)**
```sql
SELECT add_continuous_aggregate_policy('screening_snapshot',
    start_offset => INTERVAL '1 hour',
    end_offset => INTERVAL '15 minutes',
    schedule_interval => INTERVAL '15 minutes'
);
```

**Option B: pg_cron**
```sql
CREATE EXTENSION IF NOT EXISTS pg_cron;
SELECT cron.schedule(
    'refresh-screening-snapshot',
    '*/15 9-16 * * 1-5',
    'REFRESH MATERIALIZED VIEW CONCURRENTLY screening_snapshot;'
);
```

**Option C: Celery Beat**
```python
# Add to celery config
beat_schedule = {
    'refresh-screening-snapshot': {
        'task': 'services.screening.tasks.refresh_screening_snapshot',
        'schedule': crontab(minute='*/15', hour='9-16', day_of_week='1-5'),
    },
}
```

## Verify Installation

```bash
python tests/test_screening_snapshot.py
```

Expected: All 8 tests pass ✓

## What's Next

Task 2 is complete! Next tasks:

- **Task 3**: Create strategy templates seed data
- **Task 22**: Implement SQL pre-filter layer (uses this view)
- **Task 23**: Implement TA-Lib scoring layer
- **Task 24**: Implement AI scoring layer

## Need Help?

See `TASK_2_IMPLEMENTATION_SUMMARY.md` for full details and troubleshooting.
