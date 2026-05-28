"""
Python Strategy Host API Router
Handles Python code editor, templates, persistence, and execution

Requirements: 13.1, 13.2, 13.3, 13.4, 13.11, 22.1, 22.2, 22.3, 37.1, 37.2
"""
from fastapi import APIRouter, HTTPException, Depends, status, BackgroundTasks
from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any, Literal
from datetime import datetime
import uuid
import json
import logging
import base64
import hashlib

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete as sql_delete, desc, and_
from sqlalchemy.dialects.postgresql import insert

from services.algo_builder.redis_client import get_redis_client
from shared.database.models import Strategy
from services.algo_builder.router import get_db, get_current_user_id
from services.algo_builder.sandbox import SandboxRunner, ValidationResult

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/algo/python", tags=["python_strategy_host"])

# ============================================================================
# Pydantic Models
# ============================================================================

class PythonCodeTemplate(BaseModel):
    """Python code template"""
    id: str
    name: str
    description: str
    category: Literal["strategy", "indicator", "condition", "action", "risk", "utility"]
    code: str
    imports: List[str] = Field(default_factory=list)
    parameters: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    usage_count: int = 0


class CodeVersion(BaseModel):
    """Code version history entry"""
    version_id: str
    code: str
    code_hash: str
    created_at: datetime
    created_by: str
    commit_message: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class PythonStrategy(BaseModel):
    """Python strategy model"""
    strategy_id: str
    user_id: str
    name: str
    description: Optional[str] = None
    code: str
    code_hash: str
    imports: List[str] = Field(default_factory=list)
    status: Literal["draft", "testing", "paper", "live", "archived"] = "draft"
    current_version: int = 1
    created_at: datetime
    updated_at: datetime


class CreatePythonStrategyRequest(BaseModel):
    """Request to create a new Python strategy"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    code: str
    template_id: Optional[str] = None
    
    @validator('code')
    def validate_code_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("Code cannot be empty")
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "RSI Strategy",
                "description": "Simple RSI-based mean reversion",
                "code": """
from signalixai_sdk import Strategy, on_bar

class MyStrategy(Strategy):
    def __init__(self):
        super().__init__()
        self.rsi_period = 14
        self.oversold = 30
        self.overbought = 70
    
    @on_bar
    def on_bar(self, data):
        rsi = self.indicators.rsi(self.rsi_period)
        if rsi < self.oversold:
            self.buy()
        elif rsi > self.overbought:
            self.sell()
""",
                "template_id": "rsi_strategy"
            }
        }


class UpdatePythonStrategyRequest(BaseModel):
    """Request to update Python strategy"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    code: Optional[str] = None
    commit_message: Optional[str] = None
    auto_save: bool = False


class SyntaxValidationRequest(BaseModel):
    """Request for syntax validation"""
    code: str


class SyntaxValidationResponse(BaseModel):
    """Response from syntax validation"""
    valid: bool
    errors: List[Dict[str, Any]] = Field(default_factory=list)
    warnings: List[Dict[str, Any]] = Field(default_factory=list)
    imports: List[str] = Field(default_factory=list)
    has_strategy_class: bool = False
    has_on_bar_handler: bool = False


class ExecuteCodeRequest(BaseModel):
    """Request to execute code in sandbox"""
    code: str
    market_data: Optional[Dict[str, Any]] = None
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    memory_limit_mb: int = Field(default=512, ge=128, le=2048)


class ExecuteCodeResponse(BaseModel):
    """Response from code execution"""
    success: bool
    output: str
    errors: Optional[str] = None
    execution_time_ms: float
    memory_used_mb: float
    signals: List[Dict[str, Any]] = Field(default_factory=list)
    logs: List[str] = Field(default_factory=list)


class CodeTemplateListResponse(BaseModel):
    """Response with list of templates"""
    templates: List[PythonCodeTemplate]
    total: int
    categories: List[str]


class VersionHistoryRequest(BaseModel):
    """Request to get version history"""
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class VersionHistoryResponse(BaseModel):
    """Response with version history"""
    strategy_id: str
    current_version: int
    versions: List[CodeVersion]
    total_versions: int


class RevertVersionRequest(BaseModel):
    """Request to revert to a version"""
    version_id: str
    confirm: bool = False


class DiffResponse(BaseModel):
    """Response with code diff"""
    version_id_1: str
    version_id_2: str
    diff: str
    added_lines: int
    removed_lines: int
    changed_lines: int


# ============================================================================
# Built-in Templates
# ============================================================================

