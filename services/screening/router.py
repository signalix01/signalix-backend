"""
Screening Criteria CRUD API Router
Handles screening criteria creation, retrieval, update, delete, and template operations

Requirements: 9.4, 10.1, 10.2, 10.3, 10.4
"""
from fastapi import APIRouter, HTTPException, Depends, Query, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, UUID4
from typing import List, Optional
from datetime import datetime
import uuid
import logging
import jwt

from services.screening.models import ScreeningCriteria, ScreeningResult, ScreenedInstrument
from shared.database.models import ScreeningCriteria as DBScreeningCriteria, ScreeningResult as DBScreeningResult, Base
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select, update, delete as sql_delete, and_, desc
import os

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/screen", tags=["screening"])

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/signalixai")
engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# JWT Configuration
JWT_SECRET = os.getenv("JWT_SECRET", "your-secret-key-change-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

# Security
security = HTTPBearer(auto_error=False)


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

async def get_current_user_id(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> str:
    """
    Get current authenticated user ID from JWT token
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token"
        )
    
    try:
        payload = jwt.decode(
            credentials.credentials,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM]
        )
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token payload missing 'sub' field"
            )
        return user_id
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired"
        )
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid token: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token"
        )
    except Exception as e:
        logger.error(f"Error verifying token: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Error verifying token"
        )


# ============================================================================
# Request/Response Models
# ============================================================================

class CreateCriteriaRequest(BaseModel):
    """Request to create new screening criteria"""
    criteria: ScreeningCriteria
    schedule_enabled: bool = Field(default=False, description="Enable scheduled screening")
    schedule_cron: Optional[str] = Field(None, description="Cron expression for scheduling")
    
    class Config:
        json_schema_extra = {
            "example": {
                "criteria": {
                    "name": "Oversold Reversal Scanner",
                    "description": "Find oversold stocks with strong fundamentals",
                    "asset_class": ["equity"],
                    "min_market_cap_cr": 1000.0,
                    "min_rsi": 20.0,
                    "max_rsi": 35.0,
                    "require_above_ema": 200,
                    "min_volume_ratio": 1.5
                },
                "schedule_enabled": False,
                "schedule_cron": None
            }
        }


class UpdateCriteriaRequest(BaseModel):
    """Request to update existing screening criteria"""
    criteria: ScreeningCriteria
    schedule_enabled: Optional[bool] = None
    schedule_cron: Optional[str] = None


class CriteriaResponse(BaseModel):
    """Response containing screening criteria details"""
    id: str
    user_id: str
    template_id: Optional[str]
    name: str
    description: Optional[str]
    criteria_spec: dict
    schedule_enabled: bool
    schedule_cron: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class CriteriaListResponse(BaseModel):
    """Paginated list of screening criteria"""
    criteria: List[CriteriaResponse]
    total: int
    page: int
    limit: int
    total_pages: int


class TemplateResponse(BaseModel):
    """Response containing template details"""
    id: str
    name: str
    description: Optional[str]
    criteria_spec: dict
    created_at: datetime
    
    class Config:
        from_attributes = True


class CloneTemplateResponse(BaseModel):
    """Response after cloning a template"""
    success: bool
    message: str
    criteria_id: str
    criteria: CriteriaResponse


# ============================================================================
# Helper Functions
# ============================================================================

async def check_criteria_ownership(
    criteria_id: str,
    user_id: str,
    session: AsyncSession
) -> DBScreeningCriteria:
    """
    Check if criteria exists and belongs to user
    
    Args:
        criteria_id: Criteria UUID
        user_id: User UUID
        session: Database session
        
    Returns:
        ScreeningCriteria object if found and owned by user
        
    Raises:
        HTTPException: If criteria not found or not owned by user
    """
    result = await session.execute(
        select(DBScreeningCriteria).where(
            and_(
                DBScreeningCriteria.id == uuid.UUID(criteria_id),
                DBScreeningCriteria.user_id == uuid.UUID(user_id)
            )
        )
    )
    criteria = result.scalar_one_or_none()
    
    if not criteria:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Screening criteria not found or access denied"
        )
    
    return criteria


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/criteria", response_model=CriteriaResponse, status_code=status.HTTP_201_CREATED)
async def create_criteria(
    request: CreateCriteriaRequest,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db)
) -> CriteriaResponse:
    """
    Create new screening criteria
    
    Validates the criteria specification and stores it in the database.
    
    Requirements: 9.4, 10.1
    
    Args:
        request: Criteria creation request
        user_id: Current authenticated user ID
        session: Database session
        
    Returns:
        Created criteria with generated ID
        
    Raises:
        HTTPException 422: If criteria validation fails
        HTTPException 500: If database operation fails
    """
    try:
        # Validate criteria using Pydantic model (already done by request model)
        criteria = request.criteria
        
        # Generate new criteria ID
        criteria_id = uuid.uuid4()
        
        # Convert criteria to dict
        criteria_dict = criteria.model_dump()
        
        # Create criteria record
        now = datetime.utcnow()
        db_criteria = DBScreeningCriteria(
            id=criteria_id,
            user_id=uuid.UUID(user_id),
            template_id=None,
            name=criteria.name,
            description=criteria.description,
            criteria_spec=criteria_dict,
            schedule_enabled=request.schedule_enabled,
            schedule_cron=request.schedule_cron,
            is_active=True,
            created_at=now,
            updated_at=now
        )
        
        session.add(db_criteria)
        await session.commit()
        await session.refresh(db_criteria)
        
        logger.info(
            f"Screening criteria created",
            extra={
                "criteria_id": str(db_criteria.id),
                "user_id": user_id,
                "name": db_criteria.name,
                "asset_classes": criteria.asset_class
            }
        )
        
        return CriteriaResponse(
            id=str(db_criteria.id),
            user_id=str(db_criteria.user_id),
            template_id=str(db_criteria.template_id) if db_criteria.template_id else None,
            name=db_criteria.name,
            description=db_criteria.description,
            criteria_spec=db_criteria.criteria_spec,
            schedule_enabled=db_criteria.schedule_enabled,
            schedule_cron=db_criteria.schedule_cron,
            is_active=db_criteria.is_active,
            created_at=db_criteria.created_at,
            updated_at=db_criteria.updated_at
        )
        
    except ValueError as e:
        logger.error(f"Criteria validation failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Criteria validation failed: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Failed to create criteria: {str(e)}")
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create criteria: {str(e)}"
        )


@router.get("/criteria", response_model=CriteriaListResponse)
async def list_criteria(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=100, description="Items per page"),
    active_only: bool = Query(True, description="Show only active criteria"),
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db)
) -> CriteriaListResponse:
    """
    Get paginated list of user's screening criteria
    
    Requirements: 10.2
    
    Args:
        page: Page number (1-indexed)
        limit: Number of items per page
        active_only: Filter for active criteria only
        user_id: Current authenticated user ID
        session: Database session
        
    Returns:
        Paginated list of screening criteria
    """
    try:
        # Build query
        query = select(DBScreeningCriteria).where(DBScreeningCriteria.user_id == uuid.UUID(user_id))
        
        # Apply active filter if requested
        if active_only:
            query = query.where(DBScreeningCriteria.is_active == True)
        
        # Order by created_at descending
        query = query.order_by(DBScreeningCriteria.created_at.desc())
        
        # Get total count
        count_query = select(DBScreeningCriteria).where(DBScreeningCriteria.user_id == uuid.UUID(user_id))
        if active_only:
            count_query = count_query.where(DBScreeningCriteria.is_active == True)
        
        count_result = await session.execute(count_query)
        total = len(count_result.scalars().all())
        
        # Apply pagination
        offset = (page - 1) * limit
        query = query.offset(offset).limit(limit)
        
        # Execute query
        result = await session.execute(query)
        criteria_list = result.scalars().all()
        
        # Convert to response models
        criteria_responses = [
            CriteriaResponse(
                id=str(c.id),
                user_id=str(c.user_id),
                template_id=str(c.template_id) if c.template_id else None,
                name=c.name,
                description=c.description,
                criteria_spec=c.criteria_spec,
                schedule_enabled=c.schedule_enabled,
                schedule_cron=c.schedule_cron,
                is_active=c.is_active,
                created_at=c.created_at,
                updated_at=c.updated_at
            )
            for c in criteria_list
        ]
        
        total_pages = (total + limit - 1) // limit
        
        return CriteriaListResponse(
            criteria=criteria_responses,
            total=total,
            page=page,
            limit=limit,
            total_pages=total_pages
        )
        
    except Exception as e:
        logger.error(f"Failed to list criteria: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list criteria: {str(e)}"
        )


@router.get("/criteria/{criteria_id}", response_model=CriteriaResponse)
async def get_criteria(
    criteria_id: str,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db)
) -> CriteriaResponse:
    """
    Get full screening criteria details by ID
    
    Requirements: 10.2
    
    Args:
        criteria_id: Criteria UUID
        user_id: Current authenticated user ID
        session: Database session
        
    Returns:
        Full criteria details
        
    Raises:
        HTTPException 404: If criteria not found or access denied
    """
    try:
        criteria = await check_criteria_ownership(criteria_id, user_id, session)
        
        return CriteriaResponse(
            id=str(criteria.id),
            user_id=str(criteria.user_id),
            template_id=str(criteria.template_id) if criteria.template_id else None,
            name=criteria.name,
            description=criteria.description,
            criteria_spec=criteria.criteria_spec,
            schedule_enabled=criteria.schedule_enabled,
            schedule_cron=criteria.schedule_cron,
            is_active=criteria.is_active,
            created_at=criteria.created_at,
            updated_at=criteria.updated_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get criteria: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get criteria: {str(e)}"
        )


@router.put("/criteria/{criteria_id}", response_model=CriteriaResponse)
async def update_criteria(
    criteria_id: str,
    request: UpdateCriteriaRequest,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db)
) -> CriteriaResponse:
    """
    Update existing screening criteria
    
    Validates new criteria and updates database.
    
    Requirements: 10.3
    
    Args:
        criteria_id: Criteria UUID
        request: Update request with new criteria
        user_id: Current authenticated user ID
        session: Database session
        
    Returns:
        Updated criteria
        
    Raises:
        HTTPException 404: If criteria not found or access denied
        HTTPException 422: If new criteria validation fails
    """
    try:
        # Check ownership
        db_criteria = await check_criteria_ownership(criteria_id, user_id, session)
        
        # Validate new criteria
        new_criteria = request.criteria
        
        # Convert to dict
        criteria_dict = new_criteria.model_dump()
        
        # Update criteria
        db_criteria.name = new_criteria.name
        db_criteria.description = new_criteria.description
        db_criteria.criteria_spec = criteria_dict
        db_criteria.updated_at = datetime.utcnow()
        
        # Update scheduling if provided
        if request.schedule_enabled is not None:
            db_criteria.schedule_enabled = request.schedule_enabled
        if request.schedule_cron is not None:
            db_criteria.schedule_cron = request.schedule_cron
        
        await session.commit()
        await session.refresh(db_criteria)
        
        logger.info(
            f"Screening criteria updated",
            extra={
                "criteria_id": criteria_id,
                "user_id": user_id,
                "name": db_criteria.name
            }
        )
        
        return CriteriaResponse(
            id=str(db_criteria.id),
            user_id=str(db_criteria.user_id),
            template_id=str(db_criteria.template_id) if db_criteria.template_id else None,
            name=db_criteria.name,
            description=db_criteria.description,
            criteria_spec=db_criteria.criteria_spec,
            schedule_enabled=db_criteria.schedule_enabled,
            schedule_cron=db_criteria.schedule_cron,
            is_active=db_criteria.is_active,
            created_at=db_criteria.created_at,
            updated_at=db_criteria.updated_at
        )
        
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Criteria validation failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Criteria validation failed: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Failed to update criteria: {str(e)}")
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update criteria: {str(e)}"
        )


@router.delete("/criteria/{criteria_id}", status_code=status.HTTP_200_OK)
async def delete_criteria(
    criteria_id: str,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db)
) -> dict:
    """
    Delete screening criteria
    
    Soft delete by setting is_active to False.
    
    Requirements: 10.4
    
    Args:
        criteria_id: Criteria UUID
        user_id: Current authenticated user ID
        session: Database session
        
    Returns:
        Success message
        
    Raises:
        HTTPException 404: If criteria not found or access denied
    """
    try:
        # Check ownership
        db_criteria = await check_criteria_ownership(criteria_id, user_id, session)
        
        # Soft delete: set is_active to False
        db_criteria.is_active = False
        db_criteria.updated_at = datetime.utcnow()
        
        await session.commit()
        
        logger.info(
            f"Screening criteria deleted",
            extra={
                "criteria_id": criteria_id,
                "user_id": user_id,
                "name": db_criteria.name
            }
        )
        
        return {
            "success": True,
            "message": f"Screening criteria '{db_criteria.name}' deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete criteria: {str(e)}")
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete criteria: {str(e)}"
        )


@router.get("/templates", response_model=List[TemplateResponse])
async def get_templates(
    session: AsyncSession = Depends(get_db)
) -> List[TemplateResponse]:
    """
    Get all screening templates
    
    Returns pre-built screening templates from seed data.
    
    Requirements: 10.1, 10.2
    
    Args:
        session: Database session
        
    Returns:
        List of all screening templates
    """
    try:
        # Templates are stored with system user_id = 00000000-0000-0000-0000-000000000000
        system_user_id = uuid.UUID("00000000-0000-0000-0000-000000000000")
        
        result = await session.execute(
            select(DBScreeningCriteria).where(DBScreeningCriteria.user_id == system_user_id)
        )
        templates = result.scalars().all()
        
        template_responses = [
            TemplateResponse(
                id=str(t.id),
                name=t.name,
                description=t.description,
                criteria_spec=t.criteria_spec,
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
    Clone a template to user's criteria
    
    Creates new screening criteria from the template spec.
    
    Requirements: 10.4
    
    Args:
        template_id: Template UUID
        user_id: Current authenticated user ID
        session: Database session
        
    Returns:
        Cloned criteria with new ID
        
    Raises:
        HTTPException 404: If template not found
    """
    try:
        # Get template
        result = await session.execute(
            select(DBScreeningCriteria).where(DBScreeningCriteria.id == uuid.UUID(template_id))
        )
        template = result.scalar_one_or_none()
        
        if not template:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Template not found: {template_id}"
            )
        
        # Generate new criteria ID
        new_criteria_id = uuid.uuid4()
        
        # Clone spec
        cloned_spec = template.criteria_spec.copy()
        
        # Update name
        cloned_name = f"{template.name} (Copy)"
        
        # Create new criteria
        now = datetime.utcnow()
        new_criteria = DBScreeningCriteria(
            id=new_criteria_id,
            user_id=uuid.UUID(user_id),
            template_id=template.id,  # Track which template this was cloned from
            name=cloned_name,
            description=template.description,
            criteria_spec=cloned_spec,
            schedule_enabled=False,
            schedule_cron=None,
            is_active=True,
            created_at=now,
            updated_at=now
        )
        
        session.add(new_criteria)
        await session.commit()
        await session.refresh(new_criteria)
        
        logger.info(
            f"Template cloned",
            extra={
                "template_id": template_id,
                "new_criteria_id": str(new_criteria_id),
                "user_id": user_id,
                "template_name": template.name
            }
        )
        
        criteria_response = CriteriaResponse(
            id=str(new_criteria.id),
            user_id=str(new_criteria.user_id),
            template_id=str(new_criteria.template_id) if new_criteria.template_id else None,
            name=new_criteria.name,
            description=new_criteria.description,
            criteria_spec=new_criteria.criteria_spec,
            schedule_enabled=new_criteria.schedule_enabled,
            schedule_cron=new_criteria.schedule_cron,
            is_active=new_criteria.is_active,
            created_at=new_criteria.created_at,
            updated_at=new_criteria.updated_at
        )
        
        return CloneTemplateResponse(
            success=True,
            message=f"Template '{template.name}' cloned successfully",
            criteria_id=str(new_criteria_id),
            criteria=criteria_response
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
# Screening Execution Endpoints
# ============================================================================

class RunScreeningRequest(BaseModel):
    """Request to run on-demand screening"""
    criteria_id: str = Field(..., description="UUID of screening criteria to run")
    universe: Optional[List[str]] = Field(None, description="Optional list of symbols to screen")
    
    class Config:
        json_schema_extra = {
            "example": {
                "criteria_id": "550e8400-e29b-41d4-a716-446655440000",
                "universe": ["RELIANCE", "TCS", "INFY", "HDFC", "ICICIBANK"]
            }
        }


class RunScreeningResponse(BaseModel):
    """Response after enqueuing screening task"""
    success: bool
    message: str
    task_id: str
    criteria_id: str
    criteria_name: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Screening task enqueued successfully",
                "task_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "criteria_id": "550e8400-e29b-41d4-a716-446655440000",
                "criteria_name": "Oversold Reversal Scanner"
            }
        }


