"""
Database models for Signalix Algo Builder, Backtesting, Screening & Alert Engine
"""
from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Text, JSON, Index, ForeignKey, Enum as SQLEnum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from datetime import datetime
import uuid
import enum

Base = declarative_base()


class StrategyStatus(str, enum.Enum):
    """Strategy lifecycle status"""
    DRAFT = "draft"
    TESTING = "testing"
    PAPER = "paper"
    LIVE = "live"
    DELETED = "deleted"


class AnomalyType(str, enum.Enum):
    """Types of anomalies detected"""
    PRICE_SPIKE = "price_spike"
    VOLUME_SURGE = "volume_surge"
    VOLATILITY_EXPLOSION = "volatility_explosion"
    GAP_UP = "gap_up"
    GAP_DOWN = "gap_down"
    FLASH_CRASH = "flash_crash"
    FLASH_RALLY = "flash_rally"
    UNUSUAL_PATTERN = "unusual_pattern"
    WHALE_MOVEMENT = "whale_movement"
    INSTITUTIONAL_FLOW = "institutional_flow"
    OPTIONS_UNUSUAL = "options_unusual"
    CORRELATION_BREAK = "correlation_break"
    REGIME_CHANGE = "regime_change"


class AnomalySeverity(str, enum.Enum):
    """Severity levels for anomalies"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Strategy(Base):
    """
    Stores user-defined trading strategies
    Requirements: 1.8, 1.9
    """
    __tablename__ = "strategies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    template_id = Column(UUID(as_uuid=True), nullable=True)  # If cloned from template
    
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    
    # Complete strategy specification as JSONB
    spec = Column(JSONB, nullable=False)
    
    # Compiled strategy hash for cache invalidation
    compiled_hash = Column(String(64), nullable=True, index=True)
    
    status = Column(SQLEnum(StrategyStatus), nullable=False, default=StrategyStatus.DRAFT, index=True)
    
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_strategies_user_status', 'user_id', 'status'),
    )


class BacktestResult(Base):
    """
    Stores backtest results
    Requirements: 4.1, 4.5, 4.6, 4.7, 4.8
    """
    __tablename__ = "backtest_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    strategy_id = Column(UUID(as_uuid=True), ForeignKey('strategies.id'), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    
    instrument = Column(String(50), nullable=False)
    asset_class = Column(String(20), nullable=False)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    mode = Column(String(20), nullable=False)  # vectorised or event_driven
    
    # Core performance metrics
    total_return_pct = Column(Float, nullable=True)
    cagr_pct = Column(Float, nullable=True)
    sharpe_ratio = Column(Float, nullable=True)
    sortino_ratio = Column(Float, nullable=True)
    calmar_ratio = Column(Float, nullable=True)
    max_drawdown_pct = Column(Float, nullable=True)
    avg_drawdown_pct = Column(Float, nullable=True)
    max_drawdown_duration_days = Column(Integer, nullable=True)
    
    # Trade statistics
    total_trades = Column(Integer, nullable=True)
    win_rate_pct = Column(Float, nullable=True)
    avg_win_pct = Column(Float, nullable=True)
    avg_loss_pct = Column(Float, nullable=True)
    profit_factor = Column(Float, nullable=True)
    expectancy_per_trade = Column(Float, nullable=True)
    avg_hold_days = Column(Float, nullable=True)
    max_consecutive_losses = Column(Integer, nullable=True)
    
    # Risk metrics
    kelly_fraction = Column(Float, nullable=True)
    half_kelly = Column(Float, nullable=True)
    
    # Walk-forward results
    wf_train_return = Column(Float, nullable=True)
    wf_validate_return = Column(Float, nullable=True)
    wf_test_return = Column(Float, nullable=True)
    wf_consistency_score = Column(Float, nullable=True)
    
    # Regime analysis
    trending_bull_return = Column(Float, nullable=True)
    trending_bear_return = Column(Float, nullable=True)
    ranging_return = Column(Float, nullable=True)
    volatile_return = Column(Float, nullable=True)
    
    # Monte Carlo
    mc_median_return = Column(Float, nullable=True)
    mc_5th_percentile_return = Column(Float, nullable=True)
    mc_95th_percentile_return = Column(Float, nullable=True)
    mc_ruin_probability = Column(Float, nullable=True)
    
    # Full result data (trades, equity curve, etc.)
    result_data = Column(JSONB, nullable=True)
    
    status = Column(String(20), nullable=False, default='pending')  # pending, running, complete, failed
    error_message = Column(Text, nullable=True)
    
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    completed_at = Column(DateTime, nullable=True)
    
    __table_args__ = (
        Index('idx_backtest_user_created', 'user_id', 'created_at'),
        Index('idx_backtest_strategy_created', 'strategy_id', 'created_at'),
    )


class ScreeningCriteria(Base):
    """
    Stores user-defined screening criteria
    Requirements: 9.4, 10.1, 10.2, 10.3, 10.4
    """
    __tablename__ = "screening_criteria"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    template_id = Column(UUID(as_uuid=True), nullable=True)  # If cloned from template
    
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    
    # Complete criteria specification as JSONB
    criteria_spec = Column(JSONB, nullable=False)
    
    # Scheduling
    schedule_enabled = Column(Boolean, nullable=False, default=False)
    schedule_cron = Column(String(100), nullable=True)  # Cron expression
    
    is_active = Column(Boolean, nullable=False, default=True)
    
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_screening_criteria_user_active', 'user_id', 'is_active'),
    )


class ScreeningResult(Base):
    """
    Stores screening results (TimescaleDB hypertable)
    Requirements: 9.5, 9.6, 9.7, 16.3
    """
    __tablename__ = "screening_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    criteria_id = Column(UUID(as_uuid=True), ForeignKey('screening_criteria.id'), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    
    run_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)  # Partition key
    
    duration_seconds = Column(Float, nullable=True)
    instruments_scanned = Column(Integer, nullable=True)
    instruments_passed = Column(Integer, nullable=True)
    
    # Full result data
    results = Column(JSONB, nullable=True)
    
    # Cost tracking for AI scoring
    cost_usd = Column(Float, nullable=True)
    
    __table_args__ = (
        Index('idx_screening_results_criteria_run', 'criteria_id', 'run_at'),
    )


class AnomalyEvent(Base):
    """
    Stores detected anomaly events (TimescaleDB hypertable)
    Requirements: 11.5, 11.7, 16.2
    """
    __tablename__ = "anomaly_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    instrument = Column(String(50), nullable=False, index=True)
    asset_class = Column(String(20), nullable=False)
    exchange = Column(String(20), nullable=True)
    
    anomaly_type = Column(SQLEnum(AnomalyType), nullable=False, index=True)
    severity = Column(SQLEnum(AnomalySeverity), nullable=False, index=True)
    
    detected_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)  # Partition key
    
    description = Column(Text, nullable=False)
    
    # Statistical metrics
    z_score = Column(Float, nullable=True)
    price = Column(Float, nullable=True)
    volume = Column(Float, nullable=True)
    
    # Full raw data
    raw_data = Column(JSONB, nullable=True)
    
    # Affected instruments (for correlation tracking)
    affected_instruments = Column(ARRAY(String), nullable=True)
    
    __table_args__ = (
        Index('idx_anomaly_instrument_detected', 'instrument', 'detected_at'),
        Index('idx_anomaly_type_severity_detected', 'anomaly_type', 'severity', 'detected_at'),
    )


class AlertRule(Base):
    """
    Stores user-defined alert rules
    Requirements: 13.1, 13.8
    """
    __tablename__ = "alert_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    
    # Filters
    instruments = Column(ARRAY(String), nullable=False)  # ["ALL"] for all watchlisted
    asset_classes = Column(ARRAY(String), nullable=False)
    anomaly_types = Column(ARRAY(String), nullable=False)
    min_severity = Column(SQLEnum(AnomalySeverity), nullable=False, default=AnomalySeverity.MEDIUM)
    
    # Delivery channels
    channels = Column(ARRAY(String), nullable=False)  # ["in_app", "push", "email", etc.]
    
    # Rate limiting
    max_alerts_per_hour = Column(Integer, nullable=False, default=10)
    
    # Quiet hours (IST timezone)
    quiet_hours_start = Column(String(5), nullable=True)  # "22:00"
    quiet_hours_end = Column(String(5), nullable=True)    # "08:00"
    
    # Webhook configuration
    webhook_url = Column(String(500), nullable=True)
    webhook_secret = Column(String(100), nullable=True)
    
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_alert_rules_user_enabled', 'user_id', 'enabled'),
    )


class AlertDeliveryLog(Base):
    """
    Logs all alert delivery attempts
    Requirements: 14.1, 14.2, 14.3
    """
    __tablename__ = "alert_delivery_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    anomaly_event_id = Column(UUID(as_uuid=True), ForeignKey('anomaly_events.id'), nullable=False, index=True)
    alert_rule_id = Column(UUID(as_uuid=True), ForeignKey('alert_rules.id'), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    
    channel = Column(String(20), nullable=False)  # in_app, push, email, etc.
    
    status = Column(String(20), nullable=False)  # pending, sent, failed, retrying
    
    attempt_number = Column(Integer, nullable=False, default=1)
    
    delivered_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    
    # Latency tracking
    detection_to_delivery_ms = Column(Integer, nullable=True)
    
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    
    __table_args__ = (
        Index('idx_alert_delivery_user_created', 'user_id', 'created_at'),
        Index('idx_alert_delivery_event_rule', 'anomaly_event_id', 'alert_rule_id'),
    )
