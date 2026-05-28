# Affiliate Program Implementation

**Task:** 30 - Build affiliate program  
**Requirements:** 12.7, 12.8  
**Status:** ✅ Complete

## Overview

Complete affiliate program implementation for SignalixAI AI, enabling content creators, trading educators, and influencers to earn 20% recurring commission for 12 months on referred subscriptions.

## Features Implemented

### Backend (Task 30.1)

#### Database Schema
- **affiliates** table: Stores affiliate partner information
- **affiliate_clicks** table: Tracks link clicks for attribution
- **affiliate_conversions** table: Tracks referred users and subscription status
- **affiliate_commissions** table: Individual commission records (12 months per conversion)
- **affiliate_payouts** table: Batch payout processing
- **affiliate_resources** table: Marketing materials library

#### API Endpoints

**Registration & Management:**
- `POST /api/v1/affiliates/register` - Register new affiliate
- `GET /api/v1/affiliates/{id}/stats` - Get affiliate statistics
- `GET /api/v1/affiliates/code/{code}` - Validate affiliate code

**Tracking:**
- `POST /api/v1/affiliates/track-click` - Track affiliate link clicks
- `POST /api/v1/affiliates/track-conversion` - Track signup/payment events
- `POST /api/v1/affiliates/record-commission` - Record commission for payment

**Commission & Payouts:**
- `GET /api/v1/affiliates/{id}/commissions` - Get commission history (paginated, filterable)
- `GET /api/v1/affiliates/{id}/conversions` - Get conversion tracking records
- `GET /api/v1/affiliates/{id}/payouts` - Get payout history

**Resources:**
- `GET /api/v1/affiliates/resources` - Get marketing resources (filterable by type)

### Frontend (Task 30.2)

#### Affiliate Dashboard (`/affiliate/dashboard`)

**Stats Overview:**
- Total clicks, signups, conversions
- Total earnings, pending commissions, paid commissions
- Conversion rate calculation
- Commission rate display

**Affiliate Link Management:**
- Unique affiliate link display
- One-click copy to clipboard
- Link format: `https://signalixai.com/signup?aff={code}`

**Commission History:**
- Paginated table of all commission records
- Shows: date, period (1-12), subscription amount, commission, status, payment date
- Filter by status: pending, approved, paid, cancelled

**Payout History:**
- Monthly payout batches
- Shows: date, amount, commission count, payment method, reference, status
- Status tracking: pending, processing, completed, failed

**Marketing Resources:**
- Downloadable banner ads (various sizes)
- Email templates
- Social media copy
- Product screenshots
- Organized by resource type with thumbnails

## Commission Structure

### Recurring Commission Model
- **Rate:** 20% of subscription payment
- **Duration:** 12 months per referred subscription
- **Calculation:** Commission = Subscription Amount × 0.20
- **Tracking:** Individual commission record per monthly payment (period 1-12)

### Example
If affiliate refers a user who subscribes to Pro plan (₹1,999/month):
- Month 1: ₹399.80 commission
- Month 2: ₹399.80 commission
- ...
- Month 12: ₹399.80 commission
- **Total over 12 months:** ₹4,797.60

### Commission Lifecycle
1. **Pending:** Commission recorded, awaiting approval
2. **Approved:** Verified and ready for payout
3. **Paid:** Included in payout batch and processed
4. **Cancelled:** Subscription cancelled, commission voided

## Integration Points

### 1. Signup Flow Integration

When a user visits with affiliate code:

```typescript
// Capture affiliate code from URL
const affiliateCode = searchParams.get('aff');

// Validate code
const response = await fetch(`/api/v1/affiliates/code/${affiliateCode}`);
if (response.ok) {
  // Store in localStorage for attribution
  localStorage.setItem('affiliate_code', affiliateCode);
  
  // Track click
  await fetch('/api/v1/affiliates/track-click', {
    method: 'POST',
    body: JSON.stringify({
      affiliate_code: affiliateCode,
      visitor_id: getVisitorId(),
      landing_page: window.location.href,
      // ... other tracking data
    }),
  });
}
```

### 2. Signup Completion

