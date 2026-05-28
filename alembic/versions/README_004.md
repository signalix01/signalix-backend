# Migration 004: Algo Builder, Backtesting, Screening & Alert Engine Schema

## Overview

This migration creates the complete database schema for four new institutional-grade systems:

1. **Algo Builder** - No-code strategy specification and compilation
2. **Backtesting Engine** - Vectorised and event-driven backtesting with walk-forward validation
3. **AI Screening Engine** - Multi-market asset screener with AI scoring
4. **Anomaly & Alert Engine** - Real-time statistical anomaly detection and whale tracking

## Requirements Addressed

- **Requirement 1.8**: Strategy specification storage with JSONB
- **Requirement 11.7**: Anomaly event storage in TimescaleDB
- **Requirement 16.2**: 90-day retention for anomaly_events (Pro tier), 30 days (free tier)
- **Requirement 16.3**: 7-day retention for screening_results

## Tables Created

### 1. `strategies`
Stores user-defined trading strategies with complete StrategySpec JSON.

**Key Columns:**
- `id` (UUID): Primary key
- `user_id` (UUID): Owner of the strategy
- `spec` (JSONB): Complete strategy specification
- `compiled_hash` (String): SHA-256 hash of compiled code for cache invalidation
- `status` (Enum): draft, testing, paper, live, deleted

**Indexes:**
- `idx_strategies_user_status`: Fast user strategy lookups by status
- `idx_strategies_compiled_hash`: Cache lookup by hash

### 2. `backtest_results`
Stores comprehensive backtest results including walk-forward, Monte Carlo, and regime analysis.

**Key Columns:**
- `id` (UUID): Primary key
- `strategy_id` (UUID): Foreign key to strategies
- `sharpe_ratio`, `sortino_ratio`, `calmar_ratio`: Risk-adjusted returns
- `wf_train_return`, `wf_validate_return`, `wf_test_return`: Walk-forward validation
- `mc_ruin_probability`: Monte Carlo ruin probability
- `result_data` (JSONB): Full trade list, equity curve, drawdown curve

**Indexes:**
- `idx_backtest_user_created`: User backtest history
- `idx_backtest_strategy_created`: Strategy backtest history

### 3. `screening_criteria`
Stores user-defined screening criteria with scheduling configuration.

**Key Columns:**
- `id` (UUID): Primary key
- `user_id` (UUID): Owner of the criteria
- `criteria_spec` (JSONB): Complete screening criteria
- `schedule_enabled` (Boolean): Enable scheduled runs
- `schedule_cron` (String): Cron expression for scheduling

**Indexes:**
- `idx_screening_criteria_user_active`: Active criteria lookup

### 4. `screening_results` (TimescaleDB Hypertable)
Stores screening results with automatic partitioning and retention.

**Key Columns:**
- `id` (UUID): Primary key
- `criteria_id` (UUID): Foreign key to screening_criteria
- `run_at` (DateTime): **Partition key** - when the screening ran
- `results` (JSONB): Full screening results
- `cost_usd` (Float): AI scoring cost tracking

**TimescaleDB Configuration:**
- **Partition by**: `run_at`
- **Chunk interval**: 7 days
- **Retention policy**: 7 days (automatic cleanup)

**Indexes:**
- `idx_screening_results_criteria_run`: Criteria result history

### 5. `anomaly_events` (TimescaleDB Hypertable)
Stores detected anomaly events with automatic partitioning and retention.

**Key Columns:**
- `id` (UUID): Primary key
- `instrument` (String): Symbol (e.g., "BANKNIFTY")
- `anomaly_type` (Enum): price_spike, volume_surge, whale_movement, etc.
- `severity` (Enum): low, medium, high, critical
- `detected_at` (DateTime): **Partition key** - when anomaly was detected
- `z_score` (Float): Statistical Z-score
- `raw_data` (JSONB): Full anomaly context

