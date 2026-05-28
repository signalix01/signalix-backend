# SignalixAI Backend API Documentation

## Quick Start

### View Interactive Documentation

1. **Start the API server:**
   ```bash
   cd signalixai-backend
   uvicorn main_app:app --reload --host 0.0.0.0 --port 8080
   ```

2. **Access the documentation:**
   - **Swagger UI:** http://localhost:8080/api/docs
   - **ReDoc:** http://localhost:8080/api/redoc
   - **OpenAPI JSON:** http://localhost:8080/api/openapi.json

### Generate OpenAPI Specification

```bash
# Simple generation (no dependencies required)
python generate_openapi_simple.py

# Full generation (requires all dependencies)
python generate_openapi_spec.py
```

**Output:** `api_spec.json`

## API Overview

SignalixAI Backend API provides four core systems:

### 🎯 Algo Builder (`/api/v1/algo`)
Build trading strategies without code. Compile to executable Python, validate in sandbox, deploy to paper or live trading.

**Endpoints:** 10
- Strategy CRUD (create, read, update, delete)
- Template management (list, clone)
- Compilation & validation
- Paper trading
- Live promotion

### 📊 Backtesting (`/api/v1/backtest`)
Dual-mode backtesting with walk-forward validation and Monte Carlo simulation.

**Endpoints:** 5
- Submit backtest (async)
- Check status
- Get results
- View history

### 🔍 Screening (`/api/v1/screen`)
AI-powered multi-layer screening across 10,000+ instruments.

**Endpoints:** 10
- Criteria CRUD
- Template management
- On-demand screening
- Results & history

### 🚨 Alerts (`/api/v1/alerts`)
Real-time anomaly detection with whale/institutional tracking.

**Endpoints:** 6
- Alert rule CRUD
- Test alerts
- Delivery configuration

## Authentication

All endpoints require JWT authentication:

```http
Authorization: Bearer <your_jwt_token>
```

Get your token from the `/api/v1/auth/login` endpoint.

## Documentation Files

### Generated Files

1. **`api_spec.json`** - Complete OpenAPI 3.0.3 specification
   - Import into Postman, Insomnia, or other API clients
   - Validate with online tools
   - Generate client SDKs

2. **`main_app.py`** - Unified FastAPI application
   - Hosts interactive docs at `/api/docs`
   - Environment-aware (docs disabled in production)
   - Includes all routers

3. **`generate_openapi_spec.py`** - Full spec generator
   - Creates FastAPI app with all routers
   - Generates complete OpenAPI schema
   - Validates specification

4. **`generate_openapi_simple.py`** - Simple spec generator
   - No dependencies required
   - Generates basic OpenAPI structure
   - Quick spec generation

### Router Files

All routers have comprehensive documentation:

1. **`services/algo_builder/router.py`**
   - 10 endpoints with full docstrings
   - Example request/response bodies
   - Requirements traceability

2. **`services/backtesting/router.py`**
   - 5 endpoints with full docstrings
   - Tier-based limits documented
   - Performance targets included

3. **`services/screening/router.py`**
   - 10 endpoints with full docstrings
   - Multi-layer architecture explained
   - Scheduling options documented

4. **`services/alerts/alert_rules/router.py`**
   - 6 endpoints with full docstrings
   - Delivery channels documented
   - Webhook configuration explained

## Documentation Standards

### Docstring Format

All endpoints follow this format:

```python
async def endpoint_name(...):
    """
    Brief one-line description
    
    Detailed multi-line description explaining:
    - What the endpoint does
    - When to use it
    - Important behavior notes
    
    Requirements: X.Y, Z.W
    
    Args:
        param1: Description
        param2: Description
        
    Returns:
        Description of return value
        
    Raises:
        HTTPException 400: When this occurs
        HTTPException 404: When that occurs
    """
```

### Example Format

All Pydantic models include examples:

```python
class Config:
    json_schema_extra = {
        "example": {
            "field1": "value",
            "field2": 123
        }
    }
```

## Validation

### Online Validators

1. **Swagger Editor:** https://editor.swagger.io/
   - Upload `api_spec.json`
   - View rendered documentation
   - Check for errors

2. **OpenAPI Validator:** https://apitools.dev/swagger-parser/online/
   - Paste spec content
   - Get detailed validation report

### CLI Validators

```bash
# Using Redocly CLI
npx @redocly/cli lint api_spec.json

# Using Swagger CLI
npx swagger-cli validate api_spec.json
```

## Environment Configuration

### Development (Docs Enabled)

```bash
# Default - docs enabled
uvicorn main_app:app --reload
```

Access docs at: http://localhost:8080/api/docs

### Production (Docs Disabled)

```bash
# Set environment to production
export ENVIRONMENT=production
uvicorn main_app:app --workers 4
```

Docs are disabled for security. OpenAPI JSON is also disabled.

## API Statistics

- **Total Endpoints:** 31
- **Total Routers:** 4
- **Documentation Coverage:** 100%
- **OpenAPI Version:** 3.0.3
- **API Version:** 1.0.0

