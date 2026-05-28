"""
Pytest Configuration
Fixtures and test setup for all tests
"""

import pytest
import asyncio
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool

from shared.database.models import Base
from shared.config.settings import settings


# Test database URL
TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/signalixai_test"


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def test_engine():
    """Create test database engine"""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        poolclass=NullPool,
    )
    
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    # Drop all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()


@pytest.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a new database session for a test"""
    async_session = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    
    async with async_session() as session:
        yield session
        await session.rollback()


@pytest.fixture
def test_user_data():
    """Sample user data for testing"""
    return {
        "email": "test@signalixai.com",
        "phone": "+919876543210",
        "password": "Test@123456",
        "full_name": "Test User",
        "country_of_residence": "IN",
        "declared_trading_capital_inr": 50000000,  # 5 lakhs
        "risk_tolerance_score": 7,
        "investment_horizon": "swing",
        "sebi_declaration_acknowledged": True,
    }


@pytest.fixture
def test_analysis_request():
    """Sample analysis request for testing"""
    return {
        "instrument": "RELIANCE",
        "analysis_type": "swing_trade",
        "depth": "shallow",
    }