BUILTIN_TEMPLATES = [
    PythonCodeTemplate(
        id="strategy_base",
        name="Strategy Base Class",
        description="Basic strategy structure with on_bar handler",
        category="strategy",
        code='''from signalixai_sdk import Strategy, on_bar, on_tick

class MyStrategy(Strategy):
    def __init__(self):
        super().__init__()
        # Initialize your parameters here
        self.entry_threshold = 30
        self.exit_threshold = 70
    
    @on_bar
    def on_bar(self, data):
        """Called on every new bar"""
        # Your strategy logic here
        pass
    
    @on_tick
    def on_tick(self, tick):
        """Called on every tick (optional)"""
        pass
''',
        imports=["signalixai_sdk"],
        parameters={"entry_threshold": 30, "exit_threshold": 70}
    ),
    PythonCodeTemplate(
        id="rsi_strategy",
        name="RSI Mean Reversion",
        description="Buy when RSI is oversold, sell when overbought",
        category="strategy",
        code='''from signalixai_sdk import Strategy, on_bar

class RSIStrategy(Strategy):
    def __init__(self):
        super().__init__()
        self.rsi_period = 14
        self.oversold = 30
        self.overbought = 70
    
    @on_bar
    def on_bar(self, data):
        rsi = self.indicators.rsi(self.rsi_period)
        
        if rsi < self.oversold:
            self.buy(qty=1)
        elif rsi > self.overbought:
            self.sell(qty=1)
''',
        imports=["signalixai_sdk"],
        parameters={"rsi_period": 14, "oversold": 30, "overbought": 70}
    ),
    PythonCodeTemplate(
        id="ema_crossover",
        name="EMA Crossover",
        description="Buy when fast EMA crosses above slow EMA",
        category="strategy",
        code='''from signalixai_sdk import Strategy, on_bar

class EMACrossoverStrategy(Strategy):
    def __init__(self):
        super().__init__()
        self.fast_ema = 9
        self.slow_ema = 21
        self.in_position = False
    
    @on_bar
    def on_bar(self, data):
        fast = self.indicators.ema(self.fast_ema)
        slow = self.indicators.ema(self.slow_ema)
        
        if fast > slow and not self.in_position:
            self.buy(qty=1)
            self.in_position = True
        elif fast < slow and self.in_position:
            self.sell(qty=1)
            self.in_position = False
''',
        imports=["signalixai_sdk"],
        parameters={"fast_ema": 9, "slow_ema": 21}
    ),
    PythonCodeTemplate(
        id="bollinger_breakout",
        name="Bollinger Bands Breakout",
        description="Trade breakouts from Bollinger Bands",
        category="strategy",
        code='''from signalixai_sdk import Strategy, on_bar

class BollingerBreakoutStrategy(Strategy):
    def __init__(self):
        super().__init__()
        self.period = 20
        self.std_dev = 2
    
    @on_bar
    def on_bar(self, data):
        upper, middle, lower = self.indicators.bollinger_bands(
            self.period, self.std_dev
        )
        close = data.close
        
        if close > upper:
            self.buy(qty=1)
        elif close < lower:
            self.sell(qty=1)
''',
        imports=["signalixai_sdk"],
        parameters={"period": 20, "std_dev": 2}
    ),
    PythonCodeTemplate(
        id="atr_stop_loss",
        name="ATR-based Stop Loss",
        description="Dynamic stop loss based on ATR",
        category="risk",
        code='''from signalixai_sdk import Strategy, on_bar

class ATRStopLossStrategy(Strategy):
    def __init__(self):
        super().__init__()
        self.atr_period = 14
        self.atr_multiplier = 2
        self.position = None
        self.stop_price = None
    
    @on_bar
    def on_bar(self, data):
        atr = self.indicators.atr(self.atr_period)
        
        if self.position == "long":
            self.stop_price = data.close - (atr * self.atr_multiplier)
            if data.low <= self.stop_price:
                self.sell(qty=1)
                self.position = None
        
        # Entry logic
        if self.position is None and self.indicators.rsi(14) < 30:
            self.buy(qty=1)
            self.position = "long"
            self.stop_price = data.close - (atr * self.atr_multiplier)
''',
        imports=["signalixai_sdk"],
        parameters={"atr_period": 14, "atr_multiplier": 2}
    ),
]


# ============================================================================
# Helper Functions
# ============================================================================

def compute_code_hash(code: str) -> str:
    """Compute SHA-256 hash of code for versioning"""
    return hashlib.sha256(code.encode()).hexdigest()

def extract_imports(code: str) -> List[str]:
    """Extract import statements from code"""
    imports = []
    for line in code.split('\n'):
        line = line.strip()
        if line.startswith('import ') or line.startswith('from '):
            imports.append(line)
    return imports

