import uuid
from datetime import datetime
from sqlalchemy import Column, String, Float, DateTime, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
import enum
from shared.database.models import Base

class OrderType(str, enum.Enum):
    MARKET = 'market'
    LIMIT = 'limit'
    STOP_LOSS = 'stop-loss'

class OrderSide(str, enum.Enum):
    BUY = 'BUY'
    SELL = 'SELL'

class OrderStatus(str, enum.Enum):
    PENDING = 'pending'
    FILLED = 'filled'
    CANCELLED = 'cancelled'
    REJECTED = 'rejected'

class Order(Base):
    __tablename__ = "orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=True) # Adding user_id for auth
    instrument = Column(String(50), nullable=False)
    orderType = Column(SQLEnum(OrderType, name='order_type_enum'), nullable=False)
    side = Column(SQLEnum(OrderSide, name='order_side_enum'), nullable=False)
    quantity = Column(Float, nullable=False)
    price = Column(Float, nullable=True)
    status = Column(SQLEnum(OrderStatus, name='order_status_enum'), nullable=False, default=OrderStatus.PENDING)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    fillPrice = Column(Float, nullable=True)
    fillQuantity = Column(Float, nullable=True)
    fillTime = Column(DateTime, nullable=True)
    
    signalId = Column(String(50), nullable=True)
    slippage = Column(Float, nullable=True)
    exchange = Column(String(20), nullable=True, default='NSE')
    brokerId = Column(String(50), nullable=True)
    
    def to_dict(self):
        return {
            "id": str(self.id) if self.id else None,
            "instrument": self.instrument,
            "orderType": self.orderType.value if hasattr(self.orderType, 'value') else self.orderType,
            "side": self.side.value if hasattr(self.side, 'value') else self.side,
            "quantity": self.quantity,
            "price": self.price,
            "status": self.status.value if hasattr(self.status, 'value') else self.status,
            "timestamp": self.timestamp.isoformat() + "Z" if self.timestamp else None,
            "fillPrice": self.fillPrice,
            "fillQuantity": self.fillQuantity,
            "fillTime": self.fillTime.isoformat() + "Z" if self.fillTime else None,
            "signalId": self.signalId,
            "slippage": self.slippage,
            "exchange": self.exchange,
            "brokerId": self.brokerId
        }
