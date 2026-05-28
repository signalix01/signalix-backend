"""
Main FastAPI Application for SignalixAI Backend

This is the unified application that includes all service routers and hosts
the interactive API documentation at /api/docs.

In non-production environments, this serves Swagger UI for API exploration.
In production, the docs are disabled for security.

Usage:
    # Development (with docs)
    uvicorn main_app:app --reload --host 0.0.0.0 --port 8080
    
    # Production (docs disabled)
    export ENVIRONMENT=production
    uvicorn main_app:app --host 0.0.0.0 --port 8080 --workers 4
"""

import os
import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from fastapi.openapi.utils import get_openapi
from contextlib import asynccontextmanager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import all routers
from services.algo_builder.router import router as algo_router
from services.algo_builder.flow_router import router as flow_router
from services.algo_builder.python_host_router import router as python_router
from services.backtesting.router import router as backtest_router
from services.screening.router import router as screening_router
from services.screening.ws_router import ws_router as screening_ws_router
from services.alerts.alert_rules.router import router as alerts_router
from services.alerts.ws_router import ws_router as alerts_ws_router
from services.alerts.history_router import router as alerts_history_router
from services.integration_service import router as integration_router
from services.options_analytics import router as options_router
from services.telegram_service import router as telegram_router
from services.broker_integration import app as broker_integration_app
from services.user_service.router import router as auth_router, user_router, users_router
from services.market_data_service.router import router as market_router
from services.portfolio_service.router import router as portfolio_router
from services.execution.router import router as execution_router
from services.risk_service.router import router as risk_router
from services.analytics_service.router import router as analytics_router
from services.subscription_service.router import router as subscription_router
from services.user_service.watchlist_router import router as watchlist_router
from services.market_data_service.options_stream_worker import options_stream_worker
import asyncio

# Environment configuration
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
IS_PRODUCTION = ENVIRONMENT == "production"

# Docs configuration
DOCS_ENABLED = not IS_PRODUCTION
DOCS_URL = "/api/docs" if DOCS_ENABLED else None
REDOC_URL = "/api/redoc" if DOCS_ENABLED else None
OPENAPI_URL = "/api/openapi.json" if DOCS_ENABLED else None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager
    Handles startup and shutdown events
    """
    # Startup
    logger.info("=" * 80)
    logger.info("SignalixAI Backend API Starting")
    logger.info("=" * 80)
    logger.info(f"Environment: {ENVIRONMENT}")
    logger.info(f"Docs enabled: {DOCS_ENABLED}")
    logger.info(f"Docs URL: {DOCS_URL or 'disabled'}")
    logger.info(f"Total routers: 11 (algo_builder, algo_flow, python_host, backtesting, screening, alerts, integration, options, telegram, websockets)")
    logger.info(f"WebSocket endpoints: /ws/alerts, /ws/screen")
    logger.info(f"Broker Integration: mounted at /api/v1/brokers")
    logger.info("=" * 80)
    
    # Start options stream worker
    asyncio.create_task(options_stream_worker.start())
    
    yield
    
    # Shutdown
    logger.info("SignalixAI Backend API Shutting Down")
    options_stream_worker.stop()


# Create FastAPI app
app = FastAPI(
    title="SignalixAI Backend API",
    description="""
# SignalixAI Backend API

Institutional-grade algorithmic trading platform with four core systems:

## 🎯 Algo Builder
Build trading strategies without code. Compile to executable Python, validate in sandbox, deploy to paper or live trading.

## 📊 Backtesting Engine
Dual-mode backtesting (vectorised + event-driven) with walk-forward validation and Monte Carlo simulation.

## 🔍 AI Screening Engine
Multi-layer screening across 10,000+ instruments using SQL pre-filter → TA-Lib scoring → LLM scoring.

## 🚨 Anomaly & Alert Engine
Real-time statistical anomaly detection with whale/institutional tracking across all markets.

## 🔗 Integration Service
Webhook processing for TradingView, Amibroker, and ChartInk with HMAC signature validation,
rate limiting, and signal forwarding to execution engine.

## 📈 Options Analytics Service
Comprehensive options analytics with Greeks calculation (Black-Scholes), Max Pain analysis,
Gamma Exposure (GEX) tracking, Open Interest monitoring, and multi-leg strategy builder with
payoff diagrams.

---

**Authentication:** All endpoints require JWT token in Authorization header.

