"""
Visual Strategy Flow Persistence API Router
Handles flow CRUD, auto-save, export/import for React Flow canvas

Requirements: 11.11, 11.12, 21.1, 21.2, 21.3, 21.5, 57.1, 57.2, 57.3, 57.4
"""
from fastapi import APIRouter, HTTPException, Depends, status, BackgroundTasks
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Literal
from datetime import datetime
import uuid
import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete as sql_delete, desc
from sqlalchemy.dialects.postgresql import insert

from services.algo_builder.models import StrategySpec
from services.algo_builder.redis_client import get_redis_client
from shared.database.models import Strategy
from services.algo_builder.router import get_db, get_current_user_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/algo/flow", tags=["algo_flow"])

# ============================================================================
# Pydantic Models
# ============================================================================

class FlowNode(BaseModel):
    """React Flow node structure"""
    id: str
    type: str
    position: Dict[str, float]  # {x: float, y: float}
    data: Dict[str, Any] = Field(default_factory=dict)
    width: Optional[float] = None
    height: Optional[float] = None
    selected: Optional[bool] = False
    dragging: Optional[bool] = False


class FlowEdge(BaseModel):
    """React Flow edge structure"""
    id: str
    source: str
    target: str
    sourceHandle: Optional[str] = None
    targetHandle: Optional[str] = None
    type: Optional[str] = "strategy"
    animated: Optional[bool] = True
    label: Optional[str] = None


class FlowState(BaseModel):
    """Complete flow state for persistence"""
    nodes: List[FlowNode]
    edges: List[FlowEdge]
    viewport: Optional[Dict[str, Any]] = Field(
        default_factory=lambda: {"x": 0, "y": 0, "zoom": 1}
    )


class StrategyFlow(BaseModel):
    """Strategy with flow state"""
    strategy_id: str
    user_id: str
    name: str
    description: Optional[str] = None
    flow_state: FlowState
    spec: Optional[StrategySpec] = None
    status: Literal["draft", "testing", "paper", "live", "archived"] = "draft"
    version: int = 1
    created_at: datetime
    updated_at: datetime


class CreateFlowRequest(BaseModel):
    """Request to create a new strategy flow"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    flow_state: FlowState
    spec: Optional[Dict[str, Any]] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "RSI Mean Reversion",
                "description": "Simple RSI-based mean reversion strategy",
                "flow_state": {
                    "nodes": [
                        {
                            "id": "indicator-1",
                            "type": "indicator",
                            "position": {"x": 100, "y": 100},
                            "data": {"indicatorType": "rsi", "period": 14}
                        },
                        {
                            "id": "condition-1",
                            "type": "condition",
                            "position": {"x": 300, "y": 100},
                            "data": {"conditionType": "lt", "threshold": 30}
                        }
                    ],
                    "edges": [
                        {
                            "id": "edge-1",
                            "source": "indicator-1",
                            "target": "condition-1"
                        }
                    ],
                    "viewport": {"x": 0, "y": 0, "zoom": 1}
                }
            }
        }


class UpdateFlowRequest(BaseModel):
    """Request to update strategy flow"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    flow_state: Optional[FlowState] = None
    spec: Optional[Dict[str, Any]] = None
    status: Optional[Literal["draft", "testing", "paper", "live", "archived"]] = None


class AutoSaveRequest(BaseModel):
    """Request for auto-saving flow state"""
    flow_state: FlowState
    spec: Optional[Dict[str, Any]] = None


class ExportFlowResponse(BaseModel):
    """Response with exported flow data"""
    success: bool
    format: Literal["json", "png"]
    data: str  # Base64 encoded data
    filename: str
    strategy_name: str
    exported_at: datetime


