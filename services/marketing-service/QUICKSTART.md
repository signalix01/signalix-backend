# Quick Start Guide

Get the marketing service up and running in 5 minutes.

## Prerequisites

- Python 3.11+
- Redis running locally or Upstash Redis URL
- SendGrid account (free tier works)

## Step 1: Install Dependencies (1 min)

```bash
cd signalixai-backend/services/marketing-service
pip install -r requirements.txt
```

## Step 2: Configure Environment (2 min)

```bash
# Copy example env file
cp .env.example .env

# Edit .env and add your SendGrid API key
# Minimum required:
SENDGRID_API_KEY=your_key_here
REDIS_URL=redis://localhost:6379/0
```

Get SendGrid API key:
1. Sign up at https://sendgrid.com (free)
2. Go to Settings > API Keys
3. Create API Key with "Mail Send" permission
4. Copy key to `.env`

## Step 3: Create SendGrid Templates (2 min)

**Quick method** - Use SendGrid's template import:

1. Log in to SendGrid
2. Go to Email API > Dynamic Templates
3. Create 5 templates and copy the HTML from `templates/*.html`
4. Note each template ID and add to `.env`:

```env
TEMPLATE_WELCOME=d-abc123
TEMPLATE_VERIFY_EMAIL=d-def456
TEMPLATE_PASSWORD_RESET=d-ghi789
TEMPLATE_SUBSCRIPTION_CONFIRMATION=d-jkl012
TEMPLATE_PAYMENT_RECEIPT=d-mno345
```

**Detailed guide**: See `SENDGRID_SETUP.md`

## Step 4: Start RQ Worker (30 sec)

```bash
# In a separate terminal
rq worker emails --url redis://localhost:6379/0
```

## Step 5: Test It! (30 sec)

```bash
# Edit test_email_service.py and replace test@example.com with your email
# Then run:
python test_email_service.py
```

You should receive 5 test emails in your inbox!

## Usage in Your Code

```python
from marketing_service.app.tasks.email_tasks import queue_welcome_email

# Send welcome email
queue_welcome_email(
    to_email="user@example.com",
    first_name="John"
)
```

## Next Steps

- Read `README.md` for detailed documentation
- See `SENDGRID_SETUP.md` for production setup
- Check `IMPLEMENTATION.md` for architecture details

## Troubleshooting

**Email not received?**
- Check spam folder
- Verify SendGrid API key is correct
- Check RQ worker is running: `rq info`

**Template not found?**
- Verify template IDs in `.env` match SendGrid
- Ensure templates are activated in SendGrid

**Need help?**
- See `SENDGRID_SETUP.md` for detailed troubleshooting
- Check SendGrid Activity Feed for delivery status
