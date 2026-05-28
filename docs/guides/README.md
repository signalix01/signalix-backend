# SignalixAI AI Backend

Production-grade backend for SignalixAI AI trading platform with 13-agent multi-LLM orchestration and JPM User Intelligence Framework.

## Architecture

- **Microservices**: 7 independent services (Auth, Analysis, Market Data, Portfolio, Notification, Subscription, Analytics)
- **13-Agent System**: LangGraph orchestration with specialized trading agents
- **JPM Framework**: 3-tier user intelligence (mandatory, strategic, behavioral)
- **Tech Stack**: FastAPI, PostgreSQL, Redis, LangChain, LangGraph

## Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL 15+
- Redis 7+
- Docker (optional)

### Installation

1. **Clone and setup**:
```bash
cd signalixai-backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

2. **Configure environment**:
```bash
cp .env.example .env
# Edit .env with your credentials
```

3. **Run database migrations**:
```bash
alembic upgrade head
```

4. **Start services**:
```bash
# Auth Service
python services/auth-service/main.py

# Or use Docker Compose
docker-compose up
```

## Services

### 1. Auth Service (Port 8000)
- User registration with Tier 1 mandatory fields
- Email/phone OTP verification
- JWT token management
- Password reset flow
- Google OAuth integration

**Endpoints**:
- `POST /api/v1/auth/register` - Register new user
- `POST /api/v1/auth/verify-email` - Verify email with OTP
- `POST /api/v1/auth/login` - Login
- `POST /api/v1/auth/refresh` - Refresh access token
- `POST /api/v1/auth/forgot-password` - Request password reset
- `POST /api/v1/auth/reset-password` - Reset password
- `GET /api/v1/auth/me` - Get current user
- `POST /api/v1/auth/logout` - Logout

### 2. Analysis Service (Port 8001)
- 13-agent LangGraph orchestration
- 10 analysis types with routing
- Enhanced Kelly position sizing
- User context injection
- Analysis usage tracking

### 3. Market Data Service (Port 8002)
- Real-time price feeds (WebSocket)
- OHLCV data storage (QuestDB)
- Technical indicators
- Options Greeks computation

### 4. Portfolio Service (Port 8003)
- Broker API integration (read-only)
- P&L tracking
- Daily loss limit monitoring
- Performance analytics

### 5. Notification Service (Port 8004)
- Multi-channel delivery (in-app, push, email, SMS, WhatsApp, Telegram)
- Alert configuration
- Confidence threshold filtering
- Language preference support

### 6. Subscription Service (Port 8005)
- Tier management (Basic, Standard, Premium, Enterprise)
- Usage tracking
- Payment gateway integration (Razorpay, Stripe)
- Invoice generation

### 7. Analytics Service (Port 8006)
- Event tracking
- Behavioral signal computation (Tier 3)
- Signal accuracy tracking
- Retention metrics

## Database Schema

### Core Tables

- **users**: Tier 1 mandatory fields (7 fields)
- **user_risk_profiles**: Tier 2 strategic profile
- **behavioral_signals**: Tier 3 passive collection
- **signal_feedback**: Explicit user feedback
- **subscriptions**: Subscription management
- **analyses**: Analysis results
- **analysis_types**: Routing configuration (10 types)
- **watchlists**: User watchlists
- **positions**: Portfolio positions
- **alert_configs**: Alert configuration
- **telegram_connections**: Telegram integration

## JPM User Intelligence Framework

### Tier 1: Mandatory Registration (7 Fields)
1. Email
2. Phone
3. Full Name
4. Country of Residence
5. Declared Trading Capital
6. Risk Tolerance Score (1-10)
7. Investment Horizon (intraday/swing/positional/long_term)
8. SEBI Declaration Acknowledgment

### Tier 2: Strategic Wizard (Optional)
- Financial Context (income, emergency fund, portfolio value)
- Trading Style (markets, duration, position size)
- Communication Preferences (channels, threshold, depth, language)

### Tier 3: Behavioral Learning (Passive)
- Signal acceptance rate
- Average hold time
- Loss aversion indicator
- Sector rotation pattern
- Preferred analysis types
- Time-of-day pattern

## Enhanced Kelly Position Sizing

Position size calculated with user multipliers:

```python
base_kelly = (win_prob * avg_win - loss_prob * avg_loss) / avg_win

income_multiplier = {
    "0-5L": 0.7,
    "5-15L": 0.85,
    "15-50L": 1.0,
    "50L+": 1.15
}

experience_multiplier = {
    "1-3": 0.6,  # risk_tolerance_score
    "4-6": 0.8,
    "7-8": 1.0,
    "9-10": 1.2
}

final_kelly = base_kelly * income_multiplier * experience_multiplier
position_size = capital * final_kelly * (1 - loss_aversion_adjustment)
```

## Analysis Type Routing

10 analysis types with agent routing:

1. **Swing Trade**: Technical + Fundamentals (primary)
2. **Intraday Scalp**: Technical + Sentiment (primary)
3. **Options Strategy**: Options + Technical (primary)
4. **Earnings Play**: Fundamentals + Sentiment (primary)
5. **Macro Position**: Macro + Fundamentals (primary)
6. **Portfolio Hedge**: Risk Manager + Options (primary)
7. **Technical Breakout**: Technical (primary)
8. **Mean Reversion**: Technical + Sentiment (primary)
9. **Crypto Directional**: Technical + Sentiment (primary)
10. **Forex Carry**: Macro + Technical (primary)

## Development

### Running Tests

```bash
# Unit tests
pytest tests/unit -v

# Integration tests
pytest tests/integration -v

# E2E tests
pytest tests/e2e -v

# Coverage
pytest --cov=services --cov-report=html
```

### Code Quality

```bash
# Linting
flake8 services/ shared/

# Type checking
mypy services/ shared/

# Formatting
black services/ shared/
```

## Deployment

### Railway.app

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login
railway login

# Deploy
railway up
```

### Docker

```bash
# Build
docker build -f docker/Dockerfile.auth -t signalixai/auth-service .

# Run
docker-compose up -d
```

## Monitoring

- **Prometheus**: Metrics on port 9090
- **Sentry**: Error tracking
- **Logs**: JSON structured logging

## Security

- **JWT**: Access tokens (30 min) + Refresh tokens (7-90 days)
- **Bcrypt**: Password hashing with 12 rounds
- **Rate Limiting**: 60 requests/minute per IP
- **CORS**: Configured allowed origins
- **Data Residency**: Mumbai region (ap-south-1) for SEBI compliance

## API Documentation

- **Swagger UI**: http://localhost:8000/docs (development only)
- **ReDoc**: http://localhost:8000/redoc (development only)

## Support

For issues and questions:
- GitHub Issues: https://github.com/signalixai/backend/issues
- Email: support@signalixai.com

## License

Proprietary - All Rights Reserved