class ImportFlowRequest(BaseModel):
    """Request to import strategy flow from JSON"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    flow_json: str  # JSON string containing flow state
    overwrite_existing: bool = False


class ImportFlowResponse(BaseModel):
    """Response after importing flow"""
    success: bool
    strategy_id: str
    name: str
    message: str
    validation_errors: List[str] = Field(default_factory=list)
    imported_at: datetime


class DuplicateFlowRequest(BaseModel):
    """Request to duplicate a strategy"""
    new_name: Optional[str] = None
    copy_history: bool = False


class DuplicateFlowResponse(BaseModel):
    """Response after duplicating flow"""
    success: bool
    original_id: str
    new_id: str
    new_name: str
    duplicated_at: datetime


class FlowVersion(BaseModel):
    """Flow version history entry"""
    version_id: str
    strategy_id: str
    version_number: int
    flow_state: FlowState
    created_at: datetime
    created_by: str
    change_summary: Optional[str] = None


class VersionHistoryResponse(BaseModel):
    """Response with version history"""
    strategy_id: str
    current_version: int
    versions: List[FlowVersion]
    total_versions: int


class RevertRequest(BaseModel):
    """Request to revert to a specific version"""
    version_id: str
    confirm: bool = False


# ============================================================================
# Database Models (for flow versions)
# ============================================================================

from sqlalchemy import Column, String, Integer, DateTime, Text, JSON, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from shared.database.models import Base

class StrategyFlowVersion(Base):
    """Stores version history for strategy flows"""
    __tablename__ = "strategy_flow_versions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    strategy_id = Column(UUID(as_uuid=True), ForeignKey('strategies.id'), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    version_number = Column(Integer, nullable=False)
    flow_state = Column(JSONB, nullable=False)  # Complete flow state
    spec = Column(JSONB, nullable=True)  # Compiled spec if available
    change_summary = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_by = Column(String(255), nullable=False)


# ============================================================================
# Flow CRUD Operations
# ============================================================================

@router.post("/create", response_model=StrategyFlow, status_code=status.HTTP_201_CREATED)
async def create_strategy_flow(
    request: CreateFlowRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db)
):
    """
    Create a new strategy with visual flow state
    
    Requirements: 21.6, 21.7
    """
    try:
        strategy_id = str(uuid.uuid4())
        now = datetime.utcnow()
        
        # Create strategy record
        strategy = Strategy(
            id=uuid.UUID(strategy_id),
            user_id=uuid.UUID(user_id),
            name=request.name,
            description=request.description,
            spec={
                "flow_state": request.flow_state.dict(),
                "strategy_config": request.spec or {}
            },
            status="draft",
            created_at=now,
            updated_at=now
        )
        
        session.add(strategy)
        await session.commit()
        
        # Create initial version
        version = StrategyFlowVersion(
            id=uuid.uuid4(),
            strategy_id=uuid.UUID(strategy_id),
            user_id=uuid.UUID(user_id),
            version_number=1,
            flow_state=request.flow_state.dict(),
            spec=request.spec,
            change_summary="Initial creation",
            created_at=now,
            created_by=user_id
        )
        session.add(version)
        await session.commit()
        
        logger.info(
            f"Created strategy flow",
            extra={"strategy_id": strategy_id, "user_id": user_id, "name": request.name}
        )
        
        return StrategyFlow(
            strategy_id=strategy_id,
            user_id=user_id,
            name=request.name,
            description=request.description,
            flow_state=request.flow_state,
            spec=request.spec,
            status="draft",
            version=1,
            created_at=now,
            updated_at=now
        )
        
    except Exception as e:
        logger.error(f"Failed to create strategy flow: {str(e)}")
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create strategy flow: {str(e)}"
        )


@router.get("/{strategy_id}", response_model=StrategyFlow)
async def get_strategy_flow(
    strategy_id: str,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db)
):
    """
    Get strategy flow state by ID
    
    Requirements: 21.2, 21.8
    """
    try:
        result = await session.execute(
            select(Strategy).where(
                Strategy.id == uuid.UUID(strategy_id),
                Strategy.user_id == uuid.UUID(user_id)
            )
        )
        strategy = result.scalar_one_or_none()
        
        if not strategy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Strategy not found"
            )
        
        # Parse flow state from spec
        spec_data = strategy.spec or {}
        flow_state_data = spec_data.get("flow_state", {"nodes": [], "edges": []})
        
        flow_state = FlowState(**flow_state_data)
        
        return StrategyFlow(
            strategy_id=str(strategy.id),
            user_id=str(strategy.user_id),
            name=strategy.name,
            description=strategy.description,
            flow_state=flow_state,
            spec=spec_data.get("strategy_config"),
            status=strategy.status.value if hasattr(strategy.status, 'value') else strategy.status,
            version=1,  # TODO: Get from version table
            created_at=strategy.created_at,
            updated_at=strategy.updated_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get strategy flow: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get strategy flow: {str(e)}"
        )


@router.put("/{strategy_id}", response_model=StrategyFlow)
async def update_strategy_flow(
    strategy_id: str,
    request: UpdateFlowRequest,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db)
):
    """
    Update strategy flow state
    
    Requirements: 21.3, 21.5
    """
    try:
        result = await session.execute(
            select(Strategy).where(
                Strategy.id == uuid.UUID(strategy_id),
                Strategy.user_id == uuid.UUID(user_id)
            )
        )
        strategy = result.scalar_one_or_none()
        
        if not strategy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Strategy not found"
            )
        
        # Update fields
        if request.name is not None:
            strategy.name = request.name
        if request.description is not None:
            strategy.description = request.description
        if request.status is not None:
            strategy.status = request.status
        
        # Update flow state in spec
        spec_data = strategy.spec or {}
        if request.flow_state:
            spec_data["flow_state"] = request.flow_state.dict()
        if request.spec:
            spec_data["strategy_config"] = request.spec
        
        strategy.spec = spec_data
        strategy.updated_at = datetime.utcnow()
        
        await session.commit()
        
        logger.info(
            f"Updated strategy flow",
            extra={"strategy_id": strategy_id, "user_id": user_id}
        )
        
        return StrategyFlow(
            strategy_id=str(strategy.id),
            user_id=str(strategy.user_id),
            name=strategy.name,
            description=strategy.description,
            flow_state=request.flow_state or FlowState(nodes=[], edges=[]),
            spec=spec_data.get("strategy_config"),
            status=strategy.status.value if hasattr(strategy.status, 'value') else strategy.status,
            version=1,
            created_at=strategy.created_at,
            updated_at=strategy.updated_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update strategy flow: {str(e)}")
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update strategy flow: {str(e)}"
        )


@router.post("/{strategy_id}/autosave", status_code=status.HTTP_200_OK)
async def auto_save_flow(
    strategy_id: str,
    request: AutoSaveRequest,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db)
):
    """
    Auto-save flow state (every 30 seconds)
    
    Requirements: 21.1, 21.3
    """
    try:
        # Store in Redis for fast retrieval
        redis = get_redis_client()
        cache_key = f"flow:autosave:{user_id}:{strategy_id}"
        
        auto_save_data = {
            "flow_state": request.flow_state.dict(),
            "spec": request.spec,
            "saved_at": datetime.utcnow().isoformat(),
            "user_id": user_id
        }
        
        # Save to Redis with 1 hour TTL
        redis.setex(cache_key, 3600, json.dumps(auto_save_data))
        
        logger.debug(
            f"Auto-saved flow state to cache",
            extra={"strategy_id": strategy_id, "user_id": user_id}
        )
        
        return {
            "success": True,
            "message": "Flow state auto-saved",
            "saved_at": auto_save_data["saved_at"]
        }
        
    except Exception as e:
        logger.error(f"Failed to auto-save flow: {str(e)}")
        # Don't raise exception for auto-save failures - it's background operation
        return {
            "success": False,
            "message": f"Auto-save failed: {str(e)}"
        }


@router.get("/{strategy_id}/autosave", response_model=FlowState)
async def get_auto_saved_flow(
    strategy_id: str,
    user_id: str = Depends(get_current_user_id)
):
    """
    Retrieve auto-saved flow state from cache
    
    Requirements: 21.1
    """
    try:
        redis = get_redis_client()
        cache_key = f"flow:autosave:{user_id}:{strategy_id}"
        
        cached_data = redis.get(cache_key)
        if not cached_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No auto-saved state found"
            )
        
        data = json.loads(cached_data)
        return FlowState(**data["flow_state"])
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get auto-saved flow: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get auto-saved flow: {str(e)}"
        )


# ============================================================================
# Export / Import
# ============================================================================

@router.post("/{strategy_id}/export", response_model=ExportFlowResponse)
async def export_strategy_flow(
    strategy_id: str,
    format: Literal["json", "png"] = "json",
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db)
):
    """
    Export strategy flow as JSON or PNG
    
    Requirements: 57.1, 57.2, 57.3, 57.4
    """
    try:
        result = await session.execute(
            select(Strategy).where(
                Strategy.id == uuid.UUID(strategy_id),
                Strategy.user_id == uuid.UUID(user_id)
            )
        )
        strategy = result.scalar_one_or_none()
        
        if not strategy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Strategy not found"
            )
        
        spec_data = strategy.spec or {}
        flow_state = spec_data.get("flow_state", {"nodes": [], "edges": []})
        
        # Prepare export data
        export_data = {
            "version": "1.0",
            "exported_at": datetime.utcnow().isoformat(),
            "strategy": {
                "id": strategy_id,
                "name": strategy.name,
                "description": strategy.description,
                "status": strategy.status.value if hasattr(strategy.status, 'value') else strategy.status,
                "created_at": strategy.created_at.isoformat() if strategy.created_at else None,
                "updated_at": strategy.updated_at.isoformat() if strategy.updated_at else None
            },
            "flow": flow_state,
            "spec": spec_data.get("strategy_config", {})
        }
        
        json_data = json.dumps(export_data, indent=2)
        
        import base64
        base64_data = base64.b64encode(json_data.encode()).decode()
        
        filename = f"strategy_{strategy.name.replace(' ', '_').lower()}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        
        return ExportFlowResponse(
            success=True,
            format="json",
            data=base64_data,
            filename=filename,
            strategy_name=strategy.name,
            exported_at=datetime.utcnow()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to export strategy flow: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to export strategy flow: {str(e)}"
        )


@router.post("/import", response_model=ImportFlowResponse, status_code=status.HTTP_201_CREATED)
async def import_strategy_flow(
    request: ImportFlowRequest,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db)
):
    """
    Import strategy flow from JSON
    
    Requirements: 57.2, 57.3, 57.5, 57.6, 57.7
    """
    try:
        import base64
        
        # Decode JSON data
        try:
            flow_data = json.loads(request.flow_json)
        except json.JSONDecodeError:
            # Try base64 decoding
            try:
                decoded = base64.b64decode(request.flow_json).decode()
                flow_data = json.loads(decoded)
            except Exception:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid JSON format"
                )
        
        # Validate structure
        validation_errors = []
        
        if "flow" not in flow_data and "flow_state" not in flow_data:
            validation_errors.append("Missing flow state data")
        
        flow_state_data = flow_data.get("flow") or flow_data.get("flow_state", {})
        
        if "nodes" not in flow_state_data:
            validation_errors.append("Missing nodes in flow state")
        
        if "edges" not in flow_state_data:
            validation_errors.append("Missing edges in flow state")
        
        if validation_errors:
            return ImportFlowResponse(
                success=False,
                strategy_id="",
                name=request.name,
                message="Validation failed",
                validation_errors=validation_errors,
                imported_at=datetime.utcnow()
            )
        
        # Check for node ID conflicts and resolve
        nodes = flow_state_data.get("nodes", [])
        edges = flow_state_data.get("edges", [])
        
        # Generate new IDs to avoid conflicts
        id_mapping = {}
        for node in nodes:
            old_id = node.get("id")
            new_id = f"{old_id}_{uuid.uuid4().hex[:8]}"
            id_mapping[old_id] = new_id
            node["id"] = new_id
        
        # Update edge references
        for edge in edges:
            if edge.get("source") in id_mapping:
                edge["source"] = id_mapping[edge.get("source")]
            if edge.get("target") in id_mapping:
                edge["target"] = id_mapping[edge.get("target")]
            edge["id"] = f"edge_{uuid.uuid4().hex[:8]}"
        
        # Create new strategy
        strategy_id = str(uuid.uuid4())
        now = datetime.utcnow()
        
        strategy = Strategy(
            id=uuid.UUID(strategy_id),
            user_id=uuid.UUID(user_id),
            name=request.name,
            description=request.description or flow_data.get("strategy", {}).get("description"),
            spec={
                "flow_state": flow_state_data,
                "strategy_config": flow_data.get("spec", {}),
                "imported_from": flow_data.get("strategy", {}).get("id"),
                "imported_at": now.isoformat()
            },
            status="draft",
            created_at=now,
            updated_at=now
        )
        
        session.add(strategy)
        await session.commit()
        
        logger.info(
            f"Imported strategy flow",
            extra={
                "strategy_id": strategy_id,
                "user_id": user_id,
                "name": request.name,
                "original_id": flow_data.get("strategy", {}).get("id")
            }
        )
        
        return ImportFlowResponse(
            success=True,
            strategy_id=strategy_id,
            name=request.name,
            message=f"Strategy '{request.name}' imported successfully",
            validation_errors=[],
            imported_at=now
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to import strategy flow: {str(e)}")
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to import strategy flow: {str(e)}"
        )


# ============================================================================
# Duplicate Strategy
# ============================================================================

@router.post("/{strategy_id}/duplicate", response_model=DuplicateFlowResponse)
async def duplicate_strategy_flow(
    strategy_id: str,
    request: DuplicateFlowRequest,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db)
):
    """
    Duplicate an existing strategy
    
    Requirements: 21.8
    """
    try:
        result = await session.execute(
            select(Strategy).where(
                Strategy.id == uuid.UUID(strategy_id),
                Strategy.user_id == uuid.UUID(user_id)
            )
        )
        original = result.scalar_one_or_none()
        
        if not original:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Strategy not found"
            )
        
        new_id = str(uuid.uuid4())
        now = datetime.utcnow()
        
        # Generate new name
        new_name = request.new_name or f"{original.name} (Copy)"
        
        # Create duplicate
        duplicate = Strategy(
            id=uuid.UUID(new_id),
            user_id=uuid.UUID(user_id),
            name=new_name,
            description=original.description,
            spec=original.spec,
            status="draft",  # Always start as draft
            created_at=now,
            updated_at=now
        )
        
        session.add(duplicate)
        await session.commit()
        
        logger.info(
            f"Duplicated strategy",
            extra={
                "original_id": strategy_id,
                "new_id": new_id,
                "user_id": user_id,
                "new_name": new_name
            }
        )
        
        return DuplicateFlowResponse(
            success=True,
            original_id=strategy_id,
            new_id=new_id,
            new_name=new_name,
            duplicated_at=now
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to duplicate strategy: {str(e)}")
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to duplicate strategy: {str(e)}"
        )


# ============================================================================
# Version History
# ============================================================================

@router.get("/{strategy_id}/versions", response_model=VersionHistoryResponse)
async def get_version_history(
    strategy_id: str,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db)
):
    """
    Get version history for a strategy
    
    Requirements: 21.5
    """
    try:
        from services.algo_builder.flow_router import StrategyFlowVersion
        
        result = await session.execute(
            select(StrategyFlowVersion).where(
                StrategyFlowVersion.strategy_id == uuid.UUID(strategy_id),
                StrategyFlowVersion.user_id == uuid.UUID(user_id)
            ).order_by(desc(StrategyFlowVersion.version_number))
        )
        versions = result.scalars().all()
        
        version_list = []
        for v in versions:
            version_list.append(FlowVersion(
                version_id=str(v.id),
                strategy_id=str(v.strategy_id),
                version_number=v.version_number,
                flow_state=FlowState(**v.flow_state),
                created_at=v.created_at,
                created_by=v.created_by,
                change_summary=v.change_summary
            ))
        
        return VersionHistoryResponse(
            strategy_id=strategy_id,
            current_version=len(version_list),
            versions=version_list,
            total_versions=len(version_list)
        )
        
    except Exception as e:
        logger.error(f"Failed to get version history: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get version history: {str(e)}"
        )


# ============================================================================
# Health Check
# ============================================================================

@router.get("/health")
async def health_check():
    """Health check endpoint for flow router"""
    return {
        "status": "healthy",
        "service": "algo_flow",
        "version": "1.0.0"
    }