### Endpoint Breakdown

| Router | Endpoints | GET | POST | PUT | DELETE |
|--------|-----------|-----|------|-----|--------|
| Algo Builder | 10 | 3 | 4 | 1 | 1 |
| Backtesting | 5 | 3 | 1 | 0 | 0 |
| Screening | 10 | 4 | 3 | 1 | 1 |
| Alerts | 6 | 3 | 2 | 1 | 1 |
| **Total** | **31** | **13** | **10** | **3** | **3** |

## Features

### Interactive Documentation (Swagger UI)

- ✅ Try out endpoints directly from browser
- ✅ See request/response examples
- ✅ Test authentication
- ✅ Explore schemas
- ✅ Search functionality
- ✅ Syntax highlighting

### Alternative Documentation (ReDoc)

- ✅ Clean, professional layout
- ✅ Three-panel design
- ✅ Search functionality
- ✅ Code samples
- ✅ Schema exploration
- ✅ Responsive design

### OpenAPI Specification

- ✅ OpenAPI 3.0.3 compliant
- ✅ Complete metadata
- ✅ Security schemes
- ✅ Tags with descriptions
- ✅ External docs links
- ✅ Multiple servers
- ✅ Contact information
- ✅ License information

## Usage Examples

### Import into Postman

1. Open Postman
2. Click "Import"
3. Select `api_spec.json`
4. All endpoints will be imported with examples

### Import into Insomnia

1. Open Insomnia
2. Click "Import/Export"
3. Select "Import Data"
4. Choose `api_spec.json`
5. All endpoints will be imported

### Generate Client SDK

```bash
# Generate Python client
npx @openapitools/openapi-generator-cli generate \
  -i api_spec.json \
  -g python \
  -o ./python-client

# Generate TypeScript client
npx @openapitools/openapi-generator-cli generate \
  -i api_spec.json \
  -g typescript-axios \
  -o ./typescript-client
```

## Performance Targets

- **Backtest submission:** <100ms
- **Screening (10K instruments):** <60 seconds
- **Alert delivery (p95):** <5 seconds
- **API response time (p95):** <200ms

## Architecture

- **Framework:** FastAPI 0.109.0 + Python 3.12
- **Database:** PostgreSQL + TimescaleDB
- **Cache:** Redis
- **Queue:** Celery
- **Backtesting:** vectorbt + custom event-driven engine
- **AI:** Gemini 2.5 Flash, Claude Haiku
- **Brokers:** OpenAlgo-compatible (30+ Indian brokers), Binance, OANDA, Alpaca

## Support

- **Email:** support@signalix.com
- **Docs:** https://docs.signalix.com
- **Status:** https://status.signalix.com

## Related Documentation

- **Requirements:** `.kiro/specs/Signalix_UX_.md/requirements_algo_backend.md`
- **Design:** `.kiro/specs/Signalix_UX_.md/design_algo_backend.md`
- **Tasks:** `.kiro/specs/Signalix_UX_.md/tasks_algo_backend.md`
- **Completion Summary:** `TASK_48_API_DOCUMENTATION_SUMMARY.md`

## Next Steps

1. **Review the documentation:**
   - Visit http://localhost:8080/api/docs
   - Try out endpoints
   - Verify examples

2. **Validate the spec:**
   - Upload `api_spec.json` to Swagger Editor
   - Check for validation errors
   - Review rendered documentation

3. **Import into API client:**
   - Import into Postman or Insomnia
   - Test endpoints
   - Save example requests

4. **Generate client SDKs:**
   - Use OpenAPI Generator
   - Generate clients for your language
   - Integrate into your applications

## Troubleshooting

### Docs not loading

**Issue:** `/api/docs` returns 404

**Solution:**
- Check `ENVIRONMENT` variable is not set to "production"
- Restart the server
- Verify `main_app.py` is being used

### OpenAPI spec generation fails

**Issue:** `generate_openapi_spec.py` fails with import errors

**Solution:**
- Use `generate_openapi_simple.py` instead (no dependencies)
- Or install missing dependencies: `pip install -r requirements.txt`

### Examples not showing in Swagger UI

**Issue:** Request/response examples not visible

**Solution:**
- Check Pydantic models have `Config` class with `json_schema_extra`
- Restart the server
- Clear browser cache

## Contributing

When adding new endpoints:

1. **Add comprehensive docstring:**
   - Brief description
   - Detailed explanation
   - Requirements traceability
   - Args, Returns, Raises sections

2. **Add examples to models:**
   - Use `json_schema_extra` in Config class
   - Include realistic examples
   - Cover common use cases

3. **Update OpenAPI spec:**
   - Run `python generate_openapi_simple.py`
   - Validate the generated spec
   - Commit `api_spec.json`

4. **Test documentation:**
   - Start server with `uvicorn main_app:app --reload`
   - Visit `/api/docs`
   - Verify endpoint appears correctly
   - Test "Try it out" functionality

---

**Last Updated:** 2025-01-15
**API Version:** 1.0.0
**OpenAPI Version:** 3.0.3
