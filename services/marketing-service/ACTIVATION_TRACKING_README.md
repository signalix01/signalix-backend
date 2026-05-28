# Activation Event Tracking System

## Overview

The activation tracking system monitors user progress through key onboarding milestones and determines when a user has completed "activation". This system is critical for measuring product-market fit, optimizing onboarding flows, and triggering behavioral email sequences.

**Task**: 22 - Implement activation event tracking  
**Requirements**: 10.1, 10.8  
**Spec**: comprehensive-marketing-growth-system

## Activation Definition

A user is considered "activated" when they complete ALL of the following milestones:

1. **Risk Profile Saved** - User completes risk profiling wizard
2. **Watchlist Added** - User adds 3+ instruments to their watchlist
3. **First Analysis Run** - User runs their first market analysis
4. **First Signal Viewed** - User views the full details of a signal

**Target Time-to-Activation**: <10 minutes from signup

## Architecture

### Frontend Components

#### 1. Activation Tracking Module
**Location**: `signalixai-frontend/lib/analytics/activation.ts`

Provides functions to track activation events from the frontend:

```typescript
import {
  trackRiskProfileSaved,
  trackWatchlistAdded,
  trackFirstAnalysisRun,
  trackFirstSignalViewed,
  getActivationStatus,
  isUserActivated
} from '@/lib/analytics/activation';

// Track risk profile saved
await trackRiskProfileSaved(userId, {
  experience: 'intermediate',
  markets: ['nse_fo', 'crypto'],
  capital: 500000
});

// Track watchlist milestone (only fires when count >= 3)
await trackWatchlistAdded(userId, instrumentCount);

// Track first analysis
await trackFirstAnalysisRun(userId, {
  instrument: 'NIFTY',
  analysisType: 'technical'
});

// Track first signal viewed
await trackFirstSignalViewed(userId, {
  signalId: 'sig_123',
  instrument: 'NIFTY',
  recommendation: 'BUY'
});

// Check activation status
const status = await getActivationStatus(userId);
console.log(status.isActivated); // true/false
console.log(status.completedEvents); // ['risk_profile_saved', ...]
console.log(status.timeToActivation); // seconds
```

#### 2. Next.js API Routes
**Location**: `signalixai-frontend/app/api/v1/tracking/activation/`

Proxies requests to the marketing service:
- `POST /api/v1/tracking/activation` - Track activation event
- `GET /api/v1/tracking/activation/[userId]` - Get activation status

### Backend Components

#### 1. Activation Router (In-Memory)
**Location**: `signalixai-backend/services/marketing-service/app/routers/activation.py`

Simple in-memory implementation for development and testing.

#### 2. Activation Router (Database-backed)
**Location**: `signalixai-backend/services/marketing-service/app/routers/activation_db.py`

Production-ready implementation using PostgreSQL for persistence.

#### 3. Database Schema
**Location**: `signalixai-backend/services/marketing-service/migrations/001_create_activation_events_table.sql`

```sql
CREATE TABLE user_activation_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Unique constraint prevents duplicate events per user
CREATE UNIQUE INDEX idx_user_activation_events_unique 
    ON user_activation_events(user_id, event_type);
```

## API Endpoints

### Track Activation Event

**Endpoint**: `POST /api/v1/tracking/activation`

**Request Body**:
```json
{
  "event_type": "risk_profile_saved",
  "user_id": "user_123",
  "timestamp": "2024-01-15T10:30:00Z",
  "metadata": {
    "experience": "intermediate",
    "markets": ["nse_fo", "crypto"],
    "capital": 500000
  }
}
```

**Response**:
```json
{
  "success": true,
  "message": "Activation event tracked",
  "activation_status": {
    "is_activated": false,
    "completed_events": ["risk_profile_saved"],
    "pending_events": [
      "watchlist_added",
      "first_analysis_run",
      "first_signal_viewed"
    ],
    "activated_at": null,
    "time_to_activation": null
  }
}
```

### Get Activation Status

**Endpoint**: `GET /api/v1/tracking/activation/{user_id}`

**Response**:
```json
{
  "is_activated": true,
  "completed_events": [
    "risk_profile_saved",
    "watchlist_added",
    "first_analysis_run",
    "first_signal_viewed",
    "activation_completed"
  ],
  "pending_events": [],
  "activated_at": "2024-01-15T10:38:45Z",
  "time_to_activation": 525
}
```

### Get Activation Events

**Endpoint**: `GET /api/v1/tracking/activation/{user_id}/events`

