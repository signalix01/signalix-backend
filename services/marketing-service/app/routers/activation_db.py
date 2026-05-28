"""
Activation Tracking Router (Database-backed)

Handles activation event tracking and status computation using PostgreSQL.
Activation is defined as: risk profile saved + 3+ watchlist instruments + 
first analysis run + first signal viewed.

Requirements: 10.1, 10.8
Task: 22

This is the production version that uses PostgreSQL for persistence.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from enum import Enum
import logging
import os
import asyncpg

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


# Database connection pool
db_pool: Optional[asyncpg.Pool] = None


async def get_db_pool():
    """Get database connection pool"""
    global db_pool
    if db_pool is None:
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise ValueError("DATABASE_URL environment variable not set")
        
        db_pool = await asyncpg.create_pool(database_url)
    
    return db_pool


def get_required_events() -> List[ActivationEventType]:
    """Get list of required events for activation"""
    return [
        ActivationEventType.RISK_PROFILE_SAVED,
        ActivationEventType.WATCHLIST_ADDED,
        ActivationEventType.FIRST_ANALYSIS_RUN,
        ActivationEventType.FIRST_SIGNAL_VIEWED,
    ]


async def compute_activation_status(user_id: str, pool: asyncpg.Pool) -> ActivationStatusResponse:
    """
    Compute activation status for a user from database
    
    Args:
        user_id: User ID
        pool: Database connection pool
        
    Returns:
        Activation status
    """
    async with pool.acquire() as conn:
        # Get user's events
        rows = await conn.fetch(
            """
            SELECT event_type, timestamp, metadata
            FROM user_activation_events
            WHERE user_id = $1
            ORDER BY timestamp ASC
            """,
            user_id
        )
        
        # Get completed event types
        completed_event_types = list(set([row['event_type'] for row in rows]))
        
        # Get required events
        required_events = get_required_events()
        
        # Check if all required events are completed
        is_activated = all(
            event_type.value in completed_event_types 
            for event_type in required_events
        )
        
        # Get pending events
        pending_events = [
            event_type for event_type in required_events 
            if event_type.value not in completed_event_types
        ]
        
        # Calculate time to activation
        activated_at = None
        time_to_activation = None
        
        if is_activated and rows:
            # Find the timestamp of the last required event
            required_event_values = [e.value for e in required_events]
            last_event = max(
                [row for row in rows if row['event_type'] in required_event_values],
                key=lambda r: r['timestamp']
            )
            activated_at = last_event['timestamp'].isoformat()
            
            # Calculate time from first event (signup) to activation
            first_event = min(rows, key=lambda r: r['timestamp'])
            time_to_activation = int(
                (last_event['timestamp'] - first_event['timestamp']).total_seconds()
            )
        
        return ActivationStatusResponse(
            is_activated=is_activated,
            completed_events=[ActivationEventType(e) for e in completed_event_types],
            pending_events=pending_events,
            activated_at=activated_at,
            time_to_activation=time_to_activation
        )


@router.post("/activation", status_code=201)
async def track_activation_event(request: TrackActivationEventRequest):
    """
    Track an activation event
    
    Stores the event in database and computes activation status.
    If user becomes activated, fires activation_completed event.
    """
    try:
        pool = await get_db_pool()
        
        # Parse timestamp
        try:
            timestamp = datetime.fromisoformat(request.timestamp.replace('Z', '+00:00'))
        except ValueError:
            timestamp = datetime.now(timezone.utc)
        
        async with pool.acquire() as conn:
            # Insert event (ON CONFLICT DO NOTHING to prevent duplicates)
            await conn.execute(
                """
                INSERT INTO user_activation_events (user_id, event_type, timestamp, metadata)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (user_id, event_type) DO NOTHING
                """,
                request.user_id,
                request.event_type.value,
                timestamp,
                request.metadata or {}
            )
            
            logger.info(f"Tracked activation event: {request.event_type} for user {request.user_id}")
        
        # Compute activation status
        status = await compute_activation_status(request.user_id, pool)
        
        # If user just became activated, fire activation_completed event
        if status.is_activated:
            async with pool.acquire() as conn:
                # Check if activation_completed event already exists
                existing = await conn.fetchval(
                    """
                    SELECT COUNT(*) FROM user_activation_events
                    WHERE user_id = $1 AND event_type = $2
                    """,
                    request.user_id,
                    ActivationEventType.ACTIVATION_COMPLETED.value
                )
                
                if existing == 0:
                    # Insert activation_completed event
                    await conn.execute(
                        """
                        INSERT INTO user_activation_events (user_id, event_type, timestamp, metadata)
                        VALUES ($1, $2, $3, $4)
                        """,
                        request.user_id,
                        ActivationEventType.ACTIVATION_COMPLETED.value,
                        datetime.now(timezone.utc),
                        {
                            "time_to_activation": status.time_to_activation,
                            "activated_at": status.activated_at
                        }
                    )
                    logger.info(
                        f"User {request.user_id} completed activation in {status.time_to_activation}s"
                    )
        
        return {
            "success": True,
            "message": "Activation event tracked",
            "activation_status": status.dict()
        }
        
    except Exception as e:
        logger.error(f"Error tracking activation event: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to track activation event: {str(e)}"
        )


@router.get("/activation/{user_id}", response_model=ActivationStatusResponse)
async def get_activation_status_endpoint(user_id: str):
    """
    Get activation status for a user
    
    Returns completed events, pending events, and activation status.
    """
    try:
        pool = await get_db_pool()
        status = await compute_activation_status(user_id, pool)
        return status
        
    except Exception as e:
        logger.error(f"Error getting activation status: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to get activation status: {str(e)}"
        )


@router.get("/activation/{user_id}/events")
async def get_activation_events(user_id: str):
    """
    Get all activation events for a user
    
    Returns list of activation events with timestamps.
    """
    try:
        pool = await get_db_pool()
        
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT event_type, timestamp, metadata, created_at
                FROM user_activation_events
                WHERE user_id = $1
                ORDER BY timestamp ASC
                """,
                user_id
            )
        
        return {
            "user_id": user_id,
            "events": [
                {
                    "event_type": row['event_type'],
                    "timestamp": row['timestamp'].isoformat(),
                    "metadata": row['metadata'],
                    "created_at": row['created_at'].isoformat()
                }
                for row in rows
            ],
            "total_events": len(rows)
        }
        
    except Exception as e:
        logger.error(f"Error getting activation events: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to get activation events: {str(e)}"
        )


@router.delete("/activation/{user_id}")
async def reset_activation_events(user_id: str):
    """
    Reset activation events for a user (for testing purposes)
    
    Removes all activation events for the specified user.
    """
    try:
        pool = await get_db_pool()
        
        async with pool.acquire() as conn:
            await conn.execute(
                """
                DELETE FROM user_activation_events
                WHERE user_id = $1
                """,
                user_id
            )
        
        logger.info(f"Reset activation events for user {user_id}")
        
        return {
            "success": True,
            "message": f"Activation events reset for user {user_id}"
        }
        
    except Exception as e:
        logger.error(f"Error resetting activation events: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to reset activation events: {str(e)}"
        )


@router.on_event("shutdown")
async def shutdown_db_pool():
    """Close database connection pool on shutdown"""
    global db_pool
    if db_pool:
        await db_pool.close()