def validate_syntax(code: str) -> SyntaxValidationResponse:
    """Validate Python syntax without executing"""
    import ast
    
    errors = []
    warnings = []
    
    try:
        ast.parse(code)
        valid = True
    except SyntaxError as e:
        valid = False
        errors.append({
            "type": "syntax_error",
            "line": e.lineno,
            "message": str(e)
        })
    except Exception as e:
        valid = False
        errors.append({
            "type": "parse_error",
            "message": str(e)
        })
    
    # Check for strategy class
    has_strategy_class = "class" in code and "Strategy" in code
    has_on_bar_handler = "@on_bar" in code or "def on_bar" in code
    
    # Check for restricted imports
    restricted_modules = ['os', 'sys', 'subprocess', 'socket', 'requests']
    imports = extract_imports(code)
    for imp in imports:
        for restricted in restricted_modules:
            if restricted in imp:
                warnings.append({
                    "type": "restricted_import",
                    "message": f"Import of '{restricted}' may be restricted in sandbox"
                })
    
    return SyntaxValidationResponse(
        valid=valid,
        errors=errors,
        warnings=warnings,
        imports=imports,
        has_strategy_class=has_strategy_class,
        has_on_bar_handler=has_on_bar_handler
    )


# ============================================================================
# Template Endpoints
# ============================================================================

@router.get("/templates", response_model=CodeTemplateListResponse)
async def list_templates(
    category: Optional[str] = None,
    search: Optional[str] = None
):
    """
    List available code templates
    
    Requirements: 13.4, 14.1, 14.2
    """
    templates = BUILTIN_TEMPLATES
    
    if category:
        templates = [t for t in templates if t.category == category]
    
    if search:
        search_lower = search.lower()
        templates = [
            t for t in templates 
            if search_lower in t.name.lower() or search_lower in t.description.lower()
        ]
    
    categories = list(set(t.category for t in BUILTIN_TEMPLATES))
    
    return CodeTemplateListResponse(
        templates=templates,
        total=len(templates),
        categories=categories
    )


@router.get("/templates/{template_id}", response_model=PythonCodeTemplate)
async def get_template(template_id: str):
    """Get a specific template by ID"""
    for template in BUILTIN_TEMPLATES:
        if template.id == template_id:
            return template
    
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Template not found"
    )


# ============================================================================
# Strategy CRUD
# ============================================================================

@router.post("/strategies", response_model=PythonStrategy, status_code=status.HTTP_201_CREATED)
async def create_python_strategy(
    request: CreatePythonStrategyRequest,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db)
):
    """
    Create a new Python strategy
    
    Requirements: 13.11, 54.1, 54.2
    """
    try:
        # Validate syntax
        validation = validate_syntax(request.code)
        if not validation.valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "Syntax validation failed",
                    "errors": validation.errors
                }
            )
        
        strategy_id = str(uuid.uuid4())
        now = datetime.utcnow()
        code_hash = compute_code_hash(request.code)
        imports = extract_imports(request.code)
        
        # If using template, prepend template code
        code = request.code
        if request.template_id:
            template = next((t for t in BUILTIN_TEMPLATES if t.id == request.template_id), None)
            if template:
                code = f"# Based on template: {template.name}\n\n{code}"
        
        strategy = Strategy(
            id=uuid.UUID(strategy_id),
            user_id=uuid.UUID(user_id),
            name=request.name,
            description=request.description,
            spec={
                "type": "python_strategy",
                "code": code,
                "code_hash": code_hash,
                "imports": imports,
                "template_id": request.template_id
            },
            status="draft",
            created_at=now,
            updated_at=now
        )
        
        session.add(strategy)
        await session.commit()
        
        logger.info(
            f"Created Python strategy",
            extra={"strategy_id": strategy_id, "user_id": user_id, "name": request.name}
        )
        
        return PythonStrategy(
            strategy_id=strategy_id,
            user_id=user_id,
            name=request.name,
            description=request.description,
            code=code,
            code_hash=code_hash,
            imports=imports,
            status="draft",
            current_version=1,
            created_at=now,
            updated_at=now
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create Python strategy: {str(e)}")
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create Python strategy: {str(e)}"
        )


@router.get("/strategies/{strategy_id}", response_model=PythonStrategy)
async def get_python_strategy(
    strategy_id: str,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db)
):
    """Get Python strategy by ID"""
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
        
        spec = strategy.spec or {}
        
        return PythonStrategy(
            strategy_id=str(strategy.id),
            user_id=str(strategy.user_id),
            name=strategy.name,
            description=strategy.description,
            code=spec.get("code", ""),
            code_hash=spec.get("code_hash", ""),
            imports=spec.get("imports", []),
            status=strategy.status.value if hasattr(strategy.status, 'value') else strategy.status,
            current_version=spec.get("version", 1),
            created_at=strategy.created_at,
            updated_at=strategy.updated_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get Python strategy: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get Python strategy: {str(e)}"
        )