**Response**:
```json
{
  "user_id": "user_123",
  "events": [
    {
      "event_type": "risk_profile_saved",
      "timestamp": "2024-01-15T10:30:00Z",
      "metadata": {
        "experience": "intermediate"
      },
      "created_at": "2024-01-15T10:30:01Z"
    },
    {
      "event_type": "watchlist_added",
      "timestamp": "2024-01-15T10:32:15Z",
      "metadata": {
        "instrument_count": 3
      },
      "created_at": "2024-01-15T10:32:16Z"
    }
  ],
  "total_events": 2
}
```

### Reset Activation Events (Testing)

**Endpoint**: `DELETE /api/v1/tracking/activation/{user_id}`

**Response**:
```json
{
  "success": true,
  "message": "Activation events reset for user user_123"
}
```

## Event Types

| Event Type | Description | Metadata Fields |
|------------|-------------|-----------------|
| `risk_profile_saved` | User completes risk profiling | `experience`, `markets`, `capital` |
| `watchlist_added` | User adds 3+ instruments | `instrument_count` |
| `first_analysis_run` | User runs first analysis | `instrument`, `analysisType` |
| `first_signal_viewed` | User views signal details | `signalId`, `instrument`, `recommendation` |
| `activation_completed` | User completes all milestones | `time_to_activation`, `activated_at` |

## Integration Points

### 1. Risk Profiling Wizard
**Component**: `signalixai-frontend/components/auth/RiskProfilingWizard.tsx`

```typescript
import { trackRiskProfileSaved } from '@/lib/analytics/activation';

const handleSubmit = async (profileData) => {
  // Save profile to backend
  await saveRiskProfile(profileData);
  
  // Track activation event
  await trackRiskProfileSaved(userId, {
    experience: profileData.experience,
    markets: profileData.markets,
    capital: profileData.capital
  });
};
```

### 2. Watchlist Component
**Component**: `signalixai-frontend/components/watchlist/WatchlistManager.tsx`

```typescript
import { trackWatchlistAdded } from '@/lib/analytics/activation';

const handleAddInstrument = async (instrument) => {
  // Add instrument to watchlist
  await addToWatchlist(instrument);
  
  // Get updated count
  const count = await getWatchlistCount(userId);
  
  // Track activation event (only fires when count >= 3)
  await trackWatchlistAdded(userId, count);
};
```

### 3. Analysis Component
**Component**: `signalixai-frontend/components/analysis/AnalysisRunner.tsx`

```typescript
import { trackFirstAnalysisRun } from '@/lib/analytics/activation';

const handleRunAnalysis = async (instrument) => {
  // Run analysis
  const result = await runAnalysis(instrument);
  
  // Check if this is first analysis
  const isFirstAnalysis = await checkIfFirstAnalysis(userId);
  
  if (isFirstAnalysis) {
    await trackFirstAnalysisRun(userId, {
      instrument: instrument.symbol,
      analysisType: 'full'
    });
  }
};
```

### 4. Signal Detail Component
**Component**: `signalixai-frontend/components/signals/SignalDetail.tsx`

```typescript
import { trackFirstSignalViewed } from '@/lib/analytics/activation';

const handleViewSignal = async (signal) => {
  // Check if this is first signal view
  const isFirstView = await checkIfFirstSignalView(userId);
  
  if (isFirstView) {
    await trackFirstSignalViewed(userId, {
      signalId: signal.id,
      instrument: signal.instrument,
      recommendation: signal.recommendation
    });
  }
};
```

## Analytics Integration

### Google Tag Manager

All activation events are automatically pushed to the GTM data layer:

```javascript
window.dataLayer.push({
  event: 'activation_event',
  activation_event_type: 'risk_profile_saved',
  user_id: 'user_123',
  timestamp: '2024-01-15T10:30:00Z',
  // ... metadata
});
```

### Mixpanel

Events are also tracked in Mixpanel for product analytics:

```javascript
mixpanel.track('activation_event', {
  event_type: 'risk_profile_saved',
  user_id: 'user_123',
  // ... metadata
});
```

## Behavioral Triggers

When a user completes activation (`activation_completed` event fires), the following actions are triggered:

1. **Email Sequence**: User is enrolled in the "Activated User" nurture sequence
2. **In-App Celebration**: Confetti animation and congratulations message
3. **Feature Unlock**: Access to advanced features (if applicable)
4. **Referral Prompt**: Invitation to refer friends (Day 7 after activation)

## Monitoring and Metrics

### Key Metrics

1. **Activation Rate**: % of signups who complete activation
   - **Target**: >50%
   
2. **Time-to-Activation**: Average time from signup to activation
   - **Target**: <10 minutes
   
3. **Drop-off Points**: Which milestone has highest drop-off
   
4. **Day 1/7/30 Retention**: Retention rates by activation status

### Queries

