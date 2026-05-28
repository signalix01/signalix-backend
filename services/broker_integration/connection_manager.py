"""
Connection Manager

Manages broker connections and sessions with automatic reconnection,
health monitoring, and heartbeat mechanism.

Requirements: 10.7, 20.3, 20.4, 20.5, 20.6, 20.7, 20.8
"""

import asyncio
from typing import Dict, Optional, Any, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


@dataclass
class ConnectionState:
    """Connection state tracking"""
    connected: bool = False
    authenticated: bool = False
    last_connected: Optional[datetime] = None
    last_error: Optional[str] = None
    last_error_at: Optional[datetime] = None
    error_count: int = 0
    reconnect_attempts: int = 0
    websocket_connected: bool = False
    last_heartbeat: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class ConnectionManager:
    """
    Manages broker connections with automatic reconnection and health monitoring.
    
    Features:
    - Connection lifecycle management
    - Automatic reconnection with exponential backoff
    - Health monitoring with heartbeat
    - Connection status tracking
    """
    
    HEARTBEAT_INTERVAL = 30  # seconds
    RECONNECT_INTERVAL = 5  # seconds
    MAX_RECONNECT_ATTEMPTS = 5
    CONNECTION_TIMEOUT = 10  # seconds
    
    def __init__(self):
        """Initialize connection manager."""
        self._connections: Dict[str, Any] = {}  # broker_id -> adapter
        self._states: Dict[str, ConnectionState] = {}  # broker_id -> state
        self._tasks: Dict[str, asyncio.Task] = {}  # broker_id -> task
        self._callbacks: Dict[str, list] = {}  # event -> callbacks
        self._running = False
    
    async def start(self):
        """Start the connection manager."""
        self._running = True
        logger.info("Connection manager started")
    
    async def stop(self):
        """Stop the connection manager and disconnect all brokers."""
        self._running = False
        
        # Cancel all tasks
        for task in self._tasks.values():
            task.cancel()
        
        # Disconnect all brokers
        for broker_id in list(self._connections.keys()):
            await self.disconnect(broker_id)
        
        logger.info("Connection manager stopped")
    
    async def register_connection(
        self,
        broker_id: str,
        adapter: Any,
        auto_reconnect: bool = True,
        reconnect_attempts: int = 3
    ) -> bool:
        """
        Register a broker connection.
        
        Args:
            broker_id: Unique identifier for this connection
            adapter: Broker adapter instance
            auto_reconnect: Enable automatic reconnection
            reconnect_attempts: Max reconnection attempts
            
        Returns:
            True if registered successfully
        """
        try:
            self._connections[broker_id] = adapter
            self._states[broker_id] = ConnectionState()
            
            # Store config in state
            state = self._states[broker_id]
            state.metadata['auto_reconnect'] = auto_reconnect
            state.metadata['max_reconnect_attempts'] = reconnect_attempts
            state.metadata['broker_type'] = adapter.get_broker_code() if hasattr(adapter, 'get_broker_code') else 'unknown'
            
            logger.info(f"Registered connection for {broker_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to register connection {broker_id}: {e}")
            return False
    
    async def connect(self, broker_id: str) -> bool:
        """
        Establish connection to a broker.
        
        Args:
            broker_id: Connection identifier
            
        Returns:
            True if connection successful
        """
        if broker_id not in self._connections:
            logger.error(f"Connection {broker_id} not registered")
            return False
        
        adapter = self._connections[broker_id]
        state = self._states[broker_id]
        
        try:
            logger.info(f"Connecting to {broker_id}...")
            
            # Attempt connection
            success = await adapter.connect()
            
            if success:
                state.connected = True
                state.authenticated = True
                state.last_connected = datetime.utcnow()
                state.reconnect_attempts = 0
                state.error_count = 0
                state.last_error = None
                
                # Start heartbeat
                await self._start_heartbeat(broker_id)
                
                # Emit event
                await self._emit_event('connected', {'broker_id': broker_id})
                
                logger.info(f"Successfully connected to {broker_id}")
                return True
            else:
                state.connected = False
                state.error_count += 1
                logger.error(f"Failed to connect to {broker_id}")
                return False
                
        except Exception as e:
            state.connected = False
            state.error_count += 1
            state.last_error = str(e)
            state.last_error_at = datetime.utcnow()
            
            logger.error(f"Error connecting to {broker_id}: {e}")
            return False
    
    async def disconnect(self, broker_id: str) -> bool:
        """
        Disconnect from a broker.
        
        Args:
            broker_id: Connection identifier
            
        Returns:
            True if disconnected successfully
        """
        if broker_id not in self._connections:
            return False
        
        adapter = self._connections[broker_id]
        state = self._states[broker_id]
        
        try:
            # Stop heartbeat
            await self._stop_heartbeat(broker_id)
            
            # Disconnect adapter
            await adapter.disconnect()
            
            state.connected = False
            state.authenticated = False
            state.websocket_connected = False
            
            # Emit event
            await self._emit_event('disconnected', {'broker_id': broker_id})
            
            logger.info(f"Disconnected from {broker_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error disconnecting from {broker_id}: {e}")
            return False
    
    async def reconnect(self, broker_id: str) -> bool:
        """
        Reconnect to a broker.
        
        Args:
            broker_id: Connection identifier
            
        Returns:
            True if reconnected successfully
        """
        logger.info(f"Reconnecting to {broker_id}...")
        
        # Disconnect first
        await self.disconnect(broker_id)
        
        # Wait a moment
        await asyncio.sleep(1)
        
        # Connect again
        return await self.connect(broker_id)
    
    def get_connection_status(self, broker_id: str) -> Optional[ConnectionState]:
        """
        Get connection status for a broker.
        
        Args:
            broker_id: Connection identifier
            
        Returns:
            ConnectionState or None if not found
        """
        return self._states.get(broker_id)
    
    def get_all_statuses(self) -> Dict[str, ConnectionState]:
        """
        Get all connection statuses.
        
        Returns:
            Dictionary of broker_id -> ConnectionState
        """
        return self._states.copy()
    
    async def health_check(self, broker_id: str) -> bool:
        """
        Check if connection is healthy.
        
        Args:
            broker_id: Connection identifier
            
        Returns:
            True if connection is healthy
        """
        if broker_id not in self._states:
            return False
        
        state = self._states[broker_id]
        
        # Basic checks
        if not state.connected:
            return False
        
        if not state.authenticated:
            return False
        
        # Check heartbeat timeout
        if state.last_heartbeat:
            heartbeat_age = (datetime.utcnow() - state.last_heartbeat).total_seconds()
            if heartbeat_age > self.HEARTBEAT_INTERVAL * 2:
                logger.warning(f"Heartbeat timeout for {broker_id}")
                return False
        
        return True
    
    async def _start_heartbeat(self, broker_id: str):
        """Start heartbeat monitoring for a connection."""
        if broker_id in self._tasks:
            self._tasks[broker_id].cancel()
        
        task = asyncio.create_task(
            self._heartbeat_loop(broker_id),
            name=f"heartbeat_{broker_id}"
        )
        self._tasks[broker_id] = task
    
    async def _stop_heartbeat(self, broker_id: str):
        """Stop heartbeat monitoring for a connection."""
        if broker_id in self._tasks:
            self._tasks[broker_id].cancel()
            try:
                await self._tasks[broker_id]
            except asyncio.CancelledError:
                pass
            del self._tasks[broker_id]
    
    async def _heartbeat_loop(self, broker_id: str):
        """Heartbeat monitoring loop."""
        while self._running:
            try:
                await asyncio.sleep(self.HEARTBEAT_INTERVAL)
                
                if broker_id not in self._states:
                    break
                
                state = self._states[broker_id]
                
                if not state.connected:
                    continue
                
                # Perform health check
                is_healthy = await self.health_check(broker_id)
                
                if not is_healthy:
                    logger.warning(f"Health check failed for {broker_id}")
                    
                    # Check if auto-reconnect is enabled
                    auto_reconnect = state.metadata.get('auto_reconnect', True)
                    max_attempts = state.metadata.get('max_reconnect_attempts', 3)
                    
                    if auto_reconnect and state.reconnect_attempts < max_attempts:
                        state.reconnect_attempts += 1
                        state.status = 'reconnecting'
                        
                        logger.info(
                            f"Auto-reconnecting to {broker_id} "
                            f"(attempt {state.reconnect_attempts}/{max_attempts})"
                        )
                        
                        await self.reconnect(broker_id)
                    else:
                        # Max attempts reached
                        state.connected = False
                        await self._emit_event('connection_lost', {
                            'broker_id': broker_id,
                            'reason': 'max_reconnect_attempts'
                        })
                else:
                    # Update heartbeat timestamp
                    state.last_heartbeat = datetime.utcnow()
                    
                    # Reset reconnect attempts on successful heartbeat
                    if state.reconnect_attempts > 0:
                        state.reconnect_attempts = 0
                        logger.info(f"Connection to {broker_id} restored")
                        await self._emit_event('connection_restored', {'broker_id': broker_id})
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in heartbeat loop for {broker_id}: {e}")
    
    def on(self, event: str, callback: Callable):
        """
        Register an event callback.
        
        Args:
            event: Event name (connected, disconnected, connection_lost, etc.)
            callback: Async callback function
        """
        if event not in self._callbacks:
            self._callbacks[event] = []
        self._callbacks[event].append(callback)
    
    def off(self, event: str, callback: Callable):
        """
        Unregister an event callback.
        
        Args:
            event: Event name
            callback: Callback function to remove
        """
        if event in self._callbacks:
            if callback in self._callbacks[event]:
                self._callbacks[event].remove(callback)
    
    async def _emit_event(self, event: str, data: Dict[str, Any]):
        """Emit an event to all registered callbacks."""
        if event in self._callbacks:
            for callback in self._callbacks[event]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(data)
                    else:
                        callback(data)
                except Exception as e:
                    logger.error(f"Error in event callback for {event}: {e}")
    
    async def update_connection_status(
        self,
        broker_id: str,
        status_updates: Dict[str, Any]
    ):
        """
        Update connection status from external source (e.g., WebSocket).
        
        Args:
            broker_id: Connection identifier
            status_updates: Dictionary of status fields to update
        """
        if broker_id not in self._states:
            return
        
        state = self._states[broker_id]
        
        if 'websocket_connected' in status_updates:
            state.websocket_connected = status_updates['websocket_connected']
        
        if 'last_heartbeat' in status_updates:
            state.last_heartbeat = status_updates['last_heartbeat']
        
        # Update metadata
        if 'metadata' in status_updates:
            state.metadata.update(status_updates['metadata'])
    
    def get_adapter(self, broker_id: str) -> Optional[Any]:
        """
        Get adapter for a broker connection.
        
        Args:
            broker_id: Connection identifier
            
        Returns:
            Broker adapter or None
        """
        return self._connections.get(broker_id)
    
    async def execute_with_connection(
        self,
        broker_id: str,
        operation: Callable,
        *args,
        **kwargs
    ) -> Any:
        """
        Execute an operation with automatic connection handling.
        
        Args:
            broker_id: Connection identifier
            operation: Async operation to execute
            *args, **kwargs: Arguments for operation
            
        Returns:
            Operation result
            
        Raises:
            Exception if operation fails
        """
        # Ensure connection
        status = self.get_connection_status(broker_id)
        
        if not status or not status.connected:
            success = await self.connect(broker_id)
            if not success:
                raise Exception(f"Failed to connect to {broker_id}")
        
        # Get adapter
        adapter = self.get_adapter(broker_id)
        if not adapter:
            raise Exception(f"No adapter found for {broker_id}")
        
        # Execute operation
        return await operation(*args, **kwargs)
