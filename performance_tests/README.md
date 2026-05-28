# Performance Benchmarking Suite

Comprehensive performance testing for the Signalix Algo Backend.

## Overview

This suite tests the performance of critical backend systems:

1. **Screening SQL Pre-Filter** - 100 concurrent requests, < 500ms target
2. **Backtest Horizontal Scaling** - 10 concurrent tasks, all complete successfully
3. **Anomaly Detection Pipeline** - 1,000 bars in 60s, process in < 30s
4. **Alert Delivery** - 100 critical events, p95 < 5s

## Requirements

### Python Dependencies

Install Locust for load testing:

```bash
pip install locust==2.20.0
```

Or install all test dependencies:

```bash
pip install -r requirements-test.txt
```

### System Requirements

- Backend services running on `http://localhost:8000`
- Database accessible (TimescaleDB/PostgreSQL)
- Redis accessible
- Celery workers running (for backtest tests)

## Quick Start

### Run All Benchmarks

```bash
cd signalixai-backend
python performance_tests/run_all_benchmarks.py
```

This will:
1. Run all 4 performance tests
2. Generate HTML reports in `performance_tests/reports/`
3. Create `PERFORMANCE_REPORT.md` with results

### Run Individual Tests

#### 1. Screening Load Test

```bash
locust -f performance_tests/locustfile_screening.py \
    --headless \
    --users 100 \
    --spawn-rate 10 \
    --run-time 2m \
    --host http://localhost:8000
```

**Target:** SQL pre-filter < 500ms under 100 concurrent users

#### 2. Backtest Load Test

```bash
locust -f performance_tests/locustfile_backtest.py \
    --headless \
    --users 10 \
    --spawn-rate 2 \
    --run-time 5m \
    --host http://localhost:8000
```

**Target:** All 10 concurrent backtests complete without errors

#### 3. Anomaly Pipeline Test

```bash
python performance_tests/test_anomaly_pipeline.py
```

**Target:** Process 1,000 bars (injected over 60s) within 30 seconds

#### 4. Alert Delivery Test

```bash
python performance_tests/test_alert_delivery.py
```

**Target:** P95 delivery latency < 5 seconds for 100 critical events

## Interactive Locust UI

For interactive load testing with real-time graphs:

```bash
# Screening test
locust -f performance_tests/locustfile_screening.py --host http://localhost:8000

# Backtest test
locust -f performance_tests/locustfile_backtest.py --host http://localhost:8000
```

Then open http://localhost:8089 in your browser.

## Test Configuration

### Screening Load Test

- **Users:** 100 concurrent
- **Duration:** 2 minutes
- **Endpoints:**
  - `POST /api/v1/screening/run` (simple criteria)
  - `POST /api/v1/screening/run` (complex criteria)
  - `GET /api/v1/screening/templates`
- **Success Criteria:** SQL pre-filter < 500ms

### Backtest Load Test

- **Users:** 10 concurrent
- **Duration:** 5 minutes
- **Endpoints:**
  - `POST /api/v1/backtest/run` (submit)
  - `GET /api/v1/backtest/status/{task_id}` (poll)
- **Success Criteria:** All 10 complete without errors

### Anomaly Pipeline Test

- **Bars:** 1,000 synthetic OHLCV bars
- **Injection:** Over 60 seconds
- **Symbols:** 10 different test symbols
- **Success Criteria:** Process all within 30 seconds

### Alert Delivery Test

- **Events:** 100 critical anomaly events
- **Severity:** CRITICAL
- **Channels:** in_app (WebSocket)
- **Success Criteria:** P95 latency < 5 seconds

## Output

### Console Output

All tests print detailed progress and results to console:

```
======================================================================
SCREENING LOAD TEST RESULTS
======================================================================
Total requests: 1,234
SQL PRE-FILTER PERFORMANCE STATISTICS
  Average time: 245.32ms
  P95 time: 387.45ms
  Target: < 500ms
  Status: ✅ PASS
======================================================================
```

### HTML Reports

Locust tests generate HTML reports in `performance_tests/reports/`:

- `screening_load_test.html`
- `backtest_load_test.html`