**Documentation:**
- Swagger UI: `/api/docs` (interactive)
- ReDoc: `/api/redoc` (alternative)
- OpenAPI Spec: `/api/openapi.json` (JSON)

**Support:** support@signalixai.com
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
    docs_url=None,  # We'll serve custom docs
    redoc_url=None,  # We'll serve custom redoc
    openapi_url=OPENAPI_URL,
    lifespan=lifespan
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "https://signalixai.com",
        "https://www.signalixai.com",
        "https://app.signalixai.com"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Custom OpenAPI schema with enhanced metadata
def custom_openapi():
    """
    Generate custom OpenAPI schema with enhanced metadata
    """
    if app.openapi_schema:
        return app.openapi_schema
    
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
            "description": "**No-code algorithmic strategy builder**\n\nBuild, compile, validate, and deploy trading strategies without writing code. Includes pre-built templates from legendary traders.",
            "externalDocs": {
                "description": "Algo Builder Documentation",
                "url": "https://docs.signalixai.com/algo-builder"
            }
        },
        {
            "name": "algo_flow",
            "description": "**Visual Strategy Flow Builder**\n\nReact Flow-based visual strategy builder with drag-and-drop nodes. Features auto-save, version history,\nexport/import (JSON/PNG), and flow persistence. Supports condition nodes, action nodes, and risk management nodes.",
            "externalDocs": {
                "description": "Visual Flow Builder Documentation",
                "url": "https://docs.signalixai.com/algo-flow"
            }
        },
        {
            "name": "python_strategy_host",
            "description": "**Python Strategy Host**\n\nIn-browser Python code editor with CodeMirror for strategy development. Features syntax highlighting,\nautocomplete, real-time validation, code templates, version history, and secure sandboxed execution\nwith Docker isolation.",
            "externalDocs": {
                "description": "Python Strategy Host Documentation",
                "url": "https://docs.signalixai.com/python-strategies"
            }
        },
        {
            "name": "backtesting",
            "description": "**Dual-mode backtesting engine**\n\nVectorised mode for speed (10 years in <30s) or event-driven mode for realism (slippage, partial fills, transaction costs).",
            "externalDocs": {
                "description": "Backtesting Documentation",
                "url": "https://docs.signalixai.com/backtesting"
            }
        },
        {
            "name": "screening",
            "description": "**AI-powered multi-layer screening**\n\nScreen 10,000+ instruments across all markets using SQL pre-filter → TA-Lib scoring → LLM scoring.",
            "externalDocs": {
                "description": "Screening Documentation",
                "url": "https://docs.signalixai.com/screening"
            }
        },
        {
            "name": "alerts",
            "description": "**Real-time anomaly detection & alerts**\n\nStatistical anomaly detection (Z-score, CUSUM, Isolation Forest) with whale/institutional tracking.",
            "externalDocs": {
                "description": "Alerts Documentation",
                "url": "https://docs.signalixai.com/alerts"
            }
        },
        {
            "name": "integration",
            "description": "**External Platform Integration Service**\n\nWebhook processing for TradingView, Amibroker, and ChartInk. Features HMAC-SHA256 signature validation,\nreplay attack prevention, rate limiting, signal parsing, and queue-based processing with dead letter queue.",
            "externalDocs": {
                "description": "Integration Documentation",
                "url": "https://docs.signalixai.com/integration"
            }
        },
        {
            "name": "options",
            "description": "**📈 Options Analytics Service**\n\nComprehensive options analytics with Greeks calculation (Delta, Gamma, Theta, Vega, Rho using Black-Scholes),\nMax Pain analysis, Gamma Exposure (GEX) tracking, Open Interest monitoring, and multi-leg strategy builder\nwith payoff diagrams and breakeven analysis.",
            "externalDocs": {
                "description": "Options Analytics Documentation",
                "url": "https://docs.signalixai.com/options"
            }
        },
        {
            "name": "telegram",
            "description": "**💬 Telegram Bot Service**\n\nTelegram bot integration for real-time order alerts and trading commands. Receive instant notifications\nfor order executions, view positions and orders, and execute trades directly from Telegram with\nsecure authentication and rate limiting.",
            "externalDocs": {
                "description": "Telegram Bot Service Documentation",
                "url": "https://docs.signalixai.com/telegram"
            }
        },
        {
            "name": "brokers",
            "description": "**🏦 Broker Integration Service**\n\nUnified broker integration for 30+ Indian brokers (Zerodha, Dhan, Upstox, Angel One, ICICI Direct, etc.).\nFeatures connection management, order execution, position tracking, symbol normalization,\nWebSocket streaming, and a plugin architecture for easy broker extensibility.",
            "externalDocs": {
                "description": "Broker Integration Documentation",
                "url": "https://docs.signalixai.com/brokers"
            }
        },
    ]
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi


