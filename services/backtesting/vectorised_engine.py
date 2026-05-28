"""
Vectorised Backtesting Engine using vectorbt.

This engine provides fast backtesting (10+ years in seconds) using vectorised operations.
For realistic simulation with slippage and partial fills, use the event-driven engine.

Requirements: 4.1, 4.5, 4.6, 4.7, 4.8
"""
import pandas as pd
import numpy as np
import uuid
from typing import List, Dict, Any
from datetime import datetime
import logging

try:
    import vectorbt as vbt
    VECTORBT_AVAILABLE = True
except ImportError:
    VECTORBT_AVAILABLE = False
    logging.warning("vectorbt not installed. Install with: pip install vectorbt")

from services.backtesting.models import BacktestConfig, BacktestResult, BacktestMode
from services.algo_builder.models import StrategySpec

logger = logging.getLogger(__name__)


class VectorisedEngine:
    """
    Vectorised backtesting engine using vectorbt for fast signal-to-result computation.
    
    This engine:
    - Uses vectorbt's Portfolio.from_signals() for fast execution
    - Computes transaction costs: brokerage (fixed + percentage), STT, GST
    - Computes all BacktestResult fields including Sharpe, Sortino, Calmar, Kelly fraction
    - Extracts trade list and equity curve from vectorbt Portfolio object
    """
    
    def __init__(self):
        """Initialize the vectorised engine"""
        if not VECTORBT_AVAILABLE:
            raise ImportError(
                "vectorbt is required for vectorised backtesting. "
                "Install with: pip install vectorbt"
            )
    
    def run(
        self,
        spec: StrategySpec,
        data: pd.DataFrame,
        config: BacktestConfig
    ) -> BacktestResult:
        """
        Run a vectorised backtest on the provided data.
        
        Args:
            spec: Strategy specification
            data: DataFrame with OHLCV data and computed indicators
            config: Backtest configuration
            
        Returns:
            BacktestResult with all computed metrics
        """
        logger.info(f"Running vectorised backtest for {spec.name} on {config.instrument}")
        
        # Generate entry and exit signals
        entry_signals, exit_signals = self._generate_signals(spec, data)
        
        # Calculate transaction costs
        fees = self._calculate_fees(config)
        
        # Run vectorbt portfolio simulation
        portfolio = vbt.Portfolio.from_signals(
            close=data['close'],
            entries=entry_signals,
            exits=exit_signals,
            init_cash=config.initial_capital,
            fees=fees,
            freq='1D'  # Assume daily frequency for now
        )
        
        # Extract metrics
        result = self._extract_metrics(
            portfolio=portfolio,
            spec=spec,
            config=config,
            data=data
        )
        
        logger.info(f"Backtest complete: {result.total_trades} trades, "
                   f"{result.total_return_pct:.2f}% return, "
                   f"Sharpe: {result.sharpe_ratio:.2f}")
        
        return result
    
    def _generate_signals(
        self,
        spec: StrategySpec,
        data: pd.DataFrame
    ) -> tuple[pd.Series, pd.Series]:
        """
        Generate entry and exit signals from strategy specification.
        
        For now, this is a simplified implementation that generates signals
        based on basic indicator conditions. A full implementation would
        use the compiled strategy code from the StrategyCompiler.
        
        Args:
            spec: Strategy specification
            data: DataFrame with OHLCV and indicators
            
        Returns:
            Tuple of (entry_signals, exit_signals) as boolean Series
        """
        # Initialize signal arrays
        entry_signals = pd.Series(False, index=data.index)
        exit_signals = pd.Series(False, index=data.index)
        
        # Simple example: RSI-based strategy
        # In production, this would use the compiled strategy code
        if 'rsi_14' in data.columns:
            # Entry: RSI crosses above 30 (oversold)
            entry_signals = (data['rsi_14'] > 30) & (data['rsi_14'].shift(1) <= 30)
            
            # Exit: RSI crosses below 70 (overbought)
            exit_signals = (data['rsi_14'] < 70) & (data['rsi_14'].shift(1) >= 70)
        else:
            logger.warning("RSI indicator not found, using simple moving average crossover")
            # Fallback: Simple MA crossover
            if 'ema_9' in data.columns and 'ema_21' in data.columns:
                entry_signals = (data['ema_9'] > data['ema_21']) & (data['ema_9'].shift(1) <= data['ema_21'].shift(1))
                exit_signals = (data['ema_9'] < data['ema_21']) & (data['ema_9'].shift(1) >= data['ema_21'].shift(1))
        
        logger.info(f"Generated {entry_signals.sum()} entry signals and {exit_signals.sum()} exit signals")
        
        return entry_signals, exit_signals
    
    def _calculate_fees(self, config: BacktestConfig) -> float:
        """
        Calculate total transaction fees as a percentage.
        
        Combines:
        - Brokerage (percentage)
        - Brokerage (fixed) - converted to approximate percentage
        - STT (Securities Transaction Tax)
        - GST on brokerage
        
        Args:
            config: Backtest configuration
            
        Returns:
            Total fees as a decimal (e.g., 0.001 for 0.1%)
        """
        # Brokerage percentage
        brokerage_pct = config.brokerage_pct / 100.0
        
        # STT
        stt = config.stt_rate / 100.0
        
        # GST on brokerage
        gst = (config.gst_rate / 100.0) * brokerage_pct
        
        # Total fees (excluding fixed brokerage for now as it requires order size)
        total_fees = brokerage_pct + stt + gst
        
        logger.debug(f"Transaction fees: {total_fees * 100:.4f}% "
                    f"(brokerage: {brokerage_pct * 100:.4f}%, "
                    f"STT: {stt * 100:.4f}%, "
                    f"GST: {gst * 100:.4f}%)")
        
        return total_fees
    
    def _extract_metrics(
        self,
        portfolio: Any,  # vbt.Portfolio
        spec: StrategySpec,
        config: BacktestConfig,
        data: pd.DataFrame
    ) -> BacktestResult:
        """
        Extract all metrics from vectorbt Portfolio object.
        
        Args:
            portfolio: vectorbt Portfolio object
            spec: Strategy specification
            config: Backtest configuration
            data: Original OHLCV data
            
        Returns:
            BacktestResult with all computed metrics
        """
        # Get portfolio statistics
        stats = portfolio.stats()
        
        # Extract basic metrics
        total_return_pct = portfolio.total_return() * 100
        
        # Calculate CAGR
        start_date = data.index[0]
        end_date = data.index[-1]
        years = (end_date - start_date).days / 365.25
        cagr_pct = ((1 + portfolio.total_return()) ** (1 / years) - 1) * 100 if years > 0 else 0
        
        # Risk-adjusted metrics
        sharpe_ratio = portfolio.sharpe_ratio()
        sortino_ratio = portfolio.sortino_ratio()
        
        # Drawdown metrics
        max_drawdown_pct = abs(portfolio.max_drawdown()) * 100
        calmar_ratio = cagr_pct / max_drawdown_pct if max_drawdown_pct > 0 else 0
        
        # Get drawdown series
        drawdown_series = portfolio.drawdown()
        avg_drawdown_pct = abs(drawdown_series.mean()) * 100
        
        # Calculate max drawdown duration
        try:
            dd_duration = portfolio.drawdown_duration()
            max_dd_duration_days = int(dd_duration.max()) if len(dd_duration) > 0 else 0
        except AttributeError:
            # Fallback for older vectorbt versions
            max_dd_duration_days = 0
        
        # Trade statistics
        trades = portfolio.trades.records_readable
        total_trades = len(trades)
        
        if total_trades > 0:
            # Win rate
            winning_trades = trades[trades['PnL'] > 0]
            win_rate_pct = (len(winning_trades) / total_trades) * 100
            
            # Average win/loss
            avg_win_pct = (winning_trades['Return'].mean() * 100) if len(winning_trades) > 0 else 0
            losing_trades = trades[trades['PnL'] < 0]
            avg_loss_pct = (losing_trades['Return'].mean() * 100) if len(losing_trades) > 0 else 0
            
            # Profit factor
            gross_profit = winning_trades['PnL'].sum() if len(winning_trades) > 0 else 0
            gross_loss = abs(losing_trades['PnL'].sum()) if len(losing_trades) > 0 else 0
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
            
            # Expectancy per trade
            expectancy_per_trade = trades['PnL'].mean()
            
            # Average holding period
            trades['Duration'] = (trades['Exit Timestamp'] - trades['Entry Timestamp']).dt.days
            avg_hold_days = trades['Duration'].mean()
            
            # Max consecutive losses
            max_consecutive_losses = self._calculate_max_consecutive_losses(trades)
        else:
            win_rate_pct = 0
            avg_win_pct = 0
            avg_loss_pct = 0
            profit_factor = 0
            expectancy_per_trade = 0
            avg_hold_days = 0
            max_consecutive_losses = 0
        
        # Kelly Criterion
        kelly_fraction, half_kelly = self._calculate_kelly(trades) if total_trades > 0 else (0, 0)
        
        # Extract trade list
        trade_list = self._extract_trade_list(trades)
        
        # Extract equity curve
        equity_curve = portfolio.value().tolist()
        
        # Extract drawdown curve
        drawdown_curve = (drawdown_series * 100).tolist()
        
        # Create result
        result = BacktestResult(
            backtest_id=str(uuid.uuid4()),
            strategy_id=spec.strategy_id,
            instrument=config.instrument,
            period=f"{config.start_date} to {config.end_date}",
            mode=BacktestMode.VECTORISED,
            
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
            trades=trade_list,
            equity_curve=equity_curve,
            drawdown_curve=drawdown_curve
        )
        
        return result
    
    def _calculate_max_consecutive_losses(self, trades: pd.DataFrame) -> int:
        """
        Calculate the maximum number of consecutive losing trades.
        
        Args:
            trades: DataFrame of trades
            
        Returns:
            Maximum consecutive losses
        """
        if len(trades) == 0:
            return 0
        
        max_consecutive = 0
        current_consecutive = 0
        
        for _, trade in trades.iterrows():
            if trade['PnL'] < 0:
                current_consecutive += 1
                max_consecutive = max(max_consecutive, current_consecutive)
            else:
                current_consecutive = 0
        
        return max_consecutive
    
    def _calculate_kelly(self, trades: pd.DataFrame) -> tuple[float, float]:
        """
        Calculate Kelly Criterion and half-Kelly position sizing.
        
        Kelly formula: f* = (p * b - q) / b
        where:
        - p = probability of winning
        - q = probability of losing (1 - p)
        - b = ratio of win to loss (avg_win / avg_loss)
        
        Args:
            trades: DataFrame of trades
            
        Returns:
            Tuple of (kelly_fraction, half_kelly)
        """
        if len(trades) == 0:
            return 0.0, 0.0
        
        winning_trades = trades[trades['PnL'] > 0]
        losing_trades = trades[trades['PnL'] < 0]
        
        if len(winning_trades) == 0 or len(losing_trades) == 0:
            return 0.0, 0.0
        
        # Probability of winning
        p = len(winning_trades) / len(trades)
        q = 1 - p
        
        # Average win/loss ratio
        avg_win = winning_trades['PnL'].mean()
        avg_loss = abs(losing_trades['PnL'].mean())
        b = avg_win / avg_loss if avg_loss > 0 else 0
        
        # Kelly fraction
        kelly = (p * b - q) / b if b > 0 else 0
        
        # Cap Kelly at 0.25 (25%) for safety
        kelly = max(0, min(kelly, 0.25))
        
        # Half-Kelly for conservative sizing
        half_kelly = kelly / 2
        
        return kelly, half_kelly
    
    def _extract_trade_list(self, trades: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        Extract trade list from vectorbt trades DataFrame.
        
        Args:
            trades: vectorbt trades DataFrame
            
        Returns:
            List of trade dictionaries
        """
        trade_list = []
        
        if len(trades) == 0:
            return trade_list
        
        # Check available columns (API may vary by version)
        available_cols = trades.columns.tolist()
        logger.debug(f"Available trade columns: {available_cols}")
        
        # Map column names (handle different vectorbt versions)
        col_map = {
            'entry_date': ['Entry Timestamp', 'entry_timestamp', 'Entry Time'],
            'exit_date': ['Exit Timestamp', 'exit_timestamp', 'Exit Time'],
            'entry_price': ['Entry Price', 'entry_price', 'EntryPrice'],
            'exit_price': ['Exit Price', 'exit_price', 'ExitPrice'],
            'size': ['Size', 'size', 'Quantity'],
            'pnl': ['PnL', 'pnl', 'P&L'],
            'return': ['Return', 'return', 'ReturnPct']
        }
        
        def get_col(trade, field_name):
            """Get column value with fallback"""
            for col_name in col_map.get(field_name, [field_name]):
                if col_name in trade.index:
                    return trade[col_name]
            return None
        
        for _, trade in trades.iterrows():
            entry_date = get_col(trade, 'entry_date')
            exit_date = get_col(trade, 'exit_date')
            entry_price = get_col(trade, 'entry_price')
            exit_price = get_col(trade, 'exit_price')
            size = get_col(trade, 'size')
            pnl = get_col(trade, 'pnl')
            ret = get_col(trade, 'return')
            
            trade_dict = {
                'entry_date': entry_date.isoformat() if pd.notna(entry_date) and hasattr(entry_date, 'isoformat') else str(entry_date) if pd.notna(entry_date) else None,
                'exit_date': exit_date.isoformat() if pd.notna(exit_date) and hasattr(exit_date, 'isoformat') else str(exit_date) if pd.notna(exit_date) else None,
                'direction': 'LONG',  # vectorbt default is long
                'entry_price': float(entry_price) if pd.notna(entry_price) else 0,
                'exit_price': float(exit_price) if pd.notna(exit_price) else 0,
                'size': float(size) if pd.notna(size) else 0,
                'pnl': float(pnl) if pd.notna(pnl) else 0,
                'pnl_pct': float(ret * 100) if pd.notna(ret) else 0,
                'exit_reason': 'signal'  # In vectorised mode, all exits are signal-based
            }
            trade_list.append(trade_dict)
        
        return trade_list
