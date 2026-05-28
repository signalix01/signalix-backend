"""
Generate OpenAPI specification for SignalixAI Backend API

This script creates a comprehensive OpenAPI 3.0 specification by:
1. Creating a FastAPI app with all routers
2. Adding detailed metadata and descriptions
3. Exporting the OpenAPI JSON spec
4. Validating against OpenAPI 3.0 schema

Usage:
    python generate_openapi_spec.py

Output:
    api_spec.json - Complete OpenAPI 3.0 specification
"""

import json
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

# Import all routers
from services.algo_builder.router import router as algo_router
from services.backtesting.router import router as backtest_router
from services.screening.router import router as screening_router
from services.alerts.alert_rules.router import router as alerts_router


def create_app_with_all_routers() -> FastAPI:
    """
    Create FastAPI app with all routers and comprehensive metadata
    """
    app = FastAPI(
        title="SignalixAI Backend API",
        description="""
# SignalixAI Backend API

Institutional-grade algorithmic trading platform with four core systems:

## 🎯 Algo Builder
Build trading strategies without code using a visual interface. Compile strategies to executable Python, 
validate in sandbox, and deploy to paper or live trading.

**Key Features:**
- No-code strategy builder with 16+ technical indicators
- Pre-built templates from legendary traders (Turtle, Thorp, Jones, etc.)
- Sandboxed compilation with security restrictions
- Paper trading validation (30-day minimum)
- Live execution with broker integration

## 📊 Backtesting Engine
Rigorous backtesting across all financial markets with dual-mode execution:

**Vectorised Mode:** Lightning-fast backtests (10 years in <30 seconds)
**Event-Driven Mode:** Realistic simulation with slippage, partial fills, and transaction costs

**Advanced Validation:**
- Walk-forward validation (70/15/15 split)
- Monte Carlo simulation (10,000+ runs)
- Market regime analysis (bull/bear/ranging/volatile/crisis)
- Kelly Criterion position sizing

## 🔍 AI Screening Engine
Multi-layer screening across 10,000+ instruments:

**Layer 1:** SQL pre-filter (<500ms for 10K instruments)
**Layer 2:** TA-Lib scoring (<10 seconds for 200 instruments)
**Layer 3:** LLM scoring via Gemini 2.5 Flash (top 50 candidates)

**Supported Markets:**
- NSE equities (2,000+ instruments)
- NSE F&O (200+ instruments)
- Crypto (top 200 by market cap)
- Forex (28 major/minor pairs)
- MCX commodities
- US equities (S&P 500 + NASDAQ 100)

## 🚨 Anomaly & Alert Engine
Real-time statistical anomaly detection with whale/institutional tracking:

**Detection Methods:**
- Z-score (rolling 20-period window)
- CUSUM (structural breaks)
- Isolation Forest (ML-based)
- Flash crash/rally detection

**Whale Tracking:**
- India: NSE block deals, BSE bulk deals, FII/DII flows
- F&O: OI changes, IV spikes, large premium trades
- Crypto: Glassnode exchange netflows, whale transfers
- US: Dark pool prints, unusual options activity

**Delivery Channels:**
- In-app WebSocket (real-time)
- Push notifications (FCM)
- WhatsApp (Twilio)
- SMS (critical alerts only)
- Email (digest)
- Telegram
- Webhook (for algo traders)

---

## 🔐 Authentication
All endpoints require authentication via JWT token in Authorization header:
```
Authorization: Bearer <your_jwt_token>
```

## 📚 Documentation
- **Swagger UI:** `/api/docs` (interactive API explorer)
- **ReDoc:** `/api/redoc` (alternative documentation)
- **OpenAPI Spec:** `/api/openapi.json` (machine-readable spec)

## 🏗️ Architecture
- **Framework:** FastAPI 0.109.0 + Python 3.12
- **Database:** PostgreSQL + TimescaleDB (time-series)
- **Cache:** Redis (compiled strategies, rate limiting)
- **Queue:** Celery (async backtests, screening)
- **Backtesting:** vectorbt + custom event-driven engine
- **AI:** Gemini 2.5 Flash, Claude Haiku
- **Brokers:** OpenAlgo-compatible (30+ Indian brokers), Binance, OANDA, Alpaca

## 📈 Performance Targets
- Backtest submission: <100ms
- Screening (10K instruments): <60 seconds
- Alert delivery (p95): <5 seconds
- API response time (p95): <200ms

## 🔗 Related Services
- **Frontend:** React + TypeScript
- **Mobile:** React Native
- **Analytics:** Prometheus + Grafana
- **Monitoring:** Sentry

## 📞 Support
- **Email:** support@signalixai.com
- **Docs:** https://docs.signalixai.com
- **Status:** https://status.signalixai.com
        """,
        version="1.0.0",
        terms_of_service="https://signalixai.com/terms",
        contact={
            "name": "SignalixAI Support",
            "url": "https://signalixai.com/support",
            "email": "support@signalixai.com"
        },
        license_info={
            "name": "Proprietary",
            "url": "https://signalixai.com/license"
        },
        servers=[
            {
                "url": "https://api.signalixai.com",
                "description": "Production server"
            },
            {
                "url": "https://staging-api.signalixai.com",
                "description": "Staging server"
            },
            {
                "url": "http://localhost:8080",
                "description": "Local development server"
            }
        ],
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json"
    )
    
    # Include all routers
    app.include_router(algo_router)
    app.include_router(backtest_router)
    app.include_router(screening_router)
    app.include_router(alerts_router)
    
    return app


