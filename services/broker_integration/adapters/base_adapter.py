"""
Enhanced Base Broker Adapter Interface

All broker adapters must implement this interface to ensure consistent behavior
across different brokers and markets.

Requirements: 10.2, 10.4, 10.5, 16.1, 16.2, 16.3, 16.7, 16.8, 25.1, 25.2, 25.5, 25.7
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional, List, Dict, Any, Tuple
from pydantic import BaseModel, Field
from datetime import datetime
import logging
import asyncio
import random

logger = logging.getLogger(__name__)


class OrderType(str, Enum):
    """Normalized order type enumeration"""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_LOSS = "STOP_LOSS"
    STOP_LOSS_MARKET = "STOP_LOSS_MARKET"
    STOP_LOSS_LIMIT = "STOP_LOSS_LIMIT"


class OrderSide(str, Enum):
    """Normalized order side enumeration"""
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, Enum):
    """Normalized order status enumeration"""
    PENDING = "PENDING"
    OPEN = "OPEN"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class ProductType(str, Enum):
    """Normalized product type for Indian markets"""
    DELIVERY = "DELIVERY"  # Cash & Carry / CNC
    INTRADAY = "INTRADAY"  # MIS
    MARGIN = "MARGIN"      # NRML for F&O
    BO = "BO"              # Bracket Order
    CO = "CO"              # Cover Order


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


class Order(BaseModel):
    """Normalized order representation"""
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
    """Normalized position representation"""
    symbol: str
    exchange: str
    product_type: ProductType
    quantity: float  # Positive for long, negative for short
    average_price: float
    last_price: float
    pnl: float
    pnl_percentage: float
    day_pnl: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    realized_pnl: Optional[float] = None
    
    # Additional fields
    buy_quantity: float = 0.0
    sell_quantity: float = 0.0
    buy_value: float = 0.0
    sell_value: float = 0.0
    
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MarginInfo(BaseModel):
    """Normalized margin/account balance information"""
    available_cash: float
    used_margin: float
    total_margin: float
    
    # Additional fields
    collateral: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    realized_pnl: Optional[float] = None
    
    # Broker-specific fields
    metadata: Dict[str, Any] = Field(default_factory=dict)


class BrokerError(BaseModel):
    """Standardized broker error"""
    error_type: BrokerErrorType
    message: str
    broker_error_code: Optional[str] = None
    broker_error_message: Optional[str] = None
    retryable: bool = False
    
    # Context
    operation: Optional[str] = None
    request_data: Optional[Dict[str, Any]] = None


class ConnectionStatus(BaseModel):
    """Connection status information"""
    connected: bool
    authenticated: bool
    last_connected: Optional[datetime] = None
    last_error: Optional[str] = None
    error_count: int = 0
    websocket_connected: bool = False
    

class EnhancedBrokerAdapter(ABC):
    """
    Enhanced abstract base class for all broker adapters.
    
    Implements:
    - Retry logic with exponential backoff (Requirement 10.6, 41.1, 41.2)
    - Error normalization (Requirement 16.4, 16.5, 44.1, 44.2)
    - Symbol normalization (Requirement 10.5, 35.1, 35.2)
    - Connection health monitoring (Requirement 20.3, 20.4, 20.5)
    """
    
    # Retry configuration
    MAX_RETRIES = 3
    BASE_DELAY = 1.0  # seconds
    MAX_DELAY = 10.0  # seconds
    JITTER_RANGE = 0.5  # +/- 50%
    
    def __init__(self, config: Dict[str, Any], paper_trading: bool = False):
        """
        Initialize the broker adapter.
        
        Args:
            config: Broker-specific configuration (API keys, endpoints, etc.)
            paper_trading: If True, use paper trading mode (simulated execution)
        """
        self.config = config
        self.paper_trading = paper_trading
        self.connection_status = ConnectionStatus(connected=False, authenticated=False)
        self._validate_config()
        
        # Error mapping for this broker
        self._error_mapping = self._get_error_mapping()
    
    @abstractmethod
    def _validate_config(self) -> None:
        """Validate the configuration. Raise ValueError if invalid."""
        pass
    
    @abstractmethod
    def _get_error_mapping(self) -> Dict[str, BrokerErrorType]:
        """
        Get error code mapping for this broker.
        
        Returns:
            Dictionary mapping broker error codes to BrokerErrorType
        """
        pass
    
    @abstractmethod
    async def _connect_internal(self) -> bool:
        """
        Internal connect implementation. Must be implemented by subclasses.
        
        Returns:
            True if connection successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def _disconnect_internal(self) -> None:
        """Internal disconnect implementation."""
        pass
    
    async def connect(self) -> bool:
        """
        Establish connection to the broker with retry logic.
        
        Returns:
            True if connection successful, False otherwise
        """
        return await self._execute_with_retry(
            self._connect_internal,
            operation="connect",
            retryable_errors=[BrokerErrorType.NETWORK_ERROR, BrokerErrorType.BROKER_ERROR]
        )
    
    async def disconnect(self) -> None:
        """Close connection to the broker."""
        try:
            await self._disconnect_internal()
        except Exception as e:
            logger.warning(f"Error during disconnect: {e}")
        finally:
            self.connection_status.connected = False
            self.connection_status.authenticated = False
    
    async def _execute_with_retry(
        self,
        operation_func,
        operation: str,
        retryable_errors: List[BrokerErrorType] = None,
        *args,
        **kwargs
    ) -> Any:
        """
        Execute an operation with retry logic.
        
        Implements exponential backoff with jitter as per requirements:
        - 10.6: Retry failed API calls up to 3 times
        - 41.1: Use exponential backoff with jitter
        - 41.2: Distinguish retryable vs non-retryable errors
        
        Args:
            operation_func: The async function to execute
            operation: Operation name for logging
            retryable_errors: List of error types that should trigger a retry
            *args, **kwargs: Arguments to pass to operation_func
            
        Returns:
            Result of operation_func
            
        Raises:
            BrokerError: If all retries exhausted or non-retryable error
        """
        retryable_errors = retryable_errors or [
            BrokerErrorType.NETWORK_ERROR,
            BrokerErrorType.RATE_LIMIT_EXCEEDED,
            BrokerErrorType.BROKER_ERROR
        ]
        
        last_error = None
        
        for attempt in range(self.MAX_RETRIES):
            try:
                result = await operation_func(*args, **kwargs)
                
                # Update connection status on success
                if operation == "connect":
                    self.connection_status.connected = True
                    self.connection_status.authenticated = True
                    self.connection_status.last_connected = datetime.utcnow()
                    self.connection_status.error_count = 0
                
                return result
                
            except Exception as e:
                broker_error = self._normalize_error(e, operation)
                last_error = broker_error
                
                # Check if error is retryable
                if broker_error.error_type not in retryable_errors:
                    logger.warning(f"Non-retryable error in {operation}: {broker_error.message}")
                    raise self._create_exception_from_error(broker_error)
                
                # Don't retry on last attempt
                if attempt == self.MAX_RETRIES - 1:
                    logger.error(f"All retries exhausted for {operation}: {broker_error.message}")
                    break
                
                # Calculate delay with exponential backoff and jitter
                delay = min(self.BASE_DELAY * (2 ** attempt), self.MAX_DELAY)
                jitter = delay * self.JITTER_RANGE * (2 * random.random() - 1)
                actual_delay = delay + jitter
                
                logger.warning(
                    f"Retry {attempt + 1}/{self.MAX_RETRIES} for {operation} "
                    f"after {actual_delay:.2f}s due to: {broker_error.message}"
                )
                
                await asyncio.sleep(actual_delay)
        
        # All retries exhausted
        self.connection_status.error_count += 1
        if self.connection_status.error_count >= 3:
            self.connection_status.connected = False
            self.connection_status.last_error = last_error.message if last_error else "Unknown error"
        
        raise self._create_exception_from_error(last_error) if last_error else Exception("Unknown error")
    
    def _normalize_error(self, error: Exception, operation: str) -> BrokerError:
        """
        Normalize broker-specific errors to standard error types.
        
        Requirements: 16.4, 16.5, 44.1, 44.2, 44.3, 44.4
        
        Args:
            error: The exception from the broker
            operation: The operation that failed
            
        Returns:
            Standardized BrokerError
        """
        error_message = str(error).lower()
        broker_code = None
        
        # Extract broker error code if available
        if hasattr(error, 'response') and hasattr(error.response, 'json'):
            try:
                data = error.response.json()
                broker_code = data.get('code') or data.get('error_code') or data.get('status')
            except:
                pass
        
        # Map to standard error type
        if broker_code and broker_code in self._error_mapping:
            error_type = self._error_mapping[broker_code]
        elif 'margin' in error_message or 'insufficient' in error_message:
            error_type = BrokerErrorType.INSUFFICIENT_MARGIN
        elif 'symbol' in error_message or 'scrip' in error_message or 'instrument' in error_message:
            error_type = BrokerErrorType.INVALID_SYMBOL
        elif 'market' in error_message and ('closed' in error_message or 'not open' in error_message):
            error_type = BrokerErrorType.MARKET_CLOSED
        elif 'rate' in error_message and ('limit' in error_message or 'throttle' in error_message):
            error_type = BrokerErrorType.RATE_LIMIT_EXCEEDED
        elif 'session' in error_message and ('expired' in error_message or 'invalid' in error_message):
            error_type = BrokerErrorType.SESSION_EXPIRED
        elif 'network' in error_message or 'timeout' in error_message or 'connection' in error_message:
            error_type = BrokerErrorType.NETWORK_ERROR
        else:
            error_type = BrokerErrorType.BROKER_ERROR
        
        # Determine if error is retryable
        retryable = error_type in [
            BrokerErrorType.NETWORK_ERROR,
            BrokerErrorType.RATE_LIMIT_EXCEEDED,
            BrokerErrorType.BROKER_ERROR,
            BrokerErrorType.SESSION_EXPIRED
        ]
        
        return BrokerError(
            error_type=error_type,
            message=self._get_user_friendly_message(error_type, str(error)),
            broker_error_code=broker_code,
            broker_error_message=str(error),
            retryable=retryable,
            operation=operation
        )
    
    def _get_user_friendly_message(self, error_type: BrokerErrorType, original_message: str) -> str:
        """
        Convert error type to user-friendly message.
        
        Requirement: 44.4 - Provide user-friendly error messages
        """
        messages = {
            BrokerErrorType.INSUFFICIENT_MARGIN: "Insufficient margin for this order. Please check your available funds.",
            BrokerErrorType.INVALID_SYMBOL: "Invalid trading symbol. Please verify the symbol and exchange.",
            BrokerErrorType.MARKET_CLOSED: "Market is currently closed. Orders can only be placed during market hours.",
            BrokerErrorType.ORDER_TOO_LARGE: "Order quantity exceeds maximum allowed limit.",
            BrokerErrorType.ORDER_TOO_SMALL: "Order quantity is below minimum required limit.",
            BrokerErrorType.PRICE_OUT_OF_RANGE: "Order price is outside the allowed trading range.",
            BrokerErrorType.SESSION_EXPIRED: "Broker session expired. Please reconnect your broker.",
            BrokerErrorType.RATE_LIMIT_EXCEEDED: "Too many requests. Please wait before trying again.",
            BrokerErrorType.NETWORK_ERROR: "Network error. Please check your internet connection.",
            BrokerErrorType.BROKER_ERROR: f"Broker error: {original_message}",
            BrokerErrorType.UNKNOWN_ERROR: f"An unexpected error occurred: {original_message}"
        }
        return messages.get(error_type, original_message)
    
    def _create_exception_from_error(self, error: BrokerError) -> Exception:
        """Create an exception from BrokerError."""
        return BrokerAdapterException(
            error_type=error.error_type,
            message=error.message,
            broker_code=error.broker_error_code,
            broker_message=error.broker_error_message
        )
    
    def normalize_symbol(self, broker_symbol: str, exchange: Optional[str] = None) -> str:
        """
        Convert broker symbol to standard EXCHANGE:SYMBOL format.
        
        Requirements: 10.5, 35.1, 35.2
        
        Args:
            broker_symbol: Broker-specific symbol
            exchange: Exchange (optional)
            
        Returns:
            Standard symbol in EXCHANGE:SYMBOL format
        """
        # Base implementation - subclasses should override
        if exchange:
            return f"{exchange}:{broker_symbol}"
        return broker_symbol
    
    def denormalize_symbol(self, standard_symbol: str) -> Tuple[str, Optional[str]]:
        """
        Convert standard EXCHANGE:SYMBOL to broker-specific format.
        
        Requirements: 10.5, 35.3
        
        Args:
            standard_symbol: Standard symbol in EXCHANGE:SYMBOL format
            
        Returns:
            Tuple of (broker_symbol, exchange)
        """
        # Base implementation - subclasses should override
        if ":" in standard_symbol:
            parts = standard_symbol.split(":", 1)
            return parts[1], parts[0]
        return standard_symbol, None
    
    def normalize_order_response(self, broker_response: Dict[str, Any]) -> Order:
        """
        Normalize broker order response to standard Order format.
        
        Requirements: 10.4, 16.1, 16.2, 16.7, 16.8
        
        Args:
            broker_response: Raw broker response
            
        Returns:
            Normalized Order object
        """
        # Base implementation - subclasses must override
        raise NotImplementedError("Subclasses must implement normalize_order_response")
    
    def normalize_position_response(self, broker_response: Dict[str, Any]) -> Position:
        """
        Normalize broker position response to standard Position format.
        
        Requirements: 16.7, 16.8
        
        Args:
            broker_response: Raw broker response
            
        Returns:
            Normalized Position object
        """
        # Base implementation - subclasses must override
        raise NotImplementedError("Subclasses must implement normalize_position_response")
    
    @abstractmethod
    async def place_order(self, order: Order) -> Order:
        """Place an order with the broker."""
        pass
    
    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order."""
        pass
    
    @abstractmethod
    async def modify_order(
        self,
        order_id: str,
        quantity: Optional[float] = None,
        price: Optional[float] = None,
        trigger_price: Optional[float] = None
    ) -> Order:
        """Modify an open order."""
        pass
    
    @abstractmethod
    async def get_order_status(self, order_id: str) -> Order:
        """Get the current status of an order."""
        pass
    
    @abstractmethod
    async def get_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """Get all orders."""
        pass
    
    @abstractmethod
    async def get_positions(self) -> List[Position]:
        """Get all open positions."""
        pass
    
    @abstractmethod
    async def get_position(self, symbol: str, exchange: str) -> Optional[Position]:
        """Get position for a specific symbol."""
        pass
    
    @abstractmethod
    async def get_margin(self) -> MarginInfo:
        """Get account margin/balance information."""
        pass
    
    @abstractmethod
    async def get_holdings(self) -> List[Position]:
        """Get long-term holdings."""
        pass
    
    def is_paper_trading(self) -> bool:
        """Check if adapter is in paper trading mode."""
        return self.paper_trading
    
    @abstractmethod
    def get_broker_name(self) -> str:
        """Get the broker name."""
        pass
    
    @abstractmethod
    def get_broker_code(self) -> str:
        """Get the broker code/identifier."""
        pass
    
    def get_capabilities(self) -> Dict[str, bool]:
        """
        Get broker capabilities.
        
        Returns:
            Dictionary of capability flags
        """
        return {
            "supports_bracket_orders": False,
            "supports_cover_orders": False,
            "supports_amo": False,
            "supports_modify_order": True,
            "supports_websocket": False,
            "supports_multiple_accounts": False
        }


class BrokerAdapterException(Exception):
    """Exception raised for broker adapter errors."""
    
    def __init__(
        self,
        error_type: BrokerErrorType,
        message: str,
        broker_code: Optional[str] = None,
        broker_message: Optional[str] = None
    ):
        self.error_type = error_type
        self.message = message
        self.broker_code = broker_code
        self.broker_message = broker_message
        super().__init__(message)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "error_type": self.error_type.value,
            "message": self.message,
            "broker_code": self.broker_code,
            "broker_message": self.broker_message
        }