**Activation Rate**:
```sql
SELECT 
  COUNT(DISTINCT CASE WHEN event_type = 'activation_completed' THEN user_id END) * 100.0 / 
  COUNT(DISTINCT user_id) as activation_rate
FROM user_activation_events
WHERE created_at >= NOW() - INTERVAL '30 days';
```

**Average Time-to-Activation**:
```sql
SELECT 
  AVG(
    EXTRACT(EPOCH FROM (
      SELECT MAX(timestamp) 
      FROM user_activation_events e2 
      WHERE e2.user_id = e1.user_id 
        AND e2.event_type = 'activation_completed'
    ) - MIN(timestamp))
  ) / 60 as avg_minutes_to_activation
FROM user_activation_events e1
WHERE event_type != 'activation_completed'
GROUP BY user_id;
```

**Drop-off Analysis**:
```sql
SELECT 
  event_type,
  COUNT(DISTINCT user_id) as users_completed
FROM user_activation_events
WHERE event_type != 'activation_completed'
GROUP BY event_type
ORDER BY users_completed DESC;
```

## Testing

### Manual Testing

1. **Start Marketing Service**:
   ```bash
   cd signalixai-backend/services/marketing-service
   python -m uvicorn app.main:app --reload --port 8006
   ```

2. **Test Event Tracking**:
   ```bash
   curl -X POST http://localhost:8006/api/v1/tracking/activation \
     -H "Content-Type: application/json" \
     -d '{
       "event_type": "risk_profile_saved",
       "user_id": "test_user_123",
       "timestamp": "2024-01-15T10:30:00Z",
       "metadata": {"experience": "intermediate"}
     }'
   ```

3. **Check Status**:
   ```bash
   curl http://localhost:8006/api/v1/tracking/activation/test_user_123
   ```

4. **Complete Activation**:
   ```bash
   # Track all required events
   for event in risk_profile_saved watchlist_added first_analysis_run first_signal_viewed; do
     curl -X POST http://localhost:8006/api/v1/tracking/activation \
       -H "Content-Type: application/json" \
       -d "{\"event_type\": \"$event\", \"user_id\": \"test_user_123\", \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}"
   done
   ```

5. **Reset for Testing**:
   ```bash
   curl -X DELETE http://localhost:8006/api/v1/tracking/activation/test_user_123
   ```

### Frontend Testing

```typescript
// In browser console or test file
import { 
  trackRiskProfileSaved,
  trackWatchlistAdded,
  trackFirstAnalysisRun,
  trackFirstSignalViewed,
  getActivationStatus
} from '@/lib/analytics/activation';

const userId = 'test_user_123';

// Track events
await trackRiskProfileSaved(userId, { experience: 'intermediate' });
await trackWatchlistAdded(userId, 3);
await trackFirstAnalysisRun(userId, { instrument: 'NIFTY' });
await trackFirstSignalViewed(userId, { signalId: 'sig_123' });

// Check status
const status = await getActivationStatus(userId);
console.log('Activated:', status.isActivated);
console.log('Time to activation:', status.timeToActivation, 'seconds');
```

## Production Deployment

### Environment Variables

Add to `.env`:
```bash
# Marketing Service
MARKETING_SERVICE_URL=https://marketing.signalixai.com

# Database (for activation_db.py)
DATABASE_URL=postgresql://user:password@host:5432/signalixai
```

### Database Migration

Run the migration to create the table:
```bash
psql $DATABASE_URL < migrations/001_create_activation_events_table.sql
```

### Switch to Database-backed Router

In `app/main.py`, replace:
```python
from app.routers import activation
```

With:
```python
from app.routers import activation_db as activation
```

## Troubleshooting

### Events Not Tracking

1. Check browser console for errors
2. Verify marketing service is running
3. Check network tab for failed requests
4. Verify API route is proxying correctly

### Duplicate Events

Events are deduplicated by `(user_id, event_type)` unique constraint. If you see duplicates, check:
1. Database constraint is in place
2. Frontend isn't calling track functions multiple times
3. Event type values match exactly

### Activation Not Completing

1. Check all 4 required events are tracked
2. Verify event types match exactly (case-sensitive)
3. Check activation status endpoint response
4. Review backend logs for errors

## Future Enhancements

1. **Cohort Analysis**: Track activation rates by signup source, persona, etc.
2. **A/B Testing**: Test different activation definitions
3. **Predictive Scoring**: ML model to predict activation likelihood
4. **Real-time Alerts**: Notify team when activation rate drops
5. **Personalized Nudges**: In-app prompts based on pending milestones
6. **Activation Funnel Visualization**: Dashboard showing drop-off at each step

## References

- **Spec**: `.kiro/specs/comprehensive-marketing-growth-system/`
- **Requirements**: Requirements 10.1, 10.8
- **Design**: design.md sections on Activation and Onboarding
- **Tasks**: tasks.md Task 22
