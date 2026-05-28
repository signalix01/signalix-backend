"""
Activation Tracking Router

Handles activation event tracking and status computation.
Activation is defined as: risk profile saved + 3+ watchlist instruments + 
first analysis run + first signal viewed.

Requirements: 10.1, 10.8
Task: 22
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from enum import Enum
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


class ActivationEventType(str, Enum):
    """Activation event types"""
    RISK_PROFILE_SAVED = "risk_profile_saved"
    WATCHLIST_ADDED = "watchlist_added"
    FIRST_ANALYSIS_RUN = "first_analysis_run"
    FIRST_SIGNAL_VIEWED = "first_signal_viewed"
    ACTIVATION_COMPLETED = "activation_completed"


class TrackActivationEventRequest(BaseModel):
    """Request model for tracking activation events"""
    event_type: ActivationEventType
    user_id: str
    timestamp: str
    metadata: Optional[Dict[str, Any]] = None


class ActivationStatusResponse(BaseModel):
    """Response model for activation status"""
    is_activated: bool
    completed_events: List[ActivationEventType]
    pending_events: List[ActivationEventType]
    activated_at: Optional[str] = None
    time_to_activation: Optional[int] = None  # seconds


class ActivationEvent(BaseModel):
    """Activation event model"""
    id: Optional[str] = None
    user_id: str
    event_type: ActivationEventType
    timestamp: datetime
    metadata: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None


# In-memory storage for demo purposes
# In production, this would be stored in PostgreSQL
activation_events_store: Dict[str, List[ActivationEvent]] = {}
user_signup_times: Dict[str, datetime] = {}


def get_required_events() -> List[ActivationEventType]:
    """Get list of required events for activation"""
    return [
        ActivationEventType.RISK_PROFILE_SAVED,
        ActivationEventType.WATCHLIST_ADDED,
        ActivationEventType.FIRST_ANALYSIS_RUN,
        ActivationEventType.FIRST_SIGNAL_VIEWED,
    ]


def compute_activation_status(user_id: str) -> ActivationStatusResponse:
    """
    Compute activation status for a user
    
    Args:
        user_id: User ID
        
    Returns:
        Activation status
    """
    # Get user's events
    user_events = activation_events_store.get(user_id, [])
    
    # Get completed event types
    completed_event_types = list(set([event.event_type for event in user_events]))
    
    # Get required events
    required_events = get_required_events()
    
    # Check if all required events are completed
    is_activated = all(event_type in completed_event_types for event_type in required_events)
    
    # Get pending events
    pending_events = [
        event_type for event_type in required_events 
        if event_type not in completed_event_types
    ]
    
    # Calculate time to activation
    activated_at = None
    time_to_activation = None
    
    if is_activated:
        # Find the timestamp of the last required event
        last_event = max(
            [event for event in user_events if event.event_type in required_events],
            key=lambda e: e.timestamp
        )
        activated_at = last_event.timestamp.isoformat()
        
        # Calculate time from signup to activation
        if user_id in user_signup_times:
            signup_time = user_signup_times[user_id]
            time_to_activation = int((last_event.timestamp - signup_time).total_seconds())
    
    return ActivationStatusResponse(
        is_activated=is_activated,
        completed_events=completed_event_types,
        pending_events=pending_events,
        activated_at=activated_at,
        time_to_activation=time_to_activation
    )


@router.post("/activation", status_code=201)
async def track_activation_event(request: TrackActivationEventRequest):
    """
    Track an activation event
    
    Stores the event and computes activation status.
    If user becomes activated, fires activation_completed event.
    """
    try:
        # Parse timestamp
        try:
            timestamp = datetime.fromisoformat(request.timestamp.replace('Z', '+00:00'))
        except ValueError:
            timestamp = datetime.now(timezone.utc)
        
        # Create event
        event = ActivationEvent(
            user_id=request.user_id,
            event_type=request.event_type,
            timestamp=timestamp,
            metadata=request.metadata,
            created_at=datetime.now(timezone.utc)
        )
        
        # Store event
        if request.user_id not in activation_events_store:
            activation_events_store[request.user_id] = []
            # Record signup time (first event)
            user_signup_times[request.user_id] = timestamp
        
        # Check if event already exists (prevent duplicates)
        existing_events = [
            e for e in activation_events_store[request.user_id]
            if e.event_type == request.event_type
        ]
        
        if not existing_events:
            activation_events_store[request.user_id].append(event)
            logger.info(f"Tracked activation event: {request.event_type} for user {request.user_id}")
        else:
            logger.info(f"Duplicate activation event ignored: {request.event_type} for user {request.user_id}")
        
        # Compute activation status
        status = compute_activation_status(request.user_id)
        
        # If user just became activated, fire activation_completed event
        if status.is_activated:
            activation_completed_exists = any(
                e.event_type == ActivationEventType.ACTIVATION_COMPLETED
                for e in activation_events_store[request.user_id]
            )
            
            if not activation_completed_exists:
                completion_event = ActivationEvent(
                    user_id=request.user_id,
                    event_type=ActivationEventType.ACTIVATION_COMPLETED,
                    timestamp=datetime.now(timezone.utc),
                    metadata={
                        "time_to_activation": status.time_to_activation,
                        "activated_at": status.activated_at
                    },
                    created_at=datetime.now(timezone.utc)
                )
                activation_events_store[request.user_id].append(completion_event)
                logger.info(f"User {request.user_id} completed activation in {status.time_to_activation}s")
        
        return {
            "success": True,
            "message": "Activation event tracked",
            "activation_status": status.dict()
        }
        
    except Exception as e:
        logger.error(f"Error tracking activation event: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to track activation event: {str(e)}")


@router.get("/activation/{user_id}", response_model=ActivationStatusResponse)
async def get_activation_status(user_id: str):
    """
    Get activation status for a user
    
    Returns completed events, pending events, and activation status.
    """
    try:
        status = compute_activation_status(user_id)
        return status
        
    except Exception as e:
        logger.error(f"Error getting activation status: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get activation status: {str(e)}")


@router.get("/activation/{user_id}/events")
async def get_activation_events(user_id: str):
    """
    Get all activation events for a user
    
    Returns list of activation events with timestamps.
    """
    try:
        events = activation_events_store.get(user_id, [])
        
        return {
            "user_id": user_id,
            "events": [
                {
                    "event_type": event.event_type,
                    "timestamp": event.timestamp.isoformat(),
                    "metadata": event.metadata,
                    "created_at": event.created_at.isoformat() if event.created_at else None
                }
                for event in events
            ],
            "total_events": len(events)
        }
        
    except Exception as e:
        logger.error(f"Error getting activation events: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get activation events: {str(e)}")


@router.delete("/activation/{user_id}")
async def reset_activation_events(user_id: str):
    """
    Reset activation events for a user (for testing purposes)
    
    Removes all activation events for the specified user.
    """
    try:
        if user_id in activation_events_store:
            del activation_events_store[user_id]
        
        if user_id in user_signup_times:
            del user_signup_times[user_id]
        
        logger.info(f"Reset activation events for user {user_id}")
        
        return {
            "success": True,
            "message": f"Activation events reset for user {user_id}"
        }
        
    except Exception as e:
        logger.error(f"Error resetting activation events: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to reset activation events: {str(e)}")
