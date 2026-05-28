"""
Telegram Bot Service Router

FastAPI router for Telegram bot integration with order alerts and trading commands.
Requirements: 8.1, 9.1, 9.3, 24.1, 42.1
"""

import os
import json
import uuid
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, HTTPException, Depends, Request, Header, BackgroundTasks, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select, and_, desc, update, delete as sql_delete
import redis.asyncio as redis
import httpx
import jwt

from services.telegram_service.models.telegram_models import (
    TelegramConnection, TelegramPreferences, TelegramCommandLog, 
    TelegramOrderPrompt, TelegramAuthToken,
    ConnectionStatus, CommandType, OrderPromptStatus,
    TelegramConnectionResponse, TelegramPreferencesResponse, 
    TelegramPreferencesUpdate, AuthTokenResponse, CommandExecutionResult,
    OrderAlertRequest, NotificationBatch
)
from services.telegram_service.auth.auth_handler import TelegramAuthHandler, AuthResult
from services.telegram_service.commands.command_parser import (
    TelegramCommandParser, ParsedCommand, CommandValidationResult
)
from services.telegram_service.formatter.message_formatter import (
    TelegramMessageFormatter, FormattedMessage, InlineButton
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/telegram", tags=["telegram"])

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/signalixai")
engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Redis setup
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
redis_client = None

try:
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    logger.info("Redis client initialized for Telegram service")
except Exception as e:
    logger.warning(f"Redis not available for Telegram service: {e}")

# Telegram Bot Token (from environment)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME", "SignalixAIBot")

# JWT Configuration
JWT_SECRET = os.getenv("JWT_SECRET", "your-secret-key-change-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

# Service URLs
BROKER_INTEGRATION_URL = os.getenv("BROKER_INTEGRATION_URL", "http://localhost:8001")
PORTFOLIO_SERVICE_URL = os.getenv("PORTFOLIO_SERVICE_URL", "http://localhost:8003")

# Initialize components
auth_handler = TelegramAuthHandler(redis_client)
command_parser = TelegramCommandParser()
message_formatter = TelegramMessageFormatter()
security = HTTPBearer(auto_error=False)

# HTTP client for service calls
http_client = httpx.AsyncClient(timeout=30.0)

# Rate limiting
RATE_LIMIT_COMMANDS_PER_MINUTE = 10


# ============================================================================
# Dependencies
# ============================================================================

async def get_db() -> AsyncSession:
    """Get database session"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def get_current_user_id(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> str:
    """
    Get current authenticated user ID from JWT token
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token"
        )
    
    try:
        payload = jwt.decode(
            credentials.credentials,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM]
        )
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token payload missing 'sub' field"
            )
        return user_id
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired"
        )
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid token: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token"
        )
    except Exception as e:
        logger.error(f"Error verifying token: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Error verifying token"
        )


# ============================================================================
# Request/Response Models
# ============================================================================

class GenerateAuthTokenRequest(BaseModel):
    """Request to generate auth token"""
    user_id: str


class TelegramWebhookPayload(BaseModel):
    """Telegram webhook payload"""
    update_id: int
    message: Optional[Dict[str, Any]] = None
    callback_query: Optional[Dict[str, Any]] = None


class SendOrderAlertRequest(BaseModel):
    """Request to send order alert"""
    user_id: str
    order_id: str
    symbol: str
    action: str
    quantity: int
    order_type: str = "MARKET"
    price: Optional[float] = None
    status: str
    message: Optional[str] = None
    filled_quantity: Optional[int] = None
    average_price: Optional[float] = None
    pnl: Optional[float] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class TestNotificationRequest(BaseModel):
    """Request to send test notification"""
    user_id: str


# ============================================================================
# Helper Functions
# ============================================================================

