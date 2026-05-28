# Retention Service - Task 23 Implementation

## Overview

The Retention Service implements Day 1, Day 7, and Day 30 cohort retention measurement for SignalixAI AI's marketing system. It tracks user retention by activation status and provides analytics endpoints for retention metrics.

**Requirements:** 10.9  
**Task:** 23

## Features

### Core Functionality

1. **Cohort Retention Tracking**
   - Day 1 retention: Users who return 1 day after signup
   - Day 7 retention: Users who return 7 days after signup
   - Day 30 retention: Users who return 30 days after signup

2. **Activation-Based Segmentation**
   - Tracks retention separately for activated vs non-activated users
   - Enables cohort analysis by activation status

3. **Daily Cron Job**
   - Automated daily computation of retention metrics
   - Scheduled via rq scheduler to run at 2:00 AM UTC
   - Stores historical retention data for trend analysis

4. **Analytics Endpoints**
   - RESTful API for querying retention metrics
   - Filtering by cohort date, retention day, and date range
   - Summary statistics and cohort-specific views

## Architecture

### Components

```
app/
├── services/
│   └── retention_service.py      # Core retention computation logic
├── routers/
│   └── analytics.py               # Analytics API endpoints
├── tasks/
│   └── retention_tasks.py         # Background tasks and cron jobs
└── scheduler.py                   # rq scheduler configuration
```

### Data Flow

```
User Signup → Record in retention_service
     ↓
User Sessions → Track activity
     ↓
Daily Cron Job → Compute retention metrics
     ↓
Store Metrics → Historical tracking
     ↓
Analytics API → Query and analyze
```

## API Endpoints

### 1. Get Retention Metrics

```http
GET /api/v1/analytics/retention
```

**Query Parameters:**
- `cohort_date` (optional): Filter by cohort date (YYYY-MM-DD)
- `retention_day` (optional): Filter by retention day (1, 7, or 30)
- `start_date` (optional): Filter cohorts from this date
- `end_date` (optional): Filter cohorts up to this date

**Response:**
```json
{
  "metrics": [
    {
      "cohort_date": "2024-01-15",
      "retention_day": 1,
      "cohort_size": 100,
      "retained_users": 80,
      "retention_rate": 80.0,
      "activated_cohort_size": 60,
      "activated_retained_users": 55,
      "activated_retention_rate": 91.67,
      "non_activated_cohort_size": 40,
      "non_activated_retained_users": 25,
      "non_activated_retention_rate": 62.5,
      "computed_at": "2024-01-16T02:00:00Z"
    }
  ],
  "summary": {
    "total_cohorts": 30,
    "total_users": 3000,
    "avg_day1_retention": 75.5,
    "avg_day7_retention": 55.2,
    "avg_day30_retention": 35.8
  },
  "total_metrics": 90
}
```

### 2. Get Retention Summary

```http
GET /api/v1/analytics/retention/summary
```

**Response:**
```json
{
  "total_cohorts": 30,
  "total_users": 3000,
  "avg_day1_retention": 75.5,
  "avg_day7_retention": 55.2,
  "avg_day30_retention": 35.8
}
```

### 3. Compute Retention Metrics (Manual Trigger)

```http
POST /api/v1/analytics/retention/compute
```

**Response:**
```json
{
  "success": true,
  "message": "Retention metrics computed successfully",
  "computed_at": "2024-01-16T10:30:00Z",
  "metrics_count": 90,
  "summary": {
    "total_cohorts": 30,
    "total_users": 3000,
    "avg_day1_retention": 75.5,
    "avg_day7_retention": 55.2,
    "avg_day30_retention": 35.8
  }
}
```

### 4. Get Cohort-Specific Retention

```http
GET /api/v1/analytics/retention/cohort/{cohort_date}
```

**Example:** `GET /api/v1/analytics/retention/cohort/2024-01-15`

**Response:**
```json
{
  "cohort_date": "2024-01-15",
  "metrics": [
    {
      "cohort_date": "2024-01-15",
      "retention_day": 1,
      "retention_rate": 80.0,
      ...
    },
    {
      "cohort_date": "2024-01-15",
      "retention_day": 7,
      "retention_rate": 60.0,
      ...
    },
    {
      "cohort_date": "2024-01-15",
      "retention_day": 30,
      "retention_rate": 40.0,
      ...
    }
  ],
  "total_metrics": 3
}
```

### 5. Record User Session

```http
POST /api/v1/analytics/sessions/record
```

**Request Body:**
```json
{
  "user_id": "user_123",
  "session_time": "2024-01-16T10:30:00Z"
}
```

### 6. Record User Signup

```http
POST /api/v1/analytics/signups/record
```

**Request Body:**
```json
{
  "user_id": "user_123",
  "signup_time": "2024-01-15T14:20:00Z",
  "is_activated": false
}
```

### 7. Update Activation Status

```http
PUT /api/v1/analytics/activation/update
```

**Request Body:**
```json
{
  "user_id": "user_123",
  "is_activated": true
}
```

## Daily Cron Job

### Configuration

The daily retention computation job is scheduled via rq scheduler:

- **Schedule:** Every day at 2:00 AM UTC
- **Cron Expression:** `0 2 * * *`
- **Job ID:** `daily_retention_computation`
- **Timeout:** 10 minutes

### Setup

The cron job is automatically scheduled on service startup in `app/main.py`:

```python
@app.on_event("startup")
async def startup_event():
    from app.scheduler import setup_scheduled_jobs
    result = setup_scheduled_jobs()
```

### Manual Execution

To manually trigger the daily computation:

```bash
curl -X POST http://localhost:8010/api/v1/analytics/retention/compute
```

## Retention Calculation Logic