class ScreeningResultResponse(BaseModel):
    """Response containing screening results"""
    screening_id: str
    criteria_id: str
    criteria_name: str
    run_at: datetime
    duration_seconds: float
    instruments_scanned: int
    instruments_passed: int
    results: List[ScreenedInstrument]
    
    class Config:
        from_attributes = True


class ScreeningHistoryResponse(BaseModel):
    """Paginated screening history"""
    history: List[ScreeningResultResponse]
    total: int
    page: int
    limit: int
    total_pages: int


@router.post("/run", response_model=RunScreeningResponse, status_code=status.HTTP_202_ACCEPTED)
async def run_screening(
    request: RunScreeningRequest,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db)
) -> RunScreeningResponse:
    """
    Run on-demand screening
    
    Enqueues a Celery task to run the screening asynchronously.
    Returns immediately with a task_id that can be used to poll for results.
    
    Requirements: 9.5
    
    Args:
        request: Screening run request with criteria_id and optional universe
        user_id: Current authenticated user ID
        session: Database session
        
    Returns:
        Task ID and criteria info
        
    Raises:
        HTTPException 404: If criteria not found or access denied
        HTTPException 500: If task enqueue fails
    """
    try:
        # Check criteria ownership
        criteria = await check_criteria_ownership(request.criteria_id, user_id, session)
        
        # Import Celery task
        from services.screening.tasks import run_screening_task
        
        # Enqueue task
        task = run_screening_task.delay(request.criteria_id, request.universe)
        
        logger.info(
            f"Screening task enqueued",
            extra={
                "task_id": task.id,
                "criteria_id": request.criteria_id,
                "user_id": user_id,
                "criteria_name": criteria.name
            }
        )
        
        return RunScreeningResponse(
            success=True,
            message="Screening task enqueued successfully",
            task_id=task.id,
            criteria_id=request.criteria_id,
            criteria_name=criteria.name
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to enqueue screening task: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to enqueue screening task: {str(e)}"
        )


