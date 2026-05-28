"""
Telegram Message Formatter

Formats messages with emojis, monospace numbers, and inline buttons.
Requirements: 8.5, 33.1, 33.2, 33.3, 33.4, 33.7
"""

import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class InlineButton:
    """Inline keyboard button"""
    text: str
    callback_data: str
    url: Optional[str] = None


@dataclass
class FormattedMessage:
    """Formatted message with optional buttons"""
    text: str
    buttons: Optional[List[List[InlineButton]]] = None
    parse_mode: str = "HTML"


class TelegramMessageFormatter:
    """Format Telegram messages with emojis and styling"""
    
    # Emoji indicators
    EMOJI_SUCCESS = "✅"
    EMOJI_ERROR = "❌"
    EMOJI_PENDING = "⏳"
    EMOJI_INFO = "ℹ️"
    EMOJI_WARNING = "⚠️"
    EMOJI_PROFIT = "🟢"
    EMOJI_LOSS = "🔴"
    EMOJI_BUY = "📥"
    EMOJI_SELL = "📤"
    EMOJI_CHART = "📊"
    EMOJI_MONEY = "💰"
    EMOJI_CLOCK = "🕐"
    EMOJI_LINK = "🔗"
    EMOJI_LOCK = "🔒"
    EMOJI_UNLOCK = "🔓"
    EMOJI_CHECK = "✓"
    EMOJI_CROSS = "✗"
    
    def __init__(self, use_emojis: bool = True, use_monospace: bool = True, timezone: str = "UTC"):
        self.use_emojis = use_emojis
        self.use_monospace = use_monospace
        self.timezone = timezone
        
        # Max message length for Telegram
        self.MAX_MESSAGE_LENGTH = 4096
        self.TRUNCATION_THRESHOLD = 4000
    
    def format_order_alert(
        self,
        order_id: str,
        symbol: str,
        action: str,
        quantity: int,
        order_type: str,
        price: Optional[float],
        status: str,
        message: Optional[str] = None,
        timestamp: Optional[datetime] = None,
        filled_quantity: Optional[int] = None,
        average_price: Optional[float] = None,
        pnl: Optional[float] = None
    ) -> FormattedMessage:
        """
        Format order alert message.
        Requirements: 8.2, 8.3, 8.4, 33.1, 33.2, 33.3
        """
        # Determine emoji based on status and action
        if status.upper() in ["COMPLETE", "EXECUTED", "FILLED"]:
            emoji = self.EMOJI_SUCCESS
        elif status.upper() in ["REJECTED", "CANCELLED", "ERROR"]:
            emoji = self.EMOJI_ERROR
        else:
            emoji = self.EMOJI_PENDING
        
        action_emoji = self.EMOJI_BUY if action.upper() == "BUY" else self.EMOJI_SELL
        
        # Format price
        price_str = self._format_price(price) if price else "Market"
        
        # Build message
        lines = [
            f"{emoji} <b>Order {status.title()}</b>",
            "",
            f"{action_emoji} <b>Action:</b> {action.upper()}",
            f"📈 <b>Symbol:</b> {self._bold(symbol.upper())}",
            f"🔢 <b>Quantity:</b> {self._mono(quantity)}",
            f"💵 <b>Price:</b> {self._mono(price_str)}",
            f"📋 <b>Type:</b> {order_type}",
        ]
        
        # Add execution details if available
        if filled_quantity is not None and filled_quantity > 0:
            lines.append(f"✓ <b>Filled:</b> {self._mono(filled_quantity)}")
        
        if average_price is not None:
            lines.append(f"💰 <b>Avg Price:</b> {self._mono(self._format_price(average_price))}")
        
        # Add P&L for completed orders
        if pnl is not None:
            pnl_emoji = self.EMOJI_PROFIT if pnl >= 0 else self.EMOJI_LOSS
            lines.append(f"{pnl_emoji} <b>P&L:</b> {self._format_pnl(pnl)}")
        
        # Add order ID
        lines.append(f"🆔 <b>Order ID:</b> <code>{order_id}</code>")
        
        # Add timestamp
        if timestamp:
            time_str = self._format_timestamp(timestamp)
            lines.append(f"{self.EMOJI_CLOCK} <b>Time:</b> {time_str}")
        
        # Add custom message if provided
        if message:
            lines.extend(["", f"{self.EMOJI_INFO} {message}"])
        
        text = "\n".join(lines)
        
        # Add inline buttons for quick actions
        buttons = self._create_order_buttons(order_id, status)
        
        return FormattedMessage(text=text, buttons=buttons)
    
    def format_position_list(
        self,
        positions: List[Dict[str, Any]],
        total_pnl: Optional[float] = None
    ) -> FormattedMessage:
        """
        Format position list as a table.
        Requirements: 50.1, 50.2, 33.4
        """
        if not positions:
            return FormattedMessage(
                text=f"{self.EMOJI_INFO} <b>No Open Positions</b>\n\nYou don't have any open positions right now."
            )
        
        lines = [
            f"{self.EMOJI_CHART} <b>Your Positions</b>",
            f"📊 {len(positions)} open position(s)",
            "",
            "<pre>"
        ]
        
        # Table header
        lines.append("Symbol    Qty    Avg    LTP    P&L")
        lines.append("─" * 35)
        
        # Position rows
        for pos in positions:
            symbol = pos.get("symbol", "N/A")[:8].ljust(8)
            qty = str(pos.get("quantity", 0)).rjust(6)
            avg = self._format_price_compact(pos.get("average_price", 0)).rjust(6)
            ltp = self._format_price_compact(pos.get("current_price", 0)).rjust(6)
            pnl = pos.get("pnl", 0)
            pnl_str = self._format_pnl_compact(pnl).rjust(8)
            
            lines.append(f"{symbol}{qty}{avg}{ltp}{pnl_str}")
        
        lines.append("</pre>")
        
        # Total P&L
        if total_pnl is not None:
            pnl_emoji = self.EMOJI_PROFIT if total_pnl >= 0 else self.EMOJI_LOSS
            lines.extend([
                "",
                f"{pnl_emoji} <b>Total P&L:</b> {self._format_pnl(total_pnl)}"
            ])
        
        text = "\n".join(lines)
        text = self._truncate_if_needed(text)
        
        # Add refresh button
        buttons = [[InlineButton("🔄 Refresh Positions", "refresh_positions")]]
        
        return FormattedMessage(text=text, buttons=buttons)
    
    def format_order_list(
        self,
        orders: List[Dict[str, Any]],
        status_filter: Optional[str] = None
    ) -> FormattedMessage:
        """Format order list"""
        if not orders:
            filter_text = f" ({status_filter})" if status_filter else ""
            return FormattedMessage(
                text=f"{self.EMOJI_INFO} <b>No{filter_text} Orders</b>\n\nYou don't have any orders in this status."
            )
        
        lines = [
            f"{self.EMOJI_CHART} <b>Your Orders</b>",
        ]
        
        if status_filter:
            lines.append(f"📋 Status: {status_filter.title()}")
        
        lines.extend(["", "<pre>"])
        
        # Table header
        lines.append("ID          Symbol  Status      Time")
        lines.append("─" * 40)
        
        # Order rows
        for order in orders[:20]:  # Limit to 20 orders
            order_id = str(order.get("order_id", "N/A"))[-10:].ljust(10)
            symbol = order.get("symbol", "N/A")[:6].ljust(6)
            status = order.get("status", "N/A")[:10].ljust(10)
            time = self._format_time_short(order.get("timestamp"))
            
            lines.append(f"{order_id}{symbol}{status}{time}")
        
        lines.append("</pre>")
        
        if len(orders) > 20:
            lines.append(f"\n... and {len(orders) - 20} more orders")
        
        text = "\n".join(lines)
        text = self._truncate_if_needed(text)
        
        # Add filter buttons
        buttons = [
            [
                InlineButton("⏳ Pending", "orders_pending"),
                InlineButton("✓ Complete", "orders_complete"),
            ],
            [
                InlineButton("🔄 Refresh", "refresh_orders"),
            ]
        ]
        
        return FormattedMessage(text=text, buttons=buttons)
    
    def format_order_confirmation_prompt(
        self,
        symbol: str,
        action: str,
        quantity: int,
        order_type: str,
        price: Optional[float],
        product_type: str
    ) -> FormattedMessage:
        """
        Format order confirmation prompt with inline buttons.
        Requirements: 56.1, 56.2, 56.3, 56.4, 56.10
        """
        action_emoji = self.EMOJI_BUY if action.upper() == "BUY" else self.EMOJI_SELL
        price_str = self._format_price(price) if price else "Market"
        
        lines = [
            f"{self.EMOJI_WARNING} <b>Confirm Order</b>",
            "",
            f"{action_emoji} <b>Action:</b> {action.upper()}",
            f"📈 <b>Symbol:</b> {self._bold(symbol.upper())}",
            f"🔢 <b>Quantity:</b> {self._mono(quantity)}",
            f"💵 <b>Price:</b> {self._mono(price_str)}",
            f"📋 <b>Type:</b> {order_type}",
            f"📦 <b>Product:</b> {product_type}",
            "",
            f"⏱️ This prompt will expire in <b>60 seconds</b>",
        ]
        
        text = "\n".join(lines)
        
        # Add confirm/cancel buttons
        buttons = [
            [
                InlineButton(f"{self.EMOJI_SUCCESS} Confirm", f"confirm_order"),
                InlineButton(f"{self.EMOJI_ERROR} Cancel", f"cancel_order"),
            ]
        ]
        
        return FormattedMessage(text=text, buttons=buttons)
    
    def format_command_result(
        self,
        success: bool,
        message: str,
        data: Optional[Dict[str, Any]] = None
    ) -> FormattedMessage:
        """Format command execution result"""
        emoji = self.EMOJI_SUCCESS if success else self.EMOJI_ERROR
        
        lines = [f"{emoji} {message}"]
        
        if data:
            lines.append("")
            for key, value in data.items():
                lines.append(f"• <b>{key}:</b> {self._mono(value)}")
        
        text = "\n".join(lines)
        
        return FormattedMessage(text=text)
    
    def format_error(self, error_message: str, suggestion: Optional[str] = None) -> FormattedMessage:
        """Format error message"""
        lines = [
            f"{self.EMOJI_ERROR} <b>Error</b>",
            "",
            error_message
        ]
        
        if suggestion:
            lines.extend(["", f"{self.EMOJI_INFO} <b>Tip:</b> {suggestion}"])
        
        text = "\n".join(lines)
        
        return FormattedMessage(text=text)
    
    def format_welcome_message(self, first_name: Optional[str] = None) -> FormattedMessage:
        """Format welcome message for new users"""
        greeting = f"Hello {first_name}!" if first_name else "Hello!"
        
        text = f"""{self.EMOJI_SUCCESS} <b>{greeting}</b>

Welcome to <b>SignalixAI Telegram Bot</b> - your trading companion!

<b>🔐 First Steps:</b>
1. Log in to the SignalixAI Web App
2. Go to Settings → Telegram
3. Generate an authentication token
4. Use <code>/auth &lt;token&gt;</code> here

<b>📊 What You Can Do:</b>
• Receive real-time order alerts
• View positions and orders
• Execute trades via commands
• Get instant market updates

<b>ℹ️ Need Help?</b>
Type <code>/help</code> anytime for command reference.

{self.EMOJI_LINK} <a href="https://app.signalixai.com">Open SignalixAI Web App</a>
"""
        
        return FormattedMessage(text=text)
    
    def format_status_message(
        self,
        connected: bool,
        username: Optional[str] = None,
        last_activity: Optional[datetime] = None
    ) -> FormattedMessage:
        """Format connection status message"""
        if connected:
            emoji = self.EMOJI_SUCCESS
            status_text = "Connected"
            lines = [
                f"{emoji} <b>Status: {status_text}</b>",
                "",
                f"👤 <b>Account:</b> @{username}" if username else "👤 <b>Account:</b> Linked",
            ]
            
            if last_activity:
                lines.append(f"{self.EMOJI_CLOCK} <b>Last Activity:</b> {self._format_timestamp(last_activity)}")
            
            lines.extend([
                "",
                "✓ You can receive alerts and execute commands.",
            ])
        else:
            emoji = self.EMOJI_ERROR
            status_text = "Not Connected"
            lines = [
                f"{emoji} <b>Status: {status_text}</b>",
                "",
                "Your Telegram account is not linked to SignalixAI.",
                "",
                "🔐 To connect:",
                "1. Visit Settings → Telegram in the web app",
                "2. Generate an authentication token",
                "3. Use /auth &lt;token&gt; here",
            ]
        
        text = "\n".join(lines)
        
        return FormattedMessage(text=text)
    
    def _format_price(self, price: float) -> str:
        """Format price with monospace if enabled"""
        price_str = f"₹{price:,.2f}"
        return self._mono(price_str) if self.use_monospace else price_str
    
    def _format_price_compact(self, price: float) -> str:
        """Format price in compact form"""
        if price >= 1000:
            return f"{price/1000:.1f}K"
        return f"{price:.0f}"
    
    def _format_pnl(self, pnl: float) -> str:
        """Format P&L with color indicator"""
        sign = "+" if pnl >= 0 else ""
        pnl_str = f"{sign}₹{abs(pnl):,.2f}"
        
        if self.use_monospace:
            pnl_str = self._mono(pnl_str)
        
        return pnl_str
    
    def _format_pnl_compact(self, pnl: float) -> str:
        """Format P&L in compact form"""
        sign = "+" if pnl >= 0 else ""
        if abs(pnl) >= 1000:
            return f"{sign}{pnl/1000:.1f}K"
        return f"{sign}{pnl:.0f}"
    
    def _format_timestamp(self, timestamp: Any) -> str:
        """Format timestamp"""
        if isinstance(timestamp, str):
            try:
                timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            except:
                return timestamp
        
        if isinstance(timestamp, datetime):
            return timestamp.strftime("%Y-%m-%d %H:%M:%S")
        
        return str(timestamp)
    
    def _format_time_short(self, timestamp: Any) -> str:
        """Format time in short form"""
        if isinstance(timestamp, str):
            try:
                timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            except:
                return "--:--"
        
        if isinstance(timestamp, datetime):
            return timestamp.strftime("%H:%M")
        
        return "--:--"
    
    def _mono(self, text: str) -> str:
        """Wrap text in monospace HTML tag"""
        if self.use_monospace:
            return f"<code>{text}</code>"
        return text
    
    def _bold(self, text: str) -> str:
        """Wrap text in bold HTML tag"""
        return f"<b>{text}</b>"
    
    def _truncate_if_needed(self, text: str) -> str:
        """
        Truncate long messages.
        Requirements: 33.7
        """
        if len(text) <= self.MAX_MESSAGE_LENGTH:
            return text
        
        # Truncate and add notice
        truncated = text[:self.TRUNCATION_THRESHOLD]
        
        # Find last complete line
        last_newline = truncated.rfind('\n')
        if last_newline > 0:
            truncated = truncated[:last_newline]
        
        truncated += f"\n\n{self.EMOJI_WARNING} <i>Message truncated. Use the web app for full details.</i>"
        
        return truncated
    
    def _create_order_buttons(
        self, 
        order_id: str, 
        status: str
    ) -> Optional[List[List[InlineButton]]]:
        """Create inline buttons for order actions"""
        buttons = []
        
        status_upper = status.upper()
        
        # Add cancel button for pending orders
        if status_upper in ["PENDING", "OPEN"]:
            buttons.append([
                InlineButton(f"{self.EMOJI_ERROR} Cancel Order", f"cancel_order:{order_id}")
            ])
        
        # Add view buttons
        buttons.append([
            InlineButton("📊 View Positions", "view_positions"),
            InlineButton("📋 View Orders", "view_orders"),
        ])
        
        return buttons if buttons else None
    
    def batch_notifications(
        self, 
        notifications: List[FormattedMessage]
    ) -> FormattedMessage:
        """
        Batch multiple notifications into one message.
        Requirements: 8.6
        """
        if not notifications:
            return FormattedMessage(text="")
        
        if len(notifications) == 1:
            return notifications[0]
        
        lines = [
            f"{self.EMOJI_INFO} <b>{len(notifications)} Order Updates</b>",
            ""
        ]
        
        for i, notif in enumerate(notifications, 1):
            # Strip HTML tags for summary
            text = notif.text.replace('<b>', '').replace('</b>', '')
            text = text.replace('<code>', '').replace('</code>', '')
            text = text.replace('<pre>', '').replace('</pre>', '')
            
            # Extract first line (usually the status)
            first_line = text.split('\n')[0][:50]
            lines.append(f"{i}. {first_line}...")
        
        lines.extend([
            "",
            "Use the web app for complete details."
        ])
        
        text = "\n".join(lines)
        text = self._truncate_if_needed(text)
        
        return FormattedMessage(text=text)