# Include all routers
app.include_router(algo_router)
app.include_router(flow_router)
app.include_router(python_router)
app.include_router(backtest_router)
app.include_router(screening_router)
app.include_router(alerts_router)
app.include_router(alerts_history_router)
app.include_router(integration_router)
app.include_router(options_router)
app.include_router(telegram_router)
app.include_router(auth_router)
app.include_router(market_router)
app.include_router(portfolio_router)
app.include_router(execution_router)
app.include_router(risk_router)
app.include_router(analytics_router)
app.include_router(subscription_router)
app.include_router(watchlist_router)
app.include_router(user_router)
app.include_router(users_router)

# Include WebSocket routers
app.include_router(alerts_ws_router)
app.include_router(screening_ws_router)

# Mount broker integration service as sub-application
app.mount("/api/v1/brokers", broker_integration_app)

logger.info("✓ All routers registered")
logger.info("✓ WebSocket routers registered")
logger.info("✓ Broker Integration service mounted at /api/v1/brokers")


# Custom docs endpoints (only in non-production)
if DOCS_ENABLED:
    @app.get("/api/docs", include_in_schema=False)
    async def custom_swagger_ui_html():
        """
        Custom Swagger UI with enhanced styling
        """
        return get_swagger_ui_html(
            openapi_url=app.openapi_url,
            title=f"{app.title} - Swagger UI",
            oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
            swagger_js_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js",
            swagger_css_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css",
            swagger_favicon_url="https://fastapi.tiangolo.com/img/favicon.png"
        )
    
    @app.get("/api/redoc", include_in_schema=False)
    async def redoc_html():
        """
        ReDoc documentation
        """
        return get_redoc_html(
            openapi_url=app.openapi_url,
            title=f"{app.title} - ReDoc",
            redoc_js_url="https://cdn.jsdelivr.net/npm/redoc@next/bundles/redoc.standalone.js",
            redoc_favicon_url="https://fastapi.tiangolo.com/img/favicon.png"
        )


# Root endpoint
@app.get("/", include_in_schema=False)
async def root():
    """
    API root endpoint
    Redirects to docs in non-production, returns info in production
    """
    if DOCS_ENABLED:
        return RedirectResponse(url="/api/docs")
    
    return {
        "service": "SignalixAI Backend API",
        "version": app.version,
        "status": "running",
        "environment": ENVIRONMENT,
        "endpoints": {
            "algo_builder": "/api/v1/algo",
            "backtesting": "/api/v1/backtest",
            "screening": "/api/v1/screen",
            "alerts": "/api/v1/alerts",
            "integration": "/api/v1/integration",
            "options": "/api/v1/options",
            "telegram": "/api/v1/telegram",
            "brokers": "/api/v1/brokers"
        },
        "websockets": {
            "alerts": "/ws/alerts",
            "screening": "/ws/screen/{criteria_id}",
            "broker_orders": "/api/v1/brokers/ws/orders/{broker_id}"
        },
        "health_check": "/health",
        "docs": "/api/docs" if DOCS_ENABLED else None
    }


# Health check endpoint
@app.get("/health", include_in_schema=False)
async def health_check():
    """
    Health check endpoint for load balancers and monitoring
    """
    return {
        "status": "healthy",
        "service": "signalixai-backend",
        "version": app.version,
        "environment": ENVIRONMENT,
        "docs_enabled": DOCS_ENABLED
    }


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Global exception handler for unhandled errors
    """
    logger.error(
        f"Unhandled exception: {exc}",
        exc_info=True,
        extra={
            "path": request.url.path,
            "method": request.method
        }
    )
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": "An unexpected error occurred. Please contact support if the issue persists.",
            "path": request.url.path
        }
    )


if __name__ == "__main__":
    import uvicorn
    
    # Development server configuration
    uvicorn.run(
        "main_app:app",
        host="0.0.0.0",
        port=8080,
        reload=True,
        log_level="info",
        access_log=True
    )
