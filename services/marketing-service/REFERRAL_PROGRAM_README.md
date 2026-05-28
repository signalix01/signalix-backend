# Referral Program Implementation

## Overview

The referral program allows users to refer friends and earn rewards. When a referred user becomes a paying customer:
- **Referrer** gets 1 month free Pro subscription
- **Referred user** gets 20% discount on first month

## Architecture

### Backend Components

#### 1. Database Tables

**referrers**
- Stores referral codes and stats for users who refer others
- Fields: `user_id`, `referral_code`, `total_referrals`, `successful_referrals`, `total_rewards_paise`

**referrals**
- Tracks individual referral relationships
- Fields: `referrer_id`, `referred_user_id`, `status`, `signup_at`, `activated_at`, `converted_at`

**referral_rewards**
- Stores rewards granted for successful referrals
- Fields: `referral_id`, `user_id`, `reward_type`, `reward_value_paise`, `status`

#### 2. API Endpoints

**POST /api/v1/referrals/generate**
- Generates unique referral code for a user
- Returns referral link: `https://signalixai.com/signup?ref=ABC12345`

**GET /api/v1/referrals/stats/{user_id}**
- Returns referral statistics:
  - referrals_sent
  - referrals_signed_up
  - referrals_converted
  - rewards_earned_paise

**POST /api/v1/referrals/track**
- Tracks referral events: `signup`, `activation`, `conversion`
- Triggers reward granting on conversion

**GET /api/v1/referrals/code/{referral_code}**
- Validates a referral code
- Used when user visits referral link

#### 3. Reward Service

**RewardService** (`app/services/reward_service.py`)
- Handles reward application logic
- Integrates with subscription service to:
  - Extend referrer's Pro subscription by 1 month
  - Apply 20% discount coupon to referred user

### Frontend Components

#### 1. ReferralWidget

**Location**: `components/dashboard/ReferralWidget.tsx`

**Features**:
- Displays unique referral link with copy button
- Share buttons for WhatsApp, Telegram, Email
- Shows referral stats (signed up, converted, rewards earned)
- Responsive design for mobile and desktop

**Usage**:
```tsx
import { ReferralWidget } from '@/components/dashboard/ReferralWidget';

<ReferralWidget userId={currentUser.id} />
```

#### 2. Referral Landing Page

**Location**: `app/(marketing)/referral/[code]/page.tsx`

**Features**:
- Displays referral program benefits
- Shows discounted pricing
- How it works section
- Terms and conditions
- CTA to signup with referral code pre-applied

**Route**: `/referral/ABC12345`

#### 3. Referral Tracking Utilities

**Location**: `lib/referral.ts`

**Functions**:
- `captureReferralCode()` - Captures ref param from URL
- `getStoredReferralCode()` - Retrieves stored code from localStorage/cookie
- `trackReferralEvent()` - Tracks signup/activation/conversion events
- `validateReferralCode()` - Validates code with backend
- `generateReferralLink()` - Generates referral link for user

## Integration Guide

### 1. Database Setup

Run the migration to create referral tables:

```bash
cd signalixai-backend/services/marketing-service
psql $DATABASE_URL -f migrations/002_create_referral_tables.sql
```

### 2. Environment Variables

Add to `.env`:

```env
# Frontend URL for referral links
FRONTEND_URL=https://signalixai.com

# Subscription service URL for reward granting
SUBSCRIPTION_SERVICE_URL=http://localhost:8006
```

### 3. Frontend Integration

#### Initialize Referral Tracking

Add to your root layout or app component:

```tsx
'use client';

import { useEffect } from 'react';
import { initReferralTracking } from '@/lib/referral';

export function RootLayout({ children }) {
  useEffect(() => {
    initReferralTracking();
  }, []);

  return <>{children}</>;
}
```

#### Track Signup Event

In your signup completion handler:

```tsx
import { trackReferralEvent } from '@/lib/referral';

async function handleSignupComplete(userId: string) {
  // Track referral signup
  await trackReferralEvent('signup', userId);
  
  // Continue with normal signup flow
  router.push('/dashboard?welcome=true');
}
```

#### Track Activation Event

When user completes activation (first analysis):

```tsx
import { trackReferralEvent } from '@/lib/referral';

async function handleFirstAnalysisComplete(userId: string) {
  await trackReferralEvent('activation', userId);
}
```

#### Track Conversion Event

When user upgrades to paid subscription:

```tsx
import { trackReferralEvent } from '@/lib/referral';

async function handleSubscriptionUpgrade(userId: string) {
  await trackReferralEvent('conversion', userId);
}
```

#### Add ReferralWidget to Dashboard

```tsx
import { ReferralWidget } from '@/components/dashboard/ReferralWidget';

export function DashboardSidebar({ userId }) {
  return (
    <div className="space-y-6">
      {/* Other sidebar content */}
      
      <ReferralWidget userId={userId} />
    </div>
  );
}
```

### 4. Subscription Service Integration

The reward service calls the subscription service to grant rewards. Ensure these endpoints exist:

