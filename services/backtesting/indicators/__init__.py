"""
Technical indicators for backtesting.

This module provides custom indicator implementations not available in TA-Lib.
"""

from .supertrend import compute_supertrend

__all__ = ['compute_supertrend']