After user completes signup:

```typescript
const affiliateCode = localStorage.getItem('affiliate_code');
if (affiliateCode) {
  await fetch('/api/v1/affiliates/track-conversion', {
    method: 'POST',
    body: JSON.stringify({
      affiliate_code: affiliateCode,
      referred_user_id: newUserId,
      event: 'signup',
    }),
  });
}
```

### 3. First Payment

When referred user makes first payment:

```typescript
await fetch('/api/v1/affiliates/track-conversion', {
  method: 'POST',
  body: JSON.stringify({
    affiliate_code: affiliateCode,
    referred_user_id: userId,
    subscription_id: subscriptionId,
    event: 'first_payment',
  }),
});
```

### 4. Recurring Payments

On each monthly subscription payment (via webhook):

```python
# In payment webhook handler
async def handle_subscription_payment(payment_data):
    # Check if user was referred by affiliate
    conversion = await get_affiliate_conversion(payment_data['user_id'])
    
    if conversion and conversion.status == 'active':
        # Determine period (1-12)
        period = calculate_period(conversion.first_payment_at, payment_data['payment_date'])
        
        if period <= 12:
            # Record commission
            await record_commission(
                affiliate_id=conversion.affiliate_id,
                conversion_id=conversion.id,
                referred_user_id=payment_data['user_id'],
                subscription_id=payment_data['subscription_id'],
                payment_id=payment_data['payment_id'],
                subscription_amount_paise=payment_data['amount_paise'],
                period=period
            )
```

## Payout Processing

### Monthly Payout Workflow

1. **Aggregation (1st of month):**
   - Query all approved commissions from previous month
   - Group by affiliate_id
   - Calculate total payout amount per affiliate

2. **Batch Creation:**
   ```python
   payout = {
       'affiliate_id': affiliate_id,
       'amount_paise': total_commission_paise,
       'commission_count': len(commissions),
       'payment_method': affiliate.payment_method,
       'status': 'pending',
       'scheduled_date': date.today()
   }
   ```

3. **Payment Processing:**
   - Bank transfer via payment gateway
   - Update payout status to 'processing'
   - Record payment reference (UTR/transaction ID)

4. **Completion:**
   - Mark payout as 'completed'
   - Update commission records to 'paid'
   - Update affiliate totals
   - Send payout confirmation email

### Minimum Payout Threshold
- **Threshold:** ₹1,000 (100,000 paise)
- Commissions below threshold roll over to next month

## Marketing Resources

### Resource Types

1. **Banner Ads:**
   - 728x90 (Leaderboard)
   - 300x250 (Medium Rectangle)
   - 160x600 (Wide Skyscraper)
   - 320x50 (Mobile Banner)

2. **Email Templates:**
   - Welcome email with product intro
   - Feature highlight emails
   - Success story emails

3. **Social Media Copy:**
   - Twitter/X posts
   - LinkedIn posts
   - Instagram captions
   - Facebook posts

4. **Product Screenshots:**
   - Dashboard overview
   - Signal analysis examples
   - Feature highlights

### Adding Resources

```sql
INSERT INTO affiliate_resources (
    title, description, resource_type, file_url, 
    thumbnail_url, dimensions, format, status
) VALUES (
    'Leaderboard Banner - AI Trading',
    'Horizontal banner highlighting AI trading features',
    'banner',
    'https://cdn.signalixai.com/affiliate/banners/leaderboard-728x90.png',
    'https://cdn.signalixai.com/affiliate/banners/thumbs/leaderboard-728x90.jpg',
    '728x90',
    'png',
    'active'
);
```

## Admin Operations

### Approve Affiliate Application

```sql
UPDATE affiliates 
SET status = 'active', 
    approved_at = NOW(), 
    approved_by = '{admin_user_id}'
WHERE id = '{affiliate_id}';
```

### Adjust Commission Rate

```sql
UPDATE affiliates 
SET commission_rate = 25.00  -- Custom rate for special partners
WHERE id = '{affiliate_id}';
```

### Suspend Affiliate

```sql
UPDATE affiliates 
SET status = 'suspended'
WHERE id = '{affiliate_id}';
```

