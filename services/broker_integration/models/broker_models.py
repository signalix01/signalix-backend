"""
Broker Integration Service Models

Database models for Broker Integration Service.
Requirements: 10.1, 10.2, 10.10, 16.1, 16.6, 20.1, 20.10, 58.1, 58.2, 58.3, 58.4, 58.5
"""

from enum import Enum
from datetime import datetime
from typing import Optional, Dict, Any, List
from uuid import uuid4

from sqlalchemy import Column, String, DateTime, Boolean, JSON, Integer, Float, Enum as SQLEnum, Text, ForeignKey, Index, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class BrokerType(str, Enum):
    """Supported broker types"""
    ZERODHA = "zerodha"
    DHAN = "dhan"
    UPSTOX = "upstox"
    ANGEL_ONE = "angel_one"
    ICICI_DIRECT = "icici_direct"
    FYERS = "fyers"
    ALICEBLUE = "aliceblue"
    FINVASIA = "finvasia"
    KOTAK = "kotak"
    MOTILAL = "motilal"


class ConnectionStatus(str, Enum):
    """Broker connection status"""
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    CONNECTING = "connecting"
    RECONNECTING = "reconnecting"


class AuthType(str, Enum):
    """Authentication types"""
    API_KEY = "api_key"
    OAUTH = "oauth"
    SESSION_TOKEN = "session_token"
    TWO_FACTOR = "two_factor"


class OrderStatus(str, Enum):
    """Order lifecycle status"""
    PENDING = "pending"
    OPEN = "open"
    COMPLETE = "complete"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    PARTIALLY_FILLED = "partially_filled"
    EXPIRED = "expired"


class OrderType(str, Enum):
    """Order types"""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_LOSS = "STOP_LOSS"
    STOP_LOSS_MARKET = "STOP_LOSS_MARKET"
    SL_LIMIT = "SL_LIMIT"


class ProductType(str, Enum):
    """Product types for Indian markets"""
    INTRADAY = "INTRADAY"  # MIS
    DELIVERY = "DELIVERY"  # CNC
    MARGIN = "MARGIN"      # NRML
    BO = "BO"              # Bracket Order
    CO = "CO"              # Cover Order


class OrderAction(str, Enum):
    """Order actions"""
    BUY = "BUY"
    SELL = "SELL"


class BrokerErrorType(str, Enum):
    """Standardized broker error types"""
    INSUFFICIENT_MARGIN = "insufficient_margin"
    INVALID_SYMBOL = "invalid_symbol"
    MARKET_CLOSED = "market_closed"
    ORDER_TOO_LARGE = "order_too_large"
    ORDER_TOO_SMALL = "order_too_small"
    PRICE_OUT_OF_RANGE = "price_out_of_range"
    SESSION_EXPIRED = "session_expired"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    NETWORK_ERROR = "network_error"
    BROKER_ERROR = "broker_error"
    UNKNOWN_ERROR = "unknown_error"


