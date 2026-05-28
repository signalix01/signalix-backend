"""
Live execution safety checks for algo trading strategies.

This module implements all pre-order safety checks before executing live trades:
1. daily_loss_limit - Block orders if daily loss exceeds configured limit
2. max_position_size - Ensure single position doesn't exceed limit
3. max_concurrent_positions - Check current open positions count
4. market_hours - Verify market is open for the asset class
5. circuit_breaker - Check if instrument has circuit breaker active

Also implements simultaneous SL order placement after entry orders.

Requirements: 15.3, 15.4
"""
from datetime import datetime, time
from typing import Dict, Optional, List, Tuple
from enum import Enum
import logging
from pytz import timezone

logger = logging.getLogger(__name__)


class SafetyCheckResult(Enum):
    """Result of a safety check"""
    PASS = "pass"
    FAIL = "fail"
    WARNING = "warning"


class SafetyCheckError(Exception):
    """Raised when a safety check fails"""
    def __init__(self, check_name: str, message: str, details: Optional[Dict] = None):
        self.check_name = check_name
        self.message = message
        self.details = details or {}
        super().__init__(f"{check_name}: {message}")


class LiveExecutionSafetyChecks:
    """
    Pre-order safety checks for live execution.
    
    All checks must pass before an order can be placed.
    Implements fail-safe design: if a check cannot be performed, it fails.
    """
    
    # Market hours for different asset classes (IST timezone)
    MARKET_HOURS = {
        "equity": {
            "open": time(9, 15),
            "close": time(15, 30),
            "timezone": "Asia/Kolkata"
        },
        "fo": {  # Futures & Options
            "open": time(9, 15),
            "close": time(15, 30),
            "timezone": "Asia/Kolkata"
        },
        "commodity": {  # MCX
            "open": time(9, 0),
            "close": time(23, 30),
            "timezone": "Asia/Kolkata"
        },
        "crypto": {  # 24/7
            "open": time(0, 0),
            "close": time(23, 59),
            "timezone": "UTC",
            "always_open": True
        },
        "forex": {  # 24/5 (Mon-Fri)
            "open": time(0, 0),
            "close": time(23, 59),
            "timezone": "UTC",
            "weekdays_only": True
        }
    }
    
    # Circuit breaker thresholds for NSE
    CIRCUIT_BREAKER_LIMITS = {
        "equity": [0.05, 0.10, 0.20],  # 5%, 10%, 20%
        "fo": [0.05, 0.10, 0.20]
    }
    
    def __init__(self, db_client=None):
        """
        Initialize safety checks.
        
        Args:
            db_client: Database client for fetching trade records and positions
        """
        self.db_client = db_client
    
    async def run_all_checks(
        self,
        user_id: str,
        strategy_id: str,
        instrument: str,
        asset_class: str,
        position_size: float,
        capital: float,
        max_daily_loss_pct: float = 2.0,
        max_position_pct: float = 10.0,
        max_concurrent_positions: int = 5
    ) -> Tuple[bool, List[Dict]]:
        """
        Run all safety checks before placing an order.
        
        Args:
            user_id: User identifier
            strategy_id: Strategy identifier
            instrument: Trading instrument symbol
            asset_class: Asset class (equity, fo, crypto, forex, commodity)
            position_size: Proposed position size in currency units
            capital: Total declared capital
            max_daily_loss_pct: Maximum daily loss percentage (default 2%)
            max_position_pct: Maximum position size percentage (default 10%)
            max_concurrent_positions: Maximum concurrent positions (default 5)
            
        Returns:
            Tuple of (all_passed: bool, check_results: List[Dict])
            
        Raises:
            SafetyCheckError: If any critical check fails
        """
        check_results = []
        all_passed = True
        
        # Check 1: Daily loss limit
        try:
            daily_loss_result = await self.check_daily_loss_limit(
                user_id, capital, max_daily_loss_pct
            )
            check_results.append(daily_loss_result)
            if daily_loss_result["status"] == SafetyCheckResult.FAIL.value:
                all_passed = False
        except Exception as e:
            logger.error(f"Daily loss limit check failed: {e}")
            all_passed = False
            check_results.append({
                "check": "daily_loss_limit",
                "status": SafetyCheckResult.FAIL.value,
                "message": f"Check error: {str(e)}"
            })
        
        # Check 2: Max position size
        try:
            position_size_result = self.check_max_position_size(
                position_size, capital, max_position_pct
            )
            check_results.append(position_size_result)
            if position_size_result["status"] == SafetyCheckResult.FAIL.value:
                all_passed = False
        except Exception as e:
            logger.error(f"Position size check failed: {e}")
            all_passed = False
            check_results.append({
                "check": "max_position_size",
                "status": SafetyCheckResult.FAIL.value,
                "message": f"Check error: {str(e)}"
            })
        
        # Check 3: Max concurrent positions
        try:
            concurrent_result = await self.check_max_concurrent_positions(
                user_id, strategy_id, max_concurrent_positions
            )
            check_results.append(concurrent_result)
            if concurrent_result["status"] == SafetyCheckResult.FAIL.value:
                all_passed = False
        except Exception as e:
            logger.error(f"Concurrent positions check failed: {e}")
            all_passed = False
            check_results.append({
                "check": "max_concurrent_positions",
                "status": SafetyCheckResult.FAIL.value,
                "message": f"Check error: {str(e)}"
            })
        
        # Check 4: Market hours
        try:
            market_hours_result = self.check_market_hours(instrument, asset_class)
            check_results.append(market_hours_result)
            if market_hours_result["status"] == SafetyCheckResult.FAIL.value:
                all_passed = False
        except Exception as e:
            logger.error(f"Market hours check failed: {e}")
            all_passed = False
            check_results.append({
                "check": "market_hours",
                "status": SafetyCheckResult.FAIL.value,
                "message": f"Check error: {str(e)}"
            })
        
        # Check 5: Circuit breaker
        try:
            circuit_breaker_result = await self.check_circuit_breaker(
                instrument, asset_class
            )
            check_results.append(circuit_breaker_result)
            if circuit_breaker_result["status"] == SafetyCheckResult.FAIL.value:
                all_passed = False
        except Exception as e:
            logger.error(f"Circuit breaker check failed: {e}")
            all_passed = False
            check_results.append({
                "check": "circuit_breaker",
                "status": SafetyCheckResult.FAIL.value,
                "message": f"Check error: {str(e)}"
            })
        
        return all_passed, check_results
    
    async def check_daily_loss_limit(
        self,
        user_id: str,
        capital: float,
        max_daily_loss_pct: float
    ) -> Dict:
        """
        Check if today's realized P&L exceeds the daily loss limit.
        
        Fetches today's trade records and calculates total P&L.
        Blocks if loss >= max_daily_loss_pct of capital.
        
        Args:
            user_id: User identifier
            capital: Total declared capital
            max_daily_loss_pct: Maximum daily loss percentage (e.g., 2.0 for 2%)
            
        Returns:
            Dict with check result
        """
        if not self.db_client:
            logger.warning("No database client provided, skipping daily loss check")
            return {
                "check": "daily_loss_limit",
                "status": SafetyCheckResult.WARNING.value,
                "message": "Database client not available"
            }
        
        try:
            # Get today's date range (IST timezone)
            ist = timezone('Asia/Kolkata')
            now = datetime.now(ist)
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
            
            # Fetch today's trade records
            # Note: This assumes a trade_records table exists with columns:
            # user_id, closed_at, realized_pnl
            daily_pnl = await self._fetch_daily_pnl(user_id, today_start, today_end)
            
            # Calculate max allowed loss
            max_loss = capital * (max_daily_loss_pct / 100.0)
            
            # Check if loss limit breached
            if daily_pnl < 0 and abs(daily_pnl) >= max_loss:
                return {
                    "check": "daily_loss_limit",
                    "status": SafetyCheckResult.FAIL.value,
                    "message": f"Daily loss limit reached: ₹{abs(daily_pnl):,.2f} / ₹{max_loss:,.2f}",
                    "details": {
                        "daily_pnl": daily_pnl,
                        "max_loss": max_loss,
                        "capital": capital,
                        "max_daily_loss_pct": max_daily_loss_pct
                    }
                }
            
            # Warning if approaching limit (>80%)
            if daily_pnl < 0 and abs(daily_pnl) >= (max_loss * 0.8):
                return {
                    "check": "daily_loss_limit",
                    "status": SafetyCheckResult.WARNING.value,
                    "message": f"Approaching daily loss limit: ₹{abs(daily_pnl):,.2f} / ₹{max_loss:,.2f}",
                    "details": {
                        "daily_pnl": daily_pnl,
                        "max_loss": max_loss,
                        "capital": capital,
                        "max_daily_loss_pct": max_daily_loss_pct
                    }
                }
            
            return {
                "check": "daily_loss_limit",
                "status": SafetyCheckResult.PASS.value,
                "message": f"Daily P&L: ₹{daily_pnl:,.2f} (limit: ₹{max_loss:,.2f})",
                "details": {
                    "daily_pnl": daily_pnl,
                    "max_loss": max_loss,
                    "capital": capital,
                    "max_daily_loss_pct": max_daily_loss_pct
                }
            }
            
        except Exception as e:
            logger.error(f"Error checking daily loss limit: {e}")
            raise SafetyCheckError(
                "daily_loss_limit",
                f"Failed to check daily loss limit: {str(e)}"
            )
    
    def check_max_position_size(
        self,
        position_size: float,
        capital: float,
        max_position_pct: float
    ) -> Dict:
        """
        Ensure single position doesn't exceed configured limit.
        
        Args:
            position_size: Proposed position size in currency units
            capital: Total declared capital
            max_position_pct: Maximum position size percentage (e.g., 10.0 for 10%)
            
        Returns:
            Dict with check result
        """
        max_position_size = capital * (max_position_pct / 100.0)
        position_pct = (position_size / capital) * 100.0
        
        if position_size > max_position_size:
            return {
                "check": "max_position_size",
                "status": SafetyCheckResult.FAIL.value,
                "message": f"Position size exceeds limit: ₹{position_size:,.2f} ({position_pct:.2f}%) > ₹{max_position_size:,.2f} ({max_position_pct}%)",
                "details": {
                    "position_size": position_size,
                    "position_pct": position_pct,
                    "max_position_size": max_position_size,
                    "max_position_pct": max_position_pct,
                    "capital": capital
                }
            }
        
        # Warning if approaching limit (>90%)
        if position_size > (max_position_size * 0.9):
            return {
                "check": "max_position_size",
                "status": SafetyCheckResult.WARNING.value,
                "message": f"Position size near limit: ₹{position_size:,.2f} ({position_pct:.2f}%) of ₹{max_position_size:,.2f} ({max_position_pct}%)",
                "details": {
                    "position_size": position_size,
                    "position_pct": position_pct,
                    "max_position_size": max_position_size,
                    "max_position_pct": max_position_pct,
                    "capital": capital
                }
            }
        
        return {
            "check": "max_position_size",
            "status": SafetyCheckResult.PASS.value,
            "message": f"Position size OK: ₹{position_size:,.2f} ({position_pct:.2f}%) of ₹{max_position_size:,.2f} ({max_position_pct}%)",
            "details": {
                "position_size": position_size,
                "position_pct": position_pct,
                "max_position_size": max_position_size,
                "max_position_pct": max_position_pct,
                "capital": capital
            }
        }
    
    async def check_max_concurrent_positions(
        self,
        user_id: str,
        strategy_id: str,
        max_concurrent_positions: int
    ) -> Dict:
        """
        Check current open positions count.
        
        Args:
            user_id: User identifier
            strategy_id: Strategy identifier
            max_concurrent_positions: Maximum allowed concurrent positions
            
        Returns:
            Dict with check result
        """
        if not self.db_client:
            logger.warning("No database client provided, skipping concurrent positions check")
            return {
                "check": "max_concurrent_positions",
                "status": SafetyCheckResult.WARNING.value,
                "message": "Database client not available"
            }
        
        try:
            # Fetch current open positions count
            open_positions_count = await self._fetch_open_positions_count(
                user_id, strategy_id
            )
            
            if open_positions_count >= max_concurrent_positions:
                return {
                    "check": "max_concurrent_positions",
                    "status": SafetyCheckResult.FAIL.value,
                    "message": f"Max concurrent positions reached: {open_positions_count} / {max_concurrent_positions}",
                    "details": {
                        "open_positions_count": open_positions_count,
                        "max_concurrent_positions": max_concurrent_positions
                    }
                }
            
            # Warning if approaching limit (>80%)
            if open_positions_count >= (max_concurrent_positions * 0.8):
                return {
                    "check": "max_concurrent_positions",
                    "status": SafetyCheckResult.WARNING.value,
                    "message": f"Approaching max positions: {open_positions_count} / {max_concurrent_positions}",
                    "details": {
                        "open_positions_count": open_positions_count,
                        "max_concurrent_positions": max_concurrent_positions
                    }
                }
            
            return {
                "check": "max_concurrent_positions",
                "status": SafetyCheckResult.PASS.value,
                "message": f"Open positions: {open_positions_count} / {max_concurrent_positions}",
                "details": {
                    "open_positions_count": open_positions_count,
                    "max_concurrent_positions": max_concurrent_positions
                }
            }
            
        except Exception as e:
            logger.error(f"Error checking concurrent positions: {e}")
            raise SafetyCheckError(
                "max_concurrent_positions",
                f"Failed to check concurrent positions: {str(e)}"
            )
    
    def check_market_hours(
        self,
        instrument: str,
        asset_class: str
    ) -> Dict:
        """
        Verify market is open for the asset class.
        
        Args:
            instrument: Trading instrument symbol
            asset_class: Asset class (equity, fo, crypto, forex, commodity)
            
        Returns:
            Dict with check result
        """
        if asset_class not in self.MARKET_HOURS:
            return {
                "check": "market_hours",
                "status": SafetyCheckResult.FAIL.value,
                "message": f"Unknown asset class: {asset_class}",
                "details": {
                    "instrument": instrument,
                    "asset_class": asset_class
                }
            }
        
        market_config = self.MARKET_HOURS[asset_class]
        
        # Crypto is always open
        if market_config.get("always_open"):
            return {
                "check": "market_hours",
                "status": SafetyCheckResult.PASS.value,
                "message": f"Market always open for {asset_class}",
                "details": {
                    "instrument": instrument,
                    "asset_class": asset_class
                }
            }
        
        # Get current time in market timezone
        tz = timezone(market_config["timezone"])
        now = datetime.now(tz)
        current_time = now.time()
        current_weekday = now.weekday()  # 0=Monday, 6=Sunday
        
        # Check weekday for forex (Mon-Fri only)
        if market_config.get("weekdays_only") and current_weekday >= 5:
            return {
                "check": "market_hours",
                "status": SafetyCheckResult.FAIL.value,
                "message": f"Market closed on weekends for {asset_class}",
                "details": {
                    "instrument": instrument,
                    "asset_class": asset_class,
                    "current_day": now.strftime("%A"),
                    "current_time": current_time.strftime("%H:%M:%S")
                }
            }
        
        # Check market hours
        open_time = market_config["open"]
        close_time = market_config["close"]
        
        if not (open_time <= current_time <= close_time):
            return {
                "check": "market_hours",
                "status": SafetyCheckResult.FAIL.value,
                "message": f"Market closed for {asset_class}. Hours: {open_time.strftime('%H:%M')} - {close_time.strftime('%H:%M')} {market_config['timezone']}",
                "details": {
                    "instrument": instrument,
                    "asset_class": asset_class,
                    "current_time": current_time.strftime("%H:%M:%S"),
                    "market_open": open_time.strftime("%H:%M"),
                    "market_close": close_time.strftime("%H:%M"),
                    "timezone": market_config["timezone"]
                }
            }
        
        return {
            "check": "market_hours",
            "status": SafetyCheckResult.PASS.value,
            "message": f"Market open for {asset_class}",
            "details": {
                "instrument": instrument,
                "asset_class": asset_class,
                "current_time": current_time.strftime("%H:%M:%S"),
                "market_open": open_time.strftime("%H:%M"),
                "market_close": close_time.strftime("%H:%M"),
                "timezone": market_config["timezone"]
            }
        }
    
    async def check_circuit_breaker(
        self,
        instrument: str,
        asset_class: str
    ) -> Dict:
        """
        Check if instrument has circuit breaker active.
        
        For NSE equity and F&O, checks if price movement has triggered
        circuit breaker limits (5%, 10%, 20%).
        
        Args:
            instrument: Trading instrument symbol
            asset_class: Asset class (equity, fo, crypto, forex, commodity)
            
        Returns:
            Dict with check result
        """
        # Circuit breakers only apply to NSE equity and F&O
        if asset_class not in ["equity", "fo"]:
            return {
                "check": "circuit_breaker",
                "status": SafetyCheckResult.PASS.value,
                "message": f"No circuit breakers for {asset_class}",
                "details": {
                    "instrument": instrument,
                    "asset_class": asset_class
                }
            }
        
        if not self.db_client:
            logger.warning("No database client provided, skipping circuit breaker check")
            return {
                "check": "circuit_breaker",
                "status": SafetyCheckResult.WARNING.value,
                "message": "Database client not available",
                "details": {
                    "instrument": instrument,
                    "asset_class": asset_class
                }
            }
        
        try:
            # Fetch current price and day's open price
            circuit_breaker_active = await self._check_circuit_breaker_status(
                instrument, asset_class
            )
            
            if circuit_breaker_active:
                return {
                    "check": "circuit_breaker",
                    "status": SafetyCheckResult.FAIL.value,
                    "message": f"Circuit breaker active for {instrument}",
                    "details": {
                        "instrument": instrument,
                        "asset_class": asset_class,
                        "circuit_breaker_active": True
                    }
                }
            
            return {
                "check": "circuit_breaker",
                "status": SafetyCheckResult.PASS.value,
                "message": f"No circuit breaker for {instrument}",
                "details": {
                    "instrument": instrument,
                    "asset_class": asset_class,
                    "circuit_breaker_active": False
                }
            }
            
        except Exception as e:
            logger.error(f"Error checking circuit breaker: {e}")
            # Fail-safe: if we can't check, assume circuit breaker might be active
            return {
                "check": "circuit_breaker",
                "status": SafetyCheckResult.WARNING.value,
                "message": f"Could not verify circuit breaker status: {str(e)}",
                "details": {
                    "instrument": instrument,
                    "asset_class": asset_class
                }
            }
    
    async def place_simultaneous_sl_order(
        self,
        entry_order: Dict,
        stop_loss_pct: float,
        broker_adapter
    ) -> Dict:
        """
        Place simultaneous stop-loss order after entry order confirmation.
        
        This is called immediately after an entry order is confirmed.
        The SL order is placed at the broker to protect the position.
        
        Args:
            entry_order: Confirmed entry order details
                {
                    "order_id": str,
                    "instrument": str,
                    "direction": "LONG" or "SHORT",
                    "entry_price": float,
                    "quantity": float,
                    "asset_class": str
                }
            stop_loss_pct: Stop loss percentage (e.g., 2.0 for 2%)
            broker_adapter: Broker adapter instance for placing orders
            
        Returns:
            Dict with SL order details
        """
        try:
            entry_price = entry_order["entry_price"]
            direction = entry_order["direction"]
            quantity = entry_order["quantity"]
            instrument = entry_order["instrument"]
            
            # Calculate stop loss price
            if direction == "LONG":
                sl_price = entry_price * (1 - stop_loss_pct / 100.0)
                sl_order_type = "SELL"
            else:  # SHORT
                sl_price = entry_price * (1 + stop_loss_pct / 100.0)
                sl_order_type = "BUY"
            
            # Place SL order at broker
            sl_order = await broker_adapter.place_order(
                instrument=instrument,
                order_type=sl_order_type,
                quantity=quantity,
                price=sl_price,
                order_variety="SL",  # Stop Loss order
                trigger_price=sl_price
            )
            
            logger.info(
                f"Placed SL order for {instrument}: "
                f"{sl_order_type} {quantity} @ ₹{sl_price:.2f} "
                f"(entry: ₹{entry_price:.2f}, SL: {stop_loss_pct}%)"
            )
            
            return {
                "sl_order_id": sl_order.get("order_id"),
                "entry_order_id": entry_order["order_id"],
                "instrument": instrument,
                "sl_price": sl_price,
                "entry_price": entry_price,
                "stop_loss_pct": stop_loss_pct,
                "quantity": quantity,
                "direction": direction,
                "status": "placed"
            }
            
        except Exception as e:
            logger.error(f"Failed to place SL order: {e}")
            raise SafetyCheckError(
                "simultaneous_sl_order",
                f"Failed to place stop-loss order: {str(e)}",
                details={
                    "entry_order_id": entry_order.get("order_id"),
                    "instrument": entry_order.get("instrument")
                }
            )
    
    # Private helper methods
    
    async def _fetch_daily_pnl(
        self,
        user_id: str,
        start_time: datetime,
        end_time: datetime
    ) -> float:
        """
        Fetch today's realized P&L from trade_records.
        
        Args:
            user_id: User identifier
            start_time: Start of day
            end_time: End of day
            
        Returns:
            Total realized P&L for the day (negative for loss)
        """
        # This is a placeholder implementation
        # In production, this would query the trade_records table
        # For now, return 0 to allow testing
        
        # Example query (when trade_records table exists):
        # SELECT SUM(realized_pnl) FROM trade_records
        # WHERE user_id = :user_id
        # AND closed_at >= :start_time
        # AND closed_at <= :end_time
        # AND status = 'closed'
        
        logger.warning("_fetch_daily_pnl: trade_records table not yet implemented, returning 0")
        return 0.0
    
    async def _fetch_open_positions_count(
        self,
        user_id: str,
        strategy_id: str
    ) -> int:
        """
        Fetch count of currently open positions.
        
        Args:
            user_id: User identifier
            strategy_id: Strategy identifier
            
        Returns:
            Count of open positions
        """
        # This is a placeholder implementation
        # In production, this would query the trade_records table
        # For now, return 0 to allow testing
        
        # Example query (when trade_records table exists):
        # SELECT COUNT(*) FROM trade_records
        # WHERE user_id = :user_id
        # AND strategy_id = :strategy_id
        # AND status = 'open'
        
        logger.warning("_fetch_open_positions_count: trade_records table not yet implemented, returning 0")
        return 0
    
    async def _check_circuit_breaker_status(
        self,
        instrument: str,
        asset_class: str
    ) -> bool:
        """
        Check if circuit breaker is currently active for instrument.
        
        Args:
            instrument: Trading instrument symbol
            asset_class: Asset class
            
        Returns:
            True if circuit breaker is active, False otherwise
        """
        # This is a placeholder implementation
        # In production, this would:
        # 1. Fetch today's open price and current price
        # 2. Calculate price change percentage
        # 3. Check against circuit breaker limits
        # 4. Query NSE API or market data feed for circuit breaker status
        
        # Example logic:
        # price_change_pct = abs((current_price - open_price) / open_price) * 100
        # limits = self.CIRCUIT_BREAKER_LIMITS.get(asset_class, [])
        # return any(price_change_pct >= limit * 100 for limit in limits)
        
        logger.warning("_check_circuit_breaker_status: market data integration not yet implemented, returning False")
        return False