### CSV Data

Locust tests also generate CSV files for further analysis:

- `screening_load_test_stats.csv`
- `screening_load_test_failures.csv`
- `backtest_load_test_stats.csv`
- `backtest_load_test_failures.csv`

### Performance Report

The comprehensive report is generated at:

```
signalixai-backend/PERFORMANCE_REPORT.md
```

This includes:
- Executive summary
- Detailed results for each test
- Requirements validation
- Recommendations

## Requirements Mapping

| Test | Requirements | Description |
|------|--------------|-------------|
| Screening Load Test | 16.2 | SQL pre-filter < 500ms for 10K instruments |
| Backtest Load Test | 16.5 | Horizontal scaling of backtest workers |
| Anomaly Pipeline | 16.4 | Process all watchlist instruments within 30s |
| Alert Delivery | 14.5, 16.5 | P95 delivery < 5s for critical alerts |

## Troubleshooting

### Backend Not Running

```
Error: Connection refused
```

**Solution:** Start the backend services:

```bash
cd signalixai-backend
uvicorn gateway:app --reload
```

### Celery Workers Not Running

```
Error: Backtest tasks not processing
```

**Solution:** Start Celery workers:

```bash
cd signalixai-backend/services/backtesting
celery -A celery_app worker --loglevel=info
```

### Database Connection Issues

```
Error: Could not connect to database
```

**Solution:** Check database connection in `.env`:

```bash
DATABASE_URL=postgresql://user:pass@localhost:5432/signalixai
```

### Redis Connection Issues

```
Error: Could not connect to Redis
```

**Solution:** Start Redis and check connection:

```bash
redis-server
redis-cli ping  # Should return PONG
```

## Performance Tuning

### Screening Performance

If SQL pre-filter exceeds 500ms:

1. **Add Database Indexes:**
   ```sql
   CREATE INDEX idx_screening_snapshot_rsi ON screening_snapshot(rsi_14);
   CREATE INDEX idx_screening_snapshot_volume ON screening_snapshot(volume, volume_ma_20);
   ```

2. **Optimize Materialized View Refresh:**
   ```sql
   REFRESH MATERIALIZED VIEW CONCURRENTLY screening_snapshot;
   ```

3. **Scale Database:**
   - Increase PostgreSQL `shared_buffers`
   - Add read replicas for screening queries

### Backtest Performance

If backtests fail or timeout:

1. **Scale Celery Workers:**
   ```bash
   celery -A celery_app worker --concurrency=10
   ```

2. **Optimize Vectorbt:**
   - Use vectorised mode for initial testing
   - Reserve event-driven mode for final validation

3. **Add Worker Nodes:**
   - Deploy multiple Celery worker instances
   - Use SQS for distributed task queue

### Anomaly Detection Performance

If processing exceeds 30s:

1. **Optimize Detector Algorithms:**
   - Use rolling windows efficiently
   - Cache indicator calculations

2. **Parallelize Processing:**
   - Process multiple symbols concurrently
   - Use asyncio for I/O-bound operations

3. **Scale Processing:**
   - Add more detector worker instances
   - Use Redis for distributed caching

### Alert Delivery Performance

If P95 latency exceeds 5s:

1. **Optimize Delivery Channels:**
   - Use WebSocket for in-app (fastest)
   - Batch email/SMS deliveries

2. **Add Message Queue:**
   - Use SQS FIFO for reliable delivery
   - Implement retry with exponential backoff

3. **Scale Delivery Workers:**
   - Deploy multiple delivery engine instances
   - Use Redis pub/sub for WebSocket fanout

## CI/CD Integration

### GitHub Actions

```yaml
name: Performance Tests

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  performance:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-test.txt
      
      - name: Start services
        run: |
          docker-compose up -d
          sleep 10
      
      - name: Run performance tests
        run: |
          cd signalixai-backend
          python performance_tests/run_all_benchmarks.py
      
      - name: Upload report
        uses: actions/upload-artifact@v3
        with:
          name: performance-report
          path: signalixai-backend/PERFORMANCE_REPORT.md
```

## License

Part of the Signalix Algo Backend project.