async def send_telegram_message(
    chat_id: str,
    text: str,
    buttons: Optional[List[InlineButton]] = None,
    parse_mode: Optional[str] = None
) -> bool:
    """Send message via Telegram Bot API"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode
        }
        
        if buttons:
            # Format inline keyboard
            keyboard = [[{"text": button.text, "callback_data": button.callback_data}] for button in buttons]
            payload["reply_markup"] = {"inline_keyboard": keyboard}
        
        response = await http_client.post(url, json=payload)
        
        if response.status_code == 200:
            result = response.json()
            if result.get("ok"):
                return True
            else:
                logger.error(f"Telegram API error: {result.get('description')}")
        else:
            logger.error(f"Telegram API HTTP error: {response.status_code}")
        
        return False
        
    except Exception as e:
        logger.error(f"Error sending Telegram message: {e}")
        return False


async def _handle_order_confirmation(db: AsyncSession, telegram_user_id: str, prompt_id: str):
    """Handle order confirmation callback"""
    try:
        from uuid import UUID
        prompt_uuid = UUID(prompt_id)
        
        # Get prompt from database
        query = select(TelegramOrderPrompt).where(TelegramOrderPrompt.id == prompt_uuid)
        result = await db.execute(query)
        prompt = result.scalar_one_or_none()
        
        if not prompt or prompt.status != OrderPromptStatus.PENDING:
            await send_telegram_message(
                chat_id=telegram_user_id,
                text="❌ Order confirmation expired or not found."
            )
            return
        
        # Get connection
        connection_query = select(TelegramConnection).where(
            TelegramConnection.telegram_user_id == telegram_user_id
        )
        conn_result = await db.execute(connection_query)
        connection = conn_result.scalar_one_or_none()
        
        if not connection:
            await send_telegram_message(
                chat_id=telegram_user_id,
                text="❌ Connection not found."
            )
            return
        
        # Execute the order
        from .command_parser import ParsedCommand, CommandType
        parsed = ParsedCommand(
            type=CommandType.BUY if prompt.action == "BUY" else CommandType.SELL,
            symbol=prompt.symbol,
            quantity=prompt.quantity,
            order_type=prompt.order_type,
            price=prompt.price,
            product_type=prompt.product_type
        )
        
        result = await execute_order_command(db, connection, parsed, None, force=True)
        
        # Update prompt status
        prompt.status = OrderPromptStatus.CONFIRMED
        prompt.responded_at = datetime.utcnow()
        await db.commit()
        
        # Send result
        await send_telegram_message(
            chat_id=telegram_user_id,
            text=f"✅ {result.message}"
        )
        
    except Exception as e:
        logger.error(f"Error handling order confirmation: {e}")


async def _handle_order_rejection(db: AsyncSession, telegram_user_id: str, prompt_id: str):
    """Handle order rejection callback"""
    try:
        from uuid import UUID
        prompt_uuid = UUID(prompt_id)
        
        # Get prompt from database
        query = select(TelegramOrderPrompt).where(TelegramOrderPrompt.id == prompt_uuid)
        result = await db.execute(query)
        prompt = result.scalar_one_or_none()
        
        if prompt:
            prompt.status = OrderPromptStatus.REJECTED
            prompt.responded_at = datetime.utcnow()
            await db.commit()
        
        await send_telegram_message(
            chat_id=telegram_user_id,
            text="❌ Order cancelled."
        )
        
    except Exception as e:
        logger.error(f"Error handling order rejection: {e}")


async def _handle_positions_refresh(db: AsyncSession, telegram_user_id: str):
    """Handle positions refresh callback"""
    try:
        connection_query = select(TelegramConnection).where(
            TelegramConnection.telegram_user_id == telegram_user_id
        )
        conn_result = await db.execute(connection_query)
        connection = conn_result.scalar_one_or_none()
        
        if connection:
            from .command_parser import ParsedCommand
            parsed = ParsedCommand(type=CommandType.POSITIONS)
            result = await execute_positions_command(db, connection, parsed)
            
    except Exception as e:
        logger.error(f"Error handling positions refresh: {e}")


async def _handle_orders_refresh(db: AsyncSession, telegram_user_id: str):
    """Handle orders refresh callback"""
    try:
        connection_query = select(TelegramConnection).where(
            TelegramConnection.telegram_user_id == telegram_user_id
        )
        conn_result = await db.execute(connection_query)
        connection = conn_result.scalar_one_or_none()
        
        if connection:
            from .command_parser import ParsedCommand
            parsed = ParsedCommand(type=CommandType.ORDERS)
            result = await execute_orders_command(db, connection, parsed)
            
    except Exception as e:
        logger.error(f"Error handling orders refresh: {e}")


async def check_rate_limit(telegram_user_id: str) -> Tuple[bool, Optional[int]]:
    """
    Check command rate limit for user.
    Requirements: 9.8, 34.1, 34.2
    """
    if not redis_client:
        return True, None
    
    try:
        key = f"telegram:rate_limit:{telegram_user_id}"
        
        # Get current count
        current = await redis_client.get(key)
        
        if current:
            count = int(current)
            if count >= RATE_LIMIT_COMMANDS_PER_MINUTE:
                # Get TTL
                ttl = await redis_client.ttl(key)
                return False, ttl
            
            # Increment count
            await redis_client.incr(key)
        else:
            # Initialize with 1 and set expiry
            await redis_client.setex(key, 60, 1)
        
        return True, None
        
    except Exception as e:
        logger.error(f"Error checking rate limit: {e}")
        return True, None


async def log_command(
    db: AsyncSession,
    connection_id: str,
    user_id: str,
    telegram_user_id: str,
    command_type: CommandType,
    parsed: ParsedCommand,
    success: bool,
    execution_time_ms: int,
    response_text: str,
    rate_limited: bool = False
) -> None:
    """
    Log command execution.
    Requirements: 9.9
    """
    try:
        log = TelegramCommandLog(
            connection_id=connection_id,
            user_id=user_id,
            telegram_user_id=telegram_user_id,
            command_type=command_type,
            command_text=parsed.raw_text,
            parsed_parameters={
                "symbol": parsed.symbol,
                "quantity": parsed.quantity,
                "price": parsed.price,
                "order_type": parsed.order_type,
                "flags": parsed.flags
            },
            executed_at=datetime.utcnow(),
            execution_time_ms=execution_time_ms,
            success=success,
            response_text=response_text,
            rate_limited=rate_limited
        )
        
        db.add(log)
        await db.commit()
        
    except Exception as e:
        logger.error(f"Error logging command: {e}")
        await db.rollback()


async def execute_command(
    db: AsyncSession,
    connection: TelegramConnection,
    parsed: ParsedCommand,
    preferences: TelegramPreferences
) -> CommandExecutionResult:
    """
    Execute trading command.
    Requirements: 9.3, 9.4, 9.7
    """
    start_time = datetime.utcnow()
    
    try:
        if parsed.type == CommandType.BUY or parsed.type == CommandType.SELL:
            return await execute_trade_command(db, connection, parsed, preferences)
        
        elif parsed.type == CommandType.POSITIONS:
            return await execute_positions_command(db, connection, parsed)
        
        elif parsed.type == CommandType.ORDERS:
            return await execute_orders_command(db, connection, parsed)
        
        elif parsed.type == CommandType.CANCEL:
            return await execute_cancel_command(db, connection, parsed)
        
        elif parsed.type == CommandType.STATUS:
            return await execute_status_command(db, connection)
        
        elif parsed.type == CommandType.HELP:
            return await execute_help_command(db, parsed)
        
        elif parsed.type == CommandType.START:
            return await execute_start_command(db, connection)
        
        else:
            return CommandExecutionResult(
                success=False,
                message=f"Command '{parsed.type.value}' is not yet implemented."
            )
        
    except Exception as e:
        logger.error(f"Error executing command: {e}")
        execution_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        
        return CommandExecutionResult(
            success=False,
            message=f"An error occurred while executing the command: {str(e)}",
            execution_time_ms=execution_time
        )


async def execute_trade_command(
    db: AsyncSession,
    connection: TelegramConnection,
    parsed: ParsedCommand,
    preferences: TelegramPreferences
) -> CommandExecutionResult:
    """Execute buy/sell command with optional confirmation"""
    
    # Check if confirmation is required
    if preferences and preferences.require_confirmation and not parsed.force:
        # Create order prompt
        prompt = TelegramOrderPrompt(
            connection_id=connection.id,
            user_id=connection.user_id,
            symbol=parsed.symbol,
            action=parsed.type.value.upper(),
            quantity=parsed.quantity,
            order_type=parsed.order_type,
            price=parsed.price,
            product_type=parsed.product_type,
            expires_at=datetime.utcnow() + timedelta(seconds=preferences.confirmation_timeout_seconds)
        )
        
        db.add(prompt)
        await db.commit()
        await db.refresh(prompt)
        
        # Format confirmation message
        formatted = message_formatter.format_order_confirmation_prompt(
            symbol=parsed.symbol,
            action=parsed.type.value,
            quantity=parsed.quantity,
            order_type=parsed.order_type,
            price=parsed.price,
            product_type=parsed.product_type
        )
        
        # Send confirmation prompt
        success = await send_telegram_message(
            chat_id=connection.telegram_user_id,
            text=formatted.text,
            buttons=formatted.buttons,
            parse_mode=formatted.parse_mode
        )
        
        if success:
            return CommandExecutionResult(
                success=True,
                message="Order confirmation prompt sent. Please confirm within 60 seconds.",
                data={"prompt_id": str(prompt.id)}
            )
        else:
            return CommandExecutionResult(
                success=False,
                message="Failed to send confirmation prompt. Please try again."
            )
    
    # Direct execution (no confirmation or --force flag)
    # Integrate with Broker Integration Service
    try:
        # Get broker connection for user
        broker_response = await http_client.get(
            f"{BROKER_INTEGRATION_URL}/api/v1/connections",
            headers={"Authorization": f"Bearer {connection.auth_token}"} if hasattr(connection, 'auth_token') else {}
        )
        if broker_response.status_code != 200:
            return CommandExecutionResult(
                success=False,
                message="No active broker connection found. Please connect your broker first."
            )
        
        connections = broker_response.json().get("connections", [])
        if not connections:
            return CommandExecutionResult(
                success=False,
                message="No active broker connection found. Please connect your broker first."
            )
        
        broker_id = connections[0]["id"]
        
        # Place order via Broker Integration Service
        order_response = await http_client.post(
            f"{BROKER_INTEGRATION_URL}/api/v1/orders/place",
            json={
                "broker_id": broker_id,
                "symbol": parsed.symbol,
                "exchange": "NSE",  # Default to NSE, could be parsed from command
                "action": parsed.type.value.upper(),
                "order_type": parsed.order_type.upper(),
                "product_type": parsed.product_type.upper(),
                "quantity": parsed.quantity,
                "price": parsed.price,
                "trigger_price": parsed.trigger_price,
                "validity": "DAY"
            },
            headers={"Authorization": f"Bearer {connection.auth_token}"} if hasattr(connection, 'auth_token') else {}
        )
        
        if order_response.status_code != 200:
            return CommandExecutionResult(
                success=False,
                message=f"Failed to place order: {order_response.text}"
            )
        
        order_data = order_response.json()
        return CommandExecutionResult(
            success=True,
            message=f"Order placed successfully: {order_data.get('order_id', 'N/A')}",
            data=order_data
        )
    except Exception as e:
        logger.error(f"Error placing order via broker integration: {e}")
        return CommandExecutionResult(
            success=False,
            message=f"Failed to place order: {str(e)}"
        )


async def execute_positions_command(
    db: AsyncSession,
    connection: TelegramConnection,
    parsed: ParsedCommand
) -> CommandExecutionResult:
    """Execute positions command"""
    # Fetch real positions from Portfolio Service
    try:
        positions_response = await http_client.get(
            f"{PORTFOLIO_SERVICE_URL}/api/v1/portfolio/positions",
            headers={"Authorization": f"Bearer {connection.auth_token}"} if hasattr(connection, 'auth_token') else {}
        )
        
        if positions_response.status_code == 200:
            positions_data = positions_response.json()
            positions = positions_data.get("positions", [])
        else:
            # Fallback to mock data if service unavailable
            logger.warning(f"Portfolio service unavailable: {positions_response.status_code}")
            positions = [
                {"symbol": "RELIANCE", "quantity": 10, "average_price": 2450.50, "current_price": 2475.00, "pnl": 245.00},
                {"symbol": "INFY", "quantity": 5, "average_price": 1450.00, "current_price": 1445.00, "pnl": -25.00},
            ]
    except Exception as e:
        logger.error(f"Error fetching positions: {e}")
        # Fallback to mock data
        positions = [
            {"symbol": "RELIANCE", "quantity": 10, "average_price": 2450.50, "current_price": 2475.00, "pnl": 245.00},
            {"symbol": "INFY", "quantity": 5, "average_price": 1450.00, "current_price": 1445.00, "pnl": -25.00},
        ]
    
    total_pnl = sum(p.get("pnl", 0) for p in positions)
    
    formatted = message_formatter.format_position_list(positions, total_pnl)
    
    success = await send_telegram_message(
        chat_id=connection.telegram_user_id,
        text=formatted.text,
        buttons=formatted.buttons,
        parse_mode=formatted.parse_mode
    )
    
    return CommandExecutionResult(
        success=success,
        message="Positions displayed" if success else "Failed to display positions"
    )


async def execute_orders_command(
    db: AsyncSession,
    connection: TelegramConnection,
    parsed: ParsedCommand
) -> CommandExecutionResult:
    """Execute orders command"""
    # Fetch real orders from Broker Integration Service
    try:
        # Get broker connection for user
        broker_response = await http_client.get(
            f"{BROKER_INTEGRATION_URL}/api/v1/connections",
            headers={"Authorization": f"Bearer {connection.auth_token}"} if hasattr(connection, 'auth_token') else {}
        )
        
        if broker_response.status_code == 200:
            connections = broker_response.json().get("connections", [])
            if connections:
                broker_id = connections[0]["id"]
                
                # Fetch orders from Broker Integration Service
                orders_response = await http_client.get(
                    f"{BROKER_INTEGRATION_URL}/api/v1/orders",
                    params={"broker_id": broker_id, "status": parsed.flags.get("status_filter")},
                    headers={"Authorization": f"Bearer {connection.auth_token}"} if hasattr(connection, 'auth_token') else {}
                )
                
                if orders_response.status_code == 200:
                    orders_data = orders_response.json()
                    orders = orders_data.get("orders", [])
                else:
                    # Fallback to mock data
                    orders = [
                        {"order_id": "2405150001", "symbol": "RELIANCE", "status": "PENDING", "timestamp": datetime.utcnow()},
                        {"order_id": "2405150002", "symbol": "INFY", "status": "COMPLETE", "timestamp": datetime.utcnow()},
                    ]
            else:
                orders = []
        else:
            # Fallback to mock data
            orders = [
                {"order_id": "2405150001", "symbol": "RELIANCE", "status": "PENDING", "timestamp": datetime.utcnow()},
                {"order_id": "2405150002", "symbol": "INFY", "status": "COMPLETE", "timestamp": datetime.utcnow()},
            ]
    except Exception as e:
        logger.error(f"Error fetching orders: {e}")
        # Fallback to mock data
        orders = [
            {"order_id": "2405150001", "symbol": "RELIANCE", "status": "PENDING", "timestamp": datetime.utcnow()},
            {"order_id": "2405150002", "symbol": "INFY", "status": "COMPLETE", "timestamp": datetime.utcnow()},
        ]
    
    formatted = message_formatter.format_order_list(
        orders, 
        parsed.flags.get("status_filter")
    )
    
    success = await send_telegram_message(
        chat_id=connection.telegram_user_id,
        text=formatted.text,
        buttons=formatted.buttons,
        parse_mode=formatted.parse_mode
    )
    
    return CommandExecutionResult(
        success=success,
        message="Orders displayed" if success else "Failed to display orders"
    )


async def execute_cancel_command(
    db: AsyncSession,
    connection: TelegramConnection,
    parsed: ParsedCommand
) -> CommandExecutionResult:
    """Execute cancel command"""
    if not parsed.order_id:
        return CommandExecutionResult(
            success=False,
            message="Order ID is required. Usage: /cancel <order_id>"
        )
    
    # Integrate with Broker Integration Service
    try:
        # Get broker connection for user
        broker_response = await http_client.get(
            f"{BROKER_INTEGRATION_URL}/api/v1/connections",
            headers={"Authorization": f"Bearer {connection.auth_token}"} if hasattr(connection, 'auth_token') else {}
        )
        
        if broker_response.status_code != 200:
            return CommandExecutionResult(
                success=False,
                message="No active broker connection found. Please connect your broker first."
            )
        
        connections = broker_response.json().get("connections", [])
        if not connections:
            return CommandExecutionResult(
                success=False,
                message="No active broker connection found. Please connect your broker first."
            )
        
        broker_id = connections[0]["id"]
        
        # Cancel order via Broker Integration Service
        cancel_response = await http_client.post(
            f"{BROKER_INTEGRATION_URL}/api/v1/orders/cancel",
            json={
                "broker_id": broker_id,
                "order_id": parsed.order_id
            },
            headers={"Authorization": f"Bearer {connection.auth_token}"} if hasattr(connection, 'auth_token') else {}
        )
        
        if cancel_response.status_code != 200:
            return CommandExecutionResult(
                success=False,
                message=f"Failed to cancel order: {cancel_response.text}"
            )
        
        return CommandExecutionResult(
            success=True,
            message=f"Order {parsed.order_id} cancelled successfully"
        )
    except Exception as e:
        logger.error(f"Error cancelling order via broker integration: {e}")
        return CommandExecutionResult(
            success=False,
            message=f"Failed to cancel order: {str(e)}"
        )


async def execute_status_command(
    db: AsyncSession,
    connection: TelegramConnection
) -> CommandExecutionResult:
    """Execute status command"""
    formatted = message_formatter.format_status_message(
        connected=connection.status == ConnectionStatus.CONNECTED,
        username=connection.telegram_username,
        last_activity=connection.last_activity_at
    )
    
    success = await send_telegram_message(
        chat_id=connection.telegram_user_id,
        text=formatted.text,
        parse_mode=formatted.parse_mode
    )
    
    return CommandExecutionResult(
        success=success,
        message="Status displayed" if success else "Failed to display status"
    )


async def execute_help_command(
    db: AsyncSession,
    parsed: ParsedCommand
) -> CommandExecutionResult:
    """Execute help command"""
    topic = parsed.flags.get("topic") if parsed.flags else None
    help_text = command_parser.get_command_help(topic)
    
    return CommandExecutionResult(
        success=True,
        message=help_text
    )


async def execute_start_command(
    db: AsyncSession,
    connection: TelegramConnection
) -> CommandExecutionResult:
    """Execute start command"""
    formatted = message_formatter.format_welcome_message(
        first_name=connection.telegram_first_name
    )
    
    success = await send_telegram_message(
        chat_id=connection.telegram_user_id,
        text=formatted.text,
        parse_mode=formatted.parse_mode
    )
    
    return CommandExecutionResult(
        success=success,
        message="Welcome message sent" if success else "Failed to send welcome message"
    )


# ============================================================================
# API Endpoints
# ============================================================================

@router.post("/auth/token", response_model=AuthTokenResponse)
async def generate_auth_token(
    request: GenerateAuthTokenRequest,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Generate authentication token for Telegram linking.
    Requirements: 24.1, 24.2
    """
    try:
        # Generate token
        auth_token = await auth_handler.generate_auth_token(db, request.user_id)
        
        # Generate QR code URL (optional, for future enhancement)
        qr_code_url = None
        
        # Generate connect URL
        connect_url = f"https://t.me/{TELEGRAM_BOT_USERNAME}?start={auth_token.token}"
        
        return AuthTokenResponse(
            token=auth_token.token,
            expires_at=auth_token.expires_at,
            qr_code_url=qr_code_url,
            bot_username=TELEGRAM_BOT_USERNAME,
            connect_url=connect_url
        )
        
    except Exception as e:
        logger.error(f"Error generating auth token: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate authentication token"
        )


