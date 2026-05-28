"""
Broker Integration Service

Provides unified broker integration for 30+ Indian brokers with:
- Connection management
- Order execution
- Position tracking
- Symbol normalization
- Plugin architecture

Requirements: 10.1, 10.2, 10.4, 10.5, 10.7, 10.10, 16.1, 20.1, 25.1
"""

from .main import app
from .connection_manager import ConnectionManager, ConnectionState
from .order_manager import OrderManager, OrderRequest, OrderResponse
from .credential_manager import CredentialManager, SecureCredentialStorage
from .symbol_normalizer import SymbolNormalizer
from .plugin_system import PluginRegistry, BrokerPluginInterface, PluginMetadata
from .reconciliation import PositionReconciliation, ReconciliationResult

__all__ = [
    'app',
    'ConnectionManager',
    'ConnectionState',
    'OrderManager',
    'OrderRequest',
    'OrderResponse',
    'CredentialManager',
    'SecureCredentialStorage',
    'SymbolNormalizer',
    'PluginRegistry',
    'BrokerPluginInterface',
    'PluginMetadata',
    'PositionReconciliation',
    'ReconciliationResult'
]

__version__ = "1.0.0"
