# Algo Builder Service - Strategy CRUD API

## Overview

This service implements the Strategy CRUD API for the Signalix Algo Builder system. It provides endpoints for creating, reading, updating, and deleting trading strategies, as well as managing strategy templates.

**Requirements**: 1.8, 1.9, 2.4, 2.5

## Architecture

### Components

1. **models.py** - Pydantic models for strategy specification validation
2. **router.py** - FastAPI router with 8 endpoints for strategy management
3. **test_router.py** - Comprehensive integration tests (pytest)
4. **run_tests.py** - Simple validation test runner (no dependencies)

### Database Schema

Strategies are stored in the `strategies` table with the following structure:

```sql
CREATE TABLE strategies (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    template_id UUID,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    spec JSONB NOT NULL,
    compiled_hash VARCHAR(64),
    status VARCHAR(20) NOT NULL DEFAULT 'draft',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
```

## API Endpoints

### 1. Create Strategy
**POST** `/api/v1/algo/strategies`

Creates a new trading strategy with validation.

**Request Body:**
```json
{
  "spec": {
    "strategy_id": "my_strategy_001",
    "user_id": "user_123",
    "name": "My RSI Strategy",
    "description": "A simple RSI oversold strategy",
    "asset_class": "equity",
    "instruments": ["NIFTY", "BANKNIFTY"],
    "entry_rules": [...],
    "exit_rules": [...],
    "position_sizing": {...},
    "market_filter": {...},
    "indicators_config": {...},
    "risk_per_trade_pct": 1.0,
    "max_daily_loss_pct": 2.0,
    "regime_awareness": true,
    "status": "draft",
    "created_at": "2025-01-15T10:00:00Z",
    "updated_at": "2025-01-15T10:00:00Z"
  }
}
```

**Response:** `201 Created`
```json
{
  "id": "uuid",
  "user_id": "uuid",
  "template_id": null,
  "name": "My RSI Strategy",
  "description": "A simple RSI oversold strategy",
  "spec": {...},
  "compiled_hash": null,
  "status": "draft",
  "created_at": "2025-01-15T10:00:00Z",
  "updated_at": "2025-01-15T10:00:00Z"
}
```

**Validation:**
- At least 1 entry rule required
- At least 1 exit rule required
- `max_position_pct` capped at 10.0%
- All indicator types, operators, and sizing methods validated

### 2. List Strategies
**GET** `/api/v1/algo/strategies`

Returns paginated list of user's strategies.

**Query Parameters:**
- `page` (default: 1) - Page number
- `limit` (default: 10, max: 100) - Items per page
- `status_filter` (optional) - Filter by status: draft, testing, paper, live

**Response:** `200 OK`
```json
{
  "strategies": [...],
  "total": 25,
  "page": 1,
  "limit": 10,
  "total_pages": 3
}
```

### 3. Get Strategy
**GET** `/api/v1/algo/strategies/{strategy_id}`

Returns full strategy details including compiled_hash.

**Response:** `200 OK`
```json
{
  "id": "uuid",
  "user_id": "uuid",
  "template_id": null,
  "name": "My RSI Strategy",
  "description": "...",
  "spec": {...},
  "compiled_hash": "sha256_hash",
  "status": "draft",
  "created_at": "2025-01-15T10:00:00Z",
  "updated_at": "2025-01-15T10:00:00Z"
}
```

### 4. Update Strategy
**PUT** `/api/v1/algo/strategies/{strategy_id}`

Updates strategy spec and invalidates compiled cache.

**Request Body:**
```json
{
  "spec": {...}
}
```

**Response:** `200 OK`
```json
{
  "id": "uuid",
  "name": "Updated Strategy Name",
  "compiled_hash": null,
  ...
}
```

**Note:** `compiled_hash` is set to `null` to invalidate the cache.

### 5. Delete Strategy
**DELETE** `/api/v1/algo/strategies/{strategy_id}`

Soft deletes a strategy (sets status=deleted). Blocks if strategy is live.

**Response:** `200 OK`
```json
{
  "success": true,
  "message": "Strategy 'My RSI Strategy' deleted successfully"
}
```

**Error:** `400 Bad Request` if strategy is live
```json
{
  "detail": "Cannot delete a live strategy. Please stop the strategy first."
}
```

### 6. Get Templates
**GET** `/api/v1/algo/templates`

Returns all pre-built strategy templates.

**Response:** `200 OK`
```json
[
  {
    "id": "uuid",
    "name": "Turtle Breakout (Richard Dennis)",
    "description": "20-day channel breakout with ATR-based position sizing...",
    "spec": {...},
    "created_at": "2025-01-15T10:00:00Z"
  },
  ...
]
```

**Available Templates:**
1. Turtle Breakout (Richard Dennis)
2. Volatility Mean Reversion (Edward Thorp)
3. Macro Momentum (Paul Tudor Jones)
4. SuperTrend + EMA Cross
5. BankNifty Iron Condor (PR Sundar)
6. Concentrated Trend (Stanley Druckenmiller)
7. Value Momentum (Rakesh Jhunjhunwala)
8. Crypto Accumulation

