"""
Telegram Command Parser

Parses and validates Telegram bot commands.
Requirements: 9.1, 9.2, 9.6, 42.1, 42.2
"""

import re
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum

from services.telegram_service.models.telegram_models import CommandType

logger = logging.getLogger(__name__)


class CommandParameter(Enum):
    """Command parameter types"""
    SYMBOL = "symbol"
    QUANTITY = "quantity"
    PRICE = "price"
    ORDER_TYPE = "order_type"
    PRODUCT_TYPE = "product_type"
    ORDER_ID = "order_id"
    FORCE = "force"


@dataclass
class ParsedCommand:
    """Parsed command structure"""
    type: CommandType
    raw_text: str
    symbol: Optional[str] = None
    quantity: Optional[int] = None
    price: Optional[float] = None
    order_type: str = "MARKET"
    product_type: str = "INTRADAY"
    order_id: Optional[str] = None
    force: bool = False
    flags: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None


@dataclass
class CommandValidationResult:
    """Command validation result"""
    valid: bool
    error_message: Optional[str] = None
    missing_params: List[str] = field(default_factory=list)


class TelegramCommandParser:
    """Parse Telegram commands"""
    
    # Command shortcuts mapping
    COMMAND_SHORTCUTS = {
        "/b": "/buy",
        "/s": "/sell",
        "/p": "/positions",
        "/o": "/orders",
        "/c": "/cancel",
        "/st": "/status",
        "/h": "/help",
    }
    
    # Valid order types
    ORDER_TYPES = ["MARKET", "LIMIT", "SL", "SL-M", "STOP_LOSS", "STOP_LOSS_MARKET"]
    
    # Valid product types
    PRODUCT_TYPES = ["INTRADAY", "MIS", "DELIVERY", "CNC", "MARGIN", "NRML"]
    
    # Command patterns
    SYMBOL_PATTERN = re.compile(r'^[A-Z]+$')
    QUANTITY_PATTERN = re.compile(r'^\d+$')
    PRICE_PATTERN = re.compile(r'^\d+(\.\d{1,4})?$')
    
    def __init__(self):
        self.command_handlers = {
            "/start": self._parse_start,
            "/help": self._parse_help,
            "/auth": self._parse_auth,
            "/buy": self._parse_buy_sell,
            "/sell": self._parse_buy_sell,
            "/positions": self._parse_positions,
            "/orders": self._parse_orders,
            "/cancel": self._parse_cancel,
            "/status": self._parse_status,
        }
    
    def parse_command(self, message_text: str) -> ParsedCommand:
        """
        Parse command from message text.
        Requirements: 9.1, 9.2, 9.6
        """
        if not message_text:
            return ParsedCommand(
                type=CommandType.UNKNOWN,
                raw_text="",
                error_message="Empty message"
            )
        
        # Normalize command (handle shortcuts)
        normalized_text = self._normalize_command(message_text.strip())
        parts = normalized_text.split()
        
        if not parts:
            return ParsedCommand(
                type=CommandType.UNKNOWN,
                raw_text=message_text,
                error_message="Empty command"
            )
        
        command_str = parts[0].lower()
        args = parts[1:] if len(parts) > 1 else []
        
        # Get command type
        command_type = self._get_command_type(command_str)
        
        # Parse based on command type
        if command_type in [CommandType.BUY, CommandType.SELL]:
            return self._parse_buy_sell(command_type, args, message_text)
        elif command_type == CommandType.AUTH:
            return self._parse_auth(args, message_text)
        elif command_type == CommandType.CANCEL:
            return self._parse_cancel(args, message_text)
        elif command_type == CommandType.ORDERS:
            return self._parse_orders(args, message_text)
        elif command_type == CommandType.POSITIONS:
            return self._parse_positions(args, message_text)
        elif command_type == CommandType.STATUS:
            return self._parse_status(args, message_text)
        elif command_type == CommandType.HELP:
            return self._parse_help(args, message_text)
        elif command_type == CommandType.START:
            return self._parse_start(args, message_text)
        else:
            return ParsedCommand(
                type=CommandType.UNKNOWN,
                raw_text=message_text,
                error_message=f"Unknown command: {command_str}. Type /help to see available commands."
            )
    
    def _normalize_command(self, text: str) -> str:
        """Expand command shortcuts"""
        parts = text.split()
        if not parts:
            return text
        
        command = parts[0].lower()
        if command in self.COMMAND_SHORTCUTS:
            parts[0] = self.COMMAND_SHORTCUTS[command]
            return " ".join(parts)
        
        return text
    
    def _get_command_type(self, command: str) -> CommandType:
        """Get command type from command string"""
        command_map = {
            "/start": CommandType.START,
            "/help": CommandType.HELP,
            "/auth": CommandType.AUTH,
            "/buy": CommandType.BUY,
            "/sell": CommandType.SELL,
            "/positions": CommandType.POSITIONS,
            "/orders": CommandType.ORDERS,
            "/cancel": CommandType.CANCEL,
            "/status": CommandType.STATUS,
        }
        return command_map.get(command, CommandType.UNKNOWN)
    
    def _parse_buy_sell(
        self, 
        command_type: CommandType, 
        args: List[str], 
        raw_text: str
    ) -> ParsedCommand:
        """
        Parse buy/sell command.
        Format: /buy SYMBOL QUANTITY [PRICE] [--sl STOP_PRICE] [--target TARGET_PRICE] [--force]
        """
        if not args:
            return ParsedCommand(
                type=command_type,
                raw_text=raw_text,
                error_message="❌ Missing required parameters.\n\nUsage:\n/buy SYMBOL QUANTITY [PRICE]\n\nExample:\n/buy RELIANCE 10 2450.50"
            )
        
        symbol = None
        quantity = None
        price = None
        order_type = "MARKET"
        product_type = "INTRADAY"
        force = False
        flags = {}
        
        # Parse arguments
        i = 0
        while i < len(args):
            arg = args[i].upper()
            
            # Check for flags
            if arg == "--FORCE" or arg == "-F":
                force = True
                i += 1
                continue
            
            if arg == "--SL" or arg == "--STOP":
                if i + 1 < len(args):
                    try:
                        flags["stop_loss"] = float(args[i + 1])
                        i += 2
                        continue
                    except ValueError:
                        pass
                i += 1
                continue
            
            if arg == "--TARGET" or arg == "--TG":
                if i + 1 < len(args):
                    try:
                        flags["target_price"] = float(args[i + 1])
                        i += 2
                        continue
                    except ValueError:
                        pass
                i += 1
                continue
            
            if arg in ["MIS", "CNC", "NRML", "INTRADAY", "DELIVERY", "MARGIN"]:
                product_type_map = {
                    "MIS": "INTRADAY",
                    "CNC": "DELIVERY",
                    "NRML": "MARGIN"
                }
                product_type = product_type_map.get(arg, arg)
                i += 1
                continue
            
            if arg in ["MARKET", "LIMIT", "SL", "SL-M"]:
                order_type = arg
                i += 1
                continue
            
            # Parse symbol (first uppercase word)
            if symbol is None and self.SYMBOL_PATTERN.match(arg):
                symbol = arg
                i += 1
                continue
            
            # Parse quantity (first number)
            if quantity is None and self.QUANTITY_PATTERN.match(arg):
                try:
                    quantity = int(arg)
                    i += 1
                    continue
                except ValueError:
                    pass
            
            # Parse price (second number or decimal)
            if price is None and self.PRICE_PATTERN.match(arg):
                try:
                    price = float(arg)
                    order_type = "LIMIT"
                    i += 1
                    continue
                except ValueError:
                    pass
            
            i += 1
        
        # Validate required parameters
        if not symbol:
            return ParsedCommand(
                type=command_type,
                raw_text=raw_text,
                error_message="❌ Missing symbol. Please provide a valid symbol like RELIANCE, INFY, etc."
            )
        
        if not quantity:
            return ParsedCommand(
                type=command_type,
                raw_text=raw_text,
                error_message="❌ Missing quantity. Please provide the number of shares to trade."
            )
        
        return ParsedCommand(
            type=command_type,
            raw_text=raw_text,
            symbol=symbol,
            quantity=quantity,
            price=price,
            order_type=order_type,
            product_type=product_type,
            force=force,
            flags=flags
        )
    
    def _parse_auth(self, args: List[str], raw_text: str) -> ParsedCommand:
        """Parse auth command"""
        if not args:
            return ParsedCommand(
                type=CommandType.AUTH,
                raw_text=raw_text,
                error_message="❌ Missing authentication token.\n\nUsage: /auth <token>\n\nGet your token from the SignalixAI web app Settings → Telegram."
            )
        
        token = args[0]
        
        return ParsedCommand(
            type=CommandType.AUTH,
            raw_text=raw_text,
            flags={"token": token}
        )
    
    def _parse_cancel(self, args: List[str], raw_text: str) -> ParsedCommand:
        """Parse cancel command"""
        if not args:
            return ParsedCommand(
                type=CommandType.CANCEL,
                raw_text=raw_text,
                error_message="❌ Missing order ID.\n\nUsage: /cancel <order_id>\n\nUse /orders to see your pending orders."
            )
        
        order_id = args[0]
        
        return ParsedCommand(
            type=CommandType.CANCEL,
            raw_text=raw_text,
            order_id=order_id
        )
    
    def _parse_orders(self, args: List[str], raw_text: str) -> ParsedCommand:
        """Parse orders command"""
        status_filter = None
        
        if args:
            status = args[0].upper()
            if status in ["PENDING", "OPEN", "COMPLETE", "CANCELLED", "REJECTED", "ALL"]:
                status_filter = status if status != "ALL" else None
        
        return ParsedCommand(
            type=CommandType.ORDERS,
            raw_text=raw_text,
            flags={"status_filter": status_filter}
        )
    
    def _parse_positions(self, args: List[str], raw_text: str) -> ParsedCommand:
        """Parse positions command"""
        symbol_filter = None
        
        if args:
            symbol = args[0].upper()
            if self.SYMBOL_PATTERN.match(symbol):
                symbol_filter = symbol
        
        return ParsedCommand(
            type=CommandType.POSITIONS,
            raw_text=raw_text,
            symbol=symbol_filter,
            flags={"symbol_filter": symbol_filter}
        )
    
    def _parse_status(self, args: List[str], raw_text: str) -> ParsedCommand:
        """Parse status command"""
        return ParsedCommand(
            type=CommandType.STATUS,
            raw_text=raw_text
        )
    
    def _parse_help(self, args: List[str], raw_text: str) -> ParsedCommand:
        """Parse help command"""
        topic = None
        
        if args:
            topic = args[0].lower()
        
        return ParsedCommand(
            type=CommandType.HELP,
            raw_text=raw_text,
            flags={"topic": topic}
        )
    
    def _parse_start(self, args: List[str], raw_text: str) -> ParsedCommand:
        """Parse start command"""
        return ParsedCommand(
            type=CommandType.START,
            raw_text=raw_text
        )
    
    def validate_command(self, parsed: ParsedCommand) -> CommandValidationResult:
        """Validate parsed command"""
        if parsed.error_message:
            return CommandValidationResult(
                valid=False,
                error_message=parsed.error_message
            )
        
        return CommandValidationResult(valid=True)
    
    def get_command_help(self, command: Optional[str] = None) -> str:
        """
        Get help text for commands.
        Requirements: 42.1, 42.2, 42.4, 42.5
        """
        if command:
            return self._get_specific_help(command.lower())
        
        return self._get_general_help()
    
    def _get_general_help(self) -> str:
        """Get general help text"""
        return """🤖 <b>SignalixAI Telegram Bot - Available Commands</b>

<b>📊 Trading Commands</b>
/buy SYMBOL QTY [PRICE] - Place buy order
/sell SYMBOL QTY [PRICE] - Place sell order
/positions - View open positions
/orders [STATUS] - View orders
/cancel ORDER_ID - Cancel pending order

<b>ℹ️ Information Commands</b>
/status - Check connection status
/help - Show this help message
/help [command] - Show help for specific command

<b>Shortcuts</b>
/b = /buy, /s = /sell, /p = /positions
/o = /orders, /c = /cancel

<b>Examples:</b>
<code>/buy RELIANCE 10</code> - Market buy 10 shares
<code>/buy INFY 5 1450.50</code> - Limit buy at ₹1450.50
<code>/sell TCS 5 --sl 3200</code> - Sell with stop loss

Type <code>/help [command]</code> for detailed usage.
"""
    
    def _get_specific_help(self, command: str) -> str:
        """Get help for specific command"""
        help_texts = {
            "/buy": """<b>📥 /buy Command</b>

Place a buy order for a stock.

<b>Usage:</b>
/buy SYMBOL QUANTITY [PRICE] [OPTIONS]

<b>Parameters:</b>
• SYMBOL - Stock symbol (e.g., RELIANCE, INFY)
• QUANTITY - Number of shares
• PRICE - Optional limit price (omit for market order)

<b>Options:</b>
• --sl PRICE - Set stop loss
• --target PRICE - Set target price
• --force - Skip confirmation prompt
• MIS/CNC/NRML - Product type

<b>Examples:</b>
<code>/buy RELIANCE 10</code>
<code>/buy INFY 5 1450.50</code>
<code>/buy TCS 2 3200 --sl 3150</code>
<code>/buy SBIN 100 CNC</code> (Delivery)
""",
            "/sell": """<b>📤 /sell Command</b>

Place a sell order for a stock.

<b>Usage:</b>
/sell SYMBOL QUANTITY [PRICE] [OPTIONS]

<b>Parameters:</b>
• SYMBOL - Stock symbol (e.g., RELIANCE, INFY)
• QUANTITY - Number of shares
• PRICE - Optional limit price (omit for market order)

<b>Options:</b>
• --sl PRICE - Set stop loss
• --target PRICE - Set target price
• --force - Skip confirmation prompt
• MIS/CNC/NRML - Product type

<b>Examples:</b>
<code>/sell RELIANCE 10</code>
<code>/sell INFY 5 1450.50</code>
""",
            "/positions": """<b>📊 /positions Command</b>

View your open positions with P&L.

<b>Usage:</b>
/positions [SYMBOL]

<b>Examples:</b>
<code>/positions</code> - Show all positions
<code>/positions RELIANCE</code> - Show specific position
""",
            "/orders": """<b>📋 /orders Command</b>

View your orders with status filtering.

<b>Usage:</b>
/orders [STATUS]

<b>Status options:</b>
• pending - Pending orders
• open - Open orders
• complete - Completed orders
• cancelled - Cancelled orders
• rejected - Rejected orders

<b>Examples:</b>
<code>/orders</code> - Show all orders
<code>/orders pending</code> - Show pending orders
""",
            "/cancel": """<b>❌ /cancel Command</b>

Cancel a pending order.

<b>Usage:</b>
/cancel ORDER_ID

<b>Example:</b>
<code>/cancel 24051500012345</code>

Use /orders to find your order IDs.
""",
            "/auth": """<b>🔐 /auth Command</b>

Authenticate your Telegram account with SignalixAI.

<b>Usage:</b>
/auth TOKEN

<b>How to get your token:</b>
1. Log in to SignalixAI web app
2. Go to Settings → Telegram
3. Click "Generate Token"
4. Copy the token and paste here

<b>Example:</b>
<code>/auth abc123xyz789</code>
""",
        }
        
        # Normalize command
        normalized = command
        if not normalized.startswith("/"):
            normalized = "/" + normalized
        
        return help_texts.get(normalized, f"No specific help available for {command}. Type /help for general usage.")
