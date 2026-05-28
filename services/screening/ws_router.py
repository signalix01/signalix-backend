"""
WebSocket Router for Real-Time Screening Results

This module implements WebSocket streaming of screening results as they
arrive from each layer of the screening pipeline.

Requirements: 9.7
"""
import logging
import json
import asyncio
from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, HTTPException, status
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select
import uuid
import os
import jwt
from jwt.exceptions import InvalidTokenError

from shared.database.models import ScreeningCriteria as DBScreeningCriteria

logger = logging.getLogger(__name__)

ws_router = APIRouter(prefix="/ws/screen", tags=["screening-websocket"])

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/signalixai")
engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# JWT Configuration
JWT_SECRET = os.getenv("JWT_SECRET", "your-secret-key-change-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")


class ScreeningWebSocketManager:
    """
    Manages WebSocket connections for screening result streaming
    
    Clients connect to /ws/screen/{criteria_id} and receive real-time
    updates as screening progresses through each layer.
    """
    
    def __init__(self):
        """Initialize WebSocket manager"""
        self.active_connections: dict[str, list[WebSocket]] = {}
    
    async def connect(self, criteria_id: str, websocket: WebSocket):
        """
        Accept WebSocket connection and add to active connections
        
        Args:
            criteria_id: Screening criteria UUID
            websocket: WebSocket connection
        """
        await websocket.accept()
        
        if criteria_id not in self.active_connections:
            self.active_connections[criteria_id] = []
        
        self.active_connections[criteria_id].append(websocket)
        
        logger.info(
            f"WebSocket connected",
            extra={
                "criteria_id": criteria_id,
                "active_connections": len(self.active_connections[criteria_id])
            }
        )
    
    def disconnect(self, criteria_id: str, websocket: WebSocket):
        """
        Remove WebSocket connection from active connections
        
        Args:
            criteria_id: Screening criteria UUID
            websocket: WebSocket connection
        """
        if criteria_id in self.active_connections:
            if websocket in self.active_connections[criteria_id]:
                self.active_connections[criteria_id].remove(websocket)
            
            # Clean up empty lists
            if not self.active_connections[criteria_id]:
                del self.active_connections[criteria_id]
        
        logger.info(
            f"WebSocket disconnected",
            extra={
                "criteria_id": criteria_id,
                "remaining_connections": len(self.active_connections.get(criteria_id, []))
            }
        )
    
    async def broadcast(self, criteria_id: str, message: dict):
        """
        Broadcast message to all connected clients for a criteria
        
        Args:
            criteria_id: Screening criteria UUID
            message: Message dict to broadcast
        """
        if criteria_id not in self.active_connections:
            return
        
        # Send to all connected clients
        disconnected = []
        for websocket in self.active_connections[criteria_id]:
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error(f"Failed to send WebSocket message: {str(e)}")
                disconnected.append(websocket)
        
        # Clean up disconnected clients
        for websocket in disconnected:
            self.disconnect(criteria_id, websocket)
    
    async def send_layer_update(
        self,
        criteria_id: str,
        layer: int,
        status: str,
        data: Optional[dict] = None
    ):
        """
        Send layer progress update to connected clients
        
        Args:
            criteria_id: Screening criteria UUID
            layer: Layer number (1, 2, or 3)
            status: Status (started, completed, failed)
            data: Optional data dict with layer-specific info
        """
        message = {
            "type": "layer_update",
            "layer": layer,
            "status": status,
            "data": data or {}
        }
        
        await self.broadcast(criteria_id, message)
    
    async def send_result(self, criteria_id: str, result: dict):
        """
        Send final screening result to connected clients
        
        Args:
            criteria_id: Screening criteria UUID
            result: Screening result dict
        """
        message = {
            "type": "result",
            "data": result
        }
        
        await self.broadcast(criteria_id, message)
    
    async def send_error(self, criteria_id: str, error: str):
        """
        Send error message to connected clients
        
        Args:
            criteria_id: Screening criteria UUID
            error: Error message
        """
        message = {
            "type": "error",
            "error": error
        }
        
        await self.broadcast(criteria_id, message)


# Global WebSocket manager instance
ws_manager = ScreeningWebSocketManager()


@ws_router.websocket("/{criteria_id}")
async def screening_websocket(
    websocket: WebSocket,
    criteria_id: str,
    token: Optional[str] = Query(None, description="Authentication token")
):
    """
    WebSocket endpoint for real-time screening result streaming
    
    Clients connect to this endpoint to receive real-time updates as
    screening progresses through each layer:
    - Layer 1: SQL pre-filter
    - Layer 2: TA-Lib scoring
    - Layer 3: AI scoring
    
    Message format:
    {
        "type": "layer_update" | "result" | "error",
        "layer": 1 | 2 | 3,  // only for layer_update
        "status": "started" | "completed" | "failed",  // only for layer_update
        "data": {...}  // layer-specific data or final result
    }
    
    Requirements: 9.7
    
    Args:
        websocket: WebSocket connection
        criteria_id: Screening criteria UUID
        token: Optional authentication token
    """
    # Implement JWT token validation
    if token:
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            user_id = payload.get("sub")
            if not user_id:
                await websocket.close(code=1008, reason="Invalid token: missing user ID")
                return
            logger.info(f"WebSocket authenticated for user: {user_id}")
        except jwt.ExpiredSignatureError:
            await websocket.close(code=1008, reason="Token expired")
            return
        except jwt.InvalidTokenError as e:
            await websocket.close(code=1008, reason=f"Invalid token: {str(e)}")
            return
    else:
        # Allow unauthenticated connections for now (can be enforced later)
        logger.warning("WebSocket connection without authentication token")
    
    async with AsyncSessionLocal() as session:
        try:
            # Validate criteria exists
            result = await session.execute(
                select(DBScreeningCriteria).where(DBScreeningCriteria.id == uuid.UUID(criteria_id))
            )
            criteria = result.scalar_one_or_none()
            
            if not criteria:
                await websocket.close(code=1008, reason="Criteria not found")
                return
            
            # Connect WebSocket
            await ws_manager.connect(criteria_id, websocket)
            
            # Send welcome message
            await websocket.send_json({
                "type": "connected",
                "criteria_id": criteria_id,
                "criteria_name": criteria.name,
                "message": "Connected to screening stream"
            })
            
            # Keep connection alive and handle incoming messages
            try:
                while True:
                    # Wait for messages from client (e.g., ping/pong)
                    data = await websocket.receive_text()
                    
                    # Handle ping
                    if data == "ping":
                        await websocket.send_json({"type": "pong"})
                    
            except WebSocketDisconnect:
                logger.info(f"WebSocket disconnected normally: {criteria_id}")
            
        except Exception as e:
            logger.error(f"WebSocket error: {str(e)}")
            try:
                await websocket.close(code=1011, reason=f"Internal error: {str(e)}")
            except:
                pass
        
        finally:
            # Disconnect WebSocket
            ws_manager.disconnect(criteria_id, websocket)


# Export ws_manager for use in screening tasks
__all__ = ['ws_router', 'ws_manager']
