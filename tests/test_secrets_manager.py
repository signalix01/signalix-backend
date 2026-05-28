"""
Secrets Manager Tests
Test secrets management functionality
"""

import os
import pytest
from shared.utils.secrets_manager import (
    SecretsManager,
    SecretsBackend,
    get_secrets_manager,
)


def test_secrets_manager_env_backend():
    """Test secrets manager with ENV backend"""
    # Set test environment variable
    os.environ["TEST_SECRET"] = "test_value"
    
    manager = SecretsManager(backend=SecretsBackend.ENV)
    
    # Get secret
    value = manager.get_secret("TEST_SECRET")
    assert value == "test_value"
    
    # Get non-existent secret with default
    value = manager.get_secret("NON_EXISTENT", default="default_value")
    assert value == "default_value"
    
    # Clean up
    del os.environ["TEST_SECRET"]


def test_secrets_manager_caching():
    """Test secrets manager caching"""
    os.environ["CACHED_SECRET"] = "cached_value"
    
    manager = SecretsManager(backend=SecretsBackend.ENV)
    
    # First call - should fetch from env
    value1 = manager.get_secret("CACHED_SECRET")
    
    # Second call - should fetch from cache
    value2 = manager.get_secret("CACHED_SECRET")
    
    assert value1 == value2 == "cached_value"
    
    # Clean up
    del os.environ["CACHED_SECRET"]


def test_get_database_url():
    """Test get_database_url helper"""
    os.environ["DATABASE_URL"] = "postgresql+asyncpg://localhost/test"
    
    manager = SecretsManager(backend=SecretsBackend.ENV)
    url = manager.get_database_url()
    
    assert url == "postgresql+asyncpg://localhost/test"
    
    del os.environ["DATABASE_URL"]


def test_get_llm_api_keys():
    """Test get_llm_api_keys helper"""
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test"
    os.environ["OPENAI_API_KEY"] = "sk-test"
    
    manager = SecretsManager(backend=SecretsBackend.ENV)
    keys = manager.get_llm_api_keys()
    
    assert keys["anthropic"] == "sk-ant-test"
    assert keys["openai"] == "sk-test"
    assert keys["google"] is None  # Not set
    
    del os.environ["ANTHROPIC_API_KEY"]
    del os.environ["OPENAI_API_KEY"]


def test_validate_required_secrets():
    """Test validate_required_secrets"""
    # Set required secrets
    os.environ["DATABASE_URL"] = "postgresql://localhost/test"
    os.environ["REDIS_URL"] = "redis://localhost:6379"
    os.environ["JWT_SECRET_KEY"] = "test-secret-key"
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test"
    
    manager = SecretsManager(backend=SecretsBackend.ENV)
    validation = manager.validate_required_secrets()
    
    assert all(validation.values())  # All should be True
    
    # Clean up
    del os.environ["DATABASE_URL"]
    del os.environ["REDIS_URL"]
    del os.environ["JWT_SECRET_KEY"]
    del os.environ["ANTHROPIC_API_KEY"]


def test_global_secrets_manager():
    """Test global secrets manager instance"""
    manager1 = get_secrets_manager()
    manager2 = get_secrets_manager()
    
    # Should return same instance
    assert manager1 is manager2
