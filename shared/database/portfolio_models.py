from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Integer, Boolean, text
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid
from shared.database.models import Base

class Portfolio(Base):
    __tablename__ = "portfolios"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    name = Column(String(255), nullable=False, default="Main Portfolio")
    currency = Column(String(10), nullable=False, default="INR")
    
    # Track available cash
    cash_balance = Column(Float, nullable=False, default=0.0)
    
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

class Position(Base):
    __tablename__ = "positions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=True) # Adding user_id as it is in DB
    portfolio_id = Column(UUID(as_uuid=True), nullable=True)
    
    instrument = Column(String(50), nullable=False)
    exchange = Column(String(20), nullable=True)
    direction = Column(String(10), nullable=True)
    
    quantity = Column(Integer, nullable=True)
    entry_price = Column(Float, nullable=True)
    current_price = Column(Float, nullable=True)
    
    stop_loss = Column(Float, nullable=True)
    target = Column(Float, nullable=True)
    
    pnl_rs = Column(Float, nullable=True)
    pnl_pct = Column(Float, nullable=True)
    
    is_options = Column(Boolean, nullable=True)
    strike_price = Column(Float, nullable=True)
    expiry_date = Column(String(20), nullable=True)
    option_type = Column(String(10), nullable=True)
    delta = Column(Float, nullable=True)
    gamma = Column(Float, nullable=True)
    theta = Column(Float, nullable=True)
    vega = Column(Float, nullable=True)
    
    opened_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True, onupdate=datetime.utcnow)