class BrokerConnection(Base):
    """
    Broker connection configuration and status.
    
    Stores broker credentials (encrypted), connection settings,
    and real-time connection status for each broker.
    """
    __tablename__ = "broker_connections"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    
    # Broker identification
    broker_type = Column(SQLEnum(BrokerType), nullable=False, index=True)
    broker_name = Column(String(100), nullable=False)
    account_label = Column(String(100), nullable=True)  # For multi-account
    is_primary = Column(Boolean, default=False, nullable=False)
    
    # Authentication (encrypted)
    auth_type = Column(SQLEnum(AuthType), nullable=False)
    api_key = Column(Text, nullable=True)  # Encrypted
    api_secret = Column(Text, nullable=True)  # Encrypted
    access_token = Column(Text, nullable=True)  # Encrypted
    refresh_token = Column(Text, nullable=True)  # Encrypted
    client_id = Column(String(255), nullable=True)  # Encrypted
    
    # Connection settings
    enabled = Column(Boolean, default=True, nullable=False)
    auto_reconnect = Column(Boolean, default=True, nullable=False)
    reconnect_attempts = Column(Integer, default=3, nullable=False)
    
    # Connection status
    status = Column(SQLEnum(ConnectionStatus), default=ConnectionStatus.DISCONNECTED, nullable=False)
    last_connected_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)
    last_error_at = Column(DateTime, nullable=True)
    error_count = Column(Integer, default=0, nullable=False)
    
    # WebSocket status
    websocket_connected = Column(Boolean, default=False, nullable=False)
    websocket_last_ping = Column(DateTime, nullable=True)
    
    # Metadata
    broker_metadata = Column(JSON, default=dict)  # Broker-specific settings
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    orders = relationship("BrokerOrder", back_populates="connection", lazy="dynamic")
    positions = relationship("BrokerPosition", back_populates="connection", lazy="dynamic")
    
    __table_args__ = (
        Index('idx_broker_connections_user_broker', 'user_id', 'broker_type'),
        Index('idx_broker_connections_status', 'status'),
        Index('idx_broker_connections_primary', 'user_id', 'is_primary'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation (excludes sensitive data)"""
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "broker_type": self.broker_type.value,
            "broker_name": self.broker_name,
            "account_label": self.account_label,
            "is_primary": self.is_primary,
            "auth_type": self.auth_type.value,
            "enabled": self.enabled,
            "auto_reconnect": self.auto_reconnect,
            "reconnect_attempts": self.reconnect_attempts,
            "status": self.status.value,
            "last_connected_at": self.last_connected_at.isoformat() if self.last_connected_at else None,
            "last_error": self.last_error,
            "last_error_at": self.last_error_at.isoformat() if self.last_error_at else None,
            "error_count": self.error_count,
            "websocket_connected": self.websocket_connected,
            "websocket_last_ping": self.websocket_last_ping.isoformat() if self.websocket_last_ping else None,
            "broker_metadata": self.broker_metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }


class BrokerOrder(Base):
    """
    Order tracking across brokers.
    
    Stores complete order lifecycle with all state transitions
    and broker-specific order IDs.
    """
    __tablename__ = "broker_orders"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    connection_id = Column(UUID(as_uuid=True), ForeignKey("broker_connections.id"), nullable=False, index=True)
    
    # Order identifiers
    order_id = Column(String(100), nullable=False, unique=True, index=True)  # Internal order ID
    broker_order_id = Column(String(100), nullable=True, index=True)  # Broker's order ID
    exchange_order_id = Column(String(100), nullable=True)
    
    # Order details
    symbol = Column(String(50), nullable=False, index=True)
    exchange = Column(String(20), nullable=False)
    action = Column(SQLEnum(OrderAction), nullable=False)
    order_type = Column(SQLEnum(OrderType), nullable=False)
    product_type = Column(SQLEnum(ProductType), nullable=False)
    quantity = Column(Numeric(20, 8), nullable=False)
    price = Column(Numeric(20, 4), nullable=True)
    trigger_price = Column(Numeric(20, 4), nullable=True)
    disclosed_quantity = Column(Numeric(20, 8), nullable=True)
    validity = Column(String(20), default="DAY", nullable=False)
    
    # Order status tracking
    status = Column(SQLEnum(OrderStatus), default=OrderStatus.PENDING, nullable=False, index=True)
    filled_quantity = Column(Numeric(20, 8), default=0, nullable=False)
    remaining_quantity = Column(Numeric(20, 8), nullable=True)
    average_price = Column(Numeric(20, 4), nullable=True)
    
    # Status timestamps
    placed_at = Column(DateTime, nullable=True)
    executed_at = Column(DateTime, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    rejected_at = Column(DateTime, nullable=True)
    last_updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Error information
    reject_reason = Column(Text, nullable=True)
    error_code = Column(String(50), nullable=True)
    error_message = Column(Text, nullable=True)
    
    # Additional metadata
    tag = Column(String(100), nullable=True)
    metadata = Column(JSON, default=dict)
    
    # Relationships
    connection = relationship("BrokerConnection", back_populates="orders")
    status_history = relationship("OrderStatusHistory", back_populates="order", lazy="dynamic", order_by="OrderStatusHistory.changed_at")
    
    __table_args__ = (
        Index('idx_broker_orders_user_status', 'user_id', 'status'),
        Index('idx_broker_orders_symbol', 'symbol', 'exchange'),
        Index('idx_broker_orders_placed_at', 'placed_at'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation"""
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "connection_id": str(self.connection_id),
            "order_id": self.order_id,
            "broker_order_id": self.broker_order_id,
            "exchange_order_id": self.exchange_order_id,
            "symbol": self.symbol,
            "exchange": self.exchange,
            "action": self.action.value,
            "order_type": self.order_type.value,
            "product_type": self.product_type.value,
            "quantity": float(self.quantity) if self.quantity else None,
            "price": float(self.price) if self.price else None,
            "trigger_price": float(self.trigger_price) if self.trigger_price else None,
            "disclosed_quantity": float(self.disclosed_quantity) if self.disclosed_quantity else None,
            "validity": self.validity,
            "status": self.status.value,
            "filled_quantity": float(self.filled_quantity) if self.filled_quantity else None,
            "remaining_quantity": float(self.remaining_quantity) if self.remaining_quantity else None,
            "average_price": float(self.average_price) if self.average_price else None,
            "placed_at": self.placed_at.isoformat() if self.placed_at else None,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
            "cancelled_at": self.cancelled_at.isoformat() if self.cancelled_at else None,
            "rejected_at": self.rejected_at.isoformat() if self.rejected_at else None,
            "last_updated_at": self.last_updated_at.isoformat() if self.last_updated_at else None,
            "reject_reason": self.reject_reason,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "tag": self.tag,
            "metadata": self.metadata
        }


class OrderStatusHistory(Base):
    """
    Complete order status history.
    
    Tracks all state transitions for audit and debugging.
    """
    __tablename__ = "order_status_history"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    order_id = Column(UUID(as_uuid=True), ForeignKey("broker_orders.id"), nullable=False, index=True)
    
    # Status transition
    previous_status = Column(SQLEnum(OrderStatus), nullable=True)
    new_status = Column(SQLEnum(OrderStatus), nullable=False)
    
    # Additional data at transition
    filled_quantity = Column(Numeric(20, 8), nullable=True)
    average_price = Column(Numeric(20, 4), nullable=True)
    
    # Metadata
    reason = Column(Text, nullable=True)
    broker_response = Column(JSON, nullable=True)
    changed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    order = relationship("BrokerOrder", back_populates="status_history")
    
    __table_args__ = (
        Index('idx_order_status_history_order', 'order_id', 'changed_at'),
    )


class BrokerPosition(Base):
    """
    Position tracking per broker connection.
    
    Stores real-time position data with reconciliation tracking.
    """
    __tablename__ = "broker_positions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    connection_id = Column(UUID(as_uuid=True), ForeignKey("broker_connections.id"), nullable=False, index=True)
    
    # Position identification
    symbol = Column(String(50), nullable=False, index=True)
    exchange = Column(String(20), nullable=False)
    product_type = Column(SQLEnum(ProductType), nullable=False)
    
    # Position quantities
    quantity = Column(Numeric(20, 8), nullable=False)  # Positive for long, negative for short
    buy_quantity = Column(Numeric(20, 8), default=0, nullable=False)
    sell_quantity = Column(Numeric(20, 8), default=0, nullable=False)
    
    # Pricing
    average_price = Column(Numeric(20, 4), nullable=False)
    last_price = Column(Numeric(20, 4), nullable=True)
    
    # P&L
    pnl = Column(Numeric(20, 4), default=0, nullable=False)
    pnl_percentage = Column(Numeric(10, 4), default=0, nullable=False)
    day_pnl = Column(Numeric(20, 4), nullable=True)
    unrealized_pnl = Column(Numeric(20, 4), nullable=True)
    realized_pnl = Column(Numeric(20, 4), nullable=True)
    
    # Buy/Sell values
    buy_value = Column(Numeric(20, 4), default=0, nullable=False)
    sell_value = Column(Numeric(20, 4), default=0, nullable=False)
    
    # Reconciliation tracking
    last_reconciled_at = Column(DateTime, nullable=True)
    reconciliation_status = Column(String(20), default="matched", nullable=False)
    discrepancy = Column(JSON, nullable=True)
    
    # Metadata
    broker_position_id = Column(String(100), nullable=True)
    metadata = Column(JSON, default=dict)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    connection = relationship("BrokerConnection", back_populates="positions")
    
    __table_args__ = (
        Index('idx_broker_positions_user_symbol', 'user_id', 'symbol'),
        Index('idx_broker_positions_connection', 'connection_id', 'symbol'),
        Index('idx_broker_positions_reconciliation', 'reconciliation_status', 'last_reconciled_at'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation"""
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "connection_id": str(self.connection_id),
            "symbol": self.symbol,
            "exchange": self.exchange,
            "product_type": self.product_type.value,
            "quantity": float(self.quantity) if self.quantity else None,
            "buy_quantity": float(self.buy_quantity) if self.buy_quantity else None,
            "sell_quantity": float(self.sell_quantity) if self.sell_quantity else None,
            "average_price": float(self.average_price) if self.average_price else None,
            "last_price": float(self.last_price) if self.last_price else None,
            "pnl": float(self.pnl) if self.pnl else None,
            "pnl_percentage": float(self.pnl_percentage) if self.pnl_percentage else None,
            "day_pnl": float(self.day_pnl) if self.day_pnl else None,
            "unrealized_pnl": float(self.unrealized_pnl) if self.unrealized_pnl else None,
            "realized_pnl": float(self.realized_pnl) if self.realized_pnl else None,
            "buy_value": float(self.buy_value) if self.buy_value else None,
            "sell_value": float(self.sell_value) if self.sell_value else None,
            "last_reconciled_at": self.last_reconciled_at.isoformat() if self.last_reconciled_at else None,
            "reconciliation_status": self.reconciliation_status,
            "discrepancy": self.discrepancy,
            "broker_position_id": self.broker_position_id,
            "metadata": self.metadata,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class SymbolMapping(Base):
    """
    Symbol normalization mappings per broker.
    
    Maps broker-specific symbols to standard EXCHANGE:SYMBOL format.
    """
    __tablename__ = "symbol_mappings"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    broker_type = Column(SQLEnum(BrokerType), nullable=False, index=True)
    
    # Symbol mappings
    broker_symbol = Column(String(100), nullable=False, index=True)
    standard_symbol = Column(String(100), nullable=False, index=True)  # EXCHANGE:SYMBOL format
    
    # Symbol details
    exchange = Column(String(20), nullable=False)
    name = Column(String(200), nullable=True)
    instrument_type = Column(String(50), nullable=True)  # EQ, FUT, OPT, etc.
    expiry_date = Column(DateTime, nullable=True)
    strike_price = Column(Numeric(20, 4), nullable=True)
    option_type = Column(String(10), nullable=True)  # CE, PE
    lot_size = Column(Integer, nullable=True)
    tick_size = Column(Numeric(20, 4), nullable=True)
    
    # Metadata
    is_active = Column(Boolean, default=True, nullable=False)
    broker_metadata = Column(JSON, default=dict)
    last_updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index('idx_symbol_mappings_broker', 'broker_type', 'broker_symbol'),
        Index('idx_symbol_mappings_standard', 'standard_symbol'),
        Index('idx_symbol_mappings_search', 'exchange', 'name'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation"""
        return {
            "id": str(self.id),
            "broker_type": self.broker_type.value,
            "broker_symbol": self.broker_symbol,
            "standard_symbol": self.standard_symbol,
            "exchange": self.exchange,
            "name": self.name,
            "instrument_type": self.instrument_type,
            "expiry_date": self.expiry_date.isoformat() if self.expiry_date else None,
            "strike_price": float(self.strike_price) if self.strike_price else None,
            "option_type": self.option_type,
            "lot_size": self.lot_size,
            "tick_size": float(self.tick_size) if self.tick_size else None,
            "is_active": self.is_active,
            "broker_metadata": self.broker_metadata,
            "last_updated_at": self.last_updated_at.isoformat() if self.last_updated_at else None
        }


class BrokerErrorLog(Base):
    """
    Broker error logging for debugging and monitoring.
    """
    __tablename__ = "broker_error_logs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    connection_id = Column(UUID(as_uuid=True), ForeignKey("broker_connections.id"), nullable=True, index=True)
    
    # Error details
    error_type = Column(SQLEnum(BrokerErrorType), nullable=False)
    broker_error_code = Column(String(100), nullable=True)
    broker_error_message = Column(Text, nullable=True)
    
    # Context
    operation = Column(String(50), nullable=False)  # place_order, cancel_order, etc.
    request_data = Column(JSON, nullable=True)
    response_data = Column(JSON, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    __table_args__ = (
        Index('idx_broker_errors_user_type', 'user_id', 'error_type'),
        Index('idx_broker_errors_created', 'created_at'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation"""
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "connection_id": str(self.connection_id) if self.connection_id else None,
            "error_type": self.error_type.value,
            "broker_error_code": self.broker_error_code,
            "broker_error_message": self.broker_error_message,
            "operation": self.operation,
            "request_data": self.request_data,
            "response_data": self.response_data,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class ReconciliationLog(Base):
    """
    Position reconciliation audit log.
    """
    __tablename__ = "reconciliation_logs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    connection_id = Column(UUID(as_uuid=True), ForeignKey("broker_connections.id"), nullable=False, index=True)
    
    # Reconciliation results
    positions_matched = Column(Integer, default=0, nullable=False)
    positions_mismatched = Column(Integer, default=0, nullable=False)
    positions_missing = Column(Integer, default=0, nullable=False)
    
    # Discrepancy details
    discrepancies = Column(JSON, default=list)
    
    # Status
    status = Column(String(20), nullable=False)  # success, partial, failed
    error_message = Column(Text, nullable=True)
    
    # Timestamps
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    
    __table_args__ = (
        Index('idx_reconciliation_logs_user', 'user_id', 'started_at'),
        Index('idx_reconciliation_logs_status', 'status'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation"""
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "connection_id": str(self.connection_id),
            "positions_matched": self.positions_matched,
            "positions_mismatched": self.positions_mismatched,
            "positions_missing": self.positions_missing,
            "discrepancies": self.discrepancies,
            "status": self.status,
            "error_message": self.error_message,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None
        }
