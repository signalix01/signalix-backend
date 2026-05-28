"""
Server-Side Event Tracking Router

Implements Task 2.5: Server-side event tracking endpoint
Forwards critical conversions to GA4 Measurement Protocol and Mixpanel server-side API

Requirements: 2.7
"""

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import httpx
import hashlib
import logging

from ..config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

# ============================================================================
# Models
# ============================================================================

class ServerSideEventRequest(BaseModel):
    """Server-side event tracking request"""
    event_name: str = Field(..., description="Event name (e.g., 'signup_completed', 'subscription_started')")
    user_id: Optional[str] = Field(None, description="User ID")
    client_id: Optional[str] = Field(None, description="GA4 client ID")
    session_id: Optional[str] = Field(None, description="Session ID")
    properties: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Event properties")
    user_properties: Optional[Dict[str, Any]] = Field(default_factory=dict, description="User properties")
    timestamp: Optional[str] = Field(None, description="Event timestamp (ISO 8601)")
    
class ServerSideEventResponse(BaseModel):
    """Server-side event tracking response"""
    success: bool
    message: str
    ga4_sent: bool = False
    mixpanel_sent: bool = False
    deduplicated: bool = False

# ============================================================================
# Deduplication
# ============================================================================

# In-memory deduplication cache (in production, use Redis)
_deduplication_cache: Dict[str, datetime] = {}
DEDUPLICATION_WINDOW_SECONDS = 5

def generate_dedup_key(event_name: str, client_id: Optional[str], user_id: Optional[str], timestamp: str) -> str:
    """Generate deduplication key"""
    identifier = client_id or user_id or "anonymous"
    key_string = f"{event_name}:{identifier}:{timestamp}"
    return hashlib.md5(key_string.encode()).hexdigest()

def is_duplicate_event(event_name: str, client_id: Optional[str], user_id: Optional[str], timestamp: str) -> bool:
    """Check if event is duplicate within deduplication window"""
    dedup_key = generate_dedup_key(event_name, client_id, user_id, timestamp)
    
    # Clean up old entries
    now = datetime.utcnow()
    expired_keys = [k for k, v in _deduplication_cache.items() if (now - v).total_seconds() > DEDUPLICATION_WINDOW_SECONDS]
    for key in expired_keys:
        del _deduplication_cache[key]
    
    # Check if event exists
    if dedup_key in _deduplication_cache:
        return True
    
    # Store event
    _deduplication_cache[dedup_key] = now
    return False

# ============================================================================
# GA4 Measurement Protocol
# ============================================================================

async def send_to_ga4(
    event_name: str,
    client_id: str,
    user_id: Optional[str],
    properties: Dict[str, Any],
    user_properties: Dict[str, Any],
    timestamp_micros: Optional[int] = None
) -> bool:
    """Send event to GA4 Measurement Protocol"""
    if not settings.GA4_MEASUREMENT_ID or not settings.GA4_API_SECRET:
        logger.warning("GA4 credentials not configured, skipping GA4 tracking")
        return False
    
    try:
        # Build GA4 payload
        payload = {
            "client_id": client_id,
            "events": [
                {
                    "name": event_name,
                    "params": properties
                }
            ]
        }
        
        if user_id:
            payload["user_id"] = user_id
        
        if user_properties:
            payload["user_properties"] = {
                k: {"value": v} for k, v in user_properties.items()
            }
        
        if timestamp_micros:
            payload["timestamp_micros"] = timestamp_micros
        
        # Send to GA4
        url = f"https://www.google-analytics.com/mp/collect?measurement_id={settings.GA4_MEASUREMENT_ID}&api_secret={settings.GA4_API_SECRET}"
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, timeout=5.0)
            
            if response.status_code == 204:
                logger.info(f"Event '{event_name}' sent to GA4 successfully")
                return True
            else:
                logger.error(f"GA4 returned status {response.status_code}: {response.text}")
                return False
                
    except Exception as e:
        logger.error(f"Failed to send event to GA4: {str(e)}")
        return False

# ============================================================================
# Mixpanel Server-Side API
# ============================================================================

async def send_to_mixpanel(
    event_name: str,
    distinct_id: str,
    properties: Dict[str, Any],
    timestamp: Optional[datetime] = None
) -> bool:
    """Send event to Mixpanel server-side API"""
    if not settings.MIXPANEL_TOKEN:
        logger.warning("Mixpanel token not configured, skipping Mixpanel tracking")
        return False
    
    try:
        # Build Mixpanel payload
        event_data = {
            "event": event_name,
            "properties": {
                "token": settings.MIXPANEL_TOKEN,
                "distinct_id": distinct_id,
                **properties
            }
        }
        
        if timestamp:
            event_data["properties"]["time"] = int(timestamp.timestamp())
        
        # Send to Mixpanel
        url = "https://api.mixpanel.com/track"
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                json=[event_data],
                headers={"Content-Type": "application/json"},
                timeout=5.0
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get("status") == 1:
                    logger.info(f"Event '{event_name}' sent to Mixpanel successfully")
                    return True
                else:
                    logger.error(f"Mixpanel returned error: {result}")
                    return False
            else:
                logger.error(f"Mixpanel returned status {response.status_code}: {response.text}")
                return False
                
    except Exception as e:
        logger.error(f"Failed to send event to Mixpanel: {str(e)}")
        return False

# ============================================================================
# Endpoints
# ============================================================================

@router.post("/event", response_model=ServerSideEventResponse)
async def track_server_side_event(
    request: ServerSideEventRequest,
    background_tasks: BackgroundTasks
):
    """
    Track server-side event and forward to GA4 and Mixpanel
    
    This endpoint is used for critical conversions that must be tracked
    even if client-side tracking is blocked by ad blockers.
    
    Implements deduplication to prevent duplicate events from client and server.
    """
    try:
        # Parse timestamp
        timestamp = datetime.fromisoformat(request.timestamp.replace('Z', '+00:00')) if request.timestamp else datetime.utcnow()
        
        # Check for duplicates
        is_duplicate = is_duplicate_event(
            request.event_name,
            request.client_id,
            request.user_id,
            timestamp.isoformat()
        )
        
        if is_duplicate:
            logger.info(f"Duplicate event detected: {request.event_name} for user {request.user_id or request.client_id}")
            return ServerSideEventResponse(
                success=True,
                message="Event deduplicated",
                deduplicated=True
            )
        
        # Determine identifiers
        client_id = request.client_id or request.session_id or "anonymous"
        distinct_id = request.user_id or client_id
        
        # Send to GA4 (background task)
        ga4_sent = False
        if request.client_id:
            timestamp_micros = int(timestamp.timestamp() * 1_000_000)
            ga4_sent = await send_to_ga4(
                request.event_name,
                client_id,
                request.user_id,
                request.properties,
                request.user_properties,
                timestamp_micros
            )
        
        # Send to Mixpanel (background task)
        mixpanel_sent = await send_to_mixpanel(
            request.event_name,
            distinct_id,
            {**request.properties, **request.user_properties},
            timestamp
        )
        
        return ServerSideEventResponse(
            success=True,
            message="Event tracked successfully",
            ga4_sent=ga4_sent,
            mixpanel_sent=mixpanel_sent,
            deduplicated=False
        )
        
    except Exception as e:
        logger.error(f"Failed to track server-side event: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to track event: {str(e)}")

@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "tracking",
        "ga4_configured": bool(settings.GA4_MEASUREMENT_ID and settings.GA4_API_SECRET),
        "mixpanel_configured": bool(settings.MIXPANEL_TOKEN)
    }