**POST /api/v1/subscriptions/extend**
```json
{
  "user_id": "uuid",
  "tier": "pro",
  "duration_days": 30,
  "reason": "referral_reward"
}
```

**POST /api/v1/coupons/create**
```json
{
  "user_id": "uuid",
  "discount_percent": 20,
  "max_redemptions": 1,
  "duration": "once",
  "reason": "referral_reward"
}
```

## User Flow

### Referrer Flow

1. User clicks "Refer & Earn" in dashboard
2. ReferralWidget displays unique referral link
3. User shares link via WhatsApp/Telegram/Email
4. When referred user converts, referrer gets 1 month free Pro
5. Stats update in ReferralWidget

### Referred User Flow

1. User clicks referral link: `https://signalixai.com/signup?ref=ABC12345`
2. Referral code captured and stored in localStorage + cookie
3. User lands on referral landing page showing benefits
4. User clicks "Start Free Trial" → redirected to signup with ref param
5. User completes signup → referral signup event tracked
6. User completes first analysis → referral activation event tracked
7. User upgrades to paid → referral conversion event tracked
8. 20% discount automatically applied to first invoice
9. Referrer receives 1 month free Pro

## Testing

### Test Referral Code Generation

```bash
curl -X POST http://localhost:8010/api/v1/referrals/generate \
  -H "Content-Type: application/json" \
  -d '{"user_id": "123e4567-e89b-12d3-a456-426614174000"}'
```

Expected response:
```json
{
  "referral_code": "ABC12345",
  "referral_link": "https://signalixai.com/signup?ref=ABC12345"
}
```

### Test Referral Tracking

```bash
curl -X POST http://localhost:8010/api/v1/referrals/track \
  -H "Content-Type: application/json" \
  -d '{
    "referral_code": "ABC12345",
    "referred_user_id": "223e4567-e89b-12d3-a456-426614174000",
    "event": "signup"
  }'
```

### Test Referral Stats

```bash
curl http://localhost:8010/api/v1/referrals/stats/123e4567-e89b-12d3-a456-426614174000
```

Expected response:
```json
{
  "referral_code": "ABC12345",
  "referrals_sent": 5,
  "referrals_signed_up": 3,
  "referrals_converted": 1,
  "rewards_earned_paise": 199900,
  "rewards_pending_paise": 0
}
```

## Monitoring

### Key Metrics

- **Referral Conversion Rate**: `referrals_converted / referrals_sent`
- **Signup Rate**: `referrals_signed_up / referrals_sent`
- **Activation Rate**: `referrals_activated / referrals_signed_up`
- **Average Reward Value**: `total_rewards_paise / successful_referrals`

### Database Queries

**Top Referrers**:
```sql
SELECT 
  r.user_id,
  r.referral_code,
  r.successful_referrals,
  r.total_rewards_paise
FROM referrers r
ORDER BY r.successful_referrals DESC
LIMIT 10;
```

**Referral Funnel**:
```sql
SELECT 
  COUNT(*) as total_referrals,
  COUNT(*) FILTER (WHERE signup_at IS NOT NULL) as signed_up,
  COUNT(*) FILTER (WHERE activated_at IS NOT NULL) as activated,
  COUNT(*) FILTER (WHERE converted_at IS NOT NULL) as converted
FROM referrals
WHERE created_at >= NOW() - INTERVAL '30 days';
```

**Pending Rewards**:
```sql
SELECT 
  rr.user_id,
  rr.reward_type,
  rr.reward_value_paise,
  rr.created_at
FROM referral_rewards rr
WHERE rr.status = 'pending'
ORDER BY rr.created_at DESC;
```

## Troubleshooting

### Referral Code Not Captured

- Check browser console for errors
- Verify `ref` parameter in URL
- Check localStorage: `localStorage.getItem('signalixai_ref_code')`
- Check cookie: `document.cookie`

### Rewards Not Granted

- Check `referral_rewards` table for status
- Check subscription service logs for errors
- Verify subscription service endpoints are accessible
- Check reward service logs: `grep "award_referral_rewards" logs/marketing-service.log`

### Stats Not Updating

- Verify referral tracking events are being called
- Check `referrals` table for event timestamps
- Check `referrers` table for counter updates
- Review marketing service logs for tracking errors

## Future Enhancements

1. **Referral Tiers**: Different rewards based on number of successful referrals
2. **Affiliate Program**: Extended program for content creators with recurring commissions
3. **Referral Leaderboard**: Gamification with top referrers displayed
4. **Custom Referral Codes**: Allow users to choose custom codes
5. **Referral Analytics Dashboard**: Detailed analytics for referrers
6. **Email Notifications**: Notify referrers when someone signs up or converts
7. **Social Sharing Templates**: Pre-made social media posts for sharing
8. **Referral Contests**: Time-limited contests with bonus rewards

## Support

For issues or questions:
- Check logs: `tail -f logs/marketing-service.log`
- Review database state: `psql $DATABASE_URL`
- Contact: support@signalixai.com
