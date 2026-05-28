# Task 19 Implementation: Lead Magnet Nurture Sequence

## Overview

This document describes the implementation of Task 19 from the comprehensive-marketing-growth-system spec: "Build lead magnet nurture sequence".

## Implementation Summary

### What Was Built

1. **Lead Magnet Nurture Sequence Configuration** (`app/data/sequences/lead_magnet.py`)
   - 4-email sequence over 7 days
   - Personalized content based on lead magnet downloaded
   - Segmentation by lead_magnet_id

2. **Lead Capture Router** (`app/routers/leads.py`)
   - `POST /api/v1/leads/capture` - Capture leads and deliver lead magnets
   - `GET /api/v1/leads/stats` - Lead statistics
   - `GET /api/v1/leads/lead/{email}` - Get lead details
   - Auto-enrollment in nurture sequence on capture

3. **Updated Sequences Router** (`app/routers/sequences.py`)
   - Added support for "lead_magnet" sequence type
   - Updated enrollment, metadata, and cancellation endpoints

4. **Email Templates** (4 templates × 2 formats = 8 files)
   - Lead Magnet Delivery (Day 0)
   - Related Content (Day 2)
   - Case Study (Day 4)
   - Trial Invitation (Day 7)

5. **Configuration Updates**
   - Added 4 new template IDs to `app/config.py`
   - Updated email service template mapping

## Architecture

### Lead Capture Flow

```
1. User downloads lead magnet
   ↓
2. POST /api/v1/leads/capture
   ↓
3. Check if email exists (deduplication)
   ↓
4. Create/update lead record
   ↓
5. Return download URL
   ↓
6. Auto-enroll in lead magnet sequence (background task)
   ↓
7. Schedule 4 emails via rq with future delivery times
```

### Sequence Structure

```python
LEAD_MAGNET_SEQUENCE = [
    Day 0: lead_magnet_delivery (immediate)
    Day 2: related_content (48 hours)
    Day 4: case_study (96 hours)
    Day 7: trial_invitation (168 hours)
]
```

### Personalization

Each lead magnet has associated content metadata:

```python
LEAD_MAGNET_CONTENT = {
    "fo-trading-checklist": {
        "title": "F&O Trading Checklist",
        "topic": "F&O trading",
        "category": "futures_options",
        "related_resources": [...]
    },
    # ... 4 more lead magnets
}
```

This metadata is used to personalize:
- Email subject lines
- Related resource recommendations
- Content focus and examples

## API Endpoints

### POST /api/v1/leads/capture

Capture a lead and optionally deliver lead magnet.

**Request:**
```json
{
  "email": "trader@example.com",
  "source": "lead_magnet",
  "lead_magnet_id": "fo-trading-checklist",
  "page_url": "https://signalixai.com/resources/fo-trading-checklist",
  "utm_params": {
    "utm_source": "google",
    "utm_medium": "cpc",
    "utm_campaign": "lead_magnets"
  }
}
```

**Response:**
```json
{
  "success": true,
  "message": "Successfully subscribed",
  "lead_id": "lead_1234567890",
  "download_url": "https://signalixai.com/downloads/fo-trading-checklist.pdf",
  "is_new_lead": true
}
```

**Features:**
- Email deduplication (updates existing leads)
- Appends new sources to existing leads
- Returns download URL immediately
- Auto-enrolls in nurture sequence (background)

### GET /api/v1/leads/stats

Get lead statistics.

**Response:**
```json
{
  "total_leads": 1250,
  "new_today": 42,
  "by_source": {
    "lead_magnet": 850,
    "popup": 250,
    "inline": 150
  },
  "by_lead_magnet": {
    "fo-trading-checklist": 320,
    "options-greeks-cheat-sheet": 280,
    "position-sizing-calculator": 250
  }
}
```

### POST /api/v1/sequences/enroll

Enroll user in email sequence (now supports "lead_magnet" sequence).

**Request:**
```json
{
  "user_id": "user_123",
  "email": "trader@example.com",
  "sequence_name": "lead_magnet",
  "context": {
    "lead_magnet_id": "fo-trading-checklist",
    "lead_magnet_title": "F&O Trading Checklist",
    "topic": "F&O trading"
  }
}
```

**Response:**
```json
{
  "success": true,
  "message": "Successfully enrolled in lead_magnet sequence",
  "sequence_name": "lead_magnet",
  "total_emails": 4,
  "scheduled_jobs": 4,
  "enrollment_id": "user_123_lead_magnet_1234567890"
}
```

### GET /api/v1/sequences/metadata/lead_magnet

Get lead magnet sequence metadata.

**Response:**
```json
{
  "name": "lead_magnet",
  "description": "4-email nurture sequence for lead magnet downloads",
  "total_emails": 4,
  "duration_days": 7,
  "steps": [
    {
      "day": 0,
      "template_name": "lead_magnet_delivery",
      "subject": "Your {{lead_magnet_title}} is ready",
      "delay_hours": 0,
      "description": "Immediate delivery email with download link"
    },
    // ... 3 more steps
  ]
}
```

