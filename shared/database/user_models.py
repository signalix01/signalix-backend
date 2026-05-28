from sqlalchemy import Column, String, Integer, BigInteger, Boolean, DateTime, text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid
from shared.database.models import Base

class User(Base):
    """
    User model matching Supabase schema exactly.
    """
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("uuid_generate_v4()"))
    email = Column(String(255), unique=True, nullable=False, index=True)
    phone = Column(String(20), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    
    full_name = Column(String(255), nullable=False)
    country_of_residence = Column(String(2), nullable=False, default="IN")
    
    # Financial profile
    declared_trading_capital_inr = Column(BigInteger, nullable=False) # in paise
    risk_tolerance_score = Column(Integer, nullable=False)
    investment_horizon = Column(String(20), nullable=False)
    
    # Status
    sebi_declaration_acknowledged = Column(Boolean, nullable=False, default=False)
    email_verified = Column(Boolean, nullable=False, default=False)
    phone_verified = Column(Boolean, nullable=False, default=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=False), nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime(timezone=False), nullable=False, server_default=text("now()"))

class Watchlist(Base):
    __tablename__ = "watchlists"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(String(500), nullable=True)
    
    auto_scan_enabled = Column(Boolean, default=False)
    
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

class WatchlistInstrument(Base):
    __tablename__ = "watchlist_instruments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    watchlist_id = Column(UUID(as_uuid=True), ForeignKey("watchlists.id"), nullable=False, index=True)
    symbol = Column(String(50), nullable=False)
    name = Column(String(255), nullable=True)
    
    added_at = Column(DateTime, nullable=False, default=datetime.utcnow)
