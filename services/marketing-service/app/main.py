"""
Marketing Service - Main Application
FastAPI application for marketing automation, email sequences, and behavioral triggers
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from app.config import settings
from app.routers import sequences, triggers, leads, activation, analytics, churn, webhooks, referrals, affiliates, tracking

# Configure logging
logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="SignalixAI Marketing Service",
    description="Marketing automation, email sequences, and behavioral triggers",
    version="1.0.0",
    debug=settings.DEBUG
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": settings.SERVICE_NAME,
        "version": "1.0.0"
    }


# Include routers
app.include_router(
    sequences.router,
    prefix="/api/v1/sequences",
    tags=["sequences"]
)

app.include_router(
    triggers.router,
    prefix="/api/v1/triggers",
    tags=["triggers"]
)

app.include_router(
    leads.router,
    prefix="/api/v1/leads",
    tags=["leads"]
)

app.include_router(
    activation.router,
    prefix="/api/v1/tracking",
    tags=["activation"]
)

app.include_router(
    analytics.router,
    prefix="/api/v1/analytics",
    tags=["analytics"]
)

app.include_router(
    churn.router,
    prefix="/api/v1/churn",
    tags=["churn"]
)

app.include_router(
    webhooks.router,
    prefix="/api/v1/webhooks",
    tags=["webhooks"]
)

app.include_router(
    referrals.router,
    prefix="/api/v1/referrals",
    tags=["referrals"]
)

app.include_router(
    affiliates.router,
    prefix="/api/v1/affiliates",
    tags=["affiliates"]
)

app.include_router(
    tracking.router,
    prefix="/api/v1/tracking",
    tags=["tracking"]
)


@app.on_event("startup")
async def startup_event():
    """Startup event handler"""
    logger.info(f"{settings.SERVICE_NAME} starting up...")
    logger.info(f"Service port: {settings.SERVICE_PORT}")
    logger.info(f"Debug mode: {settings.DEBUG}")
    
    # Set up scheduled jobs (retention computation cron)
    try:
        from app.scheduler import setup_scheduled_jobs
        result = setup_scheduled_jobs()
        logger.info(f"Scheduled jobs initialized: {result}")
    except Exception as e:
        logger.warning(f"Failed to set up scheduled jobs: {str(e)}")
        logger.warning("Service will continue without scheduled jobs")


@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown event handler"""
    logger.info(f"{settings.SERVICE_NAME} shutting down...")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.SERVICE_PORT,
        reload=settings.DEBUG
    )
