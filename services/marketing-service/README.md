# Marketing Service

Email marketing and transactional email service for SignalixAI AI.

## Features

- **Transactional Emails**: Welcome, email verification, password reset, subscription confirmation, payment receipts
- **SendGrid Integration**: Dynamic templates with retry logic
- **Async Processing**: RQ (Redis Queue) for background email sending
- **Mobile-Responsive Templates**: All templates optimized for mobile devices
- **Plain-Text Fallback**: Every HTML template has a plain-text version

## Architecture

```
marketing-service/
├── app/
│   ├── config.py              # Service configuration
│   ├── services/
│   │   └── email_service.py   # SendGrid client wrapper
│   └── tasks/
│       └── email_tasks.py     # RQ task functions
├── templates/
│   ├── welcome.html           # Welcome email template
│   ├── welcome.txt            # Welcome email (plain text)
│   ├── verify_email.html      # Email verification template
│   ├── verify_email.txt       # Email verification (plain text)
│   ├── password_reset.html    # Password reset template
│   ├── password_reset.txt     # Password reset (plain text)
│   ├── subscription_confirmation.html
│   ├── subscription_confirmation.txt
│   ├── payment_receipt.html
│   └── payment_receipt.txt
└── requirements.txt
```

## Setup

### 1. Install Dependencies

```bash
cd signalixai-backend/services/marketing-service
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Create a `.env` file:

```env
# SendGrid
SENDGRID_API_KEY=your_sendgrid_api_key
FROM_EMAIL=noreply@signalixai.com
FROM_NAME=SignalixAI AI
REPLY_TO_EMAIL=support@signalixai.com

# SendGrid Template IDs (create these in SendGrid dashboard)
TEMPLATE_WELCOME=d-welcome-001
TEMPLATE_VERIFY_EMAIL=d-verify-email-001
TEMPLATE_PASSWORD_RESET=d-password-reset-001
TEMPLATE_SUBSCRIPTION_CONFIRMATION=d-subscription-confirmation-001
TEMPLATE_PAYMENT_RECEIPT=d-payment-receipt-001

# Redis (for RQ)
REDIS_URL=redis://localhost:6379/0

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/signalixai

