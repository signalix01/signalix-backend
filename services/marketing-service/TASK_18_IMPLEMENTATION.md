# Task 18 Implementation: Onboarding Nurture Email Sequence

## Overview

This document describes the implementation of Task 18 from the comprehensive-marketing-growth-system spec: "Build onboarding nurture email sequence".

## Implementation Summary

### Completed Components

#### 1. Onboarding Sequence Configuration (Task 18.1)
**File**: `app/data/sequences/onboarding.py`

- Defined 6-email onboarding sequence (Day 0-7)
- Email schedule:
  - **Day 0**: Welcome email (immediate)
  - **Day 1**: Getting Started Guide (24h delay)
  - **Day 2**: First Analysis Tips (48h delay)
  - **Day 3**: Feature Discovery (72h delay)
  - **Day 5**: Success Stories (120h delay)
  - **Day 6**: Trial Ending Reminder (144h delay)

- Each email step includes:
  - Day number
  - Template name
  - Subject line
  - Delay in hours
  - Description

#### 2. Sequence Enrollment Endpoint (Task 18.1)
**File**: `app/routers/sequences.py`

**Endpoint**: `POST /api/v1/sequences/enroll`

Enrolls users in email sequences and schedules all emails using rq's `enqueue_at()` with `eta` parameter for future delivery.

**Request**:
```json
{
  "user_id": "123e4567-e89b-12d3-a456-426614174000",
  "email": "trader@example.com",
  "sequence_name": "onboarding",
  "context": {
    "first_name": "Rajesh",
    "signup_date": "2024-01-15"
  }
}
```

**Response**:
```json
{
  "success": true,
  "message": "Successfully enrolled in onboarding sequence",
  "sequence_name": "onboarding",
  "total_emails": 6,
  "scheduled_jobs": 6,
  "enrollment_id": "123e4567-e89b-12d3-a456-426614174000_onboarding_1705315200"
}
```

**Additional Endpoints**:
- `GET /api/v1/sequences/metadata/{sequence_name}` - Get sequence metadata
- `POST /api/v1/sequences/cancel` - Cancel sequence enrollment

#### 3. Behavioral Trigger Service (Task 18.2)
**File**: `app/services/trigger_service.py`

Implements 4 behavioral trigger types:

1. **incomplete_onboarding**: Sent 24h after signup if onboarding not complete
2. **inactive_user**: Sent after 7 days of no login activity
3. **feature_unused**: Sent when user hasn't used a key feature
4. **upgrade_prompt**: Sent when free tier user has high usage (>80%)

Each trigger includes:
- Validation logic (time checks, tier checks, usage thresholds)
- Context preparation
- Email queueing via rq
- Comprehensive logging

#### 4. Trigger Endpoints (Task 18.2)
**File**: `app/routers/triggers.py`

**Main Endpoint**: `POST /api/v1/triggers/fire`

Generic endpoint consumed by analytics-service webhooks and other internal services.

**Request**:
```json
{
  "trigger_type": "incomplete_onboarding",
  "user_id": "123e4567-e89b-12d3-a456-426614174000",
  "email": "trader@example.com",
  "context": {
    "first_name": "Rajesh",
    "onboarding_progress": 40,
    "next_step": "Add instruments to watchlist",
    "signup_time": "2024-01-15T10:30:00Z"
  }
}
```

**Convenience Endpoints**:
- `POST /api/v1/triggers/incomplete-onboarding`
- `POST /api/v1/triggers/inactive-user`
- `POST /api/v1/triggers/feature-unused`
- `POST /api/v1/triggers/upgrade-prompt`

#### 5. Email Task Functions
**File**: `app/tasks/email_tasks.py`

Added two new task functions:
- `send_sequence_email()`: Sends emails as part of a sequence
- `send_trigger_email()`: Sends behavioral trigger emails

Both functions:
- Use the email service for actual sending
- Include comprehensive error handling
- Log all operations for monitoring

#### 6. Service Configuration
**Files**: `app/config.py`, `app/services/email_service.py`

Added template IDs for:
- Onboarding sequence emails (5 new templates)
- Behavioral trigger emails (4 new templates)

#### 7. Main Application
**File**: `app/main.py`

Created FastAPI application with:
- Health check endpoint
- CORS middleware
- Router registration for sequences and triggers
- Startup/shutdown event handlers

## Architecture

### Email Scheduling Flow

