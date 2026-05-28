# SignalixAI Backend - Production Deployment Guide

**Version**: 1.0.0  
**Last Updated**: April 25, 2026  
**Status**: ✅ Production Ready

---

## 📋 Table of Contents

1. [Prerequisites](#prerequisites)
2. [Infrastructure Setup](#infrastructure-setup)
3. [Environment Configuration](#environment-configuration)
4. [Railway Deployment](#railway-deployment)
5. [Post-Deployment](#post-deployment)
6. [Monitoring & Maintenance](#monitoring--maintenance)
7. [Troubleshooting](#troubleshooting)

---

## 1. Prerequisites

### Required Accounts

- [ ] **Railway.app** account (https://railway.app)
- [ ] **Supabase** account for PostgreSQL (https://supabase.com)
- [ ] **Upstash** account for Redis (https://upstash.com)
- [ ] **Sentry** account for error tracking (https://sentry.io)
- [ ] **LLM API Keys**:
  - Anthropic (Claude) - https://console.anthropic.com
  - OpenAI (GPT-4) - https://platform.openai.com
  - Google (Gemini) - https://makersuite.google.com
  - xAI (Grok) - https://x.ai
  - DeepSeek - https://platform.deepseek.com
  - Mistral - https://console.mistral.ai

### Required Tools

```bash
# Install Railway CLI
npm install -g @railway/cli

# Install Python 3.11+
python --version  # Should be 3.11 or higher

# Install Git
git --version
```

---

## 2. Infrastructure Setup

### 2.1 Database (Supabase PostgreSQL)

1. **Create Supabase Project**:
   - Go to https://supabase.com/dashboard
   - Click "New Project"
   - Name: `signalixai-production`
   - Region: `Mumbai (ap-south-1)` for SEBI compliance
   - Database Password: Generate strong password

2. **Get Connection String**:
   - Go to Project Settings → Database
   - Copy "Connection string" (URI format)
   - Format: `postgresql://postgres:[PASSWORD]@[HOST]:5432/postgres`
   - Convert to async: `postgresql+asyncpg://postgres:[PASSWORD]@[HOST]:5432/postgres`

3. **Configure Connection Pooling**:
   - Enable PgBouncer in Supabase settings
   - Use pooler connection string for production

### 2.2 Cache (Upstash Redis)

1. **Create Upstash Database**:
   - Go to https://console.upstash.com
   - Click "Create Database"
   - Name: `signalixai-cache`
   - Region: `Mumbai` (closest to Supabase)
   - Type: `Regional` (cheaper) or `Global` (faster)

2. **Get Connection String**:
   - Copy "Redis URL" from database details
   - Format: `redis://default:[PASSWORD]@[HOST]:6379`

### 2.3 Error Tracking (Sentry)

1. **Create Sentry Project**:
   - Go to https://sentry.io
   - Create new project
   - Platform: `Python`
   - Name: `signalixai-backend`

2. **Get DSN**:
   - Copy DSN from project settings
   - Format: `https://[KEY]@[ORG].ingest.sentry.io/[PROJECT]`

---

## 3. Environment Configuration

### 3.1 Required Environment Variables

Create a `.env.production` file with the following variables:

```env
# Application
APP_NAME=SignalixAI AI
APP_VERSION=1.0.0
ENVIRONMENT=production
DEBUG=False

# API
API_V1_PREFIX=/api/v1
ALLOWED_ORIGINS=https://signalixai.com,https://www.signalixai.com

# Database (Supabase)
DATABASE_URL=postgresql+asyncpg://postgres:[PASSWORD]@[HOST]:5432/postgres
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=10

# Redis (Upstash)
REDIS_URL=redis://default:[PASSWORD]@[HOST]:6379
REDIS_MAX_CONNECTIONS=50

# JWT
JWT_SECRET_KEY=[GENERATE_STRONG_SECRET]
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# Security
BCRYPT_ROUNDS=12
RATE_LIMIT_PER_MINUTE=60

# LLM API Keys
ANTHROPIC_API_KEY=sk-ant-[YOUR_KEY]
GOOGLE_API_KEY=AIzaSy[YOUR_KEY]
OPENAI_API_KEY=sk-[YOUR_KEY]
XAI_API_KEY=xai-[YOUR_KEY]
DEEPSEEK_API_KEY=sk-[YOUR_KEY]
MISTRAL_API_KEY=[YOUR_KEY]

# Monitoring
SENTRY_DSN=https://[KEY]@[ORG].ingest.sentry.io/[PROJECT]
PROMETHEUS_PORT=9090

# External Services (Optional)
SENDGRID_API_KEY=SG.[YOUR_KEY]
TWILIO_ACCOUNT_SID=AC[YOUR_SID]
TWILIO_AUTH_TOKEN=[YOUR_TOKEN]
WHATSAPP_API_KEY=[YOUR_KEY]
TELEGRAM_BOT_TOKEN=[YOUR_TOKEN]

# Payment Gateways (Optional)
RAZORPAY_KEY_ID=rzp_live_[YOUR_KEY]
RAZORPAY_KEY_SECRET=[YOUR_SECRET]
STRIPE_API_KEY=sk_live_[YOUR_KEY]

# Broker APIs (Optional)
ZERODHA_API_KEY=[YOUR_KEY]
ZERODHA_API_SECRET=[YOUR_SECRET]
ANGEL_ONE_API_KEY=[YOUR_KEY]
UPSTOX_API_KEY=[YOUR_KEY]

# Feature Flags
ENABLE_WHATSAPP=True
ENABLE_TELEGRAM=True
ENABLE_SMS=True
ENABLE_BEHAVIORAL_SIGNALS=True
ENABLE_FEEDBACK_LOOP=True

# Data Residency
DATA_REGION=ap-south-1
```

### 3.2 Generate JWT Secret

```bash
# Generate a secure JWT secret
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

---

## 4. Railway Deployment

### 4.1 Automated Deployment (Recommended)

```bash
# Navigate to backend directory
cd signalixai-backend

# Run deployment script
bash scripts/deploy_railway.sh
```

The script will:
1. Check Railway CLI installation
2. Authenticate with Railway
3. Create/link Railway project
4. Prompt for environment variables
5. Run database migrations
6. Seed initial data
7. Deploy all services

### 4.2 Manual Deployment

#### Step 1: Initialize Railway Project

```bash
# Login to Railway
railway login

# Initialize project
railway init

# Link to existing project (if already created)
railway link [PROJECT_ID]
```

#### Step 2: Set Environment Variables

```bash
# Set all environment variables
railway variables set DATABASE_URL="postgresql+asyncpg://..."
railway variables set REDIS_URL="redis://..."
railway variables set JWT_SECRET_KEY="..."
railway variables set ANTHROPIC_API_KEY="sk-ant-..."
railway variables set OPENAI_API_KEY="sk-..."
railway variables set GOOGLE_API_KEY="AIzaSy..."
railway variables set SENTRY_DSN="https://..."

# ... set all other variables from .env.production
```

Or use the Railway dashboard:
1. Go to https://railway.app/dashboard
2. Select your project
3. Go to "Variables" tab
4. Add all environment variables

#### Step 3: Run Database Migrations

```bash
# Run migrations
railway run alembic upgrade head

# Seed initial data
railway run python scripts/init_database.py
```

#### Step 4: Deploy Services

```bash
# Deploy all services
railway up

# Or deploy specific service
railway up --service auth-service
```

### 4.3 Configure Custom Domain

1. Go to Railway dashboard
2. Select your project
3. Go to "Settings" → "Domains"
4. Add custom domain: `api.signalixai.com`
5. Update DNS records as instructed
6. Wait for SSL certificate provisioning (automatic)

---

## 5. Post-Deployment

### 5.1 Verify Deployment

```bash
# Check service status
railway status

# View logs
railway logs

# Open in browser
railway open
```

### 5.2 Test Endpoints

```bash
# Health check
curl https://api.signalixai.com/health

# Auth service
curl https://api.signalixai.com/api/v1/auth/health

# Analysis service
curl https://api.signalixai.com/api/v1/analysis/health
```

### 5.3 Create Test User

```bash
# Create test user
railway run python scripts/create_test_user.py
```

### 5.4 Load Testing

```bash
# Install k6
brew install k6  # macOS
# or
choco install k6  # Windows

# Run load test
k6 run tests/load/basic_load_test.js
```

---

## 6. Monitoring & Maintenance

### 6.1 Monitoring Dashboards

**Sentry** (Error Tracking):
- URL: https://sentry.io/organizations/[ORG]/projects/signalixai-backend/
- Monitor: Error rates, performance issues

**Railway** (Infrastructure):
- URL: https://railway.app/dashboard
- Monitor: CPU, memory, network usage

**Prometheus** (Metrics):
- URL: https://api.signalixai.com/metrics
- Metrics: Request rates, latencies, LLM costs

### 6.2 Log Aggregation

```bash
# View real-time logs
railway logs --follow

# Filter by service
railway logs --service auth-service

# Export logs
railway logs --json > logs.json
```

### 6.3 Alerts Configuration

**Sentry Alerts**:
1. Go to Sentry project settings
2. Configure alerts for:
   - Error rate > 10/minute
   - Response time > 5 seconds
   - Database connection failures

**Railway Alerts**:
1. Go to Railway project settings
2. Configure alerts for:
   - CPU usage > 80%
   - Memory usage > 90%
   - Service crashes

### 6.4 Backup Strategy

**Database Backups** (Supabase):
- Automatic daily backups (enabled by default)
- Point-in-time recovery (7 days)
- Manual backup: Project Settings → Database → Backups

**Code Backups**:
- Git repository (GitHub)
- Tagged releases for each deployment

---

## 7. Troubleshooting

### 7.1 Common Issues

#### Issue: Service won't start

**Symptoms**: Service crashes immediately after deployment

**Solutions**:
```bash
# Check logs
railway logs --service [SERVICE_NAME]

# Verify environment variables
railway variables

# Check database connection
railway run python -c "from shared.database.session import engine; print(engine)"
```

#### Issue: Database connection timeout

**Symptoms**: `asyncpg.exceptions.ConnectionDoesNotExistError`

**Solutions**:
1. Verify DATABASE_URL is correct
2. Check Supabase database is running
3. Verify connection pooling settings
4. Increase `DATABASE_POOL_SIZE` if needed

#### Issue: Redis connection failed

**Symptoms**: `redis.exceptions.ConnectionError`

**Solutions**:
1. Verify REDIS_URL is correct
2. Check Upstash database is running
3. Verify Redis password
4. Check network connectivity

#### Issue: Rate limit errors

**Symptoms**: `429 Too Many Requests`

**Solutions**:
1. Increase rate limits in settings
2. Implement exponential backoff in client
3. Use Redis for distributed rate limiting

#### Issue: LLM API failures

**Symptoms**: `anthropic.APIError` or similar

**Solutions**:
1. Verify API keys are correct
2. Check API quota/billing
3. Implement retry logic with exponential backoff
4. Monitor LLM API status pages

### 7.2 Performance Optimization

**Slow Analysis Requests**:
```python
# Enable response caching
from shared.utils.cache import cache_analysis_result

@cache_analysis_result(ttl=3600)  # Cache for 1 hour
async def run_analysis(...):
    ...
```

**High Database Load**:
```python
# Add database indexes
alembic revision -m "add_indexes"

# In migration file:
op.create_index('idx_analyses_user_id', 'analyses', ['user_id'])
op.create_index('idx_analyses_created_at', 'analyses', ['created_at'])
```

**High Memory Usage**:
```yaml
# Increase Railway service memory
# In railway.toml:
[deploy]
memoryLimit = 2048  # 2GB
```

### 7.3 Rollback Procedure

```bash
# List deployments
railway deployments

# Rollback to previous deployment
railway rollback [DEPLOYMENT_ID]

# Or rollback database
railway run alembic downgrade -1
```

### 7.4 Emergency Contacts

- **Railway Support**: https://railway.app/help
- **Supabase Support**: https://supabase.com/support
- **Sentry Support**: https://sentry.io/support
- **LLM API Support**:
  - Anthropic: support@anthropic.com
  - OpenAI: https://help.openai.com
  - Google: https://support.google.com

---

## 8. Security Checklist

- [ ] All secrets stored in Railway environment variables (not in code)
- [ ] HTTPS enabled with valid SSL certificate
- [ ] Rate limiting configured on all endpoints
- [ ] Security headers enabled (HSTS, CSP, etc.)
- [ ] Database connection uses SSL/TLS
- [ ] Redis connection uses TLS
- [ ] CORS configured with specific origins (not `*`)
- [ ] JWT secret is strong and unique
- [ ] Sentry configured to filter sensitive data
- [ ] API documentation disabled in production (`docs_url=None`)
- [ ] Database backups enabled and tested
- [ ] Monitoring alerts configured
- [ ] Incident response plan documented

---

## 9. Cost Optimization

### Current Monthly Costs

| Service | Cost |
|---------|------|
| Railway (12 services) | $100-200 |
| Supabase PostgreSQL | $25-50 |
| Upstash Redis | $10-30 |
| Sentry | $26-99 |
| LLM APIs | $800-2780 |
| **Total** | **$961-3159/month** |

### Optimization Strategies

1. **LLM Caching**: Save 30-50% on LLM costs
   ```python
   # Cache analysis results for 24 hours
   @cache_analysis_result(ttl=86400)
   ```

2. **Auto-scaling**: Scale down during off-hours
   ```yaml
   # In railway.toml
   [deploy]
   minReplicas = 1
   maxReplicas = 5
   ```

3. **Reserved Instances**: Commit to 1-year for 30% savings

4. **Tiered Analysis**: Route to cheaper models for basic tier

---

## 10. Next Steps

After successful deployment:

1. **Frontend Deployment**: Deploy Next.js frontend to Vercel
2. **Domain Configuration**: Set up custom domain and SSL
3. **Monitoring Setup**: Configure all monitoring dashboards
4. **Load Testing**: Run comprehensive load tests
5. **Security Audit**: Conduct security penetration testing
6. **Beta Launch**: Invite beta users for testing
7. **Marketing**: Prepare for public launch

---

**Deployment Checklist**: See `PRODUCTION_READINESS_AUDIT.md` Section 13

**Support**: For deployment issues, contact the DevOps team or create an issue in the repository.

---

**Last Updated**: April 25, 2026  
**Version**: 1.0.0  
**Status**: ✅ **PRODUCTION READY**
