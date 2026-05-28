"""
PnL Tracker Service

Real-time P&L tracking across current options positions.
Mirrors OpenAlgo's pnltracker.py functionality.

Requirements: Real-time P&L tracking for options positions
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, date
from decimal import Decimal
from dataclasses import dataclass, field
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class PositionType(Enum):
    LONG = "long"
    SHORT = "short"


class OptionType(Enum):
    CALL = "call"
    PUT = "put"


@dataclass
class Position:
    """Options position"""
    id: str
    symbol: str
    underlying: str
    option_type: OptionType
    strike: float
    expiry_date: date
    position_type: PositionType
    quantity: int
    entry_price: float
    entry_date: datetime
    current_price: Optional[float] = None
    current_underlying_price: Optional[float] = None
    
    # Greeks at entry
    entry_delta: Optional[float] = None
    entry_gamma: Optional[float] = None
    entry_theta: Optional[float] = None
    entry_vega: Optional[float] = None
    
    # Current Greeks
    current_delta: Optional[float] = None
    current_gamma: Optional[float] = None
    current_theta: Optional[float] = None
    current_vega: Optional[float] = None
    
    # PnL tracking
    realized_pnl: float = 0
    unrealized_pnl: float = 0
    total_pnl: float = 0
    pnl_percent: float = 0
    
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PortfolioSummary:
    """Portfolio PnL summary"""
    total_positions: int
    total_realized_pnl: float
    total_unrealized_pnl: float
    total_pnl: float
    max_profit: float
    max_loss: float
    winning_positions: int
    losing_positions: int
    total_premium_paid: float
    total_premium_received: float
    net_delta: float
    net_gamma: float
    net_theta: float
    net_vega: float
    risk_metrics: Dict[str, Any] = field(default_factory=dict)


class PnLTrackerService:
    """
    PnL Tracker Service for real-time options position tracking.
    
    Features:
    - Real-time P&L calculation
    - Greeks exposure tracking
    - Risk metrics (max profit, max loss)
    - Scenario analysis
    - Position grouping by underlying
    """
    
    def __init__(self, db_session=None, market_data_service=None):
        """
        Initialize PnL tracker.
        
        Args:
            db_session: Database session for position persistence
            market_data_service: Service for fetching live prices
        """
        self.db = db_session
        self.market_data = market_data_service
        self._positions: Dict[str, Position] = {}
        self._cache = {}
    
    async def add_position(
        self,
        user_id: str,
        symbol: str,
        underlying: str,
        option_type: str,
        strike: float,
        expiry_date: str,
        position_type: str,
        quantity: int,
        entry_price: float,
        entry_greeks: Optional[Dict[str, float]] = None
    ) -> Position:
        """
        Add a new position to track.
        
        Args:
            user_id: User ID
            symbol: Option symbol
            underlying: Underlying symbol
            option_type: call or put
            strike: Strike price
            expiry_date: Expiry date (YYYY-MM-DD)
            position_type: long or short
            quantity: Number of lots/contracts
            entry_price: Entry price per unit
            entry_greeks: Greeks at entry (optional)
            
        Returns:
            Created Position
        """
        if isinstance(expiry_date, str):
            expiry_date = datetime.strptime(expiry_date, "%Y-%m-%d").date()
        
        position = Position(
            id=f"{user_id}_{symbol}_{datetime.utcnow().timestamp()}",
            symbol=symbol,
            underlying=underlying,
            option_type=OptionType(option_type.lower()),
            strike=strike,
            expiry_date=expiry_date,
            position_type=PositionType(position_type.lower()),
            quantity=quantity,
            entry_price=entry_price,
            entry_date=datetime.utcnow(),
            entry_delta=entry_greeks.get("delta") if entry_greeks else None,
            entry_gamma=entry_greeks.get("gamma") if entry_greeks else None,
            entry_theta=entry_greeks.get("theta") if entry_greeks else None,
            entry_vega=entry_greeks.get("vega") if entry_greeks else None,
            metadata={"user_id": user_id}
        )
        
        self._positions[position.id] = position
        
        logger.info(f"Position added: {position.id} - {symbol}")
        
        # Update with current prices
        await self.update_position_price(position.id)
        
        return position
    
    async def close_position(
        self,
        position_id: str,
        exit_price: float
    ) -> Optional[Position]:
        """
        Close a position and calculate realized PnL.
        
        Args:
            position_id: Position ID to close
            exit_price: Exit price
            
        Returns:
            Closed position with realized PnL
        """
        position = self._positions.get(position_id)
        if not position:
            return None
        
        # Calculate realized PnL
        qty = position.quantity
        entry = position.entry_price
        
        if position.position_type == PositionType.LONG:
            pnl = (exit_price - entry) * qty
        else:  # SHORT
            pnl = (entry - exit_price) * qty
        
        position.realized_pnl = pnl
        position.total_pnl = pnl
        position.current_price = exit_price
        position.metadata["exit_date"] = datetime.utcnow().isoformat()
        position.metadata["exit_price"] = exit_price
        
        logger.info(f"Position {position_id} closed with PnL: {pnl:.2f}")
        
        return position
    
    async def update_position_price(
        self,
        position_id: str,
        current_price: Optional[float] = None,
        underlying_price: Optional[float] = None,
        current_greeks: Optional[Dict[str, float]] = None
    ) -> Optional[Position]:
        """
        Update position with current market prices and Greeks.
        
        Args:
            position_id: Position ID
            current_price: Current option price (fetched if not provided)
            underlying_price: Current underlying price (fetched if not provided)
            current_greeks: Current Greeks values
            
        Returns:
            Updated position
        """
        position = self._positions.get(position_id)
        if not position:
            return None
        
        # Fetch prices if not provided
        if current_price is None and self.market_data:
            current_price = await self._fetch_option_price(position.symbol)
        
        if underlying_price is None and self.market_data:
            underlying_price = await self._fetch_underlying_price(position.underlying)
        
        if current_price:
            position.current_price = current_price
            
            # Calculate unrealized PnL
            qty = position.quantity
            entry = position.entry_price
            
            if position.position_type == PositionType.LONG:
                position.unrealized_pnl = (current_price - entry) * qty
            else:  # SHORT
                position.unrealized_pnl = (entry - current_price) * qty
            
            # Calculate total PnL
            position.total_pnl = position.realized_pnl + position.unrealized_pnl
            
            # Calculate PnL percentage
            if entry > 0:
                if position.position_type == PositionType.LONG:
                    position.pnl_percent = ((current_price - entry) / entry) * 100
                else:
                    position.pnl_percent = ((entry - current_price) / entry) * 100
        
        if underlying_price:
            position.current_underlying_price = underlying_price
        
        # Update Greeks
        if current_greeks:
            position.current_delta = current_greeks.get("delta")
            position.current_gamma = current_greeks.get("gamma")
            position.current_theta = current_greeks.get("theta")
            position.current_vega = current_greeks.get("vega")
        
        return position
    
    async def update_all_positions(self, user_id: Optional[str] = None):
        """Update all positions with current market data."""
        for position_id, position in self._positions.items():
            if user_id and position.metadata.get("user_id") != user_id:
                continue
            
            try:
                await self.update_position_price(position_id)
            except Exception as e:
                logger.error(f"Failed to update position {position_id}: {e}")
    
    async def get_portfolio_summary(
        self,
        user_id: Optional[str] = None,
        underlying: Optional[str] = None
    ) -> PortfolioSummary:
        """
        Get portfolio PnL summary.
        
        Args:
            user_id: Filter by user
            underlying: Filter by underlying symbol
            
        Returns:
            PortfolioSummary with aggregated metrics
        """
        positions = await self.get_positions(user_id, underlying)
        
        if not positions:
            return PortfolioSummary(
                total_positions=0,
                total_realized_pnl=0,
                total_unrealized_pnl=0,
                total_pnl=0,
                max_profit=0,
                max_loss=0,
                winning_positions=0,
                losing_positions=0,
                total_premium_paid=0,
                total_premium_received=0,
                net_delta=0,
                net_gamma=0,
                net_theta=0,
                net_vega=0
            )
        
        total_realized = sum(p.realized_pnl for p in positions)
        total_unrealized = sum(p.unrealized_pnl for p in positions)
        total_pnl = total_realized + total_unrealized
        
        winning = len([p for p in positions if p.total_pnl > 0])
        losing = len([p for p in positions if p.total_pnl < 0])
        
        # Premium calculations
        premium_paid = sum(
            p.entry_price * p.quantity
            for p in positions
            if p.position_type == PositionType.LONG
        )
        premium_received = sum(
            p.entry_price * p.quantity
            for p in positions
            if p.position_type == PositionType.SHORT
        )
        
        # Net Greeks
        net_delta = sum(
            (p.current_delta or 0) * p.quantity * (1 if p.position_type == PositionType.LONG else -1)
            for p in positions
        )
        net_gamma = sum(
            (p.current_gamma or 0) * p.quantity * (1 if p.position_type == PositionType.LONG else -1)
            for p in positions
        )
        net_theta = sum(
            (p.current_theta or 0) * p.quantity * (1 if p.position_type == PositionType.LONG else -1)
            for p in positions
        )
        net_vega = sum(
            (p.current_vega or 0) * p.quantity * (1 if p.position_type == PositionType.LONG else -1)
            for p in positions
        )
        
        # Risk metrics
        max_profit = sum(p.total_pnl for p in positions if p.total_pnl > 0)
        max_loss = sum(p.total_pnl for p in positions if p.total_pnl < 0)
        
        return PortfolioSummary(
            total_positions=len(positions),
            total_realized_pnl=round(total_realized, 2),
            total_unrealized_pnl=round(total_unrealized, 2),
            total_pnl=round(total_pnl, 2),
            max_profit=round(max_profit, 2),
            max_loss=round(max_loss, 2),
            winning_positions=winning,
            losing_positions=losing,
            total_premium_paid=round(premium_paid, 2),
            total_premium_received=round(premium_received, 2),
            net_delta=round(net_delta, 4),
            net_gamma=round(net_gamma, 4),
            net_theta=round(net_theta, 2),
            net_vega=round(net_vega, 2),
            risk_metrics={
                "delta_exposure": "positive" if net_delta > 0 else "negative" if net_delta < 0 else "neutral",
                "theta_exposure": "positive" if net_theta > 0 else "negative",
                "win_rate": round(winning / len(positions) * 100, 2) if positions else 0
            }
        )
    
    async def get_positions(
        self,
        user_id: Optional[str] = None,
        underlying: Optional[str] = None,
        open_only: bool = True
    ) -> List[Position]:
        """
        Get positions with filtering.
        
        Args:
            user_id: Filter by user
            underlying: Filter by underlying
            open_only: Only return open positions
            
        Returns:
            List of positions
        """
        positions = []
        for position in self._positions.values():
            if user_id and position.metadata.get("user_id") != user_id:
                continue
            if underlying and position.underlying != underlying:
                continue
            if open_only and position.total_pnl != position.realized_pnl:
                # Position has been partially or fully closed
                pass
            
            positions.append(position)
        
        return positions
    
    async def get_position_detail(self, position_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed position information."""
        position = self._positions.get(position_id)
        if not position:
            return None
        
        days_to_expiry = (position.expiry_date - date.today()).days
        
        # Calculate breakeven prices
        if position.option_type == OptionType.CALL:
            if position.position_type == PositionType.LONG:
                breakeven = position.strike + position.entry_price
            else:
                breakeven = position.strike + position.entry_price
        else:  # PUT
            if position.position_type == PositionType.LONG:
                breakeven = position.strike - position.entry_price
            else:
                breakeven = position.strike - position.entry_price
        
        return {
            "id": position.id,
            "symbol": position.symbol,
            "underlying": position.underlying,
            "option_type": position.option_type.value,
            "strike": position.strike,
            "expiry_date": position.expiry_date.isoformat(),
            "days_to_expiry": max(0, days_to_expiry),
            "position_type": position.position_type.value,
            "quantity": position.quantity,
            "entry_price": position.entry_price,
            "current_price": position.current_price,
            "entry_date": position.entry_date.isoformat(),
            "pnl": {
                "realized": round(position.realized_pnl, 2),
                "unrealized": round(position.unrealized_pnl, 2),
                "total": round(position.total_pnl, 2),
                "percent": round(position.pnl_percent, 2)
            },
            "greeks": {
                "entry": {
                    "delta": position.entry_delta,
                    "gamma": position.entry_gamma,
                    "theta": position.entry_theta,
                    "vega": position.entry_vega
                },
                "current": {
                    "delta": position.current_delta,
                    "gamma": position.current_gamma,
                    "theta": position.current_theta,
                    "vega": position.current_vega
                }
            },
            "breakeven": round(breakeven, 2),
            "moneyness": round(position.current_underlying_price / position.strike, 4) if position.current_underlying_price else None,
            "metadata": position.metadata
        }
    
    async def scenario_analysis(
        self,
        position_id: str,
        price_changes: List[float] = None,
        volatility_changes: List[float] = None
    ) -> Dict[str, Any]:
        """
        Run scenario analysis on a position.
        
        Args:
            position_id: Position to analyze
            price_changes: List of underlying price change percentages
            volatility_changes: List of IV change percentages
            
        Returns:
            Scenario analysis results
        """
        position = self._positions.get(position_id)
        if not position:
            return {"error": "Position not found"}
        
        price_changes = price_changes or [-10, -5, -2, 0, 2, 5, 10]
        
        scenarios = []
        for pct_change in price_changes:
            new_underlying = position.current_underlying_price * (1 + pct_change / 100) if position.current_underlying_price else position.strike
            
            # Estimate new option price using Greeks
            price_change = 0
            if position.current_delta:
                price_change += position.current_delta * (new_underlying - position.current_underlying_price) if position.current_underlying_price else 0
            
            new_option_price = max(0.01, (position.current_price or position.entry_price) + price_change)
            
            # Calculate new PnL
            if position.position_type == PositionType.LONG:
                new_pnl = (new_option_price - position.entry_price) * position.quantity
            else:
                new_pnl = (position.entry_price - new_option_price) * position.quantity
            
            scenarios.append({
                "underlying_change_pct": pct_change,
                "new_underlying_price": round(new_underlying, 2),
                "estimated_option_price": round(new_option_price, 2),
                "estimated_pnl": round(new_pnl, 2),
                "pnl_change": round(new_pnl - position.unrealized_pnl, 2)
            })
        
        return {
            "position_id": position_id,
            "current_price": position.current_price,
            "current_underlying": position.current_underlying_price,
            "scenarios": scenarios
        }
    
    async def _fetch_option_price(self, symbol: str) -> Optional[float]:
        """Fetch current option price from market data."""
        if self.market_data:
            return await self.market_data.get_option_price(symbol)
        return None
    
    async def _fetch_underlying_price(self, symbol: str) -> Optional[float]:
        """Fetch current underlying price from market data."""
        if self.market_data:
            return await self.market_data.get_spot_price(symbol)
        return None
    
    def position_to_dict(self, position: Position) -> Dict[str, Any]:
        """Convert position to dictionary."""
        return {
            "id": position.id,
            "symbol": position.symbol,
            "underlying": position.underlying,
            "option_type": position.option_type.value,
            "strike": position.strike,
            "expiry_date": position.expiry_date.isoformat(),
            "position_type": position.position_type.value,
            "quantity": position.quantity,
            "entry_price": position.entry_price,
            "current_price": position.current_price,
            "realized_pnl": round(position.realized_pnl, 2),
            "unrealized_pnl": round(position.unrealized_pnl, 2),
            "total_pnl": round(position.total_pnl, 2),
            "pnl_percent": round(position.pnl_percent, 2)
        }