```
1. User signs up
   ↓
2. auth-service calls POST /api/v1/sequences/enroll
   ↓
3. Sequence router schedules 6 emails via rq.enqueue_at()
   ↓
4. Each email has eta (estimated time of arrival) set
   ↓
5. rq worker executes jobs at scheduled times
   ↓
6. send_sequence_email() sends via SendGrid
```

### Behavioral Trigger Flow

```
1. analytics-service detects behavior (e.g., 7 days inactive)
   ↓
2. Webhook calls POST /api/v1/triggers/fire
   ↓
3. Trigger router validates and routes to trigger_service
   ↓
4. trigger_service checks conditions (time, tier, usage)
   ↓
5. If conditions met, queues email via rq
   ↓
6. send_trigger_email() sends via SendGrid
```

## Usage Examples

### Enroll User in Onboarding Sequence

```bash
curl -X POST http://localhost:8010/api/v1/sequences/enroll \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user-123",
    "email": "trader@example.com",
    "sequence_name": "onboarding",
    "context": {
      "first_name": "Rajesh"
    }
  }'
```

### Fire Incomplete Onboarding Trigger

```bash
curl -X POST http://localhost:8010/api/v1/triggers/fire \
  -H "Content-Type: application/json" \
  -d '{
    "trigger_type": "incomplete_onboarding",
    "user_id": "user-123",
    "email": "trader@example.com",
    "context": {
      "first_name": "Rajesh",
      "onboarding_progress": 40,
      "next_step": "Add instruments to watchlist",
      "signup_time": "2024-01-15T10:30:00Z"
    }
  }'
```

### Fire Upgrade Prompt Trigger

```bash
curl -X POST http://localhost:8010/api/v1/triggers/upgrade-prompt \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user-123",
    "email": "trader@example.com",
    "first_name": "Rajesh",
    "current_tier": "free",
    "usage_percentage": 85,
    "analyses_used": 77,
    "analyses_limit": 90
  }'
```

### Get Sequence Metadata

```bash
curl http://localhost:8010/api/v1/sequences/metadata/onboarding
```

### Cancel Sequence Enrollment

```bash
curl -X POST "http://localhost:8010/api/v1/sequences/cancel?user_id=user-123&sequence_name=onboarding"
```

## Integration Points

### 1. auth-service Integration
When a user completes signup, auth-service should call:
```python
POST /api/v1/sequences/enroll
{
  "user_id": user.id,
  "email": user.email,
  "sequence_name": "onboarding",
  "context": {
    "first_name": user.first_name,
    "signup_date": user.created_at.isoformat()
  }
}
```

### 2. analytics-service Integration
analytics-service should monitor user behavior and fire triggers:

**Incomplete Onboarding** (24h after signup):
```python
if user.signup_time + 24h and not user.onboarding_complete:
    POST /api/v1/triggers/incomplete-onboarding
```

**Inactive User** (7 days no login):
```python
if user.last_login + 7d:
    POST /api/v1/triggers/inactive-user
```

**High Usage** (approaching limit):
```python
if user.tier == "free" and user.usage_percentage > 80:
    POST /api/v1/triggers/upgrade-prompt
```

### 3. user-service Integration
user-service can fire feature unused triggers:
```python
if user.days_since_signup > 5 and not user.used_feature("options_intelligence"):
    POST /api/v1/triggers/feature-unused
```

## Email Templates

The following SendGrid dynamic templates need to be created:

### Onboarding Sequence Templates
1. `d-getting-started-001` - Getting Started Guide
2. `d-first-analysis-tips-001` - First Analysis Tips
3. `d-feature-discovery-001` - Feature Discovery
4. `d-success-stories-001` - Success Stories
5. `d-trial-ending-001` - Trial Ending Reminder

### Behavioral Trigger Templates
1. `d-incomplete-onboarding-001` - Incomplete Onboarding
2. `d-inactive-user-001` - Inactive User
3. `d-feature-unused-001` - Feature Unused
4. `d-upgrade-prompt-001` - Upgrade Prompt

**Note**: Until these templates are created in SendGrid, the system will fall back to the existing welcome template.

## Configuration

