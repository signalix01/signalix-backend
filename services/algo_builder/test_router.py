"""
Integration tests for Strategy CRUD API

Requirements: 1.8, 1.9, 2.4, 2.5
"""
import pytest
import uuid
from datetime import datetime
from httpx import AsyncClient
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select

from services.algo_builder.router import router, get_db, get_current_user_id
from services.algo_builder.models import StrategySpec
from shared.database.models import Base, Strategy

# Test database URL (use in-memory SQLite for tests)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

# Test user ID
TEST_USER_ID = "00000000-0000-0000-0000-000000000001"
SYSTEM_USER_ID = "00000000-0000-0000-0000-000000000000"


@pytest.fixture
async def test_engine():
    """Create test database engine"""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    # Drop all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()


@pytest.fixture
async def test_session(test_engine):
    """Create test database session"""
    async_session = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    
    async with async_session() as session:
        yield session


@pytest.fixture
async def test_app(test_session):
    """Create test FastAPI app"""
    app = FastAPI()
    app.include_router(router)
    
    # Override dependencies
    async def override_get_db():
        yield test_session
    
    async def override_get_current_user_id():
        return TEST_USER_ID
    
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_id] = override_get_current_user_id
    
    return app


@pytest.fixture
async def client(test_app):
    """Create test HTTP client"""
    async with AsyncClient(app=test_app, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def sample_strategy_spec():
    """Sample strategy specification"""
    return {
        "strategy_id": "test_strategy_001",
        "user_id": TEST_USER_ID,
        "name": "Test RSI Strategy",
        "description": "A simple RSI oversold strategy for testing",
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
            },
            {
                "exit_type": "stop_loss",
                "stop_loss_pct": 2.0
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
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat()
    }


@pytest.fixture
async def sample_template(test_session):
    """Create a sample template in the database"""
    template_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    
    template_spec = {
        "strategy_id": "turtle_breakout_template",
        "user_id": SYSTEM_USER_ID,
        "name": "Turtle Breakout (Richard Dennis)",
        "description": "20-day channel breakout with ATR-based position sizing",
        "asset_class": "equity",
        "instruments": ["NIFTY", "BANKNIFTY"],
        "entry_rules": [
            {
                "direction": "LONG",
                "condition_groups": [
                    {
                        "conditions": [
                            {
                                "left_operand": "close",
                                "operator": "crosses_above",
                                "right_operand": "highest_high_20",
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
                "exit_type": "indicator",
                "indicator_condition": {
                    "left_operand": "close",
                    "operator": "crosses_below",
                    "right_operand": "lowest_low_10",
                    "time_frame": "1D"
                }
            }
        ],
        "position_sizing": {
            "method": "atr_based",
            "value": 1.0,
            "max_position_pct": 10.0,
            "max_concurrent_positions": 5
        },
        "market_filter": {
            "require_above_200ema": False,
            "min_adx": None,
            "max_vix": None,
            "require_positive_breadth": False
        },
        "indicators_config": {
            "highest_high_20": {"period": 20},
            "lowest_low_10": {"period": 10},
            "atr_14": {"period": 14}
        },
        "risk_per_trade_pct": 1.0,
        "max_daily_loss_pct": 2.0,
        "regime_awareness": True,
        "status": "draft",
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat()
    }
    
    template = Strategy(
        id=template_id,
        user_id=uuid.UUID(SYSTEM_USER_ID),
        template_id=None,
        name="Turtle Breakout (Richard Dennis)",
        description="20-day channel breakout with ATR-based position sizing and 10-day channel stop",
        spec=template_spec,
        compiled_hash=None,
        status="draft",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    
    test_session.add(template)
    await test_session.commit()
    
    return template


# ============================================================================
# Test: POST /api/v1/algo/strategies
# ============================================================================

@pytest.mark.asyncio
async def test_create_strategy_success(client, sample_strategy_spec):
    """Test successful strategy creation"""
    response = await client.post(
        "/api/v1/algo/strategies",
        json={"spec": sample_strategy_spec}
    )
    
    assert response.status_code == 201
    data = response.json()
    
    assert "id" in data
    assert data["name"] == "Test RSI Strategy"
    assert data["user_id"] == TEST_USER_ID
    assert data["status"] == "draft"
    assert data["compiled_hash"] is None
    assert "spec" in data


@pytest.mark.asyncio
async def test_create_strategy_validation_error(client):
    """Test strategy creation with invalid spec"""
    invalid_spec = {
        "strategy_id": "test",
        "user_id": TEST_USER_ID,
        "name": "Invalid Strategy",
        "description": "Missing required fields",
        "asset_class": "equity",
        "instruments": [],  # Empty instruments
        "entry_rules": [],  # Empty entry rules - should fail validation
        "exit_rules": [],   # Empty exit rules - should fail validation
        "position_sizing": {
            "method": "pct_capital",
            "value": 5.0,
            "max_position_pct": 10.0,
            "max_concurrent_positions": 3
        },
        "market_filter": {
            "require_above_200ema": False
        },
        "indicators_config": {},
        "risk_per_trade_pct": 1.0,
        "max_daily_loss_pct": 2.0,
        "regime_awareness": True,
        "status": "draft",
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat()
    }
    
    response = await client.post(
        "/api/v1/algo/strategies",
        json={"spec": invalid_spec}
    )
    
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_strategy_max_position_cap(client, sample_strategy_spec):
    """Test that max_position_pct is capped at 10%"""
    # Try to create strategy with max_position_pct > 10%
    sample_strategy_spec["position_sizing"]["max_position_pct"] = 15.0
    
    response = await client.post(
        "/api/v1/algo/strategies",
        json={"spec": sample_strategy_spec}
    )
    
    # Should fail validation
    assert response.status_code == 422


# ============================================================================
# Test: GET /api/v1/algo/strategies
# ============================================================================

@pytest.mark.asyncio
async def test_list_strategies_empty(client):
    """Test listing strategies when none exist"""
    response = await client.get("/api/v1/algo/strategies")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["strategies"] == []
    assert data["total"] == 0
    assert data["page"] == 1
    assert data["total_pages"] == 0


@pytest.mark.asyncio
async def test_list_strategies_with_data(client, sample_strategy_spec):
    """Test listing strategies with data"""
    # Create 3 strategies
    for i in range(3):
        spec = sample_strategy_spec.copy()
        spec["name"] = f"Strategy {i+1}"
        await client.post("/api/v1/algo/strategies", json={"spec": spec})
    
    # List all strategies
    response = await client.get("/api/v1/algo/strategies")
    
    assert response.status_code == 200
    data = response.json()
    
    assert len(data["strategies"]) == 3
    assert data["total"] == 3
    assert data["page"] == 1
    assert data["total_pages"] == 1


@pytest.mark.asyncio
async def test_list_strategies_pagination(client, sample_strategy_spec):
    """Test strategy list pagination"""
    # Create 5 strategies
    for i in range(5):
        spec = sample_strategy_spec.copy()
        spec["name"] = f"Strategy {i+1}"
        await client.post("/api/v1/algo/strategies", json={"spec": spec})
    
    # Get page 1 with limit 2
    response = await client.get("/api/v1/algo/strategies?page=1&limit=2")
    
    assert response.status_code == 200
    data = response.json()
    
    assert len(data["strategies"]) == 2
    assert data["total"] == 5
    assert data["page"] == 1
    assert data["limit"] == 2
    assert data["total_pages"] == 3


@pytest.mark.asyncio
async def test_list_strategies_status_filter(client, sample_strategy_spec):
    """Test filtering strategies by status"""
    # Create strategies with different statuses
    for status in ["draft", "testing", "paper"]:
        spec = sample_strategy_spec.copy()
        spec["name"] = f"Strategy {status}"
        spec["status"] = status
        await client.post("/api/v1/algo/strategies", json={"spec": spec})
    
    # Filter by status=draft
    response = await client.get("/api/v1/algo/strategies?status_filter=draft")
    
    assert response.status_code == 200
    data = response.json()
    
    assert len(data["strategies"]) == 1
    assert data["strategies"][0]["status"] == "draft"


# ============================================================================
# Test: GET /api/v1/algo/strategies/{id}
# ============================================================================

@pytest.mark.asyncio
async def test_get_strategy_success(client, sample_strategy_spec):
    """Test getting a strategy by ID"""
    # Create strategy
    create_response = await client.post(
        "/api/v1/algo/strategies",
        json={"spec": sample_strategy_spec}
    )
    strategy_id = create_response.json()["id"]
    
    # Get strategy
    response = await client.get(f"/api/v1/algo/strategies/{strategy_id}")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["id"] == strategy_id
    assert data["name"] == "Test RSI Strategy"
    assert "spec" in data
    assert "compiled_hash" in data


@pytest.mark.asyncio
async def test_get_strategy_not_found(client):
    """Test getting a non-existent strategy"""
    fake_id = str(uuid.uuid4())
    response = await client.get(f"/api/v1/algo/strategies/{fake_id}")
    
    assert response.status_code == 404


# ============================================================================
# Test: PUT /api/v1/algo/strategies/{id}
# ============================================================================

@pytest.mark.asyncio
async def test_update_strategy_success(client, sample_strategy_spec):
    """Test updating a strategy"""
    # Create strategy
    create_response = await client.post(
        "/api/v1/algo/strategies",
        json={"spec": sample_strategy_spec}
    )
    strategy_id = create_response.json()["id"]
    
    # Update strategy
    updated_spec = sample_strategy_spec.copy()
    updated_spec["name"] = "Updated Strategy Name"
    updated_spec["description"] = "Updated description"
    
    response = await client.put(
        f"/api/v1/algo/strategies/{strategy_id}",
        json={"spec": updated_spec}
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["id"] == strategy_id
    assert data["name"] == "Updated Strategy Name"
    assert data["description"] == "Updated description"
    assert data["compiled_hash"] is None  # Should be invalidated


@pytest.mark.asyncio
async def test_update_strategy_not_found(client, sample_strategy_spec):
    """Test updating a non-existent strategy"""
    fake_id = str(uuid.uuid4())
    response = await client.put(
        f"/api/v1/algo/strategies/{fake_id}",
        json={"spec": sample_strategy_spec}
    )
    
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_strategy_validation_error(client, sample_strategy_spec):
    """Test updating with invalid spec"""
    # Create strategy
    create_response = await client.post(
        "/api/v1/algo/strategies",
        json={"spec": sample_strategy_spec}
    )
    strategy_id = create_response.json()["id"]
    
    # Try to update with invalid spec
    invalid_spec = sample_strategy_spec.copy()
    invalid_spec["entry_rules"] = []  # Empty entry rules
    
    response = await client.put(
        f"/api/v1/algo/strategies/{strategy_id}",
        json={"spec": invalid_spec}
    )
    
    assert response.status_code == 422


# ============================================================================
# Test: DELETE /api/v1/algo/strategies/{id}
# ============================================================================

@pytest.mark.asyncio
async def test_delete_strategy_success(client, sample_strategy_spec):
    """Test deleting a strategy"""
    # Create strategy
    create_response = await client.post(
        "/api/v1/algo/strategies",
        json={"spec": sample_strategy_spec}
    )
    strategy_id = create_response.json()["id"]
    
    # Delete strategy
    response = await client.delete(f"/api/v1/algo/strategies/{strategy_id}")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["success"] is True
    assert "deleted successfully" in data["message"]
    
    # Verify strategy is soft deleted (status=deleted)
    get_response = await client.get(f"/api/v1/algo/strategies/{strategy_id}")
    assert get_response.status_code == 200
    assert get_response.json()["status"] == "deleted"


@pytest.mark.asyncio
async def test_delete_strategy_not_found(client):
    """Test deleting a non-existent strategy"""
    fake_id = str(uuid.uuid4())
    response = await client.delete(f"/api/v1/algo/strategies/{fake_id}")
    
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_live_strategy_blocked(client, sample_strategy_spec):
    """Test that deleting a live strategy is blocked"""
    # Create strategy
    sample_strategy_spec["status"] = "live"
    create_response = await client.post(
        "/api/v1/algo/strategies",
        json={"spec": sample_strategy_spec}
    )
    strategy_id = create_response.json()["id"]
    
    # Try to delete live strategy
    response = await client.delete(f"/api/v1/algo/strategies/{strategy_id}")
    
    assert response.status_code == 400
    assert "Cannot delete a live strategy" in response.json()["detail"]


# ============================================================================
# Test: GET /api/v1/algo/templates
# ============================================================================

@pytest.mark.asyncio
async def test_get_templates_empty(client):
    """Test getting templates when none exist"""
    response = await client.get("/api/v1/algo/templates")
    
    assert response.status_code == 200
    data = response.json()
    
    assert isinstance(data, list)
    assert len(data) == 0


@pytest.mark.asyncio
async def test_get_templates_with_data(client, sample_template):
    """Test getting templates with data"""
    response = await client.get("/api/v1/algo/templates")
    
    assert response.status_code == 200
    data = response.json()
    
    assert len(data) == 1
    assert data[0]["name"] == "Turtle Breakout (Richard Dennis)"
    assert "spec" in data[0]


# ============================================================================
# Test: POST /api/v1/algo/templates/{id}/clone
# ============================================================================

@pytest.mark.asyncio
async def test_clone_template_success(client, sample_template):
    """Test cloning a template"""
    template_id = str(sample_template.id)
    
    response = await client.post(f"/api/v1/algo/templates/{template_id}/clone")
    
    assert response.status_code == 201
    data = response.json()
    
    assert data["success"] is True
    assert "cloned successfully" in data["message"]
    assert "strategy_id" in data
    assert "strategy" in data
    
    # Verify cloned strategy
    strategy = data["strategy"]
    assert strategy["name"] == "Turtle Breakout (Richard Dennis) (Copy)"
    assert strategy["status"] == "draft"
    assert strategy["user_id"] == TEST_USER_ID
    assert strategy["template_id"] == template_id


@pytest.mark.asyncio
async def test_clone_template_not_found(client):
    """Test cloning a non-existent template"""
    fake_id = str(uuid.uuid4())
    response = await client.post(f"/api/v1/algo/templates/{fake_id}/clone")
    
    assert response.status_code == 404


# ============================================================================
# Test: Ownership Check
# ============================================================================

@pytest.mark.asyncio
async def test_ownership_check(client, sample_strategy_spec, test_app):
    """Test that users can only access their own strategies"""
    # Create strategy as user 1
    create_response = await client.post(
        "/api/v1/algo/strategies",
        json={"spec": sample_strategy_spec}
    )
    strategy_id = create_response.json()["id"]
    
    # Override user ID to simulate different user
    async def override_get_current_user_id():
        return "00000000-0000-0000-0000-000000000002"  # Different user
    
    test_app.dependency_overrides[get_current_user_id] = override_get_current_user_id
    
    # Try to access strategy as user 2
    response = await client.get(f"/api/v1/algo/strategies/{strategy_id}")
    
    assert response.status_code == 404  # Should not find strategy


# ============================================================================
# Test: Health Check
# ============================================================================

@pytest.mark.asyncio
async def test_health_check(client):
    """Test health check endpoint"""
    response = await client.get("/api/v1/algo/health")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["status"] == "healthy"
    assert data["service"] == "algo_builder"
