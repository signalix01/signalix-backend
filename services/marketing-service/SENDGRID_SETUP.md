# SendGrid Setup Guide

This guide walks you through setting up SendGrid for the SignalixAI AI marketing service.

## Prerequisites

- SendGrid account (sign up at https://sendgrid.com)
- Verified sender email address
- Domain authentication (recommended for production)

## Step 1: Create SendGrid Account

1. Go to https://sendgrid.com and sign up
2. Verify your email address
3. Complete the onboarding wizard

## Step 2: Get API Key

1. Navigate to **Settings** > **API Keys**
2. Click **Create API Key**
3. Name: `SignalixAI Marketing Service`
4. Permissions: **Full Access** (or **Mail Send** + **Template Engine**)
5. Click **Create & View**
6. **Copy the API key** (you won't see it again!)
7. Add to your `.env` file:
   ```
   SENDGRID_API_KEY=SG.xxxxxxxxxxxxxxxxxxxxx
   ```

## Step 3: Verify Sender Identity

### Option A: Single Sender Verification (Quick Start)

1. Navigate to **Settings** > **Sender Authentication**
2. Click **Verify a Single Sender**
3. Fill in the form:
   - From Name: `SignalixAI AI`
   - From Email: `noreply@signalixai.com`
   - Reply To: `support@signalixai.com`
   - Company Address: `Mumbai, India`
4. Click **Create**
5. Check your email and click the verification link

### Option B: Domain Authentication (Production)

1. Navigate to **Settings** > **Sender Authentication**
2. Click **Authenticate Your Domain**
3. Select your DNS host
4. Enter your domain: `signalixai.com`
5. Follow the instructions to add DNS records
6. Wait for verification (can take up to 48 hours)

## Step 4: Create Dynamic Templates

Create 5 dynamic templates in SendGrid:

### Template 1: Welcome Email

1. Navigate to **Email API** > **Dynamic Templates**
2. Click **Create a Dynamic Template**
3. Template Name: `Welcome Email`
4. Click **Add Version**
5. Choose **Code Editor**
6. Copy content from `templates/welcome.html`
7. Click **Settings** and note the **Template ID** (e.g., `d-abc123xyz`)
8. Update `.env`:
   ```
   TEMPLATE_WELCOME=d-abc123xyz
   ```
9. Add test data:
   ```json
   {
     "first_name": "John",
     "dashboard_url": "https://signalixai.com/dashboard",
     "help_url": "https://signalixai.com/help",
     "unsubscribe_url": "https://signalixai.com/unsubscribe?email=test@example.com",
     "preferences_url": "https://signalixai.com/email-preferences?email=test@example.com"
   }
   ```
10. Click **Send Test** to verify
11. Click **Activate Template**

### Template 2: Email Verification

1. Create new template: `Email Verification`
2. Copy content from `templates/verify_email.html`
3. Note the Template ID
4. Update `.env`:
   ```
   TEMPLATE_VERIFY_EMAIL=d-xyz789abc
   ```
5. Test data:
   ```json
   {
     "verification_code": "123456"
   }
   ```
6. Send test and activate

### Template 3: Password Reset

1. Create new template: `Password Reset`
2. Copy content from `templates/password_reset.html`
3. Note the Template ID
4. Update `.env`:
   ```
   TEMPLATE_PASSWORD_RESET=d-def456ghi
   ```
5. Test data:
   ```json
   {
     "first_name": "John",
     "reset_url": "https://signalixai.com/reset-password?token=abc123",
     "reset_token": "abc123"
   }
   ```
6. Send test and activate

### Template 4: Subscription Confirmation

1. Create new template: `Subscription Confirmation`
2. Copy content from `templates/subscription_confirmation.html`
3. Note the Template ID
4. Update `.env`:
   ```
   TEMPLATE_SUBSCRIPTION_CONFIRMATION=d-jkl789mno
   ```
5. Test data:
   ```json
   {
     "first_name": "John",
     "plan_name": "Pro",
     "plan_price": "₹1,999.00",
     "billing_period": "monthly",
     "next_billing_date": "February 15, 2024",
     "dashboard_url": "https://signalixai.com/dashboard",
     "manage_subscription_url": "https://signalixai.com/settings/subscription"
   }
   ```
6. Send test and activate

### Template 5: Payment Receipt

1. Create new template: `Payment Receipt`
2. Copy content from `templates/payment_receipt.html`
3. Note the Template ID
4. Update `.env`:
   ```
   TEMPLATE_PAYMENT_RECEIPT=d-pqr012stu
   ```
5. Test data:
   ```json
   {
     "first_name": "John",
     "invoice_number": "INV-2024-001",
     "payment_date": "January 15, 2024",
     "amount_paid": "₹1,999.00",
     "plan_name": "Pro",
     "billing_period": "monthly",
     "payment_method": "Visa ending in 4242",
     "dashboard_url": "https://signalixai.com/dashboard",
     "invoice_url": "https://signalixai.com/invoices/INV-2024-001"
   }
   ```
6. Send test and activate

## Step 5: Configure Unsubscribe Groups (Optional)

For marketing emails:

1. Navigate to **Suppressions** > **Unsubscribe Groups**
2. Click **Create New Group**
3. Group Name: `Marketing Emails`
4. Description: `Promotional emails and product updates`
5. Click **Save**
6. Note the Group ID for use in marketing emails

## Step 6: Set Up Email Activity Feed

1. Navigate to **Activity**
2. Enable **Email Activity Feed**
3. Monitor email delivery, opens, clicks, bounces

## Step 7: Configure Webhooks (Optional)

For advanced tracking:

1. Navigate to **Settings** > **Mail Settings** > **Event Webhook**
2. Enable webhook
3. HTTP POST URL: `https://your-api.signalixai.com/webhooks/sendgrid`
4. Select events to track:
   - Delivered
   - Opened
   - Clicked
   - Bounced
   - Spam Report
5. Click **Save**

## Step 8: Test Integration

Run the test script:

```python
from app.tasks.email_tasks import send_welcome_email

result = send_welcome_email(
    to_email="your-email@example.com",
    first_name="Test User"
)

print(f"Email sent: {result}")
```

Check:
- ✅ Email received in inbox
- ✅ Mobile responsive design
- ✅ All links work
- ✅ Unsubscribe link present
- ✅ Plain-text version available

## Production Checklist

Before going live:

- [ ] Domain authentication completed
- [ ] All 5 templates created and activated
- [ ] Template IDs added to `.env`
- [ ] Sender identity verified
- [ ] Test emails sent and verified
- [ ] Unsubscribe groups configured
- [ ] Email activity feed enabled
- [ ] Webhooks configured (optional)
- [ ] Rate limits understood (100 emails/day free tier)
- [ ] Upgrade to paid plan if needed

## Troubleshooting

### Email not received

1. Check SendGrid Activity Feed for delivery status
2. Check spam folder
3. Verify sender identity is verified
4. Check API key permissions

### Template not found error

1. Verify template ID in `.env` matches SendGrid
2. Ensure template is activated
3. Check API key has template access

### Rate limit exceeded

1. Check your SendGrid plan limits
2. Upgrade plan if needed
3. Implement rate limiting in application

## Support

- SendGrid Documentation: https://docs.sendgrid.com
- SendGrid Support: https://support.sendgrid.com
- SignalixAI Support: support@signalixai.com