# URLs
DASHBOARD_URL=https://signalixai.com/dashboard
HELP_URL=https://signalixai.com/help
UNSUBSCRIBE_BASE_URL=https://signalixai.com/unsubscribe
PREFERENCES_BASE_URL=https://signalixai.com/email-preferences
```

### 3. Create SendGrid Templates

1. Log in to SendGrid dashboard
2. Navigate to Email API > Dynamic Templates
3. Create 5 new templates with the following IDs:
   - `d-welcome-001` - Welcome Email
   - `d-verify-email-001` - Email Verification
   - `d-password-reset-001` - Password Reset
   - `d-subscription-confirmation-001` - Subscription Confirmation
   - `d-payment-receipt-001` - Payment Receipt

4. For each template:
   - Copy the HTML content from `templates/*.html`
   - Add the plain-text version from `templates/*.txt`
   - Test with sample data
   - Activate the template

### 4. Start RQ Worker

```bash
rq worker emails --url redis://localhost:6379/0
```

## Usage

### Sending Transactional Emails

```python
from app.tasks.email_tasks import (
    queue_welcome_email,
    queue_verification_email,
    queue_password_reset_email,
    queue_subscription_confirmation_email,
    queue_payment_receipt_email
)

# Welcome email
queue_welcome_email(
    to_email="user@example.com",
    first_name="John"
)

# Email verification
queue_verification_email(
    to_email="user@example.com",
    verification_code="123456"
)

# Password reset
queue_password_reset_email(
    to_email="user@example.com",
    reset_token="abc123xyz",
    first_name="John"
)

# Subscription confirmation
queue_subscription_confirmation_email(
    to_email="user@example.com",
    first_name="John",
    plan_name="Pro",
    plan_price=1999.00,
    billing_period="monthly",
    next_billing_date="2024-02-15"
)

# Payment receipt
queue_payment_receipt_email(
    to_email="user@example.com",
    first_name="John",
    invoice_number="INV-2024-001",
    payment_date="2024-01-15",
    amount_paid=1999.00,
    plan_name="Pro",
    billing_period="monthly",
    payment_method="Visa ending in 4242"
)
```

### Direct Email Sending (Synchronous)

```python
from app.services.email_service import email_service

# Send transactional email directly
result = await email_service.send_transactional(
    template_name="welcome",
    to_email="user@example.com",
    dynamic_data={
        "first_name": "John",
        "dashboard_url": "https://signalixai.com/dashboard"
    }
)
```

## Email Templates

### Template Variables

#### Welcome Email
- `first_name`: User's first name
- `dashboard_url`: Dashboard URL
- `help_url`: Help center URL
- `unsubscribe_url`: Unsubscribe URL
- `preferences_url`: Email preferences URL

#### Email Verification
- `verification_code`: 6-digit OTP code

#### Password Reset
- `first_name`: User's first name
- `reset_url`: Password reset URL with token
- `reset_token`: Reset token (for manual entry)

#### Subscription Confirmation
- `first_name`: User's first name
- `plan_name`: Plan name (Pro, Elite)
- `plan_price`: Formatted price (e.g., "₹1,999.00")
- `billing_period`: "monthly" or "annual"
- `next_billing_date`: Next billing date
- `dashboard_url`: Dashboard URL
- `manage_subscription_url`: Subscription management URL

#### Payment Receipt
- `first_name`: User's first name
- `invoice_number`: Invoice number
- `payment_date`: Payment date
- `amount_paid`: Formatted amount (e.g., "₹1,999.00")
- `plan_name`: Plan name
- `billing_period`: "monthly" or "annual"
- `payment_method`: Payment method description
- `dashboard_url`: Dashboard URL
- `invoice_url`: Invoice download URL

## Error Handling

The email service includes automatic retry logic:
- **Max Retries**: 3 attempts
- **Retry Strategy**: Exponential backoff (4s, 16s, 60s)
- **Retry Conditions**: All exceptions (network errors, 5xx errors)

## Monitoring

Monitor email sending via:
- RQ dashboard: `rq info --url redis://localhost:6379/0`
- SendGrid dashboard: Activity feed and statistics
- Application logs: All email sends are logged with status

## Testing

Test email templates locally:

```python
# Test welcome email
from app.tasks.email_tasks import send_welcome_email

result = send_welcome_email(
    to_email="test@example.com",
    first_name="Test User"
)
print(result)
```

## Compliance

All email templates include:
- ✅ Unsubscribe link (for marketing emails)
- ✅ Physical address (Mumbai, India)
- ✅ Clear sender identification
- ✅ Mobile-responsive design
- ✅ Plain-text fallback
- ✅ CAN-SPAM and GDPR compliant

## Integration with Other Services

### Auth Service
```python
# After user signup
from marketing_service.tasks.email_tasks import queue_welcome_email

queue_welcome_email(
    to_email=user.email,
    first_name=user.first_name
)
```

### Subscription Service
```python
# After subscription created
from marketing_service.tasks.email_tasks import queue_subscription_confirmation_email

queue_subscription_confirmation_email(
    to_email=user.email,
    first_name=user.first_name,
    plan_name=subscription.plan_name,
    plan_price=subscription.price,
    billing_period=subscription.billing_period,
    next_billing_date=subscription.next_billing_date.strftime("%B %d, %Y")
)
```

## Future Enhancements

- [ ] Email sequence automation (onboarding, nurture)
- [ ] Behavioral trigger emails
- [ ] A/B testing for email templates
- [ ] Email preference center
- [ ] Marketing email campaigns
- [ ] Email analytics and reporting
