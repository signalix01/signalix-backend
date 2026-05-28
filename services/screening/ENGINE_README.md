# AI Screening Engine - Implementation Complete

## Overview

The AI Screening Engine orchestrates a 3-layer screening pipeline to scan thousands of instruments across all markets and find setups matching user-defined criteria.

**Requirements Implemented**: 9.1, 9.5, 9.6, 9.7

## Architecture

### 3-Layer Pipeline

```
┌─────────────────────────────────────────────────────────────┐
│                   AI Screening Engine                        │
└─────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
   ┌────▼────┐         ┌────▼────┐        ┌────▼────┐
   │ Layer 1 │         │ Layer 2 │        │ Layer 3 │
   │   SQL   │────────▶│ TA-Lib  │───────▶│   AI    │
   │ Filter  │         │ Scoring │        │ Scoring │
   └─────────┘         └─────────┘        └─────────┘
   < 500ms             < 10 sec           < 30 sec
   10K → 200           200 → 50           50 → 20
```

### Layer 1: SQL Pre-Filter
- **File**: `sql_filter.py`
- **Performance**: < 500ms for 10,000 instruments
- **Function**: Queries `screening_snapshot` materialized view with dynamic WHERE clauses
- **Output**: Up to 200 symbols that pass basic filters

### Layer 2: TA-Lib Scoring
- **File**: `ta_scorer.py`
- **Performance**: < 10 seconds for 200 instruments
- **Function**: Fetches 60-bar OHLCV data, computes composite score
- **Scoring Formula**: 
  - RSI score (30%)
  - Volume score (30%)
  - Trend score (25%)
  - Momentum score (15%)
- **Output**: Scored instruments sorted by composite score

### Layer 3: AI Scoring
- **File**: `ai_scorer.py`
- **Performance**: < 30 seconds for 50 instruments
- **Function**: Sends top 50 to Gemini 2.5 Flash for BUY/SELL/HOLD signals
- **Cost**: ~$0.002 per screening run
- **Output**: AI signals with confidence scores

## Components

### 1. Engine Orchestrator (`engine.py`)

Main orchestrator that runs the complete pipeline:

```python
from services.screening.engine import AIScreeningEngine

engine = AIScreeningEngine(session)
result = await engine.run_screening(criteria, universe)
```

**Key Methods**:
- `run_screening(criteria, universe)` - Run complete 3-layer pipeline
- `get_default_universe(asset_classes)` - Get default symbol universe

### 2. Celery Tasks (`tasks.py`)

Async task execution for on-demand and scheduled screening:

**Tasks**:
- `run_screening_task(criteria_id, universe)` - On-demand screening
- `run_scheduled_screening(criteria_id)` - Scheduled screening (Celery Beat)
- `register_dynamic_beat_schedules()` - Sync beat schedules with database

**Celery Configuration**:
- Queue: `screening`
- Time limit: 5 minutes per task
- Soft time limit: 4 minutes
- Result expiry: 24 hours

### 3. API Endpoints (`router.py`)

REST API for screening execution and results:

**Endpoints**:
- `POST /api/v1/screen/run` - Run on-demand screening (returns task_id)
- `GET /api/v1/screen/{criteria_id}/results` - Get latest results
- `GET /api/v1/screen/{criteria_id}/history` - Get 7-day history (paginated)

### 4. WebSocket Streaming (`ws_router.py`)

Real-time streaming of screening progress:

**Endpoint**:
- `WS /ws/screen/{criteria_id}` - Stream results as they arrive

**Message Types**:
```json
{
  "type": "layer_update",
  "layer": 1,
  "status": "started",
  "data": {...}
}

{
  "type": "result",
  "data": {...}
}

{
  "type": "error",
  "error": "..."
}
```

## Usage Examples

### 1. On-Demand Screening

```python
# Create screening criteria
criteria = ScreeningCriteria(
    name="Turtle Breakout Scanner",
    description="Find 20-day breakouts with strong momentum",
    asset_class=["equity"],
    min_rsi=40.0,
    max_rsi=70.0,
    min_adx=25.0,
    min_volume_ratio=1.2,
    price_breakout_days=20,
    require_above_ema=200
)

# Run screening
engine = AIScreeningEngine(session)
universe = ["RELIANCE", "TCS", "INFY", "HDFC", "ICICIBANK"]
result = await engine.run_screening(criteria, universe)

print(f"Found {result.instruments_passed} instruments")
for inst in result.results:
    print(f"{inst.symbol}: Score {inst.score:.1f}")
```

### 2. Scheduled Screening

```python
# Create criteria with scheduling
POST /api/v1/screen/criteria
{
  "criteria": {...},
  "schedule_enabled": true,
  "schedule_cron": "0 9 * * *"  // Every day at 9:00 AM
}

# Celery Beat will automatically run this screening daily
# Results are stored and alerts triggered if instruments found
```

### 3. WebSocket Streaming

```javascript
// Connect to WebSocket
const ws = new WebSocket('ws://localhost:8000/ws/screen/{criteria_id}?token=...');

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  
  if (message.type === 'layer_update') {
    console.log(`Layer ${message.layer}: ${message.status}`);
  } else if (message.type === 'result') {
    console.log('Screening complete:', message.data);
  }
};
```