def generate_openapi_spec(app: FastAPI, output_file: str = "api_spec.json"):
    """
    Generate and save OpenAPI specification
    
    Args:
        app: FastAPI application instance
        output_file: Output file path for JSON spec
    """
    # Generate OpenAPI schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        servers=app.servers,
        terms_of_service=app.terms_of_service,
        contact=app.contact,
        license_info=app.license_info
    )
    
    # Add security schemes
    openapi_schema["components"] = openapi_schema.get("components", {})
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "JWT token obtained from /api/v1/auth/login endpoint"
        }
    }
    
    # Add global security requirement
    openapi_schema["security"] = [{"BearerAuth": []}]
    
    # Add tags with descriptions
    openapi_schema["tags"] = [
        {
            "name": "algo_builder",
            "description": "No-code algorithmic strategy builder with compilation and validation",
            "externalDocs": {
                "description": "Algo Builder Documentation",
                "url": "https://docs.signalixai.com/algo-builder"
            }
        },
        {
            "name": "backtesting",
            "description": "Dual-mode backtesting engine with walk-forward validation and Monte Carlo simulation",
            "externalDocs": {
                "description": "Backtesting Documentation",
                "url": "https://docs.signalixai.com/backtesting"
            }
        },
        {
            "name": "screening",
            "description": "AI-powered multi-layer screening across all financial markets",
            "externalDocs": {
                "description": "Screening Documentation",
                "url": "https://docs.signalixai.com/screening"
            }
        },
        {
            "name": "alerts",
            "description": "Real-time anomaly detection and alert delivery with whale tracking",
            "externalDocs": {
                "description": "Alerts Documentation",
                "url": "https://docs.signalixai.com/alerts"
            }
        }
    ]
    
    # Write to file
    output_path = Path(output_file)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(openapi_schema, f, indent=2, ensure_ascii=False)
    
    print(f"✓ OpenAPI specification generated: {output_path.absolute()}")
    print(f"  - Total endpoints: {len([r for r in app.routes if hasattr(r, 'methods')])}")
    print(f"  - Total schemas: {len(openapi_schema.get('components', {}).get('schemas', {}))}")
    print(f"  - File size: {output_path.stat().st_size / 1024:.2f} KB")
    
    return openapi_schema


def validate_openapi_spec(spec: dict) -> bool:
    """
    Validate OpenAPI specification against OpenAPI 3.0 schema
    
    Args:
        spec: OpenAPI specification dictionary
        
    Returns:
        True if valid, False otherwise
    """
    try:
        # Basic validation checks
        required_fields = ["openapi", "info", "paths"]
        for field in required_fields:
            if field not in spec:
                print(f"✗ Validation failed: Missing required field '{field}'")
                return False
        
        # Check OpenAPI version
        if not spec["openapi"].startswith("3."):
            print(f"✗ Validation failed: OpenAPI version must be 3.x, got {spec['openapi']}")
            return False
        
        # Check info object
        info_required = ["title", "version"]
        for field in info_required:
            if field not in spec["info"]:
                print(f"✗ Validation failed: Missing required info field '{field}'")
                return False
        
        # Check paths
        if not spec["paths"]:
            print("✗ Validation failed: No paths defined")
            return False
        
        # Count endpoints
        endpoint_count = 0
        for path, methods in spec["paths"].items():
            for method in methods:
                if method in ["get", "post", "put", "delete", "patch", "options", "head"]:
                    endpoint_count += 1
        
        print(f"✓ OpenAPI specification is valid")
        print(f"  - OpenAPI version: {spec['openapi']}")
        print(f"  - API title: {spec['info']['title']}")
        print(f"  - API version: {spec['info']['version']}")
        print(f"  - Total paths: {len(spec['paths'])}")
        print(f"  - Total endpoints: {endpoint_count}")
        
        return True
        
    except Exception as e:
        print(f"✗ Validation error: {e}")
        return False


def main():
    """Main execution function"""
    print("=" * 80)
    print("SignalixAI Backend API - OpenAPI Specification Generator")
    print("=" * 80)
    print()
    
    # Create app with all routers
    print("Creating FastAPI app with all routers...")
    app = create_app_with_all_routers()
    print(f"✓ App created with {len(app.routes)} routes")
    print()
    
    # Generate OpenAPI spec
    print("Generating OpenAPI specification...")
    spec = generate_openapi_spec(app)
    print()
    
    # Validate spec
    print("Validating OpenAPI specification...")
    is_valid = validate_openapi_spec(spec)
    print()
    
    if is_valid:
        print("=" * 80)
        print("✓ SUCCESS: OpenAPI specification generated and validated")
        print("=" * 80)
        print()
        print("Next steps:")
        print("  1. Review the generated api_spec.json file")
        print("  2. Test the API documentation at http://localhost:8080/api/docs")
        print("  3. Validate with external tools:")
        print("     - Swagger Editor: https://editor.swagger.io/")
        print("     - OpenAPI Validator: https://apitools.dev/swagger-parser/online/")
        print()
        return 0
    else:
        print("=" * 80)
        print("✗ FAILED: OpenAPI specification validation failed")
        print("=" * 80)
        return 1


if __name__ == "__main__":
    sys.exit(main())
