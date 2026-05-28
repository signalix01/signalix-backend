"""
Command Executor

Executes parsed Telegram commands.
Requirements: 9.3, 9.4, 9.7, 50.1, 50.2
"""

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

from services.telegram_service.models.telegram_models import (
    TelegramConnection, TelegramPreferences, CommandType
)
from services.telegram_service.commands.command_parser import ParsedCommand

logger = logging.getLogger(__name__)


class CommandExecutor:
    """Execute Telegram commands"""
    
    def __init__(self):
        self.command_map = {
            CommandType.BUY: self._execute_buy,
            CommandType.SELL: self._execute_sell,
            CommandType.POSITIONS: self._execute_positions,
            CommandType.ORDERS: self._execute_orders,
            CommandType.CANCEL: self._execute_cancel,
            CommandType.STATUS: self._execute_status,
            CommandType.HELP: self._execute_help,
            CommandType.START: self._execute_start,
        }
    
    async def execute(
        self,
        command: ParsedCommand,
        connection: TelegramConnection,
        preferences: Optional[TelegramPreferences]
    ) -> Dict[str, Any]:
        """Execute a parsed command"""
        
        handler = self.command_map.get(command.type)
        
        if not handler:
            return {
                "success": False,
                "message": f"Command '{command.type.value}' is not yet implemented."
            }
        
        try:
            return await handler(command, connection, preferences)
        except Exception as e:
            logger.error(f"Error executing command: {e}")
            return {
                "success": False,
                "message": f"An error occurred: {str(e)}"
            }
    
    async def _execute_buy(
        self, 
        command: ParsedCommand, 
        connection: TelegramConnection,
        preferences: Optional[TelegramPreferences]
    ) -> Dict[str, Any]:
        """Execute buy command"""
        # This is handled by the trade execution in router.py
        return {
            "success": True,
            "message": f"Buy command received for {command.symbol}",
            "data": {
                "symbol": command.symbol,
                "quantity": command.quantity,
                "price": command.price,
                "order_type": command.order_type
            }
        }
    
    async def _execute_sell(
        self, 
        command: ParsedCommand, 
        connection: TelegramConnection,
        preferences: Optional[TelegramPreferences]
    ) -> Dict[str, Any]:
        """Execute sell command"""
        return {
            "success": True,
            "message": f"Sell command received for {command.symbol}",
            "data": {
                "symbol": command.symbol,
                "quantity": command.quantity,
                "price": command.price,
                "order_type": command.order_type
            }
        }
    
    async def _execute_positions(
        self, 
        command: ParsedCommand, 
        connection: TelegramConnection,
        preferences: Optional[TelegramPreferences]
    ) -> Dict[str, Any]:
        """Execute positions command"""
        return {
            "success": True,
            "message": "Fetching positions...",
            "data": {"action": "fetch_positions"}
        }
    
    async def _execute_orders(
        self, 
        command: ParsedCommand, 
        connection: TelegramConnection,
        preferences: Optional[TelegramPreferences]
    ) -> Dict[str, Any]:
        """Execute orders command"""
        return {
            "success": True,
            "message": "Fetching orders...",
            "data": {
                "action": "fetch_orders",
                "status_filter": command.flags.get("status_filter")
            }
        }
    
    async def _execute_cancel(
        self, 
        command: ParsedCommand, 
        connection: TelegramConnection,
        preferences: Optional[TelegramPreferences]
    ) -> Dict[str, Any]:
        """Execute cancel command"""
        if not command.order_id:
            return {
                "success": False,
                "message": "Order ID is required. Usage: /cancel <order_id>"
            }
        
        return {
            "success": True,
            "message": f"Cancelling order {command.order_id}...",
            "data": {"order_id": command.order_id}
        }
    
    async def _execute_status(
        self, 
        command: ParsedCommand, 
        connection: TelegramConnection,
        preferences: Optional[TelegramPreferences]
    ) -> Dict[str, Any]:
        """Execute status command"""
        return {
            "success": True,
            "message": "Checking status...",
            "data": {
                "connected": True,
                "username": connection.telegram_username,
                "last_activity": connection.last_activity_at.isoformat() if connection.last_activity_at else None
            }
        }
    
    async def _execute_help(
        self, 
        command: ParsedCommand, 
        connection: TelegramConnection,
        preferences: Optional[TelegramPreferences]
    ) -> Dict[str, Any]:
        """Execute help command"""
        return {
            "success": True,
            "message": "Displaying help...",
            "data": {"topic": command.flags.get("topic")}
        }
    
    async def _execute_start(
        self, 
        command: ParsedCommand, 
        connection: TelegramConnection,
        preferences: Optional[TelegramPreferences]
    ) -> Dict[str, Any]:
        """Execute start command"""
        return {
            "success": True,
            "message": "Welcome to SignalixAI Bot!",
            "data": {
                "first_name": connection.telegram_first_name,
                "is_new_user": connection.status.value == "pending"
            }
        }
