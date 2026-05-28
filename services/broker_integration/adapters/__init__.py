"""
Broker Adapters

Built-in broker adapter implementations for Indian brokers.
"""

from .base_adapter import (
    EnhancedBrokerAdapter,
    BrokerAdapterException,
    Order,
    OrderStatus,
    OrderType,
    OrderSide,
    Position,
    MarginInfo,
    ProductType,
    BrokerErrorType
)

from .zerodha_adapter import ZerodhaAdapter
from .dhan_adapter import DhanAdapter
from .upstox_adapter import UpstoxAdapter
from .angel_one_adapter import AngelOneAdapter
from .icici_adapter import ICICIAdapter

__all__ = [
    'EnhancedBrokerAdapter',
    'BrokerAdapterException',
    'Order',
    'OrderStatus',
    'OrderType',
    'OrderSide',
    'Position',
    'MarginInfo',
    'ProductType',
    'BrokerErrorType',
    'ZerodhaAdapter',
    'DhanAdapter',
    'UpstoxAdapter',
    'AngelOneAdapter',
    'ICICIAdapter'
]
