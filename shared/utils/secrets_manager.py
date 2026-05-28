"""
Secrets Manager

Centralized secrets management with caching and validation.
Supports ENV backend (default) with extensibility for AWS SSM / Vault.
"""

import os
import logging
from enum import Enum
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class SecretsBackend(str, Enum):
    ENV = "env"
    AWS_SSM = "aws_ssm"
    VAULT = "vault"


class SecretsManager:
    """
    Centralized secrets manager with caching.

    Usage:
        manager = SecretsManager(backend=SecretsBackend.ENV)
        db_url = manager.get_secret("DATABASE_URL")
    """

    def __init__(self, backend: SecretsBackend = SecretsBackend.ENV):
        self.backend = backend
        self._cache: Dict[str, str] = {}

    def get_secret(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get a secret value by key, with caching."""
        if key in self._cache:
            return self._cache[key]

        value: Optional[str] = None

        if self.backend == SecretsBackend.ENV:
            value = os.environ.get(key)
        elif self.backend == SecretsBackend.AWS_SSM:
            value = self._get_from_aws_ssm(key)
        elif self.backend == SecretsBackend.VAULT:
            value = self._get_from_vault(key)

        if value is None:
            return default

        self._cache[key] = value
        return value

    def get_database_url(self) -> Optional[str]:
        """Get the database URL."""
        return self.get_secret("DATABASE_URL")

    def get_llm_api_keys(self) -> Dict[str, Optional[str]]:
        """Get all LLM API keys."""
        return {
            "anthropic": self.get_secret("ANTHROPIC_API_KEY"),
            "openai": self.get_secret("OPENAI_API_KEY"),
            "google": self.get_secret("GEMINI_API_KEY"),
            "deepseek": self.get_secret("DEEPSEEK_API_KEY"),
            "mistral": self.get_secret("MISTRAL_API_KEY"),
            "xai": self.get_secret("XAI_API_KEY"),
        }

    def validate_required_secrets(self) -> Dict[str, bool]:
        """Validate that all required secrets are present."""
        required = [
            "DATABASE_URL",
            "REDIS_URL",
            "JWT_SECRET_KEY",
            "ANTHROPIC_API_KEY",
        ]
        return {key: self.get_secret(key) is not None for key in required}

    def clear_cache(self) -> None:
        """Clear the secrets cache."""
        self._cache.clear()

    # ----- Backend implementations (stubs for non-ENV) -----

    def _get_from_aws_ssm(self, key: str) -> Optional[str]:
        logger.warning("AWS SSM backend not implemented, falling back to ENV")
        return os.environ.get(key)

    def _get_from_vault(self, key: str) -> Optional[str]:
        logger.warning("Vault backend not implemented, falling back to ENV")
        return os.environ.get(key)


# Singleton
_global_manager: Optional[SecretsManager] = None


def get_secrets_manager(
    backend: SecretsBackend = SecretsBackend.ENV,
) -> SecretsManager:
    """Get or create the global SecretsManager singleton."""
    global _global_manager
    if _global_manager is None:
        _global_manager = SecretsManager(backend=backend)
    return _global_manager
