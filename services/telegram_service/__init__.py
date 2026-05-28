"""
Telegram Bot Service

FastAPI service for Telegram bot integration with order alerts and trading commands.
Requirements: 8.1, 9.1, 24.1
"""

from .router import router

__all__ = ["router"]
