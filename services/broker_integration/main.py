"""
Broker Integration Service - FastAPI Application

Main entry point for the Broker Integration Service.
Provides REST API for broker connections, order management, and position tracking.

Requirements: 10.1, 10.2, 20.1, 20.2
"""

from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from contextlib import asynccontextmanager
import os
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
import asyncio
import jwt
from jwt.exceptions import InvalidTokenError

# JWT configuration
JWT_SECRET = os.getenv("JWT_SECRET", "your-secret-key-change-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

# CORS configuration
# Default to localhost in development, require explicit ALLOWED_ORIGINS in production
default_origins = ["http://localhost:3000", "http://localhost:3001", "http://127.0.0.1:3000"]
ALLOWED_ORIGINS = [
    origin.strip() 
    for origin in os.getenv("ALLOWED_ORIGINS", ",".join(default_origins)).split(",") 
    if origin.strip()
]

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import service components
from .connection_manager import ConnectionManager
from .order_manager import OrderManager, OrderRequest
from .credential_manager import CredentialManager, SecureCredentialStorage
from .symbol_normalizer import SymbolNormalizer
from .plugin_system import PluginRegistry, BuiltInPluginLoader
from .reconciliation import PositionReconciliation

# Import new Phase 2 & 4 services
from .smart_orders import SmartOrderService, SmartOrderRequest, SmartOrderResult, OrderAction
from .action_center import ActionCenter, ActionItem, ActionStatus, ActionPriority
from .basket_orders import BasketOrderService, BasketOrder, BasketLeg, BasketStatus
from .gtt_orders import GTTOrderService, GTTOrder, GTTStatus, GTTType
from .order_splitter import OrderSplitterService, SplitOrder, SplitStrategy, SplitStatus
from .security_middleware import create_security_middleware, CSRFProtection, RateLimiter

# Global service instances
connection_manager: Optional[ConnectionManager] = None
order_manager: Optional[OrderManager] = None
credential_manager: Optional[CredentialManager] = None
plugin_registry: Optional[PluginRegistry] = None
symbol_normalizer: Optional[SymbolNormalizer] = None
reconciliation: Optional[PositionReconciliation] = None

# Phase 2 & 4 new services
smart_order_service: Optional[SmartOrderService] = None
action_center: Optional[ActionCenter] = None
basket_order_service: Optional[BasketOrderService] = None
gtt_order_service: Optional[GTTOrderService] = None
order_splitter_service: Optional[OrderSplitterService] = None
csrf_protection: Optional[CSRFProtection] = None
rate_limiter: Optional[RateLimiter] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global connection_manager, order_manager, credential_manager, plugin_registry, symbol_normalizer, reconciliation
    global smart_order_service, action_center, basket_order_service, gtt_order_service, order_splitter_service
    
    logger.info("Starting Broker Integration Service...")
    
    # Initialize components
    connection_manager = ConnectionManager()
    await connection_manager.start()
    
    credential_manager = CredentialManager(
        master_key=os.getenv('BROKER_CREDENTIAL_MASTER_KEY')
    )
    
    order_manager = OrderManager(connection_manager)
    
    # Initialize Phase 2 services
    smart_order_service = SmartOrderService(order_manager)
    action_center = ActionCenter(order_manager)
    await action_center.start()
    
    basket_order_service = BasketOrderService(order_manager)
    gtt_order_service = GTTOrderService(order_manager)
    await gtt_order_service.start()
    
    order_splitter_service = OrderSplitterService(order_manager)
    
    logger.info("Phase 2 services initialized (Smart Orders, Action Center, GTT, Basket, Splitter)")
    
    # Initialize plugin system
    plugin_registry = PluginRegistry()
    loader = BuiltInPluginLoader(plugin_registry)
    loaded_count = await loader.load_all()
    logger.info(f"Loaded {loaded_count} built-in broker plugins")
    
    # Enable hot reload in development
    if os.getenv('ENVIRONMENT') == 'development':
        await plugin_registry.enable_hot_reload()
    
    # Initialize symbol normalizer
    symbol_normalizer = SymbolNormalizer()
    
    # Initialize reconciliation
    reconciliation = PositionReconciliation(connection_manager, order_manager)
    await reconciliation.start()
    
    logger.info("Broker Integration Service started successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Broker Integration Service...")
    
    # Stop Phase 2 services
    if action_center:
        await action_center.stop()
    
    if gtt_order_service:
        await gtt_order_service.stop()
    
    if order_manager:
        await order_manager.stop()
    
    if reconciliation:
        await reconciliation.stop()
    
    if plugin_registry:
        await plugin_registry.disable_hot_reload()
    
    if connection_manager:
        await connection_manager.stop()
    
    logger.info("Broker Integration Service shut down")


# Create FastAPI app
app = FastAPI(
    title="Broker Integration Service",
    description="SignalixAI Broker Integration Service for managing broker connections and order execution",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Phase 4.3: Security Middleware (CSRF & Rate Limiting)
# Initialize after app creation but endpoints will be added at end
security_middleware_config = {
    "enable_csrf": os.getenv("ENABLE_CSRF", "true").lower() == "true",
    "enable_rate_limit": os.getenv("ENABLE_RATE_LIMIT", "true").lower() == "true",
    "rate_limit_per_minute": int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
}

# Security
security = HTTPBearer(auto_error=False)


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Validate JWT token and return user info."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Missing authentication token")
    
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Token payload missing 'sub' field")
        return {"id": user_id, "email": payload.get("email", "")}
    except InvalidTokenError as e:
        logger.warning(f"Invalid token: {e}")
        raise HTTPException(status_code=401, detail="Invalid authentication token")
    except Exception as e:
        logger.error(f"Error verifying token: {e}", exc_info=True)
        raise HTTPException(status_code=401, detail="Error verifying token")


# Health check endpoint
@app.get("/health")
async def health_check():
    """Service health check endpoint."""
    return {
        "status": "healthy",
        "service": "broker-integration",
        "timestamp": datetime.utcnow().isoformat(),
        "components": {
            "connection_manager": connection_manager is not None,
            "order_manager": order_manager is not None,
            "plugin_registry": plugin_registry is not None
        }
    }


# Connection Management Endpoints
@app.get("/api/v1/connections")
async def list_connections(user: Dict = Depends(get_current_user)):
    """List all broker connections for the user."""
    statuses = connection_manager.get_all_statuses()
    return {
        "connections": [
            {
                "broker_id": broker_id,
                "status": status.connected,
                "authenticated": status.authenticated,
                "last_connected": status.last_connected.isoformat() if status.last_connected else None,
                "last_error": status.last_error,
                "error_count": status.error_count,
                "websocket_connected": status.websocket_connected
            }
            for broker_id, status in statuses.items()
        ]
    }


@app.post("/api/v1/connections/{broker_type}")
async def create_connection(
    broker_type: str,
    config: Dict[str, Any],
    account_label: Optional[str] = None,
    auto_reconnect: bool = True,
    user: Dict = Depends(get_current_user)
):
    """Create a new broker connection."""
    try:
        # Get plugin for broker
        plugin_name = plugin_registry.get_plugin_for_broker(broker_type)
        if not plugin_name:
            raise HTTPException(status_code=400, detail=f"Unsupported broker type: {broker_type}")
        
        plugin = plugin_registry.get_plugin(plugin_name)
        
        # Validate config
        is_valid, error = plugin.validate_config(config)
        if not is_valid:
            raise HTTPException(status_code=400, detail=f"Invalid config: {error}")
        
        # Create adapter
        adapter = plugin_registry.create_adapter(plugin_name, config)
        if not adapter:
            raise HTTPException(status_code=500, detail="Failed to create broker adapter")
        
        # Register connection
        broker_id = f"{user['id']}_{broker_type}_{account_label or 'default'}"
        
        success = await connection_manager.register_connection(
            broker_id=broker_id,
            adapter=adapter,
            auto_reconnect=auto_reconnect
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to register connection")
        
        # Connect
        connected = await connection_manager.connect(broker_id)
        
        return {
            "success": True,
            "broker_id": broker_id,
            "connected": connected,
            "message": "Connection created successfully" if connected else "Connection created but not connected"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create connection: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/v1/connections/{broker_id}")
async def delete_connection(broker_id: str, user: Dict = Depends(get_current_user)):
    """Delete a broker connection."""
    try:
        await connection_manager.disconnect(broker_id)
        return {"success": True, "message": "Connection deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/connections/{broker_id}/connect")
async def connect_broker(broker_id: str, user: Dict = Depends(get_current_user)):
    """Connect to a broker."""
    try:
        success = await connection_manager.connect(broker_id)
        return {
            "success": success,
            "broker_id": broker_id,
            "status": "connected" if success else "failed"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/connections/{broker_id}/disconnect")
async def disconnect_broker(broker_id: str, user: Dict = Depends(get_current_user)):
    """Disconnect from a broker."""
    try:
        success = await connection_manager.disconnect(broker_id)
        return {
            "success": success,
            "broker_id": broker_id,
            "status": "disconnected"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/connections/{broker_id}/status")
async def get_connection_status(broker_id: str, user: Dict = Depends(get_current_user)):
    """Get connection status."""
    status = connection_manager.get_connection_status(broker_id)
    if not status:
        raise HTTPException(status_code=404, detail="Connection not found")
    
    return {
        "broker_id": broker_id,
        "connected": status.connected,
        "authenticated": status.authenticated,
        "last_connected": status.last_connected.isoformat() if status.last_connected else None,
        "last_error": status.last_error,
        "error_count": status.error_count,
        "websocket_connected": status.websocket_connected
    }


# Order Management Endpoints
@app.post("/api/v1/orders")
async def place_order(
    broker_id: str,
    order: OrderRequest,
    user: Dict = Depends(get_current_user)
):
    """Place a new order."""
    try:
        response = await order_manager.place_order(broker_id, order)
        
        if not response.success:
            raise HTTPException(status_code=400, detail=response.message)
        
        return {
            "success": True,
            "order_id": response.order_id,
            "broker_order_id": response.broker_order_id,
            "status": response.status,
            "message": response.message
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to place order: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/v1/orders/{order_id}")
async def modify_order(
    order_id: str,
    broker_id: str,
    quantity: Optional[float] = None,
    price: Optional[float] = None,
    trigger_price: Optional[float] = None,
    user: Dict = Depends(get_current_user)
):
    """Modify an existing order."""
    try:
        response = await order_manager.modify_order(
            broker_id, order_id, quantity, price, trigger_price
        )
        
        if not response.success:
            raise HTTPException(status_code=400, detail=response.message)
        
        return {
            "success": True,
            "order_id": response.order_id,
            "status": response.status,
            "message": response.message
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/v1/orders/{order_id}")
async def cancel_order(
    order_id: str,
    broker_id: str,
    user: Dict = Depends(get_current_user)
):
    """Cancel an order."""
    try:
        response = await order_manager.cancel_order(broker_id, order_id)
        
        if not response.success:
            raise HTTPException(status_code=400, detail=response.message)
        
        return {
            "success": True,
            "order_id": order_id,
            "message": response.message
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/orders")
async def list_orders(
    broker_id: str,
    status: Optional[str] = None,
    symbol: Optional[str] = None,
    user: Dict = Depends(get_current_user)
):
    """List orders for a broker connection."""
    try:
        orders = await order_manager.get_orders(broker_id, status, symbol)
        return {"orders": orders}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/orders/{order_id}")
async def get_order(
    order_id: str,
    broker_id: str,
    user: Dict = Depends(get_current_user)
):
    """Get order details."""
    try:
        order = await order_manager.get_order_status(broker_id, order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        return order
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Position Endpoints
@app.get("/api/v1/positions")
async def get_positions(broker_id: str, user: Dict = Depends(get_current_user)):
    """Get all positions for a broker."""
    try:
        adapter = connection_manager.get_adapter(broker_id)
        if not adapter:
            raise HTTPException(status_code=404, detail="Broker connection not found")
        
        positions = await adapter.get_positions()
        return {
            "positions": [
                {
                    "symbol": p.symbol,
                    "exchange": p.exchange,
                    "quantity": p.quantity,
                    "average_price": p.average_price,
                    "last_price": p.last_price,
                    "pnl": p.pnl,
                    "pnl_percentage": p.pnl_percentage
                }
                for p in positions
            ]
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/holdings")
async def get_holdings(broker_id: str, user: Dict = Depends(get_current_user)):
    """Get holdings for a broker."""
    try:
        adapter = connection_manager.get_adapter(broker_id)
        if not adapter:
            raise HTTPException(status_code=404, detail="Broker connection not found")
        
        holdings = await adapter.get_holdings()
        return {
            "holdings": [
                {
                    "symbol": h.symbol,
                    "exchange": h.exchange,
                    "quantity": h.quantity,
                    "average_price": h.average_price,
                    "last_price": h.last_price,
                    "pnl": h.pnl
                }
                for h in holdings
            ]
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/margin")
async def get_margin(broker_id: str, user: Dict = Depends(get_current_user)):
    """Get margin information."""
    try:
        adapter = connection_manager.get_adapter(broker_id)
        if not adapter:
            raise HTTPException(status_code=404, detail="Broker connection not found")
        
        margin = await adapter.get_margin()
        return {
            "available_cash": margin.available_cash,
            "used_margin": margin.used_margin,
            "total_margin": margin.total_margin,
            "collateral": margin.collateral,
            "unrealized_pnl": margin.unrealized_pnl,
            "realized_pnl": margin.realized_pnl
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Plugin Endpoints
@app.get("/api/v1/brokers")
async def list_supported_brokers():
    """List all supported brokers."""
    plugins = plugin_registry.get_all_metadata()
    
    return {
        "brokers": [
            {
                "code": broker,
                "name": metadata.name,
                "version": metadata.version,
                "description": metadata.description,
                "supported_auth_types": plugin.get_supported_auth_types(),
                "capabilities": metadata.capabilities
            }
            for broker, plugin in [(p, plugin_registry.get_plugin(p)) for p in plugin_registry.list_plugins()]
            for metadata in [plugin.get_metadata()] if plugin
        ]
    }


@app.get("/api/v1/brokers/{broker_code}/config-schema")
async def get_broker_config_schema(broker_code: str):
    """Get configuration schema for a broker."""
    plugin_name = plugin_registry.get_plugin_for_broker(broker_code)
    if not plugin_name:
        raise HTTPException(status_code=404, detail="Broker not found")
    
    plugin = plugin_registry.get_plugin(plugin_name)
    metadata = plugin.get_metadata()
    
    return {
        "broker_code": broker_code,
        "required_config": metadata.required_config,
        "optional_config": metadata.optional_config,
        "supported_auth_types": plugin.get_supported_auth_types()
    }


# Symbol Normalization Endpoints
@app.get("/api/v1/symbols/normalize")
async def normalize_symbol(
    broker: str,
    symbol: str,
    exchange: Optional[str] = None
):
    """Normalize a broker symbol to standard format."""
    try:
        normalized = symbol_normalizer.normalize(broker, symbol, exchange)
        return {
            "broker": broker,
            "broker_symbol": symbol,
            "standard_symbol": normalized
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/symbols/search")
async def search_symbols(
    query: str,
    broker: str,
    limit: int = 10
):
    """Search for symbols."""
    try:
        results = symbol_normalizer.search_symbol(query, broker, limit)
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# WebSocket for real-time updates
@app.websocket("/ws/orders/{broker_id}")
async def websocket_orders(websocket: WebSocket, broker_id: str):
    """WebSocket for real-time order updates."""
    await websocket.accept()
    
    try:
        # Register callback for order events
        async def on_order_event(data):
            await websocket.send_json({
                "type": "order_update",
                "data": data,
                "timestamp": datetime.utcnow().isoformat()
            })
        
        order_manager.on('order_status_update', on_order_event)
        order_manager.on('order_placed', on_order_event)
        
        # Keep connection alive
        while True:
            try:
                message = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=30.0
                )
                # Handle ping/pong
                if message == "ping":
                    await websocket.send_text("pong")
                    
            except asyncio.TimeoutError:
                # Send heartbeat
                await websocket.send_json({
                    "type": "heartbeat",
                    "timestamp": datetime.utcnow().isoformat()
                })
                
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for {broker_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        # Unregister callbacks
        order_manager.off('order_status_update', on_order_event)
        order_manager.off('order_placed', on_order_event)


# ============================================================================
# Phase 2: Smart Orders & Action Center Endpoints
# ============================================================================

@app.post("/api/v1/smart-orders")
async def place_smart_order(
    broker_id: str,
    symbol: str,
    exchange: str,
    action: str,
    order_type: str,
    quantity: float,
    price: Optional[float] = None,
    trigger_price: Optional[float] = None,
    product_type: str = "INTRADAY",
    check_duplicates: bool = True,
    duplicate_window_seconds: int = 60,
    max_position_size: Optional[float] = None,
    user: Dict = Depends(get_current_user)
):
    """Place a smart order with position awareness and duplicate detection."""
    try:
        request = SmartOrderRequest(
            symbol=symbol,
            exchange=exchange,
            action=OrderAction(action),
            order_type=order_type,
            quantity=quantity,
            price=price,
            trigger_price=trigger_price,
            product_type=product_type,
            check_duplicates=check_duplicates,
            duplicate_window_seconds=duplicate_window_seconds,
            adjust_for_position=max_position_size is not None,
            max_position_size=max_position_size
        )
        
        result = await smart_order_service.place_smart_order(
            broker_id, request, user.get("id")
        )
        
        return {
            "success": result.success,
            "order_id": result.order_id,
            "status": result.status.value,
            "message": result.message,
            "adjusted_quantity": result.adjusted_quantity,
            "blocked_reason": result.blocked_reason,
            "metadata": result.metadata
        }
    except Exception as e:
        logger.error(f"Smart order failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Action Center Endpoints

@app.post("/api/v1/action-center/submit")
async def submit_action(
    broker_id: str,
    order_request: Dict[str, Any],
    priority: str = "medium",
    expiry_minutes: int = 5,
    user: Dict = Depends(get_current_user)
):
    """Submit an order for manual approval via Action Center."""
    try:
        action = await action_center.submit_order_for_approval(
            broker_id=broker_id,
            user_id=user.get("id"),
            order_request=order_request,
            priority=ActionPriority[priority.upper()],
            expiry_minutes=expiry_minutes
        )
        return action_center.action_to_dict(action)
    except Exception as e:
        logger.error(f"Action submission failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/action-center/{action_id}/approve")
async def approve_action(
    action_id: str,
    notes: Optional[str] = None,
    user: Dict = Depends(get_current_user)
):
    """Approve an action in the Action Center."""
    try:
        action = await action_center.approve_action(
            action_id, user.get("id"), notes
        )
        if not action:
            raise HTTPException(status_code=404, detail="Action not found")
        return action_center.action_to_dict(action)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Action approval failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/action-center/{action_id}/reject")
async def reject_action(
    action_id: str,
    reason: str,
    user: Dict = Depends(get_current_user)
):
    """Reject an action in the Action Center."""
    try:
        action = await action_center.reject_action(
            action_id, user.get("id"), reason
        )
        if not action:
            raise HTTPException(status_code=404, detail="Action not found")
        return action_center.action_to_dict(action)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Action rejection failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/action-center/pending")
async def list_pending_actions(
    broker_id: Optional[str] = None,
    user: Dict = Depends(get_current_user)
):
    """List pending actions in the Action Center."""
    try:
        actions = await action_center.list_pending_actions(
            broker_id=broker_id,
            user_id=user.get("id")
        )
        return {
            "actions": [action_center.action_to_dict(a) for a in actions],
            "count": len(actions)
        }
    except Exception as e:
        logger.error(f"Failed to list actions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/action-center/stats")
async def get_action_stats(user: Dict = Depends(get_current_user)):
    """Get Action Center statistics."""
    try:
        stats = await action_center.get_action_stats(user.get("id"))
        return stats
    except Exception as e:
        logger.error(f"Failed to get stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Basket Orders Endpoints

@app.post("/api/v1/basket-orders")
async def create_basket_order(
    broker_id: str,
    legs: List[Dict[str, Any]],
    execution_mode: str = "sequential",
    atomic: bool = True,
    user: Dict = Depends(get_current_user)
):
    """Create a new basket order."""
    try:
        basket = await basket_order_service.create_basket(
            broker_id=broker_id,
            user_id=user.get("id"),
            legs=legs,
            execution_mode=execution_mode,
            atomic=atomic
        )
        return basket_order_service.basket_to_dict(basket)
    except Exception as e:
        logger.error(f"Basket order creation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/basket-orders/{basket_id}/execute")
async def execute_basket_order(
    basket_id: str,
    user: Dict = Depends(get_current_user)
):
    """Execute a basket order."""
    try:
        basket = await basket_order_service.execute_basket(basket_id)
        return basket_order_service.basket_to_dict(basket)
    except Exception as e:
        logger.error(f"Basket order execution failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/basket-orders")
async def list_basket_orders(
    broker_id: Optional[str] = None,
    user: Dict = Depends(get_current_user)
):
    """List basket orders."""
    try:
        baskets = await basket_order_service.list_baskets(
            broker_id=broker_id,
            user_id=user.get("id")
        )
        return {
            "baskets": [basket_order_service.basket_to_dict(b) for b in baskets]
        }
    except Exception as e:
        logger.error(f"Failed to list basket orders: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# GTT Orders Endpoints

@app.post("/api/v1/gtt-orders")
async def create_gtt_order(
    broker_id: str,
    symbol: str,
    exchange: str,
    action: str,
    quantity: float,
    gtt_type: str,
    trigger_conditions: List[Dict[str, Any]],
    product_type: str = "DELIVERY",
    validity_days: int = 30,
    user: Dict = Depends(get_current_user)
):
    """Create a new GTT (Good Till Triggered) order."""
    try:
        gtt = await gtt_order_service.create_gtt(
            broker_id=broker_id,
            user_id=user.get("id"),
            symbol=symbol,
            exchange=exchange,
            action=action,
            quantity=quantity,
            gtt_type=gtt_type,
            trigger_conditions=trigger_conditions,
            product_type=product_type,
            validity_days=validity_days
        )
        return gtt_order_service.gtt_to_dict(gtt)
    except Exception as e:
        logger.error(f"GTT order creation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/gtt-orders/{gtt_id}/cancel")
async def cancel_gtt_order(
    gtt_id: str,
    user: Dict = Depends(get_current_user)
):
    """Cancel a GTT order."""
    try:
        success = await gtt_order_service.cancel_gtt(gtt_id)
        if not success:
            raise HTTPException(status_code=404, detail="GTT order not found")
        return {"success": True, "message": "GTT order cancelled"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"GTT cancellation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/gtt-orders")
async def list_gtt_orders(
    broker_id: Optional[str] = None,
    status: Optional[str] = None,
    user: Dict = Depends(get_current_user)
):
    """List GTT orders."""
    try:
        status_enum = GTTStatus(status) if status else None
        gtts = await gtt_order_service.list_gtts(
            broker_id=broker_id,
            user_id=user.get("id"),
            status=status_enum
        )
        return {
            "gtt_orders": [gtt_order_service.gtt_to_dict(g) for g in gtts]
        }
    except Exception as e:
        logger.error(f"Failed to list GTT orders: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Order Splitter Endpoints

@app.post("/api/v1/split-orders")
async def create_split_order(
    broker_id: str,
    symbol: str,
    exchange: str,
    action: str,
    order_type: str,
    total_quantity: float,
    strategy: str,
    strategy_params: Dict[str, Any],
    price: Optional[float] = None,
    product_type: str = "INTRADAY",
    user: Dict = Depends(get_current_user)
):
    """Create a split order for large block orders."""
    try:
        split = await order_splitter_service.create_split_order(
            broker_id=broker_id,
            user_id=user.get("id"),
            symbol=symbol,
            exchange=exchange,
            action=action,
            order_type=order_type,
            total_quantity=total_quantity,
            strategy=strategy,
            strategy_params=strategy_params,
            price=price,
            product_type=product_type
        )
        return order_splitter_service.split_order_to_dict(split)
    except Exception as e:
        logger.error(f"Split order creation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/split-orders/{split_id}/execute")
async def execute_split_order(
    split_id: str,
    user: Dict = Depends(get_current_user)
):
    """Execute a split order."""
    try:
        split = await order_splitter_service.execute_split_order(split_id)
        return order_splitter_service.split_order_to_dict(split)
    except Exception as e:
        logger.error(f"Split order execution failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/split-orders")
async def list_split_orders(
    broker_id: Optional[str] = None,
    user: Dict = Depends(get_current_user)
):
    """List split orders."""
    try:
        splits = await order_splitter_service.list_split_orders(
            broker_id=broker_id,
            user_id=user.get("id")
        )
        return {
            "split_orders": [order_splitter_service.split_order_to_dict(s) for s in splits]
        }
    except Exception as e:
        logger.error(f"Failed to list split orders: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Phase 4.3: Initialize Security Middleware
# ============================================================================

@app.on_event("startup")
async def initialize_security():
    """Initialize security middleware on startup."""
    if security_middleware_config["enable_rate_limit"]:
        rate_limit = security_middleware_config["rate_limit_per_minute"]
        logger.info(f"Rate limiting enabled: {rate_limit} requests/minute")
        # Security middleware is applied via decorator pattern in security_middleware.py


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("BROKER_SERVICE_PORT", "8010"))
    uvicorn.run(app, host="0.0.0.0", port=port)
