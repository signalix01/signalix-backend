"""
Whale Tracker Module

Tracks large institutional movements across all financial markets.
Requirements: 12.1, 12.3, 12.4
"""

from .india_equity import IndiaEquityWhaleTracker
from .crypto_whale import CryptoWhaleTracker
from .fo_whale import FOWhaleTracker
from .us_equity_whale import USEquityWhaleTracker

__all__ = [
    "IndiaEquityWhaleTracker",
    "CryptoWhaleTracker",
    "FOWhaleTracker",
    "USEquityWhaleTracker"
]
