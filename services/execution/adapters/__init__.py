"""
Broker adapter layer for Signalix execution engine.

This module provides a unified interface for executing trades across multiple brokers:
- OpenAlgo-compatible adapters for Indian brokers (Angel One, Zerodha, Upstox)
- Direct API adapters for international brokers (Binance, OANDA, Alpaca)

All adapters implement the BrokerAdapter interface for consistent behavior.
"""

from .base import (
    BrokerAdapter,
    Order,
    OrderStatus,
    OrderType,
    OrderSide,
    Position,
    MarginInfo,
    ProductType
)
from .openalgo_adapter import OpenAlgoAdapter
from .binance_adapter import BinanceAdapter
from .oanda_adapter import OandaAdapter
from .alpaca_adapter import AlpacaAdapter

__all__ = [
    "BrokerAdapter",
    "Order",
    "OrderStatus",
    "OrderType",
    "OrderSide",
    "Position",
    "MarginInfo",
    "ProductType",
    "OpenAlgoAdapter",
    "BinanceAdapter",
    "OandaAdapter",
    "AlpacaAdapter",
]
