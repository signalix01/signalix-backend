"""
Webhook Models

Database models for Integration Service webhooks, signals, and logs.
Requirements: 1.1, 1.6, 2.1, 3.1, 17.1, 17.7
"""

from enum import Enum
from datetime import datetime
from typing import Optional, Dict, Any, List
from uuid import uuid4

from sqlalchemy import Column, String, DateTime, Boolean, JSON, Integer, Float, Enum as SQLEnum, Text, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class IntegrationType(str, Enum):
    """Supported integration types"""
    TRADINGVIEW = "tradingview"
    AMIBROKER = "amibroker"
    CHARTINK = "chartink"


class SignalAction(str, Enum):
    """Signal action types"""
    BUY = "buy"
    SELL = "sell"
    EXIT_LONG = "exit_long"
    EXIT_SHORT = "exit_short"


class SignalStatus(str, Enum):
    """Signal processing status"""
    PENDING = "pending"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"
    FORWARDED = "forwarded"
    EXECUTED = "executed"
    REJECTED = "rejected"


class WebhookStatus(str, Enum):
    """Webhook processing status"""
    RECEIVED = "received"
    VALIDATED = "validated"
    QUEUED = "queued"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"
    RETRYING = "retrying"
    DEAD_LETTER = "dead_letter"


class WebhookConfig(Base):
    """
    Webhook configuration for external integrations
    
    Stores webhook URLs, secrets, and configuration settings for
    TradingView, Amibroker, and ChartInk integrations.
    """
    __tablename__ = "webhook_configs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    integration_type = Column(SQLEnum(IntegrationType), nullable=False, index=True)
    
    # Webhook settings
    webhook_url = Column(String(255), nullable=False, unique=True)
    secret_key = Column(String(255), nullable=False)  # Encrypted
    enabled = Column(Boolean, default=True, nullable=False)
    
    # Rate limiting settings
    rate_limit_per_minute = Column(Integer, default=100, nullable=False)
    
    # Alert settings
    send_confirmation = Column(Boolean, default=True, nullable=False)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_used_at = Column(DateTime, nullable=True)
    
    # Relationships
    logs = relationship("WebhookLog", back_populates="config", lazy="dynamic")
    
    __table_args__ = (
        Index('idx_webhook_configs_user_integration', 'user_id', 'integration_type'),
        Index('idx_webhook_configs_enabled', 'enabled'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation"""
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "integration_type": self.integration_type.value,
            "webhook_url": self.webhook_url,
            "enabled": self.enabled,
            "rate_limit_per_minute": self.rate_limit_per_minute,
            "send_confirmation": self.send_confirmation,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None
        }


class Signal(Base):
    """
    Trading signal extracted from webhooks
    
    Stores parsed signals from TradingView, Amibroker, and ChartInk
    with full parameter details for execution.
    """
    __tablename__ = "signals"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    integration_type = Column(SQLEnum(IntegrationType), nullable=False, index=True)
    
    # Signal details
    symbol = Column(String(50), nullable=False, index=True)
    action = Column(SQLEnum(SignalAction), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    price = Column(Float, nullable=True)  # Optional limit price
    order_type = Column(String(20), nullable=False, default="MARKET")
    product_type = Column(String(20), nullable=False, default="INTRADAY")
    
    # Additional parameters (custom fields from various integrations)
    parameters = Column(JSON, default=dict)
    
    # Status tracking
    status = Column(SQLEnum(SignalStatus), default=SignalStatus.PENDING, nullable=False, index=True)
    
    # Timing
    received_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    processed_at = Column(DateTime, nullable=True)
    executed_at = Column(DateTime, nullable=True)
    
    # Execution tracking
    execution_result = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0, nullable=False)
    
    # Webhook reference
    webhook_log_id = Column(UUID(as_uuid=True), ForeignKey("webhook_logs.id"), nullable=True)
    
    # Relationships
    webhook_log = relationship("WebhookLog", back_populates="signal")
    
    __table_args__ = (
        Index('idx_signals_user_status', 'user_id', 'status'),
        Index('idx_signals_symbol_action', 'symbol', 'action'),
        Index('idx_signals_received_at', 'received_at'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation"""
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "integration_type": self.integration_type.value,
            "symbol": self.symbol,
            "action": self.action.value,
            "quantity": self.quantity,
            "price": self.price,
            "order_type": self.order_type,
            "product_type": self.product_type,
            "parameters": self.parameters,
            "status": self.status.value,
            "received_at": self.received_at.isoformat() if self.received_at else None,
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
            "execution_result": self.execution_result,
            "error_message": self.error_message,
            "retry_count": self.retry_count,
            "webhook_log_id": str(self.webhook_log_id) if self.webhook_log_id else None
        }


class WebhookLog(Base):
    """
    Webhook request logging for audit and debugging
    
    Stores all webhook requests with payload, signature validation,
    and processing results for compliance and troubleshooting.
    """
    __tablename__ = "webhook_logs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    integration_type = Column(SQLEnum(IntegrationType), nullable=False, index=True)
    config_id = Column(UUID(as_uuid=True), ForeignKey("webhook_configs.id"), nullable=True, index=True)
    
    # Request details
    payload = Column(JSON, nullable=False)  # Sanitized payload
    raw_payload = Column(Text, nullable=True)  # Raw payload (encrypted)
    headers = Column(JSON, nullable=True)  # Request headers (sanitized)
    
    # Signature validation
    signature = Column(String(255), nullable=True)
    signature_valid = Column(Boolean, nullable=True)
    timestamp = Column(DateTime, nullable=True)
    timestamp_valid = Column(Boolean, nullable=True)
    
    # Processing status
    status = Column(SQLEnum(WebhookStatus), default=WebhookStatus.RECEIVED, nullable=False, index=True)
    
    # Rate limiting
    rate_limit_checked = Column(Boolean, default=False, nullable=False)
    rate_limit_exceeded = Column(Boolean, default=False, nullable=False)
    
    # Error tracking
    error_message = Column(Text, nullable=True)
    validation_errors = Column(JSON, nullable=True)
    
    # Performance metrics
    processing_time_ms = Column(Integer, nullable=True)
    queue_time_ms = Column(Integer, nullable=True)
    
    # Source information
    source_ip = Column(String(45), nullable=True, index=True)  # IPv6 compatible
    
    # Timing
    received_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    validated_at = Column(DateTime, nullable=True)
    queued_at = Column(DateTime, nullable=True)
    processed_at = Column(DateTime, nullable=True)
    
    # Relationships
    config = relationship("WebhookConfig", back_populates="logs")
    signal = relationship("Signal", back_populates="webhook_log", uselist=False)
    
    __table_args__ = (
        Index('idx_webhook_logs_user_integration', 'user_id', 'integration_type'),
        Index('idx_webhook_logs_status', 'status'),
        Index('idx_webhook_logs_source_ip', 'source_ip'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation"""
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "integration_type": self.integration_type.value,
            "config_id": str(self.config_id) if self.config_id else None,
            "payload": self.payload,
            "signature_valid": self.signature_valid,
            "timestamp_valid": self.timestamp_valid,
            "status": self.status.value,
            "rate_limit_exceeded": self.rate_limit_exceeded,
            "error_message": self.error_message,
            "processing_time_ms": self.processing_time_ms,
            "queue_time_ms": self.queue_time_ms,
            "source_ip": self.source_ip,
            "received_at": self.received_at.isoformat() if self.received_at else None,
            "processed_at": self.processed_at.isoformat() if self.processed_at else None
        }


class DeadLetterWebhook(Base):
    """
    Dead letter queue for failed webhooks
    
    Stores webhooks that failed after all retry attempts
    for manual investigation and replay.
    """
    __tablename__ = "dead_letter_webhooks"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    original_log_id = Column(UUID(as_uuid=True), ForeignKey("webhook_logs.id"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    integration_type = Column(SQLEnum(IntegrationType), nullable=False)
    
    # Failure details
    failure_reason = Column(Text, nullable=False)
    retry_count = Column(Integer, default=0, nullable=False)
    last_error = Column(Text, nullable=True)
    
    # Original data
    payload = Column(JSON, nullable=False)
    
    # Replay tracking
    replayed = Column(Boolean, default=False, nullable=False)
    replayed_at = Column(DateTime, nullable=True)
    replay_result = Column(JSON, nullable=True)
    
    # Timing
    failed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index('idx_dead_letter_user', 'user_id'),
        Index('idx_dead_letter_replayed', 'replayed'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation"""
        return {
            "id": str(self.id),
            "original_log_id": str(self.original_log_id),
            "user_id": str(self.user_id),
            "integration_type": self.integration_type.value,
            "failure_reason": self.failure_reason,
            "retry_count": self.retry_count,
            "last_error": self.last_error,
            "replayed": self.replayed,
            "replayed_at": self.replayed_at.isoformat() if self.replayed_at else None,
            "replay_result": self.replay_result,
            "failed_at": self.failed_at.isoformat() if self.failed_at else None
        }