### Day N Retention

A user is considered "retained" on Day N if they had at least one session on Day N after their signup date.

**Example:**
- User signs up: 2024-01-15 10:00 AM
- Day 1 window: 2024-01-16 00:00 AM - 2024-01-16 11:59 PM
- Day 7 window: 2024-01-22 00:00 AM - 2024-01-22 11:59 PM
- Day 30 window: 2024-02-14 00:00 AM - 2024-02-14 11:59 PM

### Cohort Definition

A cohort consists of all users who signed up on the same calendar day (00:00 - 23:59 UTC).

### Activation Segmentation

Retention is tracked separately for:
- **Activated users:** Users who completed the activation criteria
- **Non-activated users:** Users who have not completed activation

This enables analysis of how activation impacts retention.

## Testing

### Run Test Suite

```bash
cd signalixai-backend/services/marketing-service
python test_retention.py
```

### Test Coverage

The test suite verifies:
- ✓ User signup recording
- ✓ Session tracking
- ✓ Day 1, 7, 30 retention computation
- ✓ Activation status segmentation
- ✓ Analytics endpoint functionality
- ✓ Filtering and querying
- ✓ Summary statistics
- ✓ Cohort-specific views

### Expected Results

For a cohort of 10 users with:
- 8 users active on Day 1 → 80% Day 1 retention
- 6 users active on Day 7 → 60% Day 7 retention
- 4 users active on Day 30 → 40% Day 30 retention

## Integration

### With User Service

When a user signs up, call the signup recording endpoint:

```python
import httpx

async def on_user_signup(user_id: str, signup_time: datetime):
    async with httpx.AsyncClient() as client:
        await client.post(
            "http://marketing-service:8010/api/v1/analytics/signups/record",
            json={
                "user_id": user_id,
                "signup_time": signup_time.isoformat(),
                "is_activated": False
            }
        )
```

### With Session Tracking

When a user logs in or has a session, record it:

```python
async def on_user_session(user_id: str, session_time: datetime):
    async with httpx.AsyncClient() as client:
        await client.post(
            "http://marketing-service:8010/api/v1/analytics/sessions/record",
            json={
                "user_id": user_id,
                "session_time": session_time.isoformat()
            }
        )
```

### With Activation Tracking

When a user completes activation, update their status:

```python
async def on_user_activated(user_id: str):
    async with httpx.AsyncClient() as client:
        await client.put(
            "http://marketing-service:8010/api/v1/analytics/activation/update",
            json={
                "user_id": user_id,
                "is_activated": True
            }
        )
```

## Production Considerations

### Database Storage

The current implementation uses in-memory storage for demonstration. For production:

1. **Create PostgreSQL tables:**

```sql
-- User signups table
CREATE TABLE user_signups (
    user_id UUID PRIMARY KEY,
    signup_time TIMESTAMP WITH TIME ZONE NOT NULL,
    is_activated BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- User sessions table
CREATE TABLE user_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    session_time TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_user_sessions_user_id ON user_sessions(user_id);
CREATE INDEX idx_user_sessions_session_time ON user_sessions(session_time);

-- Retention metrics table
CREATE TABLE retention_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cohort_date DATE NOT NULL,
    retention_day INTEGER NOT NULL,
    cohort_size INTEGER NOT NULL,
    retained_users INTEGER NOT NULL,
    retention_rate DECIMAL(5,2) NOT NULL,
    activated_cohort_size INTEGER NOT NULL,
    activated_retained_users INTEGER NOT NULL,
    activated_retention_rate DECIMAL(5,2) NOT NULL,
    non_activated_cohort_size INTEGER NOT NULL,
    non_activated_retained_users INTEGER NOT NULL,
    non_activated_retention_rate DECIMAL(5,2) NOT NULL,
    computed_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(cohort_date, retention_day, computed_at)
);

CREATE INDEX idx_retention_metrics_cohort_date ON retention_metrics(cohort_date);
CREATE INDEX idx_retention_metrics_retention_day ON retention_metrics(retention_day);
```

2. **Update `retention_service.py`** to use SQLAlchemy for database operations

3. **Add database connection** to `app/main.py` lifespan

### Redis Configuration

Ensure Redis is configured for rq scheduler:

```bash
# .env
REDIS_URL=redis://localhost:6379/0
```

### Monitoring

Monitor the daily cron job:

```bash
# Check scheduled jobs
rq info --url redis://localhost:6379/0

# View job status
rq info --url redis://localhost:6379/0 --queue marketing
```

## Troubleshooting

### Cron Job Not Running

1. Check Redis connection:
   ```bash
   redis-cli ping
   ```

2. Check scheduler logs:
   ```bash
   tail -f logs/marketing-service.log | grep retention
   ```

3. Manually trigger computation:
   ```bash
   curl -X POST http://localhost:8010/api/v1/analytics/retention/compute
   ```

### Missing Retention Data

1. Verify user signups are recorded
2. Verify sessions are tracked
3. Check cohort date is old enough (1, 7, or 30 days)
4. Run manual computation to backfill

### Low Retention Rates

1. Check activation rates
2. Verify session tracking is working
3. Analyze retention by activation status
4. Review onboarding flow effectiveness

## Next Steps

1. **Database Migration:** Implement PostgreSQL storage
2. **Backfill Script:** Create script to backfill historical retention data
3. **Dashboard Integration:** Add retention charts to marketing dashboard
4. **Alerting:** Set up alerts for retention rate drops
5. **Cohort Analysis:** Add more segmentation dimensions (source, market, etc.)

## References

- **Requirements:** Requirement 10.9 in requirements.md
- **Design:** Design document section on retention measurement
- **Task:** Task 23 in tasks.md