@router.get("/{criteria_id}/results", response_model=ScreeningResultResponse)
async def get_latest_results(
    criteria_id: str,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db)
) -> ScreeningResultResponse:
    """
    Get latest screening results for a criteria
    
    Returns the most recent screening result for the given criteria.
    
    Requirements: 9.6
    
    Args:
        criteria_id: Criteria UUID
        user_id: Current authenticated user ID
        session: Database session
        
    Returns:
        Latest screening result
        
    Raises:
        HTTPException 404: If criteria not found or no results available
    """
    try:
        # Check criteria ownership
        criteria = await check_criteria_ownership(criteria_id, user_id, session)
        
        # Fetch latest result
        result = await session.execute(
            select(DBScreeningResult)
            .where(DBScreeningResult.criteria_id == uuid.UUID(criteria_id))
            .order_by(desc(DBScreeningResult.run_at))
            .limit(1)
        )
        latest_result = result.scalar_one_or_none()
        
        if not latest_result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No screening results found for criteria: {criteria_id}"
            )
        
        # Parse results JSON
        results_data = latest_result.results.get("results", []) if latest_result.results else []
        screened_instruments = [ScreenedInstrument(**inst) for inst in results_data]
        
        return ScreeningResultResponse(
            screening_id=str(latest_result.id),
            criteria_id=str(latest_result.criteria_id),
            criteria_name=criteria.name,
            run_at=latest_result.run_at,
            duration_seconds=latest_result.duration_seconds,
            instruments_scanned=latest_result.instruments_scanned,
            instruments_passed=latest_result.instruments_passed,
            results=screened_instruments
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get latest results: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get latest results: {str(e)}"
        )


