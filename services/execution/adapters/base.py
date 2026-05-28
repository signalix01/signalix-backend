"""
Base broker adapter interface.

All broker adapters must implement this interface to ensure consistent behavior
across different brokers and markets.
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class OrderType(str, Enum):
    """Order type enumeration"""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_LOSS = "STOP_LOSS"
    STOP_LOSS_LIMIT = "STOP_LOSS_LIMIT"


class OrderSide(str, Enum):
    """Order side enumeration"""
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, Enum):
    """Order status enumeration"""
    PENDING = "PENDING"
    OPEN = "OPEN"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class ProductType(str, Enum):
    """Product type for Indian markets"""
    DELIVERY = "DELIVERY"  # Cash & Carry
    INTRADAY = "INTRADAY"  # MIS
    MARGIN = "MARGIN"      # NRML for F&O
    BO = "BO"              # Bracket Order
    CO = "CO"              # Cover Order


class Order(BaseModel):
    """Order representation"""
    symbol: str
    exchange: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    price: Optional[float] = None
    trigger_price: Optional[float] = None
    product_type: ProductType = ProductType.INTRADAY
    validity: str = "DAY"
    disclosed_quantity: Optional[float] = None
    
    # Order identifiers (set after placement)
    order_id: Optional[str] = None
    broker_order_id: Optional[str] = None
    
    # Order status
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: float = 0.0
    average_price: Optional[float] = None
    
    # Timestamps
    placed_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    # Additional metadata
    tag: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Position(BaseModel):
    """Position representation"""
    symbol: str
    exchange: str
    product_type: ProductType
    quantity: float  # Positive for long, negative for short
    average_price: float
    last_price: float
    pnl: float
    pnl_percentage: float
    day_pnl: Optional[float] = None
    
    # Additional fields
    buy_quantity: float = 0.0
    sell_quantity: float = 0.0
    buy_value: float = 0.0
    sell_value: float = 0.0
    
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MarginInfo(BaseModel):
    """Margin/account balance information"""
    available_cash: float
    used_margin: float
    total_margin: float
    
    # Additional fields
    collateral: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    realized_pnl: Optional[float] = None
    
    # Broker-specific fields
    metadata: Dict[str, Any] = Field(default_factory=dict)


class BrokerAdapter(ABC):
    """
    Abstract base class for all broker adapters.
    
    All adapters must implement these methods to provide a unified interface
    for order execution, position management, and account information.
    """
    
    def __init__(self, config: Dict[str, Any], paper_trading: bool = False):
        """
        Initialize the broker adapter.
        
        Args:
            config: Broker-specific configuration (API keys, endpoints, etc.)
            paper_trading: If True, use paper trading mode (simulated execution)
        """
        self.config = config
        self.paper_trading = paper_trading
        self._validate_config()
    
    @abstractmethod
    def _validate_config(self) -> None:
        """Validate the configuration. Raise ValueError if invalid."""
        pass
    
    @abstractmethod
    async def connect(self) -> bool:
        """
        Establish connection to the broker.
        
        Returns:
            True if connection successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to the broker."""
        pass
    
    @abstractmethod
    async def place_order(self, order: Order) -> Order:
        """
        Place an order with the broker.
        
        Args:
            order: Order object with order details
            
        Returns:
            Order object with broker_order_id and status updated
            
        Raises:
            Exception if order placement fails
        """
        pass
    
    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an open order.
        
        Args:
            order_id: Broker order ID or internal order ID
            
        Returns:
            True if cancellation successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def modify_order(self, order_id: str, quantity: Optional[float] = None,
                          price: Optional[float] = None,
                          trigger_price: Optional[float] = None) -> Order:
        """
        Modify an open order.
        
        Args:
            order_id: Broker order ID or internal order ID
            quantity: New quantity (optional)
            price: New price (optional)
            trigger_price: New trigger price (optional)
            
        Returns:
            Updated Order object
        """
        pass
    
    @abstractmethod
    async def get_order_status(self, order_id: str) -> Order:
        """
        Get the current status of an order.
        
        Args:
            order_id: Broker order ID or internal order ID
            
        Returns:
            Order object with current status
        """
        pass
    
    @abstractmethod
    async def get_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """
        Get all orders (optionally filtered by symbol).
        
        Args:
            symbol: Filter by symbol (optional)
            
        Returns:
            List of Order objects
        """
        pass
    
    @abstractmethod
    async def get_positions(self) -> List[Position]:
        """
        Get all open positions.
        
        Returns:
            List of Position objects
        """
        pass
    
    @abstractmethod
    async def get_position(self, symbol: str, exchange: str) -> Optional[Position]:
        """
        Get position for a specific symbol.
        
        Args:
            symbol: Symbol to query
            exchange: Exchange (NSE, BSE, NFO, etc.)
            
        Returns:
            Position object if position exists, None otherwise
        """
        pass
    
    @abstractmethod
    async def get_margin(self) -> MarginInfo:
        """
        Get account margin/balance information.
        
        Returns:
            MarginInfo object with account details
        """
        pass
    
    @abstractmethod
    async def get_holdings(self) -> List[Position]:
        """
        Get long-term holdings (delivery positions).
        
        Returns:
            List of Position objects representing holdings
        """
        pass
    
    def is_paper_trading(self) -> bool:
        """Check if adapter is in paper trading mode."""
        return self.paper_trading
    
    def get_broker_name(self) -> str:
        """Get the broker name."""
        return self.__class__.__name__.replace("Adapter", "")
