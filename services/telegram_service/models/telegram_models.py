"""
Telegram Service Models

Database models for Telegram Bot Service.
Requirements: 8.1, 9.1, 24.1, 24.3
"""

import enum
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List

from sqlalchemy import (
    Column, String, Integer, Boolean, DateTime, Text, 
    ForeignKey, Enum, Float, JSON, Index
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class ConnectionStatus(str, enum.Enum):
    """Telegram connection status"""
    PENDING = "pending"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    REVOKED = "revoked"


class CommandType(str, enum.Enum):
    """Telegram command types"""
    BUY = "buy"
    SELL = "sell"
    POSITIONS = "positions"
    ORDERS = "orders"
    CANCEL = "cancel"
    STATUS = "status"
    HELP = "help"
    START = "start"
    AUTH = "auth"
    UNKNOWN = "unknown"


class OrderPromptStatus(str, enum.Enum):
    """Order confirmation prompt status"""
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    EXECUTED = "executed"


class TelegramConnection(Base):
    """Telegram user connection to SignalixAI account"""
    __tablename__ = "telegram_connections"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    telegram_user_id = Column(String(50), nullable=False, index=True, unique=True)
    telegram_username = Column(String(100), nullable=True)
    telegram_first_name = Column(String(100), nullable=True)
    telegram_last_name = Column(String(100), nullable=True)
    
    # Authentication
    auth_token = Column(String(100), nullable=True, index=True)
    auth_token_expires_at = Column(DateTime, nullable=True)
    auth_attempts = Column(Integer, default=0)
    auth_blocked_until = Column(DateTime, nullable=True)
    
    # Connection status
    status = Column(Enum(ConnectionStatus), default=ConnectionStatus.PENDING, nullable=False)
    connected_at = Column(DateTime, nullable=True)
    disconnected_at = Column(DateTime, nullable=True)
    last_activity_at = Column(DateTime, default=datetime.utcnow)
    
    # Session management
    session_expires_at = Column(DateTime, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    preferences = relationship("TelegramPreferences", back_populates="connection", uselist=False, cascade="all, delete-orphan")
    command_logs = relationship("TelegramCommandLog", back_populates="connection", cascade="all, delete-orphan")
    order_prompts = relationship("TelegramOrderPrompt", back_populates="connection", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_telegram_user_lookup', 'telegram_user_id', 'status'),
        Index('idx_telegram_auth_token', 'auth_token', 'auth_token_expires_at'),
    )


class TelegramPreferences(Base):
    """User preferences for Telegram notifications"""
    __tablename__ = "telegram_preferences"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connection_id = Column(UUID(as_uuid=True), ForeignKey("telegram_connections.id"), nullable=False, unique=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    
    # Notification settings
    order_notifications = Column(Boolean, default=True, nullable=False)
    execution_notifications = Column(Boolean, default=True, nullable=False)
    rejection_notifications = Column(Boolean, default=True, nullable=False)
    position_notifications = Column(Boolean, default=False, nullable=False)
    system_notifications = Column(Boolean, default=True, nullable=False)
    
    # Alert settings
    batch_notifications = Column(Boolean, default=True, nullable=False)
    batch_window_seconds = Column(Integer, default=5, nullable=False)
    
    # Command settings
    require_confirmation = Column(Boolean, default=True, nullable=False)
    confirmation_timeout_seconds = Column(Integer, default=60, nullable=False)
    
    # Rate limiting
    rate_limit_per_minute = Column(Integer, default=10, nullable=False)
    
    # Message formatting
    use_emojis = Column(Boolean, default=True, nullable=False)
    use_monospace_for_numbers = Column(Boolean, default=True, nullable=False)
    timezone = Column(String(50), default="UTC", nullable=False)
    
    # Symbol filter
    enabled_symbols = Column(JSONB, default=list, nullable=True)
    disabled_symbols = Column(JSONB, default=list, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    connection = relationship("TelegramConnection", back_populates="preferences")


class TelegramCommandLog(Base):
    """Log of Telegram commands executed"""
    __tablename__ = "telegram_command_logs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connection_id = Column(UUID(as_uuid=True), ForeignKey("telegram_connections.id"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    telegram_user_id = Column(String(50), nullable=False, index=True)
    
    # Command details
    command_type = Column(Enum(CommandType), nullable=False, index=True)
    command_text = Column(Text, nullable=False)
    parsed_parameters = Column(JSONB, default=dict, nullable=True)
    
    # Execution details
    executed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    execution_time_ms = Column(Integer, nullable=True)
    success = Column(Boolean, nullable=False)
    error_message = Column(Text, nullable=True)
    response_text = Column(Text, nullable=True)
    
    # Rate limiting
    rate_limited = Column(Boolean, default=False, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    connection = relationship("TelegramConnection", back_populates="command_logs")
    
    __table_args__ = (
        Index('idx_command_log_user_time', 'user_id', 'executed_at'),
        Index('idx_command_log_type_time', 'command_type', 'executed_at'),
    )


class TelegramOrderPrompt(Base):
    """Order confirmation prompts sent via Telegram"""
    __tablename__ = "telegram_order_prompts"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connection_id = Column(UUID(as_uuid=True), ForeignKey("telegram_connections.id"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    telegram_message_id = Column(String(50), nullable=True, index=True)
    
    # Order details
    symbol = Column(String(50), nullable=False)
    action = Column(String(20), nullable=False)
    quantity = Column(Integer, nullable=False)
    order_type = Column(String(20), nullable=False)
    price = Column(Float, nullable=True)
    trigger_price = Column(Float, nullable=True)
    product_type = Column(String(20), default="INTRADAY", nullable=False)
    
    # Prompt status
    status = Column(Enum(OrderPromptStatus), default=OrderPromptStatus.PENDING, nullable=False)
    
    # Timing
    sent_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    responded_at = Column(DateTime, nullable=True)
    executed_at = Column(DateTime, nullable=True)
    
    # Response
    response_action = Column(String(20), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    connection = relationship("TelegramConnection", back_populates="order_prompts")
    
    __table_args__ = (
        Index('idx_order_prompt_status', 'status', 'expires_at'),
        Index('idx_order_prompt_user', 'user_id', 'created_at'),
    )


class TelegramAuthToken(Base):
    """One-time authentication tokens for Telegram linking"""
    __tablename__ = "telegram_auth_tokens"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    token = Column(String(100), nullable=False, unique=True, index=True)
    
    # Token validity
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    used_by_telegram_user_id = Column(String(50), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index('idx_auth_token_lookup', 'token', 'expires_at'),
    )


# Pydantic models for API
from pydantic import BaseModel, Field, validator
from typing import Optional


class TelegramConnectionCreate(BaseModel):
    """Request to create Telegram connection"""
    user_id: str
    

class TelegramConnectionResponse(BaseModel):
    """Telegram connection response"""
    id: str
    user_id: str
    telegram_user_id: Optional[str]
    telegram_username: Optional[str]
    status: str
    connected_at: Optional[datetime]
    last_activity_at: Optional[datetime]
    created_at: datetime
    
    class Config:
        from_attributes = True


class TelegramPreferencesUpdate(BaseModel):
    """Update Telegram preferences"""
    order_notifications: Optional[bool] = None
    execution_notifications: Optional[bool] = None
    rejection_notifications: Optional[bool] = None
    position_notifications: Optional[bool] = None
    system_notifications: Optional[bool] = None
    batch_notifications: Optional[bool] = None
    require_confirmation: Optional[bool] = None
    use_emojis: Optional[bool] = None
    timezone: Optional[str] = None


class TelegramPreferencesResponse(BaseModel):
    """Telegram preferences response"""
    id: str
    user_id: str
    order_notifications: bool
    execution_notifications: bool
    rejection_notifications: bool
    position_notifications: bool
    system_notifications: bool
    batch_notifications: bool
    batch_window_seconds: int
    require_confirmation: bool
    confirmation_timeout_seconds: int
    rate_limit_per_minute: int
    use_emojis: bool
    use_monospace_for_numbers: bool
    timezone: str
    
    class Config:
        from_attributes = True


class AuthTokenResponse(BaseModel):
    """Authentication token response"""
    token: str
    expires_at: datetime
    qr_code_url: Optional[str] = None
    bot_username: str
    connect_url: str


class CommandExecutionResult(BaseModel):
    """Command execution result"""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    execution_time_ms: Optional[int] = None


class OrderAlertRequest(BaseModel):
    """Request to send order alert"""
    user_id: str
    order_id: str
    symbol: str
    action: str
    quantity: int
    order_type: str
    price: Optional[float] = None
    status: str
    message: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class NotificationBatch(BaseModel):
    """Batch of notifications to send"""
    user_id: str
    notifications: List[OrderAlertRequest]
    batch_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
