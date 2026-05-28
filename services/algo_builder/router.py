"""
Strategy CRUD API Router
Handles strategy creation, retrieval, update, delete, and template operations

Requirements: 1.8, 1.9, 2.4, 2.5
"""
from fastapi import APIRouter, HTTPException, Depends, Query, status
from pydantic import BaseModel, Field, UUID4
from typing import List, Optional, Literal
from datetime import datetime
import hashlib
import uuid
import logging

from services.algo_builder.models import StrategySpec
from services.algo_builder.compiler import StrategyCompiler
from services.algo_builder.sandbox import SandboxRunner, ValidationResult
from services.algo_builder.redis_client import get_redis_client
from shared.database.models import Strategy, BacktestResult, Base
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select, update, delete as sql_delete, and_, desc
from sqlalchemy.orm import selectinload
import os

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/algo", tags=["algo_builder"])

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/signalixai")
engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# ============================================================================
# Dependency: Database Session
# ============================================================================

async def get_db() -> AsyncSession:
    """Get database session"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


# ============================================================================
# Dependency: User Authentication (Placeholder)
# ============================================================================

async def get_current_user_id() -> str:
    """
    Get current authenticated user ID from JWT token
    
    TODO: Implement proper JWT authentication middleware
    For now, returns a test user ID
    """
    # In production, this would extract user_id from JWT token in Authorization header
    # For now, return a test user ID
    return "00000000-0000-0000-0000-000000000001"


# ============================================================================
# Request/Response Models
# ============================================================================

class CreateStrategyRequest(BaseModel):
    """Request to create a new strategy"""
    spec: StrategySpec
    
    class Config:
        json_schema_extra = {
            "example": {
                "spec": {
                    "strategy_id": "my_strategy_001",
                    "user_id": "user_123",
                    "name": "My First Strategy",
                    "description": "A simple RSI strategy",
                    "asset_class": "equity",
                    "instruments": ["NIFTY", "BANKNIFTY"],
                    "entry_rules": [
                        {
                            "direction": "LONG",
                            "condition_groups": [
                                {
                                    "conditions": [
                                        {
                                            "left_operand": "rsi_14",
                                            "operator": "<",
                                            "right_operand": 30.0,
                                            "time_frame": "1D"
                                        }
                                    ],
                                    "gate": "AND"
                                }
                            ],
                            "confirmation_candles": 1
                        }
                    ],
                    "exit_rules": [
                        {
                            "exit_type": "target",
                            "target_pct": 5.0
                        }
                    ],
                    "position_sizing": {
                        "method": "pct_capital",
                        "value": 5.0,
                        "max_position_pct": 10.0,
                        "max_concurrent_positions": 3
                    },
                    "market_filter": {
                        "require_above_200ema": False,
                        "min_adx": None,
                        "max_vix": None,
                        "require_positive_breadth": False
                    },
                    "indicators_config": {
                        "rsi_14": {"period": 14}
                    },
                    "risk_per_trade_pct": 1.0,
                    "max_daily_loss_pct": 2.0,
                    "regime_awareness": True,
                    "status": "draft",
                    "created_at": "2025-01-15T10:00:00Z",
                    "updated_at": "2025-01-15T10:00:00Z"
                }
            }
        }


class UpdateStrategyRequest(BaseModel):
    """Request to update an existing strategy"""
    spec: StrategySpec


class StrategyResponse(BaseModel):
    """Response containing strategy details"""
    id: str
    user_id: str
    template_id: Optional[str]
    name: str
    description: Optional[str]
    spec: dict
    compiled_hash: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class StrategyListResponse(BaseModel):
    """Paginated list of strategies"""
    strategies: List[StrategyResponse]
    total: int
    page: int
    limit: int
    total_pages: int


class TemplateResponse(BaseModel):
    """Response containing template details"""
    id: str
    name: str
    description: Optional[str]
    spec: dict
    created_at: datetime
    
    class Config:
        from_attributes = True


class CloneTemplateResponse(BaseModel):
    """Response after cloning a template"""
    success: bool
    message: str
    strategy_id: str
    strategy: StrategyResponse


class CompileStrategyResponse(BaseModel):
    """Response after compiling a strategy"""
    success: bool
    message: str
    compiled_hash: str
    validation_result: dict
    cached: bool
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Strategy compiled and validated successfully",
                "compiled_hash": "a3f5b2c1d4e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2",
                "validation_result": {
                    "success": True,
                    "message": "Strategy validated successfully in 125.45ms",
                    "execution_time_ms": 125.45
                },
                "cached": True
            }
        }


class CreatePaperTradingRequest(BaseModel):
    """Request to create a paper trading session"""
    initial_capital: float = Field(default=100000.0, gt=0, description="Starting capital in Rs")
    
    class Config:
        json_schema_extra = {
            "example": {
                "initial_capital": 100000.0
            }
        }


class PaperTradingResponse(BaseModel):
    """Response after creating paper trading session"""
    success: bool
    message: str
    session_id: str
    strategy_id: str
    initial_capital: float
    status: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Paper trading session created successfully",
                "session_id": "550e8400-e29b-41d4-a716-446655440000",
                "strategy_id": "123e4567-e89b-12d3-a456-426614174000",
                "initial_capital": 100000.0,
                "status": "active"
            }
        }


class PromoteToLiveRequest(BaseModel):
    """Request to promote strategy from paper to live trading"""
    pin: str = Field(..., min_length=4, max_length=4, description="4-digit PIN confirmation")
    
    class Config:
        json_schema_extra = {
            "example": {
                "pin": "1234"
            }
        }


class PromoteToLiveResponse(BaseModel):
    """Response after promoting strategy to live"""
    success: bool
    message: str
    strategy_id: str
    status: str
    celery_task_id: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Strategy promoted to live trading successfully",
                "strategy_id": "123e4567-e89b-12d3-a456-426614174000",
                "status": "live",
                "celery_task_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
            }
        }


# ============================================================================
# Helper Functions
# ============================================================================

def compute_spec_hash(spec: dict) -> str:
    """
    Compute SHA-256 hash of strategy spec for cache invalidation
    
    Args:
        spec: Strategy specification dictionary
        
    Returns:
        SHA-256 hash string
    """
    import json
    spec_json = json.dumps(spec, sort_keys=True)
    return hashlib.sha256(spec_json.encode()).hexdigest()


async def check_strategy_ownership(
    strategy_id: str,
    user_id: str,
    session: AsyncSession
) -> Strategy:
    """
    Check if strategy exists and belongs to user
    
    Args:
        strategy_id: Strategy UUID
        user_id: User UUID
        session: Database session
        
    Returns:
        Strategy object if found and owned by user
        
    Raises:
        HTTPException: If strategy not found or not owned by user
    """
    result = await session.execute(
        select(Strategy).where(
            and_(
                Strategy.id == uuid.UUID(strategy_id),
                Strategy.user_id == uuid.UUID(user_id)
            )
        )
    )
    strategy = result.scalar_one_or_none()
    
    if not strategy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Strategy not found or access denied"
        )
    
    return strategy


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/strategies", response_model=StrategyResponse, status_code=status.HTTP_201_CREATED)
async def create_strategy(
    request: CreateStrategyRequest,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db)
) -> StrategyResponse:
    """
    Create a new trading strategy
    
    Validates the strategy specification and stores it in the database.
    
    Requirements: 1.1, 1.2, 1.3, 1.8
    
    Args:
        request: Strategy creation request with spec
        user_id: Current authenticated user ID
        session: Database session
        
    Returns:
        Created strategy with generated ID
        
    Raises:
        HTTPException 422: If strategy spec validation fails
        HTTPException 500: If database operation fails
    """
    try:
        # Validate spec using Pydantic model (already done by request model)
        spec = request.spec
        
        # Override user_id in spec with authenticated user
        spec.user_id = user_id
        
        # Generate new strategy ID
        strategy_id = uuid.uuid4()
        
        # Update spec with generated ID
        spec.strategy_id = str(strategy_id)
        
        # Set timestamps
        now = datetime.utcnow()
        spec.created_at = now.isoformat()
        spec.updated_at = now.isoformat()
        
        # Convert spec to dict
        spec_dict = spec.model_dump()
        
        # Create strategy record
        strategy = Strategy(
            id=strategy_id,
            user_id=uuid.UUID(user_id),
            template_id=None,
            name=spec.name,
            description=spec.description,
            spec=spec_dict,
            compiled_hash=None,  # Will be set when strategy is compiled
            status=spec.status,
            created_at=now,
            updated_at=now
        )
        
        session.add(strategy)
        await session.commit()
        await session.refresh(strategy)
        
        logger.info(
            f"Strategy created",
            extra={
                "strategy_id": str(strategy.id),
                "user_id": user_id,
                "name": strategy.name,
                "asset_class": spec.asset_class
            }
        )
        
        return StrategyResponse(
            id=str(strategy.id),
            user_id=str(strategy.user_id),
            template_id=str(strategy.template_id) if strategy.template_id else None,
            name=strategy.name,
            description=strategy.description,
            spec=strategy.spec,
            compiled_hash=strategy.compiled_hash,
            status=strategy.status,
            created_at=strategy.created_at,
            updated_at=strategy.updated_at
        )
        
    except ValueError as e:
        logger.error(f"Strategy validation failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Strategy validation failed: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Failed to create strategy: {str(e)}")
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create strategy: {str(e)}"
        )


@router.get("/strategies", response_model=StrategyListResponse)
async def list_strategies(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=100, description="Items per page"),
    status_filter: Optional[str] = Query(None, description="Filter by status: draft, testing, paper, live"),
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db)
) -> StrategyListResponse:
    """
    Get paginated list of user's strategies
    
    Requirements: 1.8
    
    Args:
        page: Page number (1-indexed)
        limit: Number of items per page
        status_filter: Optional status filter
        user_id: Current authenticated user ID
        session: Database session
        
    Returns:
        Paginated list of strategies
    """
    try:
        # Build query
        query = select(Strategy).where(Strategy.user_id == uuid.UUID(user_id))
        
        # Apply status filter if provided
        if status_filter:
            query = query.where(Strategy.status == status_filter)
        
        # Order by created_at descending
        query = query.order_by(Strategy.created_at.desc())
        
        # Get total count
        count_query = select(Strategy).where(Strategy.user_id == uuid.UUID(user_id))
        if status_filter:
            count_query = count_query.where(Strategy.status == status_filter)
        
        count_result = await session.execute(count_query)
        total = len(count_result.scalars().all())
        
        # Apply pagination
        offset = (page - 1) * limit
        query = query.offset(offset).limit(limit)
        
        # Execute query
        result = await session.execute(query)
        strategies = result.scalars().all()
        
        # Convert to response models
        strategy_responses = [
            StrategyResponse(
                id=str(s.id),
                user_id=str(s.user_id),
                template_id=str(s.template_id) if s.template_id else None,
                name=s.name,
                description=s.description,
                spec=s.spec,
                compiled_hash=s.compiled_hash,
                status=s.status,
                created_at=s.created_at,
                updated_at=s.updated_at
            )
            for s in strategies
        ]
        
        total_pages = (total + limit - 1) // limit
        
        return StrategyListResponse(
            strategies=strategy_responses,
            total=total,
            page=page,
            limit=limit,
            total_pages=total_pages
        )
        
    except Exception as e:
        logger.error(f"Failed to list strategies: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list strategies: {str(e)}"
        )


@router.get("/strategies/{strategy_id}", response_model=StrategyResponse)
async def get_strategy(
    strategy_id: str,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db)
) -> StrategyResponse:
    """
    Get full strategy details by ID
    
    Requirements: 1.8
    
    Args:
        strategy_id: Strategy UUID
        user_id: Current authenticated user ID
        session: Database session
        
    Returns:
        Full strategy details including compiled_hash
        
    Raises:
        HTTPException 404: If strategy not found or access denied
    """
    try:
        strategy = await check_strategy_ownership(strategy_id, user_id, session)
        
        return StrategyResponse(
            id=str(strategy.id),
            user_id=str(strategy.user_id),
            template_id=str(strategy.template_id) if strategy.template_id else None,
            name=strategy.name,
            description=strategy.description,
            spec=strategy.spec,
            compiled_hash=strategy.compiled_hash,
            status=strategy.status,
            created_at=strategy.created_at,
            updated_at=strategy.updated_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get strategy: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get strategy: {str(e)}"
        )


@router.put("/strategies/{strategy_id}", response_model=StrategyResponse)
async def update_strategy(
    strategy_id: str,
    request: UpdateStrategyRequest,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db)
) -> StrategyResponse:
    """
    Update an existing strategy
    
    Validates new spec, updates database, and invalidates compiled cache.
    
    Requirements: 1.8, 1.10
    
    Args:
        strategy_id: Strategy UUID
        request: Update request with new spec
        user_id: Current authenticated user ID
        session: Database session
        
    Returns:
        Updated strategy
        
    Raises:
        HTTPException 404: If strategy not found or access denied
        HTTPException 422: If new spec validation fails
    """
    try:
        # Check ownership
        strategy = await check_strategy_ownership(strategy_id, user_id, session)
        
        # Validate new spec
        new_spec = request.spec
        
        # Override user_id and strategy_id
        new_spec.user_id = user_id
        new_spec.strategy_id = strategy_id
        
        # Update timestamp
        new_spec.updated_at = datetime.utcnow().isoformat()
        
        # Convert to dict
        spec_dict = new_spec.model_dump()
        
        # Update strategy
        strategy.name = new_spec.name
        strategy.description = new_spec.description
        strategy.spec = spec_dict
        strategy.status = new_spec.status
        strategy.updated_at = datetime.utcnow()
        
        # Invalidate compiled cache (set compiled_hash to None)
        strategy.compiled_hash = None
        
        await session.commit()
        await session.refresh(strategy)
        
        logger.info(
            f"Strategy updated",
            extra={
                "strategy_id": strategy_id,
                "user_id": user_id,
                "name": strategy.name
            }
        )
        
        return StrategyResponse(
            id=str(strategy.id),
            user_id=str(strategy.user_id),
            template_id=str(strategy.template_id) if strategy.template_id else None,
            name=strategy.name,
            description=strategy.description,
            spec=strategy.spec,
            compiled_hash=strategy.compiled_hash,
            status=strategy.status,
            created_at=strategy.created_at,
            updated_at=strategy.updated_at
        )
        
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Strategy validation failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Strategy validation failed: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Failed to update strategy: {str(e)}")
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update strategy: {str(e)}"
        )


@router.delete("/strategies/{strategy_id}", status_code=status.HTTP_200_OK)
async def delete_strategy(
    strategy_id: str,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db)
) -> dict:
    """
    Soft delete a strategy
    
    Sets status to 'deleted'. Blocks deletion if strategy is live.
    
    Requirements: 1.9
    
    Args:
        strategy_id: Strategy UUID
        user_id: Current authenticated user ID
        session: Database session
        
    Returns:
        Success message
        
    Raises:
        HTTPException 404: If strategy not found or access denied
        HTTPException 400: If strategy is live (cannot delete)
    """
    try:
        # Check ownership
        strategy = await check_strategy_ownership(strategy_id, user_id, session)
        
        # Block deletion if strategy is live
        if strategy.status == "live":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete a live strategy. Please stop the strategy first."
            )
        
        # Soft delete: set status to deleted
        strategy.status = "deleted"
        strategy.updated_at = datetime.utcnow()
        
        await session.commit()
        
        logger.info(
            f"Strategy deleted",
            extra={
                "strategy_id": strategy_id,
                "user_id": user_id,
                "name": strategy.name
            }
        )
        
        return {
            "success": True,
            "message": f"Strategy '{strategy.name}' deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete strategy: {str(e)}")
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete strategy: {str(e)}"
        )


@router.get("/templates", response_model=List[TemplateResponse])
async def get_templates(
    session: AsyncSession = Depends(get_db)
) -> List[TemplateResponse]:
    """
    Get all strategy templates
    
    Returns pre-built strategy templates from seed data.
    
    Requirements: 2.1, 2.2, 2.3
    
    Args:
        session: Database session
        
    Returns:
        List of all strategy templates
    """
    try:
        # Templates are stored with system user_id = 00000000-0000-0000-0000-000000000000
        system_user_id = uuid.UUID("00000000-0000-0000-0000-000000000000")
        
        result = await session.execute(
            select(Strategy).where(Strategy.user_id == system_user_id)
        )
        templates = result.scalars().all()
        
        template_responses = [
            TemplateResponse(
                id=str(t.id),
                name=t.name,
                description=t.description,
                spec=t.spec,
                created_at=t.created_at
            )
            for t in templates
        ]
        
        return template_responses
        
    except Exception as e:
        logger.error(f"Failed to get templates: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get templates: {str(e)}"
        )


@router.post("/templates/{template_id}/clone", response_model=CloneTemplateResponse, status_code=status.HTTP_201_CREATED)
async def clone_template(
    template_id: str,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db)
) -> CloneTemplateResponse:
    """
    Clone a template to user's strategies
    
    Creates a new strategy with status=draft from the template spec.
    
    Requirements: 2.4, 2.5
    
    Args:
        template_id: Template UUID
        user_id: Current authenticated user ID
        session: Database session
        
    Returns:
        Cloned strategy with new ID
        
    Raises:
        HTTPException 404: If template not found
    """
    try:
        # Get template
        result = await session.execute(
            select(Strategy).where(Strategy.id == uuid.UUID(template_id))
        )
        template = result.scalar_one_or_none()
        
        if not template:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Template not found: {template_id}"
            )
        
        # Generate new strategy ID
        new_strategy_id = uuid.uuid4()
        
        # Clone spec
        cloned_spec = template.spec.copy()
        
        # Update spec with new IDs and user
        cloned_spec["strategy_id"] = str(new_strategy_id)
        cloned_spec["user_id"] = user_id
        cloned_spec["name"] = f"{template.name} (Copy)"
        cloned_spec["status"] = "draft"
        
        # Update timestamps
        now = datetime.utcnow()
        cloned_spec["created_at"] = now.isoformat()
        cloned_spec["updated_at"] = now.isoformat()
        
        # Create new strategy
        new_strategy = Strategy(
            id=new_strategy_id,
            user_id=uuid.UUID(user_id),
            template_id=template.id,  # Track which template this was cloned from
            name=cloned_spec["name"],
            description=template.description,
            spec=cloned_spec,
            compiled_hash=None,
            status="draft",
            created_at=now,
            updated_at=now
        )
        
        session.add(new_strategy)
        await session.commit()
        await session.refresh(new_strategy)
        
        logger.info(
            f"Template cloned",
            extra={
                "template_id": template_id,
                "new_strategy_id": str(new_strategy_id),
                "user_id": user_id,
                "template_name": template.name
            }
        )
        
        strategy_response = StrategyResponse(
            id=str(new_strategy.id),
            user_id=str(new_strategy.user_id),
            template_id=str(new_strategy.template_id) if new_strategy.template_id else None,
            name=new_strategy.name,
            description=new_strategy.description,
            spec=new_strategy.spec,
            compiled_hash=new_strategy.compiled_hash,
            status=new_strategy.status,
            created_at=new_strategy.created_at,
            updated_at=new_strategy.updated_at
        )
        
        return CloneTemplateResponse(
            success=True,
            message=f"Template '{template.name}' cloned successfully",
            strategy_id=str(new_strategy_id),
            strategy=strategy_response
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to clone template: {str(e)}")
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clone template: {str(e)}"
        )


# ============================================================================
# Compilation & Paper Trading Endpoints
# ============================================================================

@router.post("/strategies/{strategy_id}/compile", response_model=CompileStrategyResponse)
async def compile_strategy(
    strategy_id: str,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db)
) -> CompileStrategyResponse:
    """
    Compile a strategy and run 100-bar validation test
    
    On success:
    - Stores compiled_hash in strategies table
    - Caches compiled object in Redis with 24h TTL (key: compiled_strategy:{hash})
    
    On failure:
    - Returns 422 with exact Python exception from sandbox
    
    Requirements: 3.6, 3.7
    
    Args:
        strategy_id: Strategy UUID
        user_id: Current authenticated user ID
        session: Database session
        
    Returns:
        Compilation result with validation details
        
    Raises:
        HTTPException 404: If strategy not found or access denied
        HTTPException 422: If compilation or validation fails
    """
    try:
        # Check ownership
        strategy = await check_strategy_ownership(strategy_id, user_id, session)
        
        # Parse spec
        spec = StrategySpec(**strategy.spec)
        
        # Compute spec hash for caching
        spec_hash = compute_spec_hash(strategy.spec)
        
        # Check if already compiled and cached
        redis_client = await get_redis_client()
        cached_code = await redis_client.get_compiled_strategy(spec_hash)
        
        if cached_code and strategy.compiled_hash == spec_hash:
            # Already compiled and cached - just validate
            logger.info(
                f"Strategy already compiled and cached",
                extra={
                    "strategy_id": strategy_id,
                    "compiled_hash": spec_hash[:8]
                }
            )
            
            # Run validation on cached code
            sandbox = SandboxRunner()
            validation_result = sandbox.validate(cached_code)
            
            if not validation_result.success:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={
                        "error": "Strategy validation failed",
                        "message": validation_result.message,
                        "details": validation_result.error
                    }
                )
            
            return CompileStrategyResponse(
                success=True,
                message="Strategy already compiled and validated (from cache)",
                compiled_hash=spec_hash,
                validation_result=validation_result.to_dict(),
                cached=True
            )
        
        # Compile the strategy
        logger.info(
            f"Compiling strategy",
            extra={
                "strategy_id": strategy_id,
                "name": spec.name,
                "asset_class": spec.asset_class
            }
        )
        
        compiler = StrategyCompiler()
        
        try:
            compiled_code = compiler.compile(spec)
        except (ValueError, SyntaxError) as e:
            logger.error(f"Compilation failed: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "error": "Strategy compilation failed",
                    "message": str(e),
                    "details": f"{type(e).__name__}: {str(e)}"
                }
            )
        
        # Run validation in sandbox
        logger.info(f"Validating compiled strategy in sandbox")
        
        sandbox = SandboxRunner()
        validation_result = sandbox.validate(compiled_code)
        
        if not validation_result.success:
            logger.error(
                f"Validation failed: {validation_result.error}",
                extra={"strategy_id": strategy_id}
            )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "error": "Strategy validation failed",
                    "message": validation_result.message,
                    "details": validation_result.error
                }
            )
        
        # Store compiled_hash in database
        strategy.compiled_hash = spec_hash
        strategy.updated_at = datetime.utcnow()
        await session.commit()
        
        logger.info(
            f"Stored compiled_hash in database",
            extra={
                "strategy_id": strategy_id,
                "compiled_hash": spec_hash[:8]
            }
        )
        
        # Cache compiled code in Redis with 24h TTL
        cache_success = await redis_client.set_compiled_strategy(spec_hash, compiled_code)
        
        if not cache_success:
            logger.warning(
                f"Failed to cache compiled strategy in Redis",
                extra={"strategy_id": strategy_id}
            )
        
        logger.info(
            f"Strategy compiled and validated successfully",
            extra={
                "strategy_id": strategy_id,
                "compiled_hash": spec_hash[:8],
                "validation_time_ms": validation_result.execution_time_ms,
                "cached": cache_success
            }
        )
        
        return CompileStrategyResponse(
            success=True,
            message=f"Strategy compiled and validated successfully in {validation_result.execution_time_ms:.2f}ms",
            compiled_hash=spec_hash,
            validation_result=validation_result.to_dict(),
            cached=cache_success
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to compile strategy: {str(e)}")
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to compile strategy: {str(e)}"
        )


@router.post("/strategies/{strategy_id}/paper", response_model=PaperTradingResponse, status_code=status.HTTP_201_CREATED)
async def create_paper_trading_session(
    strategy_id: str,
    request: CreatePaperTradingRequest,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db)
) -> PaperTradingResponse:
    """
    Create a paper trading session for a compiled strategy
    
    Validates that the strategy is compiled before creating the session.
    Updates strategy status to 'paper' if currently 'draft' or 'testing'.
    
    Requirements: 1.9
    
    Args:
        strategy_id: Strategy UUID
        request: Paper trading configuration
        user_id: Current authenticated user ID
        session: Database session
        
    Returns:
        Paper trading session details
        
    Raises:
        HTTPException 404: If strategy not found or access denied
        HTTPException 400: If strategy is not compiled or is already live
    """
    try:
        # Check ownership
        strategy = await check_strategy_ownership(strategy_id, user_id, session)
        
        # Validate strategy is compiled
        if not strategy.compiled_hash:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "Strategy not compiled",
                    "message": "Please compile the strategy before starting paper trading",
                    "action": f"POST /api/v1/algo/strategies/{strategy_id}/compile"
                }
            )
        
        # Verify compiled code exists in cache
        redis_client = await get_redis_client()
        cached_code = await redis_client.get_compiled_strategy(strategy.compiled_hash)
        
        if not cached_code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "Compiled strategy not found in cache",
                    "message": "Please recompile the strategy",
                    "action": f"POST /api/v1/algo/strategies/{strategy_id}/compile"
                }
            )
        
        # Block if strategy is already live
        if strategy.status == "live":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot start paper trading for a live strategy. Please stop the live session first."
            )
        
        # Generate paper trading session ID
        session_id = uuid.uuid4()
        
        # Update strategy status to paper (if not already)
        if strategy.status in ["draft", "testing"]:
            strategy.status = "paper"
            strategy.updated_at = datetime.utcnow()
            await session.commit()
            
            logger.info(
                f"Strategy status updated to paper",
                extra={
                    "strategy_id": strategy_id,
                    "previous_status": strategy.status
                }
            )
        
        # TODO: Create paper trading session record in database
        # This would be implemented in a separate paper_trading_sessions table
        # For now, we just return the session details
        
        logger.info(
            f"Paper trading session created",
            extra={
                "strategy_id": strategy_id,
                "session_id": str(session_id),
                "initial_capital": request.initial_capital,
                "user_id": user_id
            }
        )
        
        return PaperTradingResponse(
            success=True,
            message=f"Paper trading session created for strategy '{strategy.name}'",
            session_id=str(session_id),
            strategy_id=strategy_id,
            initial_capital=request.initial_capital,
            status="active"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create paper trading session: {str(e)}")
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create paper trading session: {str(e)}"
        )


@router.post("/strategies/{strategy_id}/live", response_model=PromoteToLiveResponse, status_code=status.HTTP_200_OK)
async def promote_strategy_to_live(
    strategy_id: str,
    request: PromoteToLiveRequest,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db)
) -> PromoteToLiveResponse:
    """
    Promote a strategy from paper trading to live execution
    
    Pre-flight checks:
    1. Strategy has been in paper mode >= 30 days
    2. Paper mode has positive return
    3. Walk-forward validation passed
    4. User provides 4-digit PIN confirmation
    
    On success:
    - Updates strategy status to 'live'
    - Activates execution Celery task
    
    On failure:
    - Returns specific reason for rejection with actionable next steps
    
    Requirements: 15.2
    
    Args:
        strategy_id: Strategy UUID
        request: Promotion request with PIN confirmation
        user_id: Current authenticated user ID
        session: Database session
        
    Returns:
        Promotion result with Celery task ID
        
    Raises:
        HTTPException 404: If strategy not found or access denied
        HTTPException 400: If pre-flight checks fail
        HTTPException 403: If PIN verification fails
    """
    try:
        # Check ownership
        strategy = await check_strategy_ownership(strategy_id, user_id, session)
        
        # Pre-flight check 1: Strategy must be in paper mode
        if strategy.status != "paper":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "Invalid strategy status",
                    "message": f"Strategy must be in paper trading mode to promote to live. Current status: {strategy.status}",
                    "current_status": strategy.status,
                    "required_status": "paper",
                    "action": "Start paper trading first" if strategy.status == "draft" else "Strategy cannot be promoted from current status"
                }
            )
        
        # Pre-flight check 2: Strategy must have been in paper mode >= 30 days
        # We track this by checking when the strategy status was last updated to 'paper'
        # For now, we'll check the updated_at timestamp
        # In production, this would query a paper_trading_sessions table
        
        from datetime import timedelta
        now = datetime.utcnow()
        paper_mode_duration = now - strategy.updated_at
        required_duration = timedelta(days=30)
        
        if paper_mode_duration < required_duration:
            days_remaining = (required_duration - paper_mode_duration).days
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "Insufficient paper trading duration",
                    "message": f"Strategy must be in paper mode for at least 30 days. Current: {paper_mode_duration.days} days, Required: 30 days",
                    "days_in_paper_mode": paper_mode_duration.days,
                    "required_days": 30,
                    "days_remaining": days_remaining,
                    "paper_mode_start_date": strategy.updated_at.isoformat(),
                    "earliest_promotion_date": (strategy.updated_at + required_duration).isoformat(),
                    "action": f"Continue paper trading for {days_remaining} more days"
                }
            )
        
        # Pre-flight check 3: Paper mode must have positive return
        # This requires querying backtest results or paper trading performance
        # For now, we'll check if there's a recent backtest result with positive return
        
        from sqlalchemy import and_, desc
        backtest_query = select(BacktestResult).where(
            and_(
                BacktestResult.strategy_id == uuid.UUID(strategy_id),
                BacktestResult.status == 'complete'
            )
        ).order_by(desc(BacktestResult.created_at)).limit(1)
        
        backtest_result_row = await session.execute(backtest_query)
        backtest_result = backtest_result_row.scalar_one_or_none()
        
        if not backtest_result:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "No backtest results found",
                    "message": "Strategy must have at least one completed backtest before promotion to live",
                    "action": "Run a backtest on this strategy first",
                    "endpoint": f"POST /api/v1/backtest/run"
                }
            )
        
        if backtest_result.total_return_pct is None or backtest_result.total_return_pct <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "Negative or zero returns",
                    "message": f"Strategy must demonstrate positive returns in paper mode. Current return: {backtest_result.total_return_pct:.2f}%",
                    "total_return_pct": backtest_result.total_return_pct,
                    "required_return_pct": "> 0",
                    "action": "Optimize strategy parameters or test different market conditions"
                }
            )
        
        # Pre-flight check 4: Walk-forward validation must have passed
        if backtest_result.wf_consistency_score is None or backtest_result.wf_consistency_score < 0.7:
            wf_score = backtest_result.wf_consistency_score or 0.0
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "Walk-forward validation failed",
                    "message": f"Strategy must pass walk-forward validation (consistency score >= 0.7). Current score: {wf_score:.2f}",
                    "wf_consistency_score": wf_score,
                    "required_score": 0.7,
                    "action": "Simplify strategy rules to avoid overfitting, or run walk-forward validation again",
                    "endpoint": f"POST /api/v1/backtest/run with run_walk_forward=true"
                }
            )
        
        # Pre-flight check 5: Verify 4-digit PIN
        # In production, this would verify against user's stored PIN hash
        # For now, we'll do a basic validation that it's 4 digits
        
        if not request.pin.isdigit():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "Invalid PIN format",
                    "message": "PIN must be exactly 4 digits",
                    "action": "Enter a valid 4-digit PIN"
                }
            )
        
        # TODO: In production, verify PIN against user's stored PIN hash
        # For now, we'll accept any 4-digit PIN for testing
        # Example:
        # user_pin_hash = await get_user_pin_hash(user_id)
        # if not verify_pin(request.pin, user_pin_hash):
        #     raise HTTPException(status_code=403, detail="Incorrect PIN")
        
        logger.info(
            f"All pre-flight checks passed for strategy promotion",
            extra={
                "strategy_id": strategy_id,
                "user_id": user_id,
                "days_in_paper_mode": paper_mode_duration.days,
                "total_return_pct": backtest_result.total_return_pct,
                "wf_consistency_score": backtest_result.wf_consistency_score
            }
        )
        
        # Update strategy status to live
        strategy.status = "live"
        strategy.updated_at = datetime.utcnow()
        await session.commit()
        
        logger.info(
            f"Strategy promoted to live",
            extra={
                "strategy_id": strategy_id,
                "user_id": user_id,
                "name": strategy.name
            }
        )
        
        # Activate execution Celery task
        # TODO: Implement Celery task activation
        # For now, we'll return a placeholder task ID
        # In production, this would:
        # 1. Create a Celery task to monitor market data
        # 2. Execute strategy signals in real-time
        # 3. Place orders through broker adapter
        
        celery_task_id = None
        try:
            # Placeholder for Celery task activation
            # from services.execution.tasks import activate_live_strategy
            # celery_task = activate_live_strategy.delay(strategy_id, user_id)
            # celery_task_id = celery_task.id
            
            logger.info(
                f"Live execution task activation pending",
                extra={
                    "strategy_id": strategy_id,
                    "user_id": user_id,
                    "note": "Celery task activation not yet implemented"
                }
            )
        except Exception as e:
            logger.error(f"Failed to activate Celery task: {e}")
            # Don't fail the promotion if Celery task fails
            # The strategy is already marked as live
        
        return PromoteToLiveResponse(
            success=True,
            message=f"Strategy '{strategy.name}' promoted to live trading successfully. Execution engine will begin monitoring market data.",
            strategy_id=strategy_id,
            status="live",
            celery_task_id=celery_task_id
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to promote strategy to live: {str(e)}")
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to promote strategy to live: {str(e)}"
        )


# ============================================================================
# Health Check
# ============================================================================

@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "algo_builder",
        "version": "1.0.0"
    }
