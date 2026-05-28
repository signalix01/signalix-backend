"""
Event-Driven Backtesting Engine with realistic market simulation.

This engine provides bar-by-bar simulation with:
- Slippage models (fixed_pips, pct_spread, market_impact)
- Overnight gap simulation
- Circuit breaker simulation
- F&O lot-size rounding
- Cumulative transaction costs tracking

Requirements: 5.1-5.7
"""
import pandas as pd
import numpy as np
import uuid
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
import logging
from enum import Enum

from services.backtesting.models import (
    BacktestConfig, BacktestResult, BacktestMode, SlippageModel
)
from services.algo_builder.models import StrategySpec
from services.algo_builder.base_strategy import BaseStrategy

logger = logging.getLogger(__name__)


class Position:
    """Represents an open position in the event-driven engine"""
    
    def __init__(
        self,
        direction: str,
        entry_price: float,
        entry_date: datetime,
        size: float,
        entry_bar_idx: int,
        stop_loss: Optional[float] = None,
        target: Optional[float] = None,
        trailing_sl_pct: Optional[float] = None
    ):
        self.direction = direction  # 'LONG' or 'SHORT'
        self.entry_price = entry_price
        self.entry_date = entry_date
        self.size = size
        self.entry_bar_idx = entry_bar_idx
        self.stop_loss = stop_loss
        self.target = target
        self.trailing_sl_pct = trailing_sl_pct
        self.highest_price = entry_price if direction == 'LONG' else entry_price
        self.lowest_price = entry_price if direction == 'SHORT' else entry_price
        self.pnl = 0.0
        self.pnl_pct = 0.0
        self.exit_price = None
        self.exit_date = None
        self.exit_reason = None
    
    def update_trailing_stop(self, current_price: float):
        """Update trailing stop loss based on current price"""
        if self.trailing_sl_pct is None:
            return
        
        if self.direction == 'LONG':
            # Track highest price for long positions
            if current_price > self.highest_price:
                self.highest_price = current_price
                # Update trailing stop
                self.stop_loss = self.highest_price * (1 - self.trailing_sl_pct / 100)
        else:  # SHORT
            # Track lowest price for short positions
            if current_price < self.lowest_price:
                self.lowest_price = current_price
                # Update trailing stop
                self.stop_loss = self.lowest_price * (1 + self.trailing_sl_pct / 100)
    
    def calculate_pnl(self, exit_price: float) -> Tuple[float, float]:
        """Calculate P&L in absolute and percentage terms"""
        if self.direction == 'LONG':
            pnl = (exit_price - self.entry_price) * self.size
            pnl_pct = ((exit_price - self.entry_price) / self.entry_price) * 100
        else:  # SHORT
            pnl = (self.entry_price - exit_price) * self.size
            pnl_pct = ((self.entry_price - exit_price) / self.entry_price) * 100
        
        return pnl, pnl_pct