@router.put("/strategies/{strategy_id}", response_model=PythonStrategy)
async def update_python_strategy(
    strategy_id: str,
    request: UpdatePythonStrategyRequest,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db)
):
    """
    Update Python strategy code
    
    Requirements: 13.11, 54.3, 54.4
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
        
        spec = strategy.spec or {}
        
        # Update fields
        if request.name:
            strategy.name = request.name
        if request.description is not None:
            strategy.description = request.description
        
        # Update code if provided
        if request.code:
            validation = validate_syntax(request.code)
            if not validation.valid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "error": "Syntax validation failed",
                        "errors": validation.errors
                    }
                )
            
            spec["code"] = request.code
            spec["code_hash"] = compute_code_hash(request.code)
            spec["imports"] = extract_imports(request.code)
            spec["version"] = spec.get("version", 1) + 1
            
            # Store previous version in Redis
            if not request.auto_save:
                redis = get_redis_client()
                version_key = f"python_strategy:version:{strategy_id}:{spec['version']}"
                version_data = {
                    "code": request.code,
                    "created_at": datetime.utcnow().isoformat(),
                    "created_by": user_id,
                    "commit_message": request.commit_message or "Code update",
                    "tags": []
                }
                redis.setex(version_key, 86400 * 90, json.dumps(version_data))  # 90 days TTL
        
        strategy.spec = spec
        strategy.updated_at = datetime.utcnow()
        
        await session.commit()
        
        return PythonStrategy(
            strategy_id=str(strategy.id),
            user_id=str(strategy.user_id),
            name=strategy.name,
            description=strategy.description,
            code=spec.get("code", ""),
            code_hash=spec.get("code_hash", ""),
            imports=spec.get("imports", []),
            status=strategy.status.value if hasattr(strategy.status, 'value') else strategy.status,
            current_version=spec.get("version", 1),
            created_at=strategy.created_at,
            updated_at=strategy.updated_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update Python strategy: {str(e)}")
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update Python strategy: {str(e)}"
        )


# ============================================================================
# Syntax Validation
# ============================================================================

@router.post("/validate-syntax", response_model=SyntaxValidationResponse)
async def validate_code_syntax(request: SyntaxValidationRequest):
    """
    Validate Python code syntax without executing
    
    Requirements: 13.3, 22.1
    """
    return validate_syntax(request.code)


# ============================================================================
# Code Execution (Sandbox)
# ============================================================================

@router.post("/execute", response_model=ExecuteCodeResponse)
async def execute_code(
    request: ExecuteCodeRequest,
    user_id: str = Depends(get_current_user_id)
):
    """
    Execute Python code in sandbox environment
    
    Requirements: 13.5, 13.6, 13.8, 23.1, 23.2, 23.6
    """
    try:
        # First validate syntax
        validation = validate_syntax(request.code)
        if not validation.valid:
            return ExecuteCodeResponse(
                success=False,
                output="",
                errors=f"Syntax errors: {validation.errors}",
                execution_time_ms=0,
                memory_used_mb=0,
                signals=[],
                logs=[]
            )
        
        # Run in sandbox
        runner = SandboxRunner()
        
        import time
        start_time = time.time()
        
        # Execute code
        result = runner.execute(
            code=request.code,
            timeout=request.timeout_seconds,
            memory_limit=request.memory_limit_mb
        )
        
        execution_time_ms = (time.time() - start_time) * 1000
        
        return ExecuteCodeResponse(
            success=result.success,
            output=result.output or "",
            errors=result.errors,
            execution_time_ms=execution_time_ms,
            memory_used_mb=result.memory_used or 0,
            signals=result.signals or [],
            logs=result.logs or []
        )
        
    except Exception as e:
        logger.error(f"Failed to execute code: {str(e)}")
        return ExecuteCodeResponse(
            success=False,
            output="",
            errors=str(e),
            execution_time_ms=0,
            memory_used_mb=0,
            signals=[],
            logs=[]
        )


# ============================================================================
# Health Check
# ============================================================================

@router.get("/health")
async def health_check():
    """Health check endpoint for Python strategy host"""
    return {
        "status": "healthy",
        "service": "python_strategy_host",
        "version": "1.0.0",
        "templates_available": len(BUILTIN_TEMPLATES)
    }
