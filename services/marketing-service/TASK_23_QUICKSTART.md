# Task 23 Quick Start Guide

## Implement Day 1/7/30 Retention Measurement

This guide helps you quickly test the retention service implementation.

## Prerequisites

1. **Redis** must be running (for rq scheduler)
2. **Python 3.11+** installed
3. **Dependencies** installed

## Setup

### 1. Install Dependencies

```bash
cd signalixai-backend/services/marketing-service
pip install -r requirements.txt
```

### 2. Configure Environment

Create `.env` file:

```bash
# Copy example
cp .env.example .env

# Edit .env and set:
REDIS_URL=redis://localhost:6379/0
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/signalixai
SENDGRID_API_KEY=your_key_here
```

### 3. Start Redis (if not running)

```bash
# macOS/Linux
redis-server

# Docker
docker run -d -p 6379:6379 redis:latest
```

## Running the Service

### Start the Marketing Service

```bash
cd signalixai-backend/services/marketing-service
python -m app.main
```

The service will start on `http://localhost:8010`

You should see:
```
INFO:app.main:marketing-service starting up...
INFO:app.scheduler:Scheduled daily retention computation job: daily_retention_computation
```

## Testing

### Run the Test Suite

In a new terminal:

```bash
cd signalixai-backend/services/marketing-service
python test_retention.py
```

### Expected Output

```
================================================================================
Testing Retention Service - Task 23
================================================================================

1. Recording user signups for cohort...
  ✓ Recorded signup for user_1 (activated: True)
  ✓ Recorded signup for user_2 (activated: False)
  ...

2. Recording user sessions...
  ✓ Recorded Day 1 session for user_1
  ✓ Recorded Day 7 session for user_1
  ...

3. Computing retention metrics...
  ✓ Retention computation successful
    - Metrics computed: 3
    - Summary: {
        "total_cohorts": 1,
        "total_users": 10,
        "avg_day1_retention": 80.0,
        "avg_day7_retention": 60.0,
        "avg_day30_retention": 40.0
      }

...

✅ All tests passed successfully!
```

## Manual API Testing

### 1. Check Service Health

```bash
curl http://localhost:8010/health
```

### 2. Record a User Signup

```bash
curl -X POST http://localhost:8010/api/v1/analytics/signups/record \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test_user_1",
    "signup_time": "2024-01-15T10:00:00Z",
    "is_activated": false
  }'
```

### 3. Record a User Session

```bash
curl -X POST http://localhost:8010/api/v1/analytics/sessions/record \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test_user_1",
    "session_time": "2024-01-16T14:30:00Z"
  }'
```

### 4. Compute Retention Metrics

```bash
curl -X POST http://localhost:8010/api/v1/analytics/retention/compute
```

### 5. Get Retention Metrics

```bash
# All metrics
curl http://localhost:8010/api/v1/analytics/retention

# Filter by retention day
curl "http://localhost:8010/api/v1/analytics/retention?retention_day=7"

# Get summary
curl http://localhost:8010/api/v1/analytics/retention/summary
```

## Verifying Daily Cron Job

### Check Scheduled Jobs

```bash
# Using rq CLI
rq info --url redis://localhost:6379/0

# Check specific queue
rq info --url redis://localhost:6379/0 --queue marketing
```

### Manually Trigger Cron Job

```bash
curl -X POST http://localhost:8010/api/v1/analytics/retention/compute
```

## Key Features Implemented

✅ **Day 1, 7, 30 Retention Computation**
- Cohort-based retention tracking
- Automatic computation for all eligible cohorts

✅ **Activation Status Segmentation**
- Separate retention rates for activated vs non-activated users
- Enables cohort analysis by activation

✅ **Daily Cron Job**
- Scheduled via rq scheduler
- Runs at 2:00 AM UTC daily
- Stores historical metrics

✅ **Analytics Endpoints**
- GET `/api/v1/analytics/retention` - Query retention metrics
- GET `/api/v1/analytics/retention/summary` - Get summary stats
- POST `/api/v1/analytics/retention/compute` - Manual trigger
- GET `/api/v1/analytics/retention/cohort/{date}` - Cohort-specific view

✅ **Session and Signup Tracking**
- POST `/api/v1/analytics/sessions/record` - Track user sessions
- POST `/api/v1/analytics/signups/record` - Track user signups
- PUT `/api/v1/analytics/activation/update` - Update activation status

## Troubleshooting

### Service Won't Start

**Issue:** `Failed to connect to Redis`

**Solution:**
```bash
# Check if Redis is running
redis-cli ping

# Start Redis if not running
redis-server
```

### Cron Job Not Scheduling

**Issue:** Scheduler not initializing

**Solution:**
1. Check Redis connection in logs
2. Verify REDIS_URL in .env
3. Check for errors in startup logs

### No Retention Data

**Issue:** Metrics return empty

**Solution:**
1. Record some test signups and sessions
2. Ensure cohort is old enough (1, 7, or 30 days)
3. Run manual computation: `POST /api/v1/analytics/retention/compute`

## Next Steps

1. ✅ **Task 23 Complete** - Retention service implemented
2. 📊 **Integration** - Connect with user-service for real data
3. 🗄️ **Database** - Migrate from in-memory to PostgreSQL
4. 📈 **Dashboard** - Add retention charts to marketing dashboard
5. 🔔 **Alerts** - Set up alerts for retention drops

## Files Created

```
signalixai-backend/services/marketing-service/
├── app/
│   ├── services/
│   │   └── retention_service.py          # Core retention logic
│   ├── routers/
│   │   └── analytics.py                  # Analytics API endpoints
│   ├── tasks/
│   │   └── retention_tasks.py            # Background tasks
│   └── scheduler.py                      # rq scheduler setup
├── test_retention.py                     # Test suite
├── RETENTION_SERVICE_README.md           # Full documentation
└── TASK_23_QUICKSTART.md                 # This file
```

## Support

For issues or questions:
1. Check logs: `tail -f logs/marketing-service.log`
2. Review documentation: `RETENTION_SERVICE_README.md`
3. Run diagnostics: `python test_retention.py`
