"""
Integration tests for strategy compilation and paper trading endpoints

Tests:
1. Compile each template strategy
2. Verify compiled_hash is stored in database
3. Verify compiled code is cached in Redis
4. Test paper trading session creation
5. Test validation failures

Requirements: 3.6, 3.7, 1.9
"""
import pytest
import asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from services.algo_builder.router import router, get_db, get_current_user_id
from services.algo_builder.redis_client import get_redis_client, close_redis_client
from shared.database.models import Strategy, Base
from fastapi import FastAPI
import uuid
from datetime import datetime


# Test configuration
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/signalixai_test"
)

# Create test app
app = FastAPI()
app.include_router(router)


# Test fixtures
@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def test_engine():
    """Create test database engine"""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    # Drop tables
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
async def test_user_id():
    """Test user ID"""
    return "00000000-0000-0000-0000-000000000001"


@pytest.fixture
async def test_client(test_session, test_user_id):
    """Create test HTTP client with dependency overrides"""
    
    async def override_get_db():
        yield test_session
    
    async def override_get_current_user_id():
        return test_user_id
    
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_id] = override_get_current_user_id
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client
    
    app.dependency_overrides.clear()


@pytest.fixture
async def sample_strategy_spec():
    """Sample strategy specification for testing"""
    return {
        "strategy_id": str(uuid.uuid4()),
        "user_id": "00000000-0000-0000-0000-000000000001",
        "name": "Test RSI Strategy",
        "description": "Simple RSI oversold/overbought strategy for testing",
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


# ============================================================================
# Test Cases
# ============================================================================

@pytest.mark.asyncio
async def test_compile_strategy_success(test_client, test_session, test_user_id, sample_strategy_spec):
    """
    Test successful strategy compilation
    
    Validates: Requirements 3.6, 3.7
    """
    # Create a strategy first
    create_response = await test_client.post(
        "/api/v1/algo/strategies",
        json={"spec": sample_strategy_spec}
    )
    assert create_response.status_code == 201
    strategy_data = create_response.json()
    strategy_id = strategy_data["id"]
    
    # Compile the strategy
    compile_response = await test_client.post(
        f"/api/v1/algo/strategies/{strategy_id}/compile"
    )
    
    assert compile_response.status_code == 200
    compile_data = compile_response.json()
    
    # Verify response structure
    assert compile_data["success"] is True
    assert "compiled_hash" in compile_data
    assert len(compile_data["compiled_hash"]) == 64  # SHA-256 hash
    assert "validation_result" in compile_data
    assert compile_data["validation_result"]["success"] is True
    assert "execution_time_ms" in compile_data["validation_result"]
    
    # Verify compiled_hash is stored in database
    result = await test_session.execute(
        select(Strategy).where(Strategy.id == uuid.UUID(strategy_id))
    )
    strategy = result.scalar_one()
    assert strategy.compiled_hash == compile_data["compiled_hash"]
    
    # Verify compiled code is cached in Redis
    redis_client = await get_redis_client()
    cached_code = await redis_client.get_compiled_strategy(compile_data["compiled_hash"])
    assert cached_code is not None
    assert "CompiledStrategy_" in cached_code
    assert "BaseStrategy" in cached_code
    
    print(f"✅ Strategy compiled successfully")
    print(f"   - Compiled hash: {compile_data['compiled_hash'][:16]}...")
    print(f"   - Validation time: {compile_data['validation_result']['execution_time_ms']:.2f}ms")
    print(f"   - Cached in Redis: {compile_data['cached']}")


@pytest.mark.asyncio
async def test_compile_strategy_cached(test_client, test_session, test_user_id, sample_strategy_spec):
    """
    Test that recompiling the same strategy uses cache
    
    Validates: Requirements 3.7
    """
    # Create and compile a strategy
    create_response = await test_client.post(
        "/api/v1/algo/strategies",
        json={"spec": sample_strategy_spec}
    )
    strategy_id = create_response.json()["id"]
    
    # First compilation
    compile_response_1 = await test_client.post(
        f"/api/v1/algo/strategies/{strategy_id}/compile"
    )
    assert compile_response_1.status_code == 200
    compile_data_1 = compile_response_1.json()
    
    # Second compilation (should use cache)
    compile_response_2 = await test_client.post(
        f"/api/v1/algo/strategies/{strategy_id}/compile"
    )
    assert compile_response_2.status_code == 200
    compile_data_2 = compile_response_2.json()
    
    # Verify same hash
    assert compile_data_1["compiled_hash"] == compile_data_2["compiled_hash"]
    
    # Verify cache was used
    assert compile_data_2["cached"] is True
    assert "from cache" in compile_data_2["message"].lower()
    
    print(f"✅ Strategy compilation cache working correctly")
    print(f"   - Hash: {compile_data_2['compiled_hash'][:16]}...")
    print(f"   - Cache hit: {compile_data_2['cached']}")


@pytest.mark.asyncio
async def test_compile_invalid_strategy(test_client, test_session, test_user_id):
    """
    Test compilation failure with invalid strategy spec
    
    Validates: Requirements 3.6
    """
    # Create a strategy with invalid spec (missing required fields)
    invalid_spec = {
        "strategy_id": str(uuid.uuid4()),
        "user_id": test_user_id,
        "name": "Invalid Strategy",
        "description": "Missing entry and exit rules",
        "asset_class": "equity",
        "instruments": ["NIFTY"],
        "entry_rules": [],  # Empty - invalid
        "exit_rules": [],   # Empty - invalid
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
    
    # Try to create strategy (should fail validation)
    create_response = await test_client.post(
        "/api/v1/algo/strategies",
        json={"spec": invalid_spec}
    )
    
    # Should fail at creation due to Pydantic validation
    assert create_response.status_code == 422
    
    print(f"✅ Invalid strategy rejected correctly")


@pytest.mark.asyncio
async def test_paper_trading_success(test_client, test_session, test_user_id, sample_strategy_spec):
    """
    Test successful paper trading session creation
    
    Validates: Requirements 1.9
    """
    # Create and compile a strategy
    create_response = await test_client.post(
        "/api/v1/algo/strategies",
        json={"spec": sample_strategy_spec}
    )
    strategy_id = create_response.json()["id"]
    
    compile_response = await test_client.post(
        f"/api/v1/algo/strategies/{strategy_id}/compile"
    )
    assert compile_response.status_code == 200
    
    # Create paper trading session
    paper_response = await test_client.post(
        f"/api/v1/algo/strategies/{strategy_id}/paper",
        json={"initial_capital": 100000.0}
    )
    
    assert paper_response.status_code == 201
    paper_data = paper_response.json()
    
    # Verify response structure
    assert paper_data["success"] is True
    assert "session_id" in paper_data
    assert paper_data["strategy_id"] == strategy_id
    assert paper_data["initial_capital"] == 100000.0
    assert paper_data["status"] == "active"
    
    # Verify strategy status updated to paper
    result = await test_session.execute(
        select(Strategy).where(Strategy.id == uuid.UUID(strategy_id))
    )
    strategy = result.scalar_one()
    assert strategy.status == "paper"
    
    print(f"✅ Paper trading session created successfully")
    print(f"   - Session ID: {paper_data['session_id']}")
    print(f"   - Initial capital: Rs {paper_data['initial_capital']:,.2f}")
    print(f"   - Strategy status: {strategy.status}")


@pytest.mark.asyncio
async def test_paper_trading_without_compilation(test_client, test_session, test_user_id, sample_strategy_spec):
    """
    Test that paper trading requires compilation first
    
    Validates: Requirements 1.9
    """
    # Create a strategy without compiling
    create_response = await test_client.post(
        "/api/v1/algo/strategies",
        json={"spec": sample_strategy_spec}
    )
    strategy_id = create_response.json()["id"]
    
    # Try to create paper trading session without compilation
    paper_response = await test_client.post(
        f"/api/v1/algo/strategies/{strategy_id}/paper",
        json={"initial_capital": 100000.0}
    )
    
    assert paper_response.status_code == 400
    error_data = paper_response.json()
    assert "not compiled" in error_data["detail"]["error"].lower()
    assert "action" in error_data["detail"]
    
    print(f"✅ Paper trading correctly requires compilation")


@pytest.mark.asyncio
async def test_compile_all_templates(test_client, test_session, test_user_id):
    """
    Test compilation of all strategy templates
    
    This test:
    1. Gets all templates
    2. Clones each template
    3. Compiles each cloned strategy
    4. Verifies hash stored and cache populated
    
    Validates: Requirements 3.6, 3.7, 2.4, 2.5
    """
    # Get all templates
    templates_response = await test_client.get("/api/v1/algo/templates")
    assert templates_response.status_code == 200
    templates = templates_response.json()
    
    print(f"\n📋 Testing compilation of {len(templates)} templates:")
    
    compiled_strategies = []
    
    for template in templates:
        template_id = template["id"]
        template_name = template["name"]
        
        print(f"\n   Testing: {template_name}")
        
        # Clone template
        clone_response = await test_client.post(
            f"/api/v1/algo/templates/{template_id}/clone"
        )
        assert clone_response.status_code == 201
        strategy_id = clone_response.json()["strategy_id"]
        
        # Compile strategy
        compile_response = await test_client.post(
            f"/api/v1/algo/strategies/{strategy_id}/compile"
        )
        
        if compile_response.status_code == 200:
            compile_data = compile_response.json()
            
            # Verify hash stored
            result = await test_session.execute(
                select(Strategy).where(Strategy.id == uuid.UUID(strategy_id))
            )
            strategy = result.scalar_one()
            assert strategy.compiled_hash == compile_data["compiled_hash"]
            
            # Verify cache populated
            redis_client = await get_redis_client()
            cached_code = await redis_client.get_compiled_strategy(compile_data["compiled_hash"])
            assert cached_code is not None
            
            compiled_strategies.append({
                "name": template_name,
                "strategy_id": strategy_id,
                "compiled_hash": compile_data["compiled_hash"],
                "validation_time_ms": compile_data["validation_result"]["execution_time_ms"]
            })
            
            print(f"      ✅ Compiled successfully")
            print(f"         Hash: {compile_data['compiled_hash'][:16]}...")
            print(f"         Validation: {compile_data['validation_result']['execution_time_ms']:.2f}ms")
        else:
            print(f"      ❌ Compilation failed: {compile_response.json()}")
            assert False, f"Template {template_name} failed to compile"
    
    print(f"\n✅ All {len(compiled_strategies)} templates compiled successfully")
    
    # Verify cache stats
    redis_client = await get_redis_client()
    cache_stats = await redis_client.get_cache_stats()
    print(f"\n📊 Redis Cache Stats:")
    print(f"   - Cached strategies: {cache_stats.get('cached_strategies', 0)}")
    print(f"   - Hit rate: {cache_stats.get('hit_rate', 0):.2f}%")


# ============================================================================
# Cleanup
# ============================================================================

@pytest.fixture(scope="session", autouse=True)
async def cleanup():
    """Cleanup after all tests"""
    yield
    # Close Redis connection
    await close_redis_client()


# ============================================================================
# Run Tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