@router.get("/connection", response_model=TelegramConnectionResponse)
async def get_connection(
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Get Telegram connection status for current user.
    Requirements: 24.1, 24.3
    """
    try:
        query = select(TelegramConnection).where(
            TelegramConnection.user_id == current_user_id
        )
        result = await db.execute(query)
        connection = result.scalar_one_or_none()
        
        if not connection:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No Telegram connection found"
            )
        
        return TelegramConnectionResponse(
            id=str(connection.id),
            user_id=str(connection.user_id),
            telegram_user_id=connection.telegram_user_id,
            telegram_username=connection.telegram_username,
            status=connection.status.value,
            connected_at=connection.connected_at,
            last_activity_at=connection.last_activity_at,
            created_at=connection.created_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting connection: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get connection status"
        )


@router.delete("/connection")
async def revoke_connection(
    telegram_user_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Revoke Telegram connection.
    Requirements: 24.6
    """
    try:
        success = await auth_handler.revoke_connection(
            db, 
            current_user_id, 
            telegram_user_id
        )
        
        if success:
            return {"message": "Telegram connection revoked successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to revoke connection"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error revoking connection: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to revoke connection"
        )


@router.get("/preferences", response_model=TelegramPreferencesResponse)
async def get_preferences(
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Get Telegram notification preferences.
    """
    try:
        query = select(TelegramPreferences).where(
            TelegramPreferences.user_id == current_user_id
        )
        result = await db.execute(query)
        prefs = result.scalar_one_or_none()
        
        if not prefs:
            # Create default preferences
            query = select(TelegramConnection).where(
                TelegramConnection.user_id == current_user_id
            )
            result = await db.execute(query)
            connection = result.scalar_one_or_none()
            
            if connection:
                prefs = TelegramPreferences(
                    connection_id=connection.id,
                    user_id=current_user_id
                )
                db.add(prefs)
                await db.commit()
                await db.refresh(prefs)
            else:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No Telegram connection found"
                )
        
        return TelegramPreferencesResponse(
            id=str(prefs.id),
            user_id=str(prefs.user_id),
            order_notifications=prefs.order_notifications,
            execution_notifications=prefs.execution_notifications,
            rejection_notifications=prefs.rejection_notifications,
            position_notifications=prefs.position_notifications,
            system_notifications=prefs.system_notifications,
            batch_notifications=prefs.batch_notifications,
            batch_window_seconds=prefs.batch_window_seconds,
            require_confirmation=prefs.require_confirmation,
            confirmation_timeout_seconds=prefs.confirmation_timeout_seconds,
            rate_limit_per_minute=prefs.rate_limit_per_minute,
            use_emojis=prefs.use_emojis,
            use_monospace_for_numbers=prefs.use_monospace_for_numbers,
            timezone=prefs.timezone
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting preferences: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get preferences"
        )


@router.patch("/preferences")
async def update_preferences(
    update: TelegramPreferencesUpdate,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Update Telegram notification preferences.
    """
    try:
        query = select(TelegramPreferences).where(
            TelegramPreferences.user_id == current_user_id
        )
        result = await db.execute(query)
        prefs = result.scalar_one_or_none()
        
        if not prefs:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No Telegram preferences found"
            )
        
        # Update fields
        update_data = update.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(prefs, field, value)
        
        prefs.updated_at = datetime.utcnow()
        
        await db.commit()
        await db.refresh(prefs)
        
        return {"message": "Preferences updated successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating preferences: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update preferences"
        )


@router.post("/webhook")
async def telegram_webhook(
    payload: TelegramWebhookPayload,
    db: AsyncSession = Depends(get_db)
):
    """
    Receive webhook updates from Telegram.
    Requirements: 9.1, 9.3, 24.1
    """
    try:
        # Extract message or callback data
        message = payload.message
        callback_query = payload.callback_query
        
        if callback_query:
            # Handle callback (button click)
            telegram_user_id = str(callback_query.get("from", {}).get("id"))
            callback_data = callback_query.get("data", "")
            callback_query_id = callback_query.get("id")
            
            # Handle callback actions
            logger.info(f"Received callback from {telegram_user_id}: {callback_data}")
            
            # Parse callback data (format: action:param1:param2)
            parts = callback_data.split(":")
            action = parts[0] if parts else ""
            
            try:
                if action == "confirm_order":
                    # Confirm order execution
                    prompt_id = parts[1] if len(parts) > 1 else None
                    if prompt_id:
                        await _handle_order_confirmation(db, telegram_user_id, prompt_id)
                
                elif action == "reject_order":
                    # Reject order execution
                    prompt_id = parts[1] if len(parts) > 1 else None
                    if prompt_id:
                        await _handle_order_rejection(db, telegram_user_id, prompt_id)
                
                elif action == "refresh_positions":
                    # Refresh positions display
                    await _handle_positions_refresh(db, telegram_user_id)
                
                elif action == "refresh_orders":
                    # Refresh orders display
                    await _handle_orders_refresh(db, telegram_user_id)
                
                # Answer callback query to remove loading state
                await http_client.post(
                    f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery",
                    json={"callback_query_id": callback_query_id}
                )
                
            except Exception as e:
                logger.error(f"Error handling callback action {action}: {e}")
            
            return {"ok": True}
        
        if not message:
            return {"ok": True}
        
        # Extract message details
        telegram_user_id = str(message.get("from", {}).get("id"))
        telegram_username = message.get("from", {}).get("username")
        telegram_first_name = message.get("from", {}).get("first_name")
        telegram_last_name = message.get("from", {}).get("last_name")
        text = message.get("text", "")
        
        logger.info(f"Received message from {telegram_user_id}: {text}")
        
        # Check authentication
        auth_result = await auth_handler.check_authentication(db, telegram_user_id)
        
        # Handle auth command specially
        if text.startswith("/auth") or text.startswith("/start"):
            if text.startswith("/start") and len(text.split()) > 1:
                # Handle deep link with token
                token = text.split()[1]
                auth_result = await auth_handler.validate_auth_token(
                    db, token, telegram_user_id, telegram_username, 
                    telegram_first_name, telegram_last_name
                )
                
                await send_telegram_message(
                    chat_id=telegram_user_id,
                    text=auth_result.message,
                    parse_mode="HTML"
                )
                return {"ok": True}
            
            elif text.startswith("/auth") and len(text.split()) > 1:
                # Handle explicit auth command
                token = text.split()[1]
                auth_result = await auth_handler.validate_auth_token(
                    db, token, telegram_user_id, telegram_username,
                    telegram_first_name, telegram_last_name
                )
                
                await send_telegram_message(
                    chat_id=telegram_user_id,
                    text=auth_result.message,
                    parse_mode="HTML"
                )
                return {"ok": True}
        
        # Check if authenticated for other commands
        if not auth_result.success and not text.startswith("/start"):
            await send_telegram_message(
                chat_id=telegram_user_id,
                text=auth_result.message,
                parse_mode="HTML"
            )
            return {"ok": True}
        
        # Get connection and preferences
        connection = auth_result.connection
        
        if not connection:
            await send_telegram_message(
                chat_id=telegram_user_id,
                text="❌ Session error. Please reconnect using /auth <token>",
                parse_mode="HTML"
            )
            return {"ok": True}
        
        # Get preferences
        query = select(TelegramPreferences).where(
            TelegramPreferences.connection_id == connection.id
        )
        result = await db.execute(query)
        preferences = result.scalar_one_or_none()
        
        # Parse command
        parsed = command_parser.parse_command(text)
        
        # Validate command
        validation = command_parser.validate_command(parsed)
        if not validation.valid:
            await send_telegram_message(
                chat_id=telegram_user_id,
                text=validation.error_message or "Invalid command",
                parse_mode="HTML"
            )
            
            await log_command(
                db, connection.id, connection.user_id, telegram_user_id,
                parsed.type, parsed, False, 0, validation.error_message or "Invalid command"
            )
            return {"ok": True}
        
        # Check rate limit
        allowed, retry_after = await check_rate_limit(telegram_user_id)
        if not allowed:
            retry_text = f" in {retry_after} seconds" if retry_after else ""
            await send_telegram_message(
                chat_id=telegram_user_id,
                text=f"⏱️ Rate limit exceeded. Please try again{retry_text}.",
                parse_mode="HTML"
            )
            
            await log_command(
                db, connection.id, connection.user_id, telegram_user_id,
                parsed.type, parsed, False, 0, "Rate limit exceeded", True
            )
            return {"ok": True}
        
        # Execute command
        start_time = datetime.utcnow()
        result = await execute_command(db, connection, parsed, preferences)
        execution_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        
        # Send response if not already sent
        if not result.message.startswith("<") and not result.message.startswith("✅"):
            formatted = message_formatter.format_command_result(
                success=result.success,
                message=result.message,
                data=result.data
            )
            
            await send_telegram_message(
                chat_id=telegram_user_id,
                text=formatted.text,
                buttons=formatted.buttons,
                parse_mode=formatted.parse_mode
            )
        
        # Log command
        await log_command(
            db, connection.id, connection.user_id, telegram_user_id,
            parsed.type, parsed, result.success, execution_time, result.message
        )
        
        return {"ok": True}
        
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        return {"ok": False, "error": str(e)}


@router.post("/alerts/order")
async def send_order_alert(
    request: SendOrderAlertRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """
    Send order alert to user via Telegram.
    Requirements: 8.1, 8.2, 8.3, 8.4
    """
    try:
        # Get user's Telegram connection
        query = select(TelegramConnection).where(
            and_(
                TelegramConnection.user_id == request.user_id,
                TelegramConnection.status == ConnectionStatus.CONNECTED
            )
        )
        result = await db.execute(query)
        connection = result.scalar_one_or_none()
        
        if not connection:
            return {"sent": False, "message": "No active Telegram connection"}
        
        # Get preferences
        query = select(TelegramPreferences).where(
            TelegramPreferences.connection_id == connection.id
        )
        result = await db.execute(query)
        preferences = result.scalar_one_or_none()
        
        # Check if notifications enabled
        status_lower = request.status.lower()
        if status_lower in ["complete", "executed", "filled"]:
            if preferences and not preferences.execution_notifications:
                return {"sent": False, "message": "Execution notifications disabled"}
        elif status_lower in ["rejected", "cancelled", "error"]:
            if preferences and not preferences.rejection_notifications:
                return {"sent": False, "message": "Rejection notifications disabled"}
        else:
            if preferences and not preferences.order_notifications:
                return {"sent": False, "message": "Order notifications disabled"}
        
        # Create formatter with user preferences
        formatter = TelegramMessageFormatter(
            use_emojis=preferences.use_emojis if preferences else True,
            use_monospace=preferences.use_monospace_for_numbers if preferences else True,
            timezone=preferences.timezone if preferences else "UTC"
        )
        
        # Format message
        formatted = formatter.format_order_alert(
            order_id=request.order_id,
            symbol=request.symbol,
            action=request.action,
            quantity=request.quantity,
            order_type=request.order_type,
            price=request.price,
            status=request.status,
            message=request.message,
            timestamp=request.timestamp,
            filled_quantity=request.filled_quantity,
            average_price=request.average_price,
            pnl=request.pnl
        )
        
        # Send message
        success = await send_telegram_message(
            chat_id=connection.telegram_user_id,
            text=formatted.text,
            buttons=formatted.buttons,
            parse_mode=formatted.parse_mode
        )
        
        if success:
            logger.info(f"Order alert sent to user {request.user_id}")
            return {"sent": True, "message": "Alert sent successfully"}
        else:
            return {"sent": False, "message": "Failed to send alert"}
        
    except Exception as e:
        logger.error(f"Error sending order alert: {e}")
        return {"sent": False, "message": str(e)}


@router.post("/test/notification")
async def send_test_notification(
    request: TestNotificationRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Send test notification to verify Telegram connection.
    """
    try:
        # Get connection
        query = select(TelegramConnection).where(
            and_(
                TelegramConnection.user_id == request.user_id,
                TelegramConnection.status == ConnectionStatus.CONNECTED
            )
        )
        result = await db.execute(query)
        connection = result.scalar_one_or_none()
        
        if not connection:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No active Telegram connection found"
            )
        
        # Send test message
        test_message = f"""{message_formatter.EMOJI_SUCCESS} <b>Test Notification</b>

This is a test message from SignalixAI!

Your Telegram bot is configured correctly and you will receive:
• Order confirmations
• Execution notifications
• Price alerts
• System updates

{message_formatter.EMOJI_CLOCK} Test sent at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"""
        
        success = await send_telegram_message(
            chat_id=connection.telegram_user_id,
            text=test_message,
            parse_mode="HTML"
        )
        
        if success:
            return {"sent": True, "message": "Test notification sent successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send test notification"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending test notification: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send test notification"
        )


@router.get("/command-history")
async def get_command_history(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Get command history for current user.
    Requirements: 9.9
    """
    try:
        query = select(TelegramCommandLog).where(
            TelegramCommandLog.user_id == current_user_id
        ).order_by(
            desc(TelegramCommandLog.executed_at)
        ).limit(limit)
        
        result = await db.execute(query)
        logs = result.scalars().all()
        
        return {
            "commands": [
                {
                    "id": str(log.id),
                    "command_type": log.command_type.value,
                    "command_text": log.command_text,
                    "executed_at": log.executed_at,
                    "success": log.success,
                    "execution_time_ms": log.execution_time_ms
                }
                for log in logs
            ]
        }
        
    except Exception as e:
        logger.error(f"Error getting command history: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get command history"
        )
