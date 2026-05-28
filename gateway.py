"""
API Gateway for SignalixAI
Routes requests to appropriate microservices
"""

from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import httpx
import asyncio
from typing import Optional
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="SignalixAI API Gateway",
    version="1.0.0",
    description="Central gateway routing to all microservices"
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Service Registry
SERVICES = {
    "auth": "http://localhost:8000",
    "analysis": "http://localhost:8001",
    "user": "http://localhost:8002",
    "portfolio": "http://localhost:8003",
    "market-data": "http://localhost:8004",
    "notification": "http://localhost:8005",
}

# Route Mapping (prefix -> service)
ROUTE_MAP = {
    "/api/v1/auth": "auth",
    "/api/v1/users": "auth",  # User endpoints in auth service
    "/api/v1/analysis": "analysis",
    "/api/v1/watchlist": "user",
    "/api/v1/user": "user",
    "/api/v1/portfolio": "portfolio",
    "/api/v1/market": "market-data",
    "/api/v1/notifications": "notification",
    "/api/v1/analytics": "auth",  # Analytics stub in auth service
    "/ws": "auth",  # WebSocket in auth service
}

# HTTP Client with connection pooling
http_client = httpx.AsyncClient(
    timeout=30.0,
    limits=httpx.Limits(max_keepalive_connections=20, max_connections=100)
)


def get_service_for_path(path: str) -> Optional[str]:
    """Determine which service should handle this path"""
    for prefix, service in ROUTE_MAP.items():
        if path.startswith(prefix):
            return service
    return None


@app.on_event("startup")
async def startup_event():
    """Check service health on startup"""
    logger.info("API Gateway starting up...")
    logger.info("Checking service health...")
    
    for service_name, service_url in SERVICES.items():
        try:
            response = await http_client.get(f"{service_url}/health", timeout=5.0)
            if response.status_code == 200:
                logger.info(f"✓ {service_name} service is healthy at {service_url}")
            else:
                logger.warning(f"⚠ {service_name} service returned {response.status_code}")
        except Exception as e:
            logger.error(f"✗ {service_name} service is not reachable: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    await http_client.aclose()


@app.get("/health")
async def health_check():
    """Gateway health check"""
    service_health = {}
    
    for service_name, service_url in SERVICES.items():
        try:
            response = await http_client.get(f"{service_url}/health", timeout=2.0)
            service_health[service_name] = {
                "status": "healthy" if response.status_code == 200 else "unhealthy",
                "url": service_url
            }
        except Exception as e:
            service_health[service_name] = {
                "status": "unreachable",
                "url": service_url,
                "error": str(e)
            }
    
    all_healthy = all(s["status"] == "healthy" for s in service_health.values())
    
    return {
        "status": "healthy" if all_healthy else "degraded",
        "gateway": "running",
        "services": service_health
    }


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def gateway_route(path: str, request: Request):
    """
    Main gateway routing logic
    Forwards requests to appropriate microservice
    """
    full_path = f"/{path}"
    
    # Handle OPTIONS for CORS preflight
    if request.method == "OPTIONS":
        return Response(status_code=200)
    
    # Determine target service
    service_name = get_service_for_path(full_path)
    
    if not service_name:
        logger.warning(f"No service found for path: {full_path}")
        raise HTTPException(status_code=404, detail=f"No service handles path: {full_path}")
    
    service_url = SERVICES.get(service_name)
    if not service_url:
        logger.error(f"Service {service_name} not found in registry")
        raise HTTPException(status_code=503, detail=f"Service {service_name} not available")
    
    # Build target URL
    target_url = f"{service_url}/{path}"
    
    # Get request body
    body = None
    if request.method in ["POST", "PUT", "PATCH"]:
        body = await request.body()
    
    # Forward headers (excluding host)
    headers = dict(request.headers)
    headers.pop("host", None)
    
    try:
        # Forward request to service
        logger.info(f"{request.method} {full_path} -> {service_name} ({target_url})")
        
        response = await http_client.request(
            method=request.method,
            url=target_url,
            content=body,
            headers=headers,
            params=request.query_params,
        )
        
        # Return response
        return Response(
            content=response.content,
            status_code=response.status_code,
            headers=dict(response.headers),
        )
        
    except httpx.TimeoutException:
        logger.error(f"Timeout calling {service_name} for {full_path}")
        raise HTTPException(status_code=504, detail=f"Service {service_name} timeout")
    
    except httpx.ConnectError:
        logger.error(f"Cannot connect to {service_name} at {service_url}")
        raise HTTPException(status_code=503, detail=f"Service {service_name} unavailable")
    
    except Exception as e:
        logger.error(f"Error proxying to {service_name}: {e}")
        raise HTTPException(status_code=500, detail=f"Gateway error: {str(e)}")


@app.get("/")
async def root():
    """Gateway root endpoint"""
    return {
        "service": "SignalixAI API Gateway",
        "version": "1.0.0",
        "status": "running",
        "services": list(SERVICES.keys()),
        "health_check": "/health"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")