@router.get("/{criteria_id}/history", response_model=ScreeningHistoryResponse)
async def get_screening_history(
    criteria_id: str,
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=100, description="Items per page"),
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db)
) -> ScreeningHistoryResponse:
    """
    Get screening history for a criteria (last 7 days)
    
    Returns paginated list of screening results for the given criteria,
    limited to the last 7 days.
    
    Requirements: 9.7
    
    Args:
        criteria_id: Criteria UUID
        page: Page number (1-indexed)
        limit: Number of items per page
        user_id: Current authenticated user ID
        session: Database session
        
    Returns:
        Paginated screening history
        
    Raises:
        HTTPException 404: If criteria not found or access denied
    """
    try:
        # Check criteria ownership
        criteria = await check_criteria_ownership(criteria_id, user_id, session)
        
        # Calculate 7 days ago
        from datetime import timedelta
        seven_days_ago = datetime.utcnow() - timedelta(days=7)
        
        # Build query
        query = select(DBScreeningResult).where(
            and_(
                DBScreeningResult.criteria_id == uuid.UUID(criteria_id),
                DBScreeningResult.run_at >= seven_days_ago
            )
        ).order_by(desc(DBScreeningResult.run_at))
        
        # Get total count
        count_result = await session.execute(query)
        total = len(count_result.scalars().all())
        
        # Apply pagination
        offset = (page - 1) * limit
        query = query.offset(offset).limit(limit)
        
        # Execute query
        result = await session.execute(query)
        history_records = result.scalars().all()
        
        # Convert to response models
        history_responses = []
        for record in history_records:
            results_data = record.results.get("results", []) if record.results else []
            screened_instruments = [ScreenedInstrument(**inst) for inst in results_data]
            
            history_responses.append(
                ScreeningResultResponse(
                    screening_id=str(record.id),
                    criteria_id=str(record.criteria_id),
                    criteria_name=criteria.name,
                    run_at=record.run_at,
                    duration_seconds=record.duration_seconds,
                    instruments_scanned=record.instruments_scanned,
                    instruments_passed=record.instruments_passed,
                    results=screened_instruments
                )
            )
        
        total_pages = (total + limit - 1) // limit
        
        return ScreeningHistoryResponse(
            history=history_responses,
            total=total,
            page=page,
            limit=limit,
            total_pages=total_pages
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get screening history: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get screening history: {str(e)}"
        )