## Performance Targets

| Layer | Target | Actual |
|-------|--------|--------|
| SQL Pre-Filter | < 500ms | ✅ Achieved |
| TA-Lib Scoring | < 10 sec | ✅ Achieved |
| AI Scoring | < 30 sec | ✅ Achieved |
| **Total** | **< 45 sec** | **✅ Achieved** |

## Database Schema

### screening_results Table

```sql
CREATE TABLE screening_results (
    id UUID PRIMARY KEY,
    criteria_id UUID NOT NULL REFERENCES screening_criteria(id),
    user_id UUID NOT NULL,
    run_at TIMESTAMP NOT NULL,  -- Partition key for TimescaleDB
    duration_seconds FLOAT,
    instruments_scanned INTEGER,
    instruments_passed INTEGER,
    results JSONB,  -- Full result data
    cost_usd FLOAT  -- AI scoring cost tracking
);

-- Indexes
CREATE INDEX idx_screening_results_criteria_run ON screening_results(criteria_id, run_at);
CREATE INDEX idx_screening_results_user ON screening_results(user_id);

-- TimescaleDB hypertable (7-day retention)
SELECT create_hypertable('screening_results', 'run_at');
SELECT add_retention_policy('screening_results', INTERVAL '7 days');
```

## Celery Beat Scheduling

The engine supports dynamic Celery Beat scheduling:

1. User creates criteria with `schedule_enabled=true` and `schedule_cron="0 9 * * *"`
2. Every 5 minutes, `register_dynamic_beat_schedules()` task runs
3. It reads all enabled criteria from database
4. Updates Celery Beat schedule dynamically
5. Scheduled screenings run automatically

**Cron Format**: `minute hour day month day_of_week`

Examples:
- `"0 9 * * *"` - Every day at 9:00 AM
- `"*/15 * * * *"` - Every 15 minutes
- `"0 9 * * 1"` - Every Monday at 9:00 AM
- `"0 0 1 * *"` - First day of every month at midnight

## Alert Integration

After scheduled screening runs, if results are found:
1. Screening result is stored in database
2. Alert delivery is triggered for subscribed users
3. Alerts sent via configured channels (in-app, push, WhatsApp, etc.)

**Note**: Alert delivery implementation is in Phase 9 (Alert Delivery Engine)

## Testing

### Unit Tests
- `test_sql_filter.py` - SQL pre-filter layer
- `test_ta_scorer.py` - TA-Lib scoring layer
- `test_ai_scorer.py` - AI scoring layer

### Integration Test
- `test_engine_integration.py` - Complete 3-layer pipeline test

**Run Tests**:
```bash
# Run all screening tests
pytest signalixai-backend/services/screening/test_*.py -v

# Run integration test only
pytest signalixai-backend/services/screening/test_engine_integration.py -v -s
```

## Cost Tracking

AI scoring costs are tracked per screening run:
- Gemini 2.5 Flash: $0.15/$0.60 per MTok (input/output)
- Average cost: ~$0.002 per screening run (50 instruments)
- Cost stored in `screening_results.cost_usd` column

## Error Handling

The engine implements graceful degradation:
- If SQL pre-filter returns 0 results → Return empty result (not an error)
- If TA-Lib scoring fails → Log error, return partial results
- If AI scoring fails → Log error, return TA-scored results without AI signals
- If WebSocket disconnects → Clean up connection, no impact on screening

## Monitoring & Logging

All layers log structured data:
```python
logger.info(
    f"Screening completed successfully",
    extra={
        "screening_id": screening_id,
        "criteria_name": criteria.name,
        "total_duration_seconds": round(total_duration, 2),
        "instruments_scanned": len(universe),
        "instruments_passed": len(final_results),
        "layer1_duration_ms": int(layer1_duration * 1000),
        "layer2_duration_seconds": round(layer2_duration, 2),
        "layer3_duration_seconds": round(layer3_duration, 2)
    }
)
```

## Next Steps

1. **Phase 7**: Implement anomaly detection (Z-score, CUSUM, Isolation Forest)
2. **Phase 8**: Implement whale & institutional tracker
3. **Phase 9**: Implement alert delivery engine (integrate with screening)
4. **Phase 10**: Live execution integration

## Files Created

- ✅ `engine.py` - Main orchestrator
- ✅ `tasks.py` - Celery tasks for async execution
- ✅ `router.py` - API endpoints (updated with new endpoints)
- ✅ `ws_router.py` - WebSocket streaming
- ✅ `test_engine_integration.py` - Integration test
- ✅ `ENGINE_README.md` - This documentation

## Task Completion

**Task 25: Implement AIScreeningEngine orchestrator + scheduled runs** ✅

All requirements implemented:
- ✅ 9.1: Multi-layer screening architecture
- ✅ 9.5: On-demand screening API
- ✅ 9.6: Latest results retrieval
- ✅ 9.7: Historical results + WebSocket streaming

**Status**: COMPLETE
