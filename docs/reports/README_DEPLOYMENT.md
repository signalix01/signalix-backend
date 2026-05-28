# SignalixAI Backend - Quick Deployment Guide

**For detailed instructions, see `DEPLOYMENT_GUIDE.md`**

---

## 🚀 Quick Start (5 Minutes)

### Prerequisites
- Python 3.11+
- Railway account
- Supabase account (PostgreSQL)
- Upstash account (Redis)
- LLM API keys (at minimum: Anthropic)

### Step 1: Clone & Install

```bash
cd signalixai-backend
pip install -r requirements.txt
```

### Step 2: Setup Infrastructure

1. **Supabase PostgreSQL**:
   - Create project at https://supabase.com
   - Copy connection string
   - Convert to async: `postgresql+asyncpg://...`

2. **Upstash Redis**:
   - Create database at https://console.upstash.com
   - Copy Redis URL

3. **Sentry** (optional):
   - Create project at https://sentry.io
   - Copy DSN

### Step 3: Configure Environment

```bash
# Copy example file
cp .env.example .env.production

# Edit with your values
nano .env.production
```

**Required variables**:
```env
DATABASE_URL=postgresql+asyncpg://...
REDIS_URL=redis://...
JWT_SECRET_KEY=<generate-strong-secret>
ANTHROPIC_API_KEY=sk-ant-...
```

### Step 4: Validate Setup

```bash
# Run validation script
python scripts/setup_production.py
```

This will check:
- ✓ Python version
- ✓ Dependencies
- ✓ Environment variables
- ✓ Database connection
- ✓ Redis connection
- ✓ Configuration validity

### Step 5: Deploy to Railway

```bash
# Automated deployment
bash scripts/deploy_railway.sh
```

Or manual:
```bash
# Install Railway CLI
npm install -g @railway/cli

# Login
railway login

# Initialize project
railway init

# Set environment variables
railway variables set DATABASE_URL="..."
railway variables set REDIS_URL="..."
# ... set all other variables

# Deploy
railway up
```

### Step 6: Verify Deployment

```bash
# Check status
railway status

# View logs
railway logs

# Test health endpoint
curl https://your-project.railway.app/health
```

---

## 📊 What Gets Deployed

### 12 Microservices:
1. **Auth Service** (Port 8000) - Authentication & JWT
2. **User Service** (Port 8001) - User profiles & wizard
3. **Analysis Service** (Port 8002) - 13-agent AI pipeline
4. **Market Data Service** (Port 8003) - Real-time quotes
5. **Portfolio Service** (Port 8004) - Broker integration
6. **Notification Service** (Port 8005) - Multi-channel alerts
7. **Subscription Service** (Port 8006) - Tier management
8. **Analytics Service** (Port 8007) - Performance metrics
9. **Backtest Service** (Port 8008) - Historical replay
10. **Risk Service** (Port 8009) - Risk assessment
11. **Execution Service** (Port 8010) - Trade execution
12. **Pricing Service** (Port 8011) - Subscription pricing

### 20 AI Agents:
- Pre-Screener, Market Regime Detector
- Fundamentals, Technical, Macro, Sentiment Analysts
- News Scanner, Forex Macro, Deep Fundamentals
- Bull & Bear Researchers
- Quant Cross-Check, Risk Manager
- Final Trader
- Options, Earnings, Sector Rotation, Volatility, Liquidity, Correlation Analysts

---

## 🔒 Security Features

✅ **Implemented**:
- Rate limiting (60 req/min global, custom per endpoint)
- Security headers (HSTS, CSP, X-Frame-Options)
- HTTPS redirect (production)
- Secrets management (environment-based)
- JWT authentication
- Input validation (Pydantic)
- SQL injection prevention (ORM)
- CORS configuration

---

## 📈 Monitoring

### Sentry (Error Tracking)
- Automatic error capture
- Performance monitoring
- Release tracking

### Prometheus (Metrics)
- Endpoint: `/metrics`
- HTTP request metrics
- LLM API cost tracking
- Database query performance
- Cache hit/miss rates

### Structured Logging
- JSON format (production)
- Request/response logging
- Error logging with context

---

## 💰 Estimated Costs

| Service | Monthly Cost |
|---------|--------------|
| Railway (12 services) | $100-200 |
| Supabase PostgreSQL | $25-50 |
| Upstash Redis | $10-30 |
| Sentry | $26-99 |
| LLM APIs | $800-2780 |
| **Total** | **$961-3159** |

---

## 🆘 Troubleshooting

### Service won't start
```bash
railway logs --service auth-service
```

### Database connection failed
- Verify DATABASE_URL format
- Check Supabase database is running
- Verify connection pooling settings

### Redis connection failed
- Verify REDIS_URL format
- Check Upstash database is running

### Rate limit errors
- Increase rate limits in settings
- Implement exponential backoff

---

## 📚 Documentation

- **Full Deployment Guide**: `DEPLOYMENT_GUIDE.md`
- **Production Audit**: `PRODUCTION_READINESS_AUDIT.md`
- **Implementation Status**: `PRODUCTION_IMPLEMENTATION_COMPLETE.md`
- **API Documentation**: `API_DOCUMENTATION.md`

---

## ✅ Deployment Checklist

- [ ] Infrastructure setup (Supabase, Upstash, Sentry)
- [ ] Environment variables configured
- [ ] Validation script passed
- [ ] Database migrations run
- [ ] Initial data seeded
- [ ] All services deployed
- [ ] Health checks passing
- [ ] SSL certificate active
- [ ] Custom domain configured
- [ ] Monitoring dashboards setup
- [ ] Alerts configured

---

## 🎯 Next Steps After Deployment

1. **Test all endpoints**
2. **Create test user**
3. **Run load tests**
4. **Configure monitoring alerts**
5. **Set up backup strategy**
6. **Deploy frontend**
7. **Beta launch**
8. **Public launch**

---

**Need Help?**
- See `DEPLOYMENT_GUIDE.md` for detailed instructions
- Check `PRODUCTION_READINESS_AUDIT.md` for requirements
- Railway Support: https://railway.app/help

---

**Status**: ✅ Production Ready  
**Last Updated**: April 25, 2026  
**Version**: 1.0.0