**TimescaleDB Configuration:**
- **Partition by**: `detected_at`
- **Chunk interval**: 1 day
- **Retention policy**: 90 days (default, tier-based at application level)

**Indexes:**
- `idx_anomaly_instrument_detected`: Instrument anomaly history
- `idx_anomaly_type_severity_detected`: Anomaly filtering by type and severity

### 6. `alert_rules`
Stores user-defined alert rules with delivery channel configuration.

**Key Columns:**
- `id` (UUID): Primary key
- `user_id` (UUID): Owner of the rule
- `instruments` (Array): Symbols to monitor (["ALL"] for all watchlisted)
- `anomaly_types` (Array): Types to alert on
- `channels` (Array): Delivery channels (in_app, push, email, etc.)
- `max_alerts_per_hour` (Integer): Rate limiting
- `quiet_hours_start`, `quiet_hours_end` (String): Quiet hours (IST)
- `webhook_url`, `webhook_secret` (String): Webhook configuration

**Indexes:**
- `idx_alert_rules_user_enabled`: Active rules lookup

### 7. `alert_delivery_log`
Logs all alert delivery attempts with latency tracking.

**Key Columns:**
- `id` (UUID): Primary key
- `anomaly_event_id` (UUID): Foreign key to anomaly_events
- `alert_rule_id` (UUID): Foreign key to alert_rules
- `channel` (String): Delivery channel used
- `status` (String): pending, sent, failed, retrying
- `detection_to_delivery_ms` (Integer): Latency tracking (Requirement 14.5)

**Indexes:**
- `idx_alert_delivery_user_created`: User delivery history
- `idx_alert_delivery_event_rule`: Event-rule delivery tracking

## TimescaleDB Features

### Hypertables
Two tables are configured as TimescaleDB hypertables for efficient time-series data management:

1. **`anomaly_events`**
   - Partitioned by `detected_at`
   - 1-day chunks for high-frequency anomaly detection
   - 90-day retention (configurable per user tier)

2. **`screening_results`**
   - Partitioned by `run_at`
   - 7-day chunks for scheduled screening runs
   - 7-day retention (automatic cleanup)

### Retention Policies
Automatic data cleanup based on age:
- `anomaly_events`: 90 days (Pro tier), 30 days (free tier) - enforced at application level
- `screening_results`: 7 days

### Benefits
- **Performance**: Automatic partitioning for fast time-range queries
- **Storage**: Automatic old data cleanup
- **Scalability**: Handles millions of events without degradation

## Running the Migration

### Prerequisites
1. PostgreSQL 14+ with TimescaleDB extension installed
2. Alembic configured with database connection

### Apply Migration
```bash
cd signalixai-backend
alembic upgrade head
```

### Verify Migration
```bash
python test_migration_004.py
```

### Rollback (if needed)
```bash
alembic downgrade -1
```

## Testing

The `test_migration_004.py` script verifies:
1. All 7 tables created
2. TimescaleDB hypertables configured correctly
3. Retention policies applied
4. All indexes created
5. Basic CRUD operations work
6. Foreign key constraints enforced

Run the test:
```bash
python test_migration_004.py
```

Expected output:
```
✓ Connected to database

=== Test 1: Verify Tables ===
✓ Table 'strategies' exists
✓ Table 'backtest_results' exists
✓ Table 'screening_criteria' exists
✓ Table 'screening_results' exists
✓ Table 'anomaly_events' exists
✓ Table 'alert_rules' exists
✓ Table 'alert_delivery_log' exists

=== Test 2: Verify TimescaleDB Hypertables ===
✓ Hypertable 'anomaly_events' configured
  - Partitioned by: detected_at
  - Chunk interval: 1 day
✓ Hypertable 'screening_results' configured
  - Partitioned by: run_at
  - Chunk interval: 7 days

...

✓ ALL TESTS PASSED
```

## Performance Considerations