class EventDrivenEngine:
    """
    Event-driven backtesting engine with realistic market simulation.
    
    This engine simulates bar-by-bar execution with:
    - Multiple slippage models
    - Overnight gap handling
    - Circuit breaker simulation
    - F&O lot-size rounding
    - Accurate transaction cost tracking
    """
    
    def __init__(self):
        """Initialize the event-driven engine"""
        self.positions: List[Position] = []
        self.closed_trades: List[Dict[str, Any]] = []
        self.equity_curve: List[float] = []
        self.cash: float = 0.0
        self.initial_capital: float = 0.0
        self.total_brokerage = 0.0
        self.total_stt = 0.0
        self.total_gst = 0.0
        self.circuit_breaker_events: List[Dict[str, Any]] = []
    
    def run(
        self,
        spec: StrategySpec,
        data: pd.DataFrame,
        config: BacktestConfig,
        strategy: Optional[BaseStrategy] = None
    ) -> BacktestResult:
        """
        Run an event-driven backtest on the provided data.
        
        Args:
            spec: Strategy specification
            data: DataFrame with OHLCV data and computed indicators
            config: Backtest configuration
            strategy: Optional compiled strategy instance (if None, uses simple RSI strategy)
            
        Returns:
            BacktestResult with all computed metrics
        """
        logger.info(f"Running event-driven backtest for {spec.name} on {config.instrument}")
        
        # Initialize state
        self.cash = config.initial_capital
        self.initial_capital = config.initial_capital
        self.positions = []
        self.closed_trades = []
        self.equity_curve = []
        self.total_brokerage = 0.0
        self.total_stt = 0.0
        self.total_gst = 0.0
        self.circuit_breaker_events = []
        
        # Get lot size for F&O instruments (default to 1 for non-F&O)
        lot_size = self._get_lot_size(config.instrument, spec.asset_class)
        
        # Bar-by-bar simulation
        for bar_idx in range(len(data)):
            bar = data.iloc[bar_idx]
            
            # Check for circuit breaker
            if self._is_circuit_breaker_active(bar, bar_idx, data):
                self.circuit_breaker_events.append({
                    'date': bar.name,
                    'price': bar['close'],
                    'reason': 'Circuit breaker triggered'
                })
                # Skip this bar - no trading allowed
                self._update_equity(bar, bar_idx)
                continue
            
            # Step 1: Check exits first (before entries)
            self._process_exits(bar, bar_idx, config, data)
            
            # Step 2: Check for overnight gaps and handle stop losses
            if bar_idx > 0:
                self._handle_overnight_gaps(bar, data.iloc[bar_idx - 1], config)
            
            # Step 3: Check entries (if no position or multiple positions allowed)
            if strategy:
                self._process_entries_with_strategy(
                    strategy, bar, bar_idx, config, lot_size, spec
                )
            else:
                # Fallback: simple RSI strategy
                self._process_entries_simple(bar, bar_idx, data, config, lot_size)
            
            # Step 4: Update trailing stops
            for position in self.positions:
                position.update_trailing_stop(bar['close'])
            
            # Step 5: Update equity curve
            self._update_equity(bar, bar_idx)
        
        # Close any remaining open positions at the end
        if len(self.positions) > 0:
            final_bar = data.iloc[-1]
            for position in self.positions[:]:  # Copy list to avoid modification during iteration
                self._close_position(
                    position, final_bar['close'], final_bar.name, 
                    'end_of_backtest', config
                )
        
        # Extract metrics
        result = self._extract_metrics(spec, config, data)
        
        logger.info(f"Event-driven backtest complete: {result.total_trades} trades, "
                   f"{result.total_return_pct:.2f}% return, "
                   f"Sharpe: {result.sharpe_ratio:.2f}")
        
        return result
    
    def _get_lot_size(self, instrument: str, asset_class: str) -> int:
        """
        Get lot size for F&O instruments.
        
        Args:
            instrument: Instrument symbol
            asset_class: Asset class (equity, fo, crypto, etc.)
            
        Returns:
            Lot size (1 for non-F&O instruments)
        """
        if asset_class != 'fo':
            return 1
        
        # Common Indian F&O lot sizes (simplified)
        lot_sizes = {
            'NIFTY': 50,
            'BANKNIFTY': 25,
            'FINNIFTY': 40,
            'MIDCPNIFTY': 75,
            'RELIANCE': 250,
            'TCS': 150,
            'INFY': 300,
            'HDFCBANK': 550,
            'ICICIBANK': 1375,
        }
        
        # Extract base symbol (remove expiry/strike info)
        base_symbol = instrument.split('-')[0].upper()
        
        return lot_sizes.get(base_symbol, 1)
    
    def _is_circuit_breaker_active(
        self, bar: pd.Series, bar_idx: int, data: pd.DataFrame
    ) -> bool:
        """
        Check if circuit breaker is active for this bar.
        
        Circuit breaker triggers when price moves ±5%, ±10%, or ±20% from previous close.
        
        Args:
            bar: Current bar
            bar_idx: Current bar index
            data: Full data DataFrame
            
        Returns:
            True if circuit breaker is active
        """
        if bar_idx == 0:
            return False
        
        prev_close = data.iloc[bar_idx - 1]['close']
        current_price = bar['close']
        
        # Calculate price change percentage
        price_change_pct = abs((current_price - prev_close) / prev_close) * 100
        
        # Circuit breaker thresholds for NSE
        circuit_breaker_levels = [5.0, 10.0, 20.0]
        
        return price_change_pct >= circuit_breaker_levels[0]
    
    def _handle_overnight_gaps(
        self, current_bar: pd.Series, prev_bar: pd.Series, config: BacktestConfig
    ):
        """
        Handle overnight gaps that exceed stop loss levels.
        
        If gap open exceeds stop loss, fill at gap open price (not stop price).
        
        Args:
            current_bar: Current bar
            prev_bar: Previous bar
            config: Backtest configuration
        """
        gap_open = current_bar['open']
        prev_close = prev_bar['close']
        
        # Check if there's a significant gap
        gap_pct = abs((gap_open - prev_close) / prev_close) * 100
        
        if gap_pct < 0.5:  # Less than 0.5% gap - not significant
            return
        
        # Check each position for stop loss breach
        for position in self.positions[:]:  # Copy to avoid modification during iteration
            if position.stop_loss is None:
                continue
            
            # Check if gap breached stop loss
            if position.direction == 'LONG':
                if gap_open < position.stop_loss:
                    # Gap down below stop loss - fill at gap open
                    logger.info(f"Overnight gap down: filling at {gap_open} "
                               f"(stop was {position.stop_loss})")
                    self._close_position(
                        position, gap_open, current_bar.name,
                        'gap_stop_loss', config
                    )
            else:  # SHORT
                if gap_open > position.stop_loss:
                    # Gap up above stop loss - fill at gap open
                    logger.info(f"Overnight gap up: filling at {gap_open} "
                               f"(stop was {position.stop_loss})")
                    self._close_position(
                        position, gap_open, current_bar.name,
                        'gap_stop_loss', config
                    )
    
    def _process_exits(
        self, bar: pd.Series, bar_idx: int, config: BacktestConfig, data: pd.DataFrame
    ):
        """
        Process exit conditions for all open positions.
        
        Args:
            bar: Current bar
            bar_idx: Current bar index
            config: Backtest configuration
            data: Full data DataFrame
        """
        for position in self.positions[:]:  # Copy to avoid modification during iteration
            should_exit = False
            exit_reason = None
            exit_price = bar['close']
            
            # Check stop loss
            if position.stop_loss is not None:
                if position.direction == 'LONG' and bar['low'] <= position.stop_loss:
                    should_exit = True
                    exit_reason = 'stop_loss'
                    exit_price = position.stop_loss
                elif position.direction == 'SHORT' and bar['high'] >= position.stop_loss:
                    should_exit = True
                    exit_reason = 'stop_loss'
                    exit_price = position.stop_loss
            
            # Check target
            if position.target is not None:
                if position.direction == 'LONG' and bar['high'] >= position.target:
                    should_exit = True
                    exit_reason = 'target'
                    exit_price = position.target
                elif position.direction == 'SHORT' and bar['low'] <= position.target:
                    should_exit = True
                    exit_reason = 'target'
                    exit_price = position.target
            
            # Apply slippage to exit price
            if should_exit:
                exit_price = self._apply_slippage(
                    exit_price, position.size, bar, config, is_entry=False
                )
                self._close_position(position, exit_price, bar.name, exit_reason, config)
    
    def _process_entries_simple(
        self,
        bar: pd.Series,
        bar_idx: int,
        data: pd.DataFrame,
        config: BacktestConfig,
        lot_size: int
    ):
        """
        Simple RSI-based entry logic (fallback when no compiled strategy provided).
        
        Args:
            bar: Current bar
            bar_idx: Current bar index
            data: Full data DataFrame
            config: Backtest configuration
            lot_size: Lot size for F&O instruments
        """
        # Only enter if no open positions
        if len(self.positions) > 0:
            return
        
        # Simple RSI strategy
        if 'rsi_14' not in data.columns or bar_idx < 1:
            return
        
        rsi_curr = bar['rsi_14']
        rsi_prev = data.iloc[bar_idx - 1]['rsi_14']
        
        if pd.isna(rsi_curr) or pd.isna(rsi_prev):
            return
        
        # Entry: RSI crosses above 30 (oversold)
        if rsi_prev <= 30 and rsi_curr > 30:
            # Calculate position size
            size = self._calculate_position_size(
                bar['close'], bar.get('atr_14', 0), config, lot_size
            )
            
            if size > 0:
                # Apply slippage
                entry_price = self._apply_slippage(
                    bar['close'], size, bar, config, is_entry=True
                )
                
                # Create position with stop loss and target
                stop_loss = entry_price * 0.98  # 2% stop loss
                target = entry_price * 1.04  # 4% target
                
                position = Position(
                    direction='LONG',
                    entry_price=entry_price,
                    entry_date=bar.name,
                    size=size,
                    entry_bar_idx=bar_idx,
                    stop_loss=stop_loss,
                    target=target
                )
                
                self.positions.append(position)
                self.cash -= entry_price * size
                
                # Apply transaction costs
                self._apply_transaction_costs(entry_price * size, config)
                
                logger.debug(f"Opened LONG position at {entry_price}, size={size}")
    
    def _process_entries_with_strategy(
        self,
        strategy: BaseStrategy,
        bar: pd.Series,
        bar_idx: int,
        config: BacktestConfig,
        lot_size: int,
        spec: StrategySpec
    ):
        """
        Process entries using compiled strategy logic.
        
        Args:
            strategy: Compiled strategy instance
            bar: Current bar
            bar_idx: Current bar index
            config: Backtest configuration
            lot_size: Lot size for F&O instruments
            spec: Strategy specification
        """
        # Check if we can enter (max concurrent positions)
        max_positions = spec.position_sizing.max_concurrent_positions
        if len(self.positions) >= max_positions:
            return
        
        # Check entry conditions
        should_enter_long = strategy.should_enter_long(bar_idx)
        should_enter_short = strategy.should_enter_short(bar_idx)
        
        if not should_enter_long and not should_enter_short:
            return
        
        direction = 'LONG' if should_enter_long else 'SHORT'
        
        # Calculate position size
        atr = bar.get('atr_14', 0)
        size = strategy.position_size(self.cash, bar['close'], atr)
        
        # Apply lot size rounding for F&O
        if lot_size > 1:
            size = self._round_to_lot_size(size, bar['close'], lot_size)
        
        if size <= 0:
            return
        
        # Apply slippage
        entry_price = self._apply_slippage(
            bar['close'], size, bar, config, is_entry=True
        )
        
        # Determine stop loss and target from exit rules
        stop_loss = None
        target = None
        trailing_sl_pct = None
        
        for exit_rule in spec.exit_rules:
            if exit_rule.exit_type == 'stop_loss' and exit_rule.stop_loss_pct:
                if direction == 'LONG':
                    stop_loss = entry_price * (1 - exit_rule.stop_loss_pct / 100)
                else:
                    stop_loss = entry_price * (1 + exit_rule.stop_loss_pct / 100)
            
            if exit_rule.exit_type == 'target' and exit_rule.target_pct:
                if direction == 'LONG':
                    target = entry_price * (1 + exit_rule.target_pct / 100)
                else:
                    target = entry_price * (1 - exit_rule.target_pct / 100)
            
            if exit_rule.exit_type == 'trailing_sl' and exit_rule.trailing_sl_pct:
                trailing_sl_pct = exit_rule.trailing_sl_pct
                if direction == 'LONG':
                    stop_loss = entry_price * (1 - trailing_sl_pct / 100)
                else:
                    stop_loss = entry_price * (1 + trailing_sl_pct / 100)
        
        # Create position
        position = Position(
            direction=direction,
            entry_price=entry_price,
            entry_date=bar.name,
            size=size,
            entry_bar_idx=bar_idx,
            stop_loss=stop_loss,
            target=target,
            trailing_sl_pct=trailing_sl_pct
        )
        
        self.positions.append(position)
        self.cash -= entry_price * size
        
        # Apply transaction costs
        self._apply_transaction_costs(entry_price * size, config)
        
        logger.debug(f"Opened {direction} position at {entry_price}, size={size}")
    
    def _calculate_position_size(
        self, price: float, atr: float, config: BacktestConfig, lot_size: int
    ) -> float:
        """
        Calculate position size based on available capital.
        
        Args:
            price: Current price
            atr: Current ATR value
            config: Backtest configuration
            lot_size: Lot size for F&O instruments
            
        Returns:
            Position size in units
        """
        # Simple: use 10% of available capital per trade
        capital_per_trade = self.cash * 0.10
        size = capital_per_trade / price
        
        # Round to lot size for F&O
        if lot_size > 1:
            size = self._round_to_lot_size(size, price, lot_size)
        
        return size
    
    def _round_to_lot_size(self, size: float, price: float, lot_size: int) -> float:
        """
        Round position size to valid lot size for F&O instruments.
        
        Formula: quantity = floor(target_size / lot_size) * lot_size
        
        Args:
            size: Target position size
            price: Current price
            lot_size: Lot size for the instrument
            
        Returns:
            Rounded position size
        """
        num_lots = int(size / lot_size)
        return num_lots * lot_size
    
    def _apply_slippage(
        self,
        price: float,
        size: float,
        bar: pd.Series,
        config: BacktestConfig,
        is_entry: bool
    ) -> float:
        """
        Apply slippage to the execution price.
        
        Supports three slippage models:
        - fixed_pips: Fixed slippage amount
        - pct_spread: Percentage of price as slippage
        - market_impact: Slippage scales with order size / average volume
        
        Args:
            price: Base price
            size: Order size
            bar: Current bar
            config: Backtest configuration
            is_entry: True for entry orders, False for exit orders
            
        Returns:
            Price with slippage applied
        """
        slippage_model = config.slippage_model
        slippage_value = config.slippage_value
        
        if slippage_model == SlippageModel.FIXED_PIPS:
            # Fixed slippage in price units
            slippage = slippage_value
        
        elif slippage_model == SlippageModel.PCT_SPREAD:
            # Percentage of price as slippage
            slippage = price * (slippage_value / 100)
        
        elif slippage_model == SlippageModel.MARKET_IMPACT:
            # Slippage scales with order size relative to volume
            avg_volume = bar.get('volume_ma_20', bar['volume'])
            if avg_volume > 0:
                impact_ratio = (size * price) / (avg_volume * price)
                # Market impact: square root of impact ratio
                slippage = price * slippage_value * np.sqrt(impact_ratio)
            else:
                slippage = price * (slippage_value / 100)
        
        else:
            slippage = 0
        
        # Apply slippage (worse price for trader)
        if is_entry:
            # Entry: pay more for buys, receive less for sells
            return price + slippage
        else:
            # Exit: receive less for sells, pay more for covers
            return price - slippage
    
    def _apply_transaction_costs(self, trade_value: float, config: BacktestConfig):
        """
        Apply transaction costs: brokerage, STT, GST.
        
        Args:
            trade_value: Value of the trade
            config: Backtest configuration
        """
        # Brokerage (percentage)
        brokerage_pct = (config.brokerage_pct / 100) * trade_value
        
        # Brokerage (fixed)
        brokerage_fixed = config.brokerage_fixed
        
        # Total brokerage
        brokerage = brokerage_pct + brokerage_fixed
        
        # STT (Securities Transaction Tax)
        stt = (config.stt_rate / 100) * trade_value
        
        # GST on brokerage
        gst = (config.gst_rate / 100) * brokerage
        
        # Total costs
        total_cost = brokerage + stt + gst
        
        # Deduct from cash
        self.cash -= total_cost
        
        # Track cumulative costs
        self.total_brokerage += brokerage
        self.total_stt += stt
        self.total_gst += gst
        
        logger.debug(f"Transaction costs: brokerage={brokerage:.2f}, "
                    f"STT={stt:.2f}, GST={gst:.2f}, total={total_cost:.2f}")
    
    def _close_position(
        self,
        position: Position,
        exit_price: float,
        exit_date: datetime,
        exit_reason: str,
        config: BacktestConfig
    ):
        """
        Close a position and record the trade.
        
        Args:
            position: Position to close
            exit_price: Exit price
            exit_date: Exit date
            exit_reason: Reason for exit
            config: Backtest configuration
        """
        # Calculate P&L
        pnl, pnl_pct = position.calculate_pnl(exit_price)
        
        # Update position
        position.exit_price = exit_price
        position.exit_date = exit_date
        position.exit_reason = exit_reason
        position.pnl = pnl
        position.pnl_pct = pnl_pct
        
        # Update cash
        self.cash += exit_price * position.size
        
        # Apply transaction costs
        self._apply_transaction_costs(exit_price * position.size, config)
        
        # Record trade
        trade = {
            'entry_date': position.entry_date.isoformat() if hasattr(position.entry_date, 'isoformat') else str(position.entry_date),
            'exit_date': exit_date.isoformat() if hasattr(exit_date, 'isoformat') else str(exit_date),
            'direction': position.direction,
            'entry_price': position.entry_price,
            'exit_price': exit_price,
            'size': position.size,
            'pnl': pnl,
            'pnl_pct': pnl_pct,
            'exit_reason': exit_reason
        }
        
        self.closed_trades.append(trade)
        
        # Remove from open positions
        self.positions.remove(position)
        
        logger.debug(f"Closed {position.direction} position: "
                    f"entry={position.entry_price:.2f}, exit={exit_price:.2f}, "
                    f"P&L={pnl:.2f} ({pnl_pct:.2f}%), reason={exit_reason}")
    
    def _update_equity(self, bar: pd.Series, bar_idx: int):
        """
        Update equity curve with current portfolio value.
        
        Args:
            bar: Current bar
            bar_idx: Current bar index
        """
        # Calculate open position value
        open_position_value = 0.0
        for position in self.positions:
            if position.direction == 'LONG':
                open_position_value += position.size * bar['close']
            else:  # SHORT
                # For short positions, value is entry value minus current value
                open_position_value += position.size * (2 * position.entry_price - bar['close'])
        
        # Total equity = cash + open position value
        total_equity = self.cash + open_position_value
        self.equity_curve.append(total_equity)
    
    def _extract_metrics(
        self,
        spec: StrategySpec,
        config: BacktestConfig,
        data: pd.DataFrame
    ) -> BacktestResult:
        """
        Extract all metrics from the backtest results.
        
        Args:
            spec: Strategy specification
            config: Backtest configuration
            data: Original OHLCV data
            
        Returns:
            BacktestResult with all computed metrics
        """
        # Basic metrics
        final_equity = self.equity_curve[-1] if self.equity_curve else self.initial_capital
        total_return_pct = ((final_equity - self.initial_capital) / self.initial_capital) * 100
        
        # Calculate CAGR
        start_date = data.index[0]
        end_date = data.index[-1]
        years = (end_date - start_date).days / 365.25
        cagr_pct = ((final_equity / self.initial_capital) ** (1 / years) - 1) * 100 if years > 0 else 0
        
        # Calculate returns series for risk metrics
        equity_series = pd.Series(self.equity_curve)
        returns = equity_series.pct_change().dropna()
        
        # Sharpe ratio
        if len(returns) > 0 and returns.std() > 0:
            sharpe_ratio = (returns.mean() / returns.std()) * np.sqrt(252)  # Annualized
        else:
            sharpe_ratio = 0.0
        
        # Sortino ratio (downside deviation)
        downside_returns = returns[returns < 0]
        if len(downside_returns) > 0 and downside_returns.std() > 0:
            sortino_ratio = (returns.mean() / downside_returns.std()) * np.sqrt(252)
        else:
            sortino_ratio = 0.0
        
        # Drawdown metrics
        cumulative_returns = (1 + returns).cumprod()
        running_max = cumulative_returns.expanding().max()
        drawdown = (cumulative_returns - running_max) / running_max
        max_drawdown_pct = abs(drawdown.min()) * 100 if len(drawdown) > 0 else 0
        avg_drawdown_pct = abs(drawdown.mean()) * 100 if len(drawdown) > 0 else 0
        
        # Calmar ratio
        calmar_ratio = cagr_pct / max_drawdown_pct if max_drawdown_pct > 0 else 0
        
        # Max drawdown duration
        max_dd_duration_days = self._calculate_max_dd_duration(drawdown)
        
        # Trade statistics
        total_trades = len(self.closed_trades)
        
        if total_trades > 0:
            # Win rate
            winning_trades = [t for t in self.closed_trades if t['pnl'] > 0]
            win_rate_pct = (len(winning_trades) / total_trades) * 100
            
            # Average win/loss
            avg_win_pct = np.mean([t['pnl_pct'] for t in winning_trades]) if winning_trades else 0
            losing_trades = [t for t in self.closed_trades if t['pnl'] < 0]
            avg_loss_pct = np.mean([t['pnl_pct'] for t in losing_trades]) if losing_trades else 0
            
            # Profit factor
            gross_profit = sum(t['pnl'] for t in winning_trades) if winning_trades else 0
            gross_loss = abs(sum(t['pnl'] for t in losing_trades)) if losing_trades else 0
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
            
            # Expectancy per trade
            expectancy_per_trade = np.mean([t['pnl'] for t in self.closed_trades])
            
            # Average holding period
            hold_days = []
            for trade in self.closed_trades:
                entry = pd.to_datetime(trade['entry_date'])
                exit = pd.to_datetime(trade['exit_date'])
                hold_days.append((exit - entry).days)
            avg_hold_days = np.mean(hold_days) if hold_days else 0
            
            # Max consecutive losses
            max_consecutive_losses = self._calculate_max_consecutive_losses()
        else:
            win_rate_pct = 0
            avg_win_pct = 0
            avg_loss_pct = 0
            profit_factor = 0
            expectancy_per_trade = 0
            avg_hold_days = 0
            max_consecutive_losses = 0
        
        # Kelly Criterion
        kelly_fraction, half_kelly = self._calculate_kelly()
        
        # Drawdown curve
        drawdown_curve = (drawdown * 100).tolist() if len(drawdown) > 0 else []
        
        # Create result
        result = BacktestResult(
            backtest_id=str(uuid.uuid4()),
            strategy_id=spec.strategy_id,
            instrument=config.instrument,
            period=f"{config.start_date} to {config.end_date}",
            mode=BacktestMode.EVENT_DRIVEN,
            
            # Core metrics
            total_return_pct=total_return_pct,
            cagr_pct=cagr_pct,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            calmar_ratio=calmar_ratio,
            max_drawdown_pct=max_drawdown_pct,
            avg_drawdown_pct=avg_drawdown_pct,
            max_drawdown_duration_days=max_dd_duration_days,
            
            # Trade statistics
            total_trades=total_trades,
            win_rate_pct=win_rate_pct,
            avg_win_pct=avg_win_pct,
            avg_loss_pct=avg_loss_pct,
            profit_factor=profit_factor,
            expectancy_per_trade=expectancy_per_trade,
            avg_hold_days=avg_hold_days,
            max_consecutive_losses=max_consecutive_losses,
            
            # Risk metrics
            kelly_fraction=kelly_fraction,
            half_kelly=half_kelly,
            
            # Data
            trades=self.closed_trades,
            equity_curve=self.equity_curve,
            drawdown_curve=drawdown_curve
        )
        
        return result
    
    def _calculate_max_dd_duration(self, drawdown: pd.Series) -> int:
        """
        Calculate maximum drawdown duration in days.
        
        Args:
            drawdown: Drawdown series
            
        Returns:
            Maximum drawdown duration in days
        """
        if len(drawdown) == 0:
            return 0
        
        max_duration = 0
        current_duration = 0
        
        for dd in drawdown:
            if dd < 0:
                current_duration += 1
                max_duration = max(max_duration, current_duration)
            else:
                current_duration = 0
        
        return max_duration
    
    def _calculate_max_consecutive_losses(self) -> int:
        """
        Calculate maximum number of consecutive losing trades.
        
        Returns:
            Maximum consecutive losses
        """
        if len(self.closed_trades) == 0:
            return 0
        
        max_consecutive = 0
        current_consecutive = 0
        
        for trade in self.closed_trades:
            if trade['pnl'] < 0:
                current_consecutive += 1
                max_consecutive = max(max_consecutive, current_consecutive)
            else:
                current_consecutive = 0
        
        return max_consecutive
    
    def _calculate_kelly(self) -> Tuple[float, float]:
        """
        Calculate Kelly Criterion and half-Kelly position sizing.
        
        Kelly formula: f* = (p * b - q) / b
        where:
        - p = probability of winning
        - q = probability of losing (1 - p)
        - b = ratio of win to loss (avg_win / avg_loss)
        
        Returns:
            Tuple of (kelly_fraction, half_kelly)
        """
        if len(self.closed_trades) == 0:
            return 0.0, 0.0
        
        winning_trades = [t for t in self.closed_trades if t['pnl'] > 0]
        losing_trades = [t for t in self.closed_trades if t['pnl'] < 0]
        
        if len(winning_trades) == 0 or len(losing_trades) == 0:
            return 0.0, 0.0
        
        # Probability of winning
        p = len(winning_trades) / len(self.closed_trades)
        q = 1 - p
        
        # Average win/loss ratio
        avg_win = np.mean([t['pnl'] for t in winning_trades])
        avg_loss = abs(np.mean([t['pnl'] for t in losing_trades]))
        b = avg_win / avg_loss if avg_loss > 0 else 0
        
        # Kelly fraction
        kelly = (p * b - q) / b if b > 0 else 0
        
        # Cap Kelly at 0.25 (25%) for safety
        kelly = max(0, min(kelly, 0.25))
        
        # Half-Kelly for conservative sizing
        half_kelly = kelly / 2
        
        return kelly, half_kelly