## Email Templates

### 1. Lead Magnet Delivery (Day 0)

**Purpose:** Immediate delivery with download link

**Key Elements:**
- Download button (primary CTA)
- What's next preview
- Trial CTA (secondary)
- Pro tip callout

**Personalization:**
- `{{lead_magnet_title}}`
- `{{topic}}`
- `{{download_url}}`

### 2. Related Content (Day 2)

**Purpose:** Provide additional value and resources

**Key Elements:**
- 3 related resource recommendations
- Quick tip section
- Social proof testimonial
- Browse resources CTA

**Personalization:**
- `{{related_resources}}` (array)
- `{{topic}}`

### 3. Case Study (Day 4)

**Purpose:** Show real results and build trust

**Key Elements:**
- Detailed case study (Priya's story)
- What AI found (multi-agent analysis)
- Outcome and savings
- Key takeaway
- Stats section (60%+ accuracy, 10K+ traders)
- Trial CTA

**Personalization:**
- Generic (not personalized by lead magnet)

### 4. Trial Invitation (Day 7)

**Purpose:** Convert lead to trial user

**Key Elements:**
- What you get (5 key features)
- Social proof testimonial
- Trial details (no credit card, 10 analyses/day)
- How it works (3 steps)
- FAQ section
- Strong CTA

**Personalization:**
- `{{lead_magnet_title}}` (reference to what they downloaded)

## Configuration

### Environment Variables

Add to `.env`:

```bash
# Lead Magnet Nurture Sequence Templates
TEMPLATE_LEAD_MAGNET_DELIVERY=d-lead-magnet-delivery-001
TEMPLATE_RELATED_CONTENT=d-related-content-001
TEMPLATE_CASE_STUDY=d-case-study-001
TEMPLATE_TRIAL_INVITATION=d-trial-invitation-001
```

### SendGrid Template Setup

Create 4 dynamic templates in SendGrid with these IDs:
- `d-lead-magnet-delivery-001`
- `d-related-content-001`
- `d-case-study-001`
- `d-trial-invitation-001`

Upload the HTML and plain text versions from the `templates/` directory.

## Testing

### Manual Testing

1. **Test Lead Capture:**
```bash
curl -X POST http://localhost:8010/api/v1/leads/capture \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "source": "lead_magnet",
    "lead_magnet_id": "fo-trading-checklist",
    "page_url": "https://signalixai.com/resources/fo-trading-checklist"
  }'
```

2. **Test Sequence Enrollment:**
```bash
curl -X POST http://localhost:8010/api/v1/sequences/enroll \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test_user",
    "email": "test@example.com",
    "sequence_name": "lead_magnet",
    "context": {
      "lead_magnet_id": "fo-trading-checklist",
      "lead_magnet_title": "F&O Trading Checklist",
      "topic": "F&O trading"
    }
  }'
```

3. **Check Lead Stats:**
```bash
curl http://localhost:8010/api/v1/leads/stats
```

4. **Get Sequence Metadata:**
```bash
curl http://localhost:8010/api/v1/sequences/metadata/lead_magnet
```

### Verify Email Scheduling

Check rq jobs:
```python
from rq import Queue
from redis import Redis

redis_conn = Redis.from_url('redis://localhost:6379')
email_queue = Queue('emails', connection=redis_conn)

# Get scheduled jobs
scheduled_jobs = email_queue.scheduled_job_registry
print(f"Scheduled jobs: {len(scheduled_jobs)}")

for job_id in scheduled_jobs.get_job_ids():
    job = email_queue.fetch_job(job_id)
    print(f"Job: {job_id}, ETA: {job.enqueued_at}")
```

## Integration Points

### Frontend Integration

**Lead Magnet Landing Page:**
```typescript
// Capture lead on form submission
const handleSubmit = async (email: string) => {
  const response = await fetch('/api/v1/leads/capture', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      email,
      source: 'lead_magnet',
      lead_magnet_id: 'fo-trading-checklist',
      page_url: window.location.href,
      utm_params: getUTMParams()
    })
  });
  
  const data = await response.json();
  
  if (data.success) {
    // Redirect to thank you page with download
    window.location.href = `/resources/fo-trading-checklist/thank-you?download=${encodeURIComponent(data.download_url)}`;
  }
};
```

**Thank You Page:**
```typescript
// Display download button and track conversion
const ThankYouPage = () => {
  const downloadUrl = new URLSearchParams(window.location.search).get('download');
  
  useEffect(() => {
    // Track lead magnet download
    trackEvent('lead_magnet_downloaded', {
      lead_magnet: 'fo-trading-checklist',
      source: 'landing_page'
    });
  }, []);
  
  return (
    <div>
      <h1>Your F&O Trading Checklist is Ready!</h1>
      <a href={downloadUrl} download>Download Now</a>
      <p>Check your email for the download link and additional resources.</p>
    </div>
  );
};
```

### Analytics Integration

Track lead magnet funnel:
```typescript
// Landing page view
trackEvent('lead_magnet_page_view', {
  lead_magnet: 'fo-trading-checklist'
});

// Form started
trackEvent('lead_magnet_form_started', {
  lead_magnet: 'fo-trading-checklist'
});

// Lead captured
trackEvent('lead_captured', {
  lead_magnet: 'fo-trading-checklist',
  source: 'landing_page'
});

// Download clicked
trackEvent('lead_magnet_downloaded', {
  lead_magnet: 'fo-trading-checklist'
});
```

## Data Storage

### Current Implementation

**In-Memory Storage (MVP):**
- Leads stored in `leads_db` dictionary
- Suitable for development and testing
- Data lost on service restart

### Production Migration

**PostgreSQL Schema:**
```sql
-- Lead magnets table
CREATE TABLE lead_magnets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(255) NOT NULL,
    description TEXT,
    type VARCHAR(50) NOT NULL,
    download_url TEXT NOT NULL,
    landing_page_url TEXT,
    status VARCHAR(20) DEFAULT 'active',
    downloads_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Leads table
CREATE TABLE leads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) NOT NULL UNIQUE,
    source VARCHAR(100) NOT NULL,
    sources TEXT[],
    lead_magnets TEXT[],
    page_url TEXT,
    utm_params JSONB,
    status VARCHAR(20) DEFAULT 'active',
    converted_to_user BOOLEAN DEFAULT FALSE,
    user_id UUID,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_leads_email ON leads(email);
CREATE INDEX idx_leads_status ON leads(status);
CREATE INDEX idx_leads_created_at ON leads(created_at);
```

**Migration Steps:**
1. Create tables using Alembic migration
2. Update `leads.py` to use database instead of in-memory dict
3. Add database session dependency
4. Update queries to use SQLAlchemy

## Monitoring and Metrics

### Key Metrics to Track

1. **Lead Capture Rate:**
   - Landing page visitors → email captured
   - Target: >25%

2. **Sequence Engagement:**
   - Email open rates (target >30%)
   - Click-through rates (target >3%)
   - Unsubscribe rate (target <0.5%)

3. **Conversion Rate:**
   - Leads → trial signups
   - Target: >10% within 30 days

4. **Lead Magnet Performance:**
   - Downloads by lead magnet
   - Conversion rate by lead magnet
   - Most popular lead magnets

### Logging

All key events are logged:
```python
logger.info("New lead captured", extra={
    "lead_id": lead_id,
    "email": email,
    "source": source,
    "lead_magnet": lead_magnet_id
})

logger.info("Lead enrolled in lead magnet sequence", extra={
    "email": email,
    "lead_magnet": lead_magnet_id,
    "scheduled_emails": len(sequence)
})
```

## Requirements Satisfied

✅ **Requirement 15.2:** Lead magnet nurture sequence with 4 emails
- Day 0: Delivery
- Day 2: Related Content
- Day 4: Case Study
- Day 7: Trial Invitation

✅ **Requirement 5.9:** Auto-enroll leads on capture
- Background task enrollment after lead capture
- Automatic scheduling via rq

✅ **Requirement 5.10:** Segment by lead_magnet_id
- Personalized content based on lead magnet
- Related resources specific to category
- Topic-specific messaging

## Next Steps

1. **Database Migration:**
   - Create Alembic migration for leads tables
   - Update leads.py to use PostgreSQL
   - Migrate in-memory data structure

2. **SendGrid Template Creation:**
   - Upload HTML templates to SendGrid
   - Configure dynamic template IDs
   - Test template rendering

3. **Frontend Integration:**
   - Create lead magnet landing pages
   - Implement thank you pages
   - Add analytics tracking

4. **Testing:**
   - End-to-end testing of capture flow
   - Verify email scheduling
   - Test personalization

5. **Monitoring:**
   - Set up Grafana dashboards
   - Configure alerts for low conversion rates
   - Track sequence performance

## Files Created/Modified

### Created:
- `app/data/sequences/lead_magnet.py`
- `app/routers/leads.py`
- `templates/lead_magnet_delivery.html`
- `templates/lead_magnet_delivery.txt`
- `templates/related_content.html`
- `templates/related_content.txt`
- `templates/case_study.html`
- `templates/case_study.txt`
- `templates/trial_invitation.html`
- `templates/trial_invitation.txt`
- `TASK_19_IMPLEMENTATION.md`

### Modified:
- `app/routers/sequences.py` (added lead_magnet sequence support)
- `app/config.py` (added 4 new template IDs)
- `app/services/email_service.py` (added template mappings)
- `app/main.py` (added leads router)

## Conclusion

Task 19 is now complete. The lead magnet nurture sequence is fully implemented with:
- 4-email sequence over 7 days
- Auto-enrollment on lead capture
- Segmentation by lead_magnet_id
- Personalized content
- Professional email templates
- Complete API endpoints

The system is ready for testing and integration with the frontend.