### Indexes
All tables have appropriate indexes for common query patterns:
- User-scoped queries: `user_id` indexes
- Time-range queries: `created_at`, `detected_at`, `run_at` indexes
- Composite indexes for common filters

### JSONB Columns
Three tables use JSONB for flexible schema:
- `strategies.spec`: Strategy specification
- `backtest_results.result_data`: Full backtest results
- `anomaly_events.raw_data`: Anomaly context

Consider adding GIN indexes for JSONB queries if needed:
```sql
CREATE INDEX idx_strategies_spec_gin ON strategies USING GIN (spec);
```

### Query Optimization
For time-range queries on hypertables, always include the partition key:
```sql
-- Good: Uses partition pruning
SELECT * FROM anomaly_events 
WHERE detected_at >= NOW() - INTERVAL '7 days'
AND instrument = 'BANKNIFTY';

-- Bad: Full table scan
SELECT * FROM anomaly_events 
WHERE instrument = 'BANKNIFTY';
```

## Next Steps

After applying this migration:

1. **Task 2**: Create `screening_snapshot` materialized view
2. **Task 3**: Seed strategy templates
3. **Task 4**: Checkpoint - verify all database setup complete

## Troubleshooting

### TimescaleDB Extension Not Found
```
ERROR: extension "timescaledb" does not exist
```

**Solution**: Install TimescaleDB extension:
```sql
CREATE EXTENSION IF NOT EXISTS timescaledb;
```

### Hypertable Creation Fails
```
ERROR: table "anomaly_events" is not empty
```

**Solution**: Ensure tables are empty before converting to hypertables. The migration handles this automatically for new installations.

### Retention Policy Not Working
Check retention policy status:
```sql
SELECT * FROM timescaledb_information.jobs 
WHERE proc_name = 'policy_retention';
```

## Schema Diagram

```
┌─────────────┐
│ strategies  │
│             │
│ - id (PK)   │
│ - user_id   │◄────┐
│ - spec      │     │
│ - status    │     │
└─────────────┘     │
                    │
┌─────────────────┐ │
│backtest_results │ │
│                 │ │
│ - id (PK)       │ │
│ - strategy_id ──┼─┘
│ - user_id       │
│ - sharpe_ratio  │
│ - result_data   │
└─────────────────┘

┌──────────────────┐
│screening_criteria│
│                  │
│ - id (PK)        │
│ - user_id        │◄────┐
│ - criteria_spec  │     │
│ - schedule_cron  │     │
└──────────────────┘     │
                         │
┌──────────────────┐     │
│screening_results │     │
│ (HYPERTABLE)     │     │
│                  │     │
│ - id (PK)        │     │
│ - criteria_id ───┼─────┘
│ - run_at (⏰)    │
│ - results        │
└──────────────────┘

┌──────────────┐
│anomaly_events│
│ (HYPERTABLE) │
│              │
│ - id (PK)    │◄────┐
│ - instrument │     │
│ - detected_at│     │
│ - severity   │     │
└──────────────┘     │
                     │
┌─────────────┐      │
│alert_rules  │      │
│             │      │
│ - id (PK)   │◄──┐  │
│ - user_id   │   │  │
│ - channels  │   │  │
└─────────────┘   │  │
                  │  │
┌──────────────────┐ │
│alert_delivery_log│ │
│                  │ │
│ - id (PK)        │ │
│ - anomaly_evt_id─┼─┘
│ - alert_rule_id──┼─┘
│ - status         │
└──────────────────┘
```

## References

- **Design Document**: `.kiro/specs/Signalix_UX_.md/design_algo_backend.md`
- **Requirements**: `.kiro/specs/Signalix_UX_.md/requirements_algo_backend.md`
- **Tasks**: `.kiro/specs/Signalix_UX_.md/tasks_algo_backend.md`
- **TimescaleDB Docs**: https://docs.timescale.com/
