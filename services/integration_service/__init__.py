"""
Integration Service

Webhook processing service for TradingView, Amibroker, and ChartInk.
Requirements: 1.1, 2.1, 3.1, 17.1
"""

from .router import router

__all__ = ["router"]
