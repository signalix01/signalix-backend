"""
Health Check Tests
Test health check endpoints and functionality
"""

import pytest
from shared.utils.health_check import (
    check_database,
    check_redis,
    check_llm_api,
    comprehensive_health_check,
    HealthStatus,
)


@pytest.mark.asyncio
async def test_database_health_check(db_session):
    """Test database health check"""
    result = await check_database(db_session)
    
    assert result["status"] == HealthStatus.HEALTHY
    assert "latency_ms" in result
    assert result["latency_ms"] is not None
    assert result["latency_ms"] < 100  # Should be fast


@pytest.mark.asyncio
async def test_redis_health_check():
    """Test Redis health check"""
    redis_url = "redis://localhost:6379/0"
    result = await check_redis(redis_url)
    
    assert result["status"] == HealthStatus.HEALTHY
    assert "latency_ms" in result
    assert result["latency_ms"] is not None


@pytest.mark.asyncio
async def test_llm_api_health_check():
    """Test LLM API health check"""
    # With API key
    result = await check_llm_api("Anthropic", "sk-ant-test-key")
    assert result["status"] == HealthStatus.HEALTHY
    
    # Without API key
    result = await check_llm_api("Anthropic", None)
    assert result["status"] == HealthStatus.DEGRADED


@pytest.mark.asyncio
async def test_comprehensive_health_check(db_session):
    """Test comprehensive health check"""
    result = await comprehensive_health_check(
        db=db_session,
        redis_url="redis://localhost:6379/0",
        anthropic_key="sk-ant-test-key",
    )
    
    assert "timestamp" in result
    assert "status" in result
    assert "components" in result
    
    # Check components
    assert "database" in result["components"]
    assert "redis" in result["components"]
    assert "anthropic_api" in result["components"]
    
    # Overall status should be healthy if all components are healthy
    if all(comp["status"] == HealthStatus.HEALTHY for comp in result["components"].values()):
        assert result["status"] == HealthStatus.HEALTHY