### 7. Clone Template
**POST** `/api/v1/algo/templates/{template_id}/clone`

Clones a template to user's strategies with status=draft.

**Response:** `201 Created`
```json
{
  "success": true,
  "message": "Template 'Turtle Breakout (Richard Dennis)' cloned successfully",
  "strategy_id": "uuid",
  "strategy": {...}
}
```

### 8. Health Check
**GET** `/api/v1/algo/health`

Service health check endpoint.

**Response:** `200 OK`
```json
{
  "status": "healthy",
  "service": "algo_builder",
  "version": "1.0.0"
}
```

## Security

### Ownership Check Middleware

All strategy endpoints (except templates) enforce ownership checks:
- Users can only access their own strategies
- Attempts to access other users' strategies return `404 Not Found`
- Template cloning creates a new strategy owned by the requesting user

### Authentication

The `get_current_user_id()` dependency extracts the user ID from the JWT token in the Authorization header.

**TODO:** Implement proper JWT authentication middleware. Currently returns a test user ID.

## Validation Rules

### Strategy Spec Validation

1. **Entry Rules**: At least 1 entry rule required
2. **Exit Rules**: At least 1 exit rule required
3. **Max Position Cap**: `max_position_pct` cannot exceed 10.0%
4. **Indicator Types**: Must be one of 16 supported types (RSI, MACD, EMA, etc.)
5. **Comparison Operators**: Must be one of 6 supported operators (>, <, crosses_above, etc.)
6. **Position Sizing Methods**: Must be one of 5 supported methods (fixed_capital, pct_capital, kelly, atr_based, vol_adj)

### Status Lifecycle

```
draft → testing → paper → live
                    ↓
                 deleted
```

**Rules:**
- Cannot promote directly from `draft` to `live` (must pass through `paper` for 30 days)
- Cannot delete a `live` strategy (must stop it first)
- Soft delete sets status to `deleted` (record remains in database)

## Testing

### Run Integration Tests (pytest)

```bash
cd signalixai-backend
pytest services/algo_builder/test_router.py -v
```

**Test Coverage:**
- ✓ Create strategy (success, validation errors, max position cap)
- ✓ List strategies (empty, with data, pagination, status filter)
- ✓ Get strategy (success, not found)
- ✓ Update strategy (success, not found, validation errors)
- ✓ Delete strategy (success, not found, live strategy blocked)
- ✓ Get templates (empty, with data)
- ✓ Clone template (success, not found)
- ✓ Ownership check (users can only access their own strategies)
- ✓ Health check

### Run Simple Validation Tests

```bash
cd signalixai-backend
python services/algo_builder/run_tests.py
```

This runs basic validation tests without requiring pytest.

## Database Setup

### Run Migrations

```bash
cd signalixai-backend
alembic upgrade head
```

This creates:
1. `strategies` table (migration 004)
2. `screening_snapshot` materialized view (migration 005)
3. Strategy templates seed data (migration 006)

### Verify Setup

```bash
cd signalixai-backend
python checkpoint_phase1_verification.py
```

## Configuration

### Environment Variables

```bash
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/signalixai
```

### Database Connection

The router creates its own database engine and session factory:

```python
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://...")
engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
```

## Integration with Gateway

Add the algo_builder service to the gateway route map:

```python
# gateway.py
ROUTE_MAP = {
    ...
    "/api/v1/algo": "algo_builder",
}

SERVICES = {
    ...
    "algo_builder": "http://localhost:8006",
}
```

## Next Steps

### Phase 3: Strategy Compiler (Tasks 7-11)

1. Implement `BaseStrategy` class
2. Implement `StrategyCompiler` to convert StrategySpec → Python code
3. Implement sandboxed execution environment
4. Add compilation endpoint: `POST /api/v1/algo/strategies/{id}/compile`
5. Add paper trading endpoint: `POST /api/v1/algo/strategies/{id}/paper`

### Integration Points

- **Backtesting Engine**: Will use compiled strategies from this API
- **Screening Engine**: Will use similar CRUD patterns
- **Alert Engine**: Will reference strategies for live execution
- **Execution Engine**: Will execute compiled strategies through broker adapters

## Troubleshooting

### Common Issues

1. **Database connection errors**
   - Check `DATABASE_URL` environment variable
   - Verify PostgreSQL is running
   - Run migrations: `alembic upgrade head`

2. **Validation errors**
   - Check that entry_rules and exit_rules are not empty
   - Verify max_position_pct ≤ 10.0
   - Ensure all enum values are valid

3. **Ownership errors (404)**
   - Verify JWT token contains correct user_id
   - Check that strategy belongs to the requesting user

## License

Copyright © 2025 Signalix. All rights reserved.
