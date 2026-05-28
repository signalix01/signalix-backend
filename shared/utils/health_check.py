"""
Health Check Utilities

Async health checks for database, Redis, and LLM API connectivity.
Used by the /health endpoint and monitoring systems.
"""

import time
import logging
from enum import Enum
from typing import Any, Dict, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


async def check_database(db_session: Any) -> Dict[str, Any]:
    """Check database connectivity and latency."""
    try:
        start = time.monotonic()
        from sqlalchemy import text
        result = await db_session.execute(text("SELECT 1"))
        result.scalar()
        latency_ms = (time.monotonic() - start) * 1000
        return {
            "status": HealthStatus.HEALTHY,
            "latency_ms": round(latency_ms, 2),
            "message": "Database connection OK",
        }
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return {
            "status": HealthStatus.UNHEALTHY,
            "latency_ms": None,
            "message": f"Database error: {str(e)}",
        }


async def check_redis(redis_url: str) -> Dict[str, Any]:
    """Check Redis connectivity and latency."""
    try:
        import redis.asyncio as aioredis
        start = time.monotonic()
        client = aioredis.from_url(redis_url, decode_responses=True)
        await client.ping()
        latency_ms = (time.monotonic() - start) * 1000
        await client.aclose()
        return {
            "status": HealthStatus.HEALTHY,
            "latency_ms": round(latency_ms, 2),
            "message": "Redis connection OK",
        }
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        return {
            "status": HealthStatus.UNHEALTHY,
            "latency_ms": None,
            "message": f"Redis error: {str(e)}",
        }


async def check_llm_api(provider: str, api_key: Optional[str]) -> Dict[str, Any]:
    """Check LLM API key availability (does NOT make an API call)."""
    if api_key and len(api_key) > 5:
        return {
            "status": HealthStatus.HEALTHY,
            "message": f"{provider} API key configured",
        }
    return {
        "status": HealthStatus.DEGRADED,
        "message": f"{provider} API key not configured",
    }


async def comprehensive_health_check(
    db: Any = None,
    redis_url: Optional[str] = None,
    anthropic_key: Optional[str] = None,
    openai_key: Optional[str] = None,
    google_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Run all health checks and return combined status."""
    components: Dict[str, Any] = {}

    if db is not None:
        components["database"] = await check_database(db)

    if redis_url:
        components["redis"] = await check_redis(redis_url)

    if anthropic_key is not None:
        components["anthropic_api"] = await check_llm_api("Anthropic", anthropic_key)

    if openai_key is not None:
        components["openai_api"] = await check_llm_api("OpenAI", openai_key)

    if google_key is not None:
        components["google_api"] = await check_llm_api("Google", google_key)

    # Determine overall status
    statuses = [c["status"] for c in components.values()]
    if all(s == HealthStatus.HEALTHY for s in statuses):
        overall = HealthStatus.HEALTHY
    elif any(s == HealthStatus.UNHEALTHY for s in statuses):
        overall = HealthStatus.UNHEALTHY
    else:
        overall = HealthStatus.DEGRADED

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": overall,
        "components": components,
    }