## Analytics & Reporting

### Key Metrics

1. **Affiliate Performance:**
   - Total affiliates (active, pending, suspended)
   - Top performers by conversions
   - Top performers by commission earned
   - Average conversion rate

2. **Commission Metrics:**
   - Total commissions paid
   - Total commissions pending
   - Average commission per conversion
   - Commission by period (1-12 months)

3. **Conversion Funnel:**
   - Clicks → Signups (signup rate)
   - Signups → First Payment (conversion rate)
   - First Payment → Month 12 (retention rate)

### Sample Queries

**Top Affiliates by Conversions:**
```sql
SELECT 
    a.name,
    a.email,
    a.total_conversions,
    a.total_commission_paise / 100.0 as total_commission_rs
FROM affiliates a
WHERE a.status = 'active'
ORDER BY a.total_conversions DESC
LIMIT 10;
```

**Commission by Period:**
```sql
SELECT 
    period,
    COUNT(*) as commission_count,
    SUM(commission_amount_paise) / 100.0 as total_commission_rs
FROM affiliate_commissions
WHERE status = 'paid'
GROUP BY period
ORDER BY period;
```

## Testing

### Test Affiliate Registration

```bash
curl -X POST http://localhost:8000/api/v1/affiliates/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "creator@example.com",
    "name": "Trading Educator",
    "payment_method": "bank_transfer",
    "payment_details": {
      "account_number": "1234567890",
      "ifsc": "HDFC0001234",
      "account_holder": "Trading Educator"
    }
  }'
```

### Test Click Tracking

```bash
curl -X POST http://localhost:8000/api/v1/affiliates/track-click \
  -H "Content-Type: application/json" \
  -d '{
    "affiliate_code": "ABC123XYZ",
    "visitor_id": "visitor_123",
    "landing_page": "https://signalixai.com/signup?aff=ABC123XYZ"
  }'
```

### Test Conversion Tracking

```bash
curl -X POST http://localhost:8000/api/v1/affiliates/track-conversion \
  -H "Content-Type: application/json" \
  -d '{
    "affiliate_code": "ABC123XYZ",
    "referred_user_id": "user_123",
    "event": "signup"
  }'
```

## Security Considerations

1. **Code Generation:**
   - 10-character alphanumeric codes
   - Excludes ambiguous characters (0, O, I, 1)
   - Collision detection with retry logic

2. **Attribution:**
   - Cookie-based tracking (7-day window)
   - localStorage backup
   - First-touch attribution model

3. **Fraud Prevention:**
   - IP address tracking
   - User agent validation
   - Duplicate conversion detection
   - Manual approval for high-value payouts

4. **Data Privacy:**
   - Affiliates see aggregate stats only
   - No PII of referred users exposed
   - GDPR-compliant data handling

## Future Enhancements

1. **Referral Tiers:**
   - Bronze: 15% commission (0-5 conversions)
   - Silver: 20% commission (6-20 conversions)
   - Gold: 25% commission (21+ conversions)

2. **Performance Bonuses:**
   - Milestone rewards (10, 25, 50, 100 conversions)
   - Monthly top performer bonuses
   - Quarterly leaderboard prizes

3. **Advanced Analytics:**
   - Real-time dashboard
   - Conversion funnel visualization
   - Geographic performance breakdown
   - Traffic source analysis

4. **Automated Payouts:**
   - Integration with Razorpay Payouts API
   - Automatic monthly processing
   - Email notifications

5. **Custom Landing Pages:**
   - Personalized landing pages per affiliate
   - A/B testing support
   - Custom messaging

## Support

For affiliate program questions:
- Email: affiliates@signalixai.com
- Documentation: https://signalixai.com/affiliate-program
- Support Portal: https://support.signalixai.com

## Changelog

### Version 1.0.0 (Current)
- ✅ Affiliate registration and approval workflow
- ✅ Click and conversion tracking
- ✅ 20% recurring commission for 12 months
- ✅ Commission and payout management
- ✅ Affiliate dashboard with stats
- ✅ Marketing resources library
- ✅ API endpoints for all operations

