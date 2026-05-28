"""
Backtest Service

Provides REST API for backtesting strategies using:
- Vectorized Engine (fast pandas/numpy based)
- Event-Driven Engine (realistic tick-level simulation)
- Walk-Forward Optimization
- Monte Carlo Simulation
- Market Regime Analysis

Requirements: Phase 1.4 - Wire backtest-service
"""

__version__ = "1.0.0"
__all__ = ["app"]

from .main import app