Add to `.env`:
```env
# Onboarding Sequence Templates
TEMPLATE_GETTING_STARTED=d-getting-started-001
TEMPLATE_FIRST_ANALYSIS_TIPS=d-first-analysis-tips-001
TEMPLATE_FEATURE_DISCOVERY=d-feature-discovery-001
TEMPLATE_SUCCESS_STORIES=d-success-stories-001
TEMPLATE_TRIAL_ENDING=d-trial-ending-001

# Behavioral Trigger Templates
TEMPLATE_INCOMPLETE_ONBOARDING=d-incomplete-onboarding-001
TEMPLATE_INACTIVE_USER=d-inactive-user-001
TEMPLATE_FEATURE_UNUSED=d-feature-unused-001
TEMPLATE_UPGRADE_PROMPT=d-upgrade-prompt-001
```

## Running the Service

### Start the service:
```bash
cd signalixai-backend/services/marketing-service
python -m app.main
```

### Start rq worker (required for email processing):
```bash
rq worker emails --url redis://localhost:6379
```

## Testing

### Test sequence enrollment:
```python
import requests

response = requests.post(
    "http://localhost:8010/api/v1/sequences/enroll",
    json={
        "user_id": "test-user-123",
        "email": "test@example.com",
        "sequence_name": "onboarding",
        "context": {"first_name": "Test"}
    }
)
print(response.json())
```

### Test trigger firing:
```python
import requests
from datetime import datetime

response = requests.post(
    "http://localhost:8010/api/v1/triggers/fire",
    json={
        "trigger_type": "incomplete_onboarding",
        "user_id": "test-user-123",
        "email": "test@example.com",
        "context": {
            "first_name": "Test",
            "onboarding_progress": 40,
            "next_step": "Complete profile",
            "signup_time": datetime.utcnow().isoformat()
        }
    }
)
print(response.json())
```

## Monitoring

### Check scheduled jobs:
```python
from rq import Queue
from redis import Redis

redis_conn = Redis.from_url("redis://localhost:6379")
queue = Queue('emails', connection=redis_conn)

# Get scheduled jobs
scheduled_jobs = queue.scheduled_job_registry
print(f"Scheduled jobs: {len(scheduled_jobs)}")

for job_id in scheduled_jobs.get_job_ids():
    job = queue.fetch_job(job_id)
    print(f"Job {job_id}: {job.func_name}, scheduled for {job.enqueued_at}")
```

### Check job status:
```python
job = queue.fetch_job("seq_onboarding_user-123_day1")
print(f"Status: {job.get_status()}")
print(f"Result: {job.result}")
```

## Requirements Satisfied

✅ **Requirement 15.1**: Welcome email sequence (Day 0-7) implemented with 6 emails
✅ **Requirement 15.3**: Behavioral trigger emails implemented (incomplete_onboarding, inactive_user, feature_unused, upgrade_prompt)
✅ **Design**: Sequence config in `onboarding.py`, sequences router with enrollment endpoint, trigger service with fire endpoint
✅ **Design**: Emails scheduled via rq with `eta` parameter for future delivery

## Task 18.3 (Optional Property Test)

Task 18.3 (Write property test for sequence scheduling) was marked as optional and skipped for faster delivery as per the task instructions.

## Next Steps

1. **Create SendGrid Templates**: Design and create the 9 new email templates in SendGrid
2. **Integration**: Integrate with auth-service, analytics-service, and user-service
3. **Monitoring**: Set up monitoring dashboards for email delivery rates and trigger firing
4. **Testing**: Conduct end-to-end testing with real user flows
5. **Documentation**: Create user-facing documentation for email preferences and unsubscribe

## Files Created

1. `app/data/__init__.py`
2. `app/data/sequences/__init__.py`
3. `app/data/sequences/onboarding.py`
4. `app/routers/__init__.py`
5. `app/routers/sequences.py`
6. `app/routers/triggers.py`
7. `app/services/trigger_service.py`
8. `app/main.py`

## Files Modified

1. `app/config.py` - Added new template IDs
2. `app/services/email_service.py` - Added new templates to mapping
3. `app/tasks/email_tasks.py` - Added sequence and trigger email functions

## Conclusion

Task 18 has been successfully implemented with all required functionality:
- ✅ Day 0-7 onboarding sequence with 6 emails
- ✅ Sequence enrollment endpoint with rq scheduling
- ✅ Behavioral trigger service with 4 trigger types
- ✅ Trigger fire endpoint for webhooks
- ✅ Complete integration with existing email infrastructure

The implementation follows the spec requirements and design document, uses rq for scheduled email delivery, and provides a robust foundation for marketing automation.
