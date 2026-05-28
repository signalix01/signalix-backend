"""BaseStrategy class for compiled strategies

This is the foundation class that all compiled strategies inherit from.
It provides helper methods for evaluating trading conditions and accessing indicator data.

Requirements: 3.1, 3.2
"""
from abc import ABC, abstractmethod
from typing import Any, Optional, Tuple, Union
import pandas as pd
import numpy as np


class BaseStrategy(ABC):
    """
    Base class for all compiled trading strategies.
    
    Provides helper methods for:
    - Accessing indicator values safely
    - Detecting crossovers (crosses_above, crosses_below)
    - Range checking (between)
    
    All compiled strategies from StrategyCompiler inherit from this class.
    """
    
    def __init__(self, data: pd.DataFrame, capital: float):
        """
        Initialize strategy with OHLCV data and starting capital.
        
        Args:
            data: DataFrame with OHLCV data and computed indicators
            capital: Starting capital in currency units
        """
        self.data = data
        self.capital = capital
        self.initial_capital = capital
        
        # Validate data
        if data is None or len(data) == 0:
            raise ValueError("Data cannot be None or empty")
        
        # Ensure data has required OHLCV columns
        required_cols = ['open', 'high', 'low', 'close', 'volume']
        missing_cols = [col for col in required_cols if col not in data.columns]
        if missing_cols:
            raise ValueError(f"Data missing required columns: {missing_cols}")
    
    # ========================================================================
    # Abstract Methods - Must be implemented by compiled strategies
    # ========================================================================
    
    @abstractmethod
    def compute_indicators(self) -> None:
        """
        Compute all technical indicators required by the strategy.
        This method is called once during strategy initialization.
        
        Compiled strategies implement this to add indicator columns to self.data.
        """
        pass
    
    @abstractmethod
    def market_filter_pass(self, bar_idx: int) -> bool:
        """
        Check if market filter conditions are met at the given bar.
        
        Args:
            bar_idx: Index of the bar to check (0-based)
            
        Returns:
            True if market conditions allow trading, False otherwise
        """
        pass
    
    @abstractmethod
    def should_enter_long(self, bar_idx: int) -> bool:
        """
        Check if long entry conditions are met at the given bar.
        
        Args:
            bar_idx: Index of the bar to check (0-based)
            
        Returns:
            True if should enter long position, False otherwise
        """
        pass
    
    @abstractmethod
    def should_enter_short(self, bar_idx: int) -> bool:
        """
        Check if short entry conditions are met at the given bar.
        
        Args:
            bar_idx: Index of the bar to check (0-based)
            
        Returns:
            True if should enter short position, False otherwise
        """
        pass
    
    @abstractmethod
    def should_exit(self, position: Any, bar_idx: int) -> Tuple[bool, str]:
        """
        Check if exit conditions are met for the given position.
        
        Args:
            position: Current position object with entry details
            bar_idx: Index of the bar to check (0-based)
            
        Returns:
            Tuple of (should_exit: bool, exit_reason: str)
        """
        pass
    
    @abstractmethod
    def position_size(self, capital: float, price: float, atr: float) -> float:
        """
        Calculate position size based on strategy's sizing method.
        
        Args:
            capital: Available capital
            price: Current price of the instrument
            atr: Current ATR value for volatility-based sizing
            
        Returns:
            Position size in currency units
        """
        pass
    
    # ========================================================================
    # Helper Methods - Available to all compiled strategies
    # ========================================================================
    
    def get_value(self, indicator_name: str, bar_idx: int) -> Optional[float]:
        """
        Safely retrieve an indicator value at a specific bar index.
        
        Args:
            indicator_name: Name of the indicator column (e.g., 'rsi_14', 'close', 'ema_50')
            bar_idx: Index of the bar (0-based)
            
        Returns:
            The indicator value, or None if not available
            
        Examples:
            >>> strategy.get_value('rsi_14', 100)
            45.2
            >>> strategy.get_value('close', 50)
            1250.75
        """
        # Validate bar index
        if bar_idx < 0 or bar_idx >= len(self.data):
            return None
        
        # Check if indicator exists
        if indicator_name not in self.data.columns:
            return None
        
        # Get value using iloc for positional indexing
        value = self.data[indicator_name].iloc[bar_idx]
        
        # Return None for NaN values
        if pd.isna(value):
            return None
        
        return float(value)
    
    def crosses_above(self, a: str, b: Union[str, float], bar_idx: int) -> bool:
        """
        Check if indicator 'a' crosses above indicator/value 'b' at bar_idx.
        
        A cross above occurs when:
        - a[bar_idx-1] < b[bar_idx-1] (a was below b in previous bar)
        - a[bar_idx] >= b[bar_idx] (a is now at or above b in current bar)
        
        Args:
            a: Name of first indicator (e.g., 'ema_9')
            b: Name of second indicator or numeric value (e.g., 'ema_21' or 50.0)
            bar_idx: Index of the bar to check (0-based)
            
        Returns:
            True if 'a' crosses above 'b', False otherwise
            
        Examples:
            >>> strategy.crosses_above('ema_9', 'ema_21', 100)
            True  # EMA 9 just crossed above EMA 21
            >>> strategy.crosses_above('rsi_14', 30, 50)
            True  # RSI just crossed above 30 (oversold threshold)
        """
        # Need at least 2 bars for crossover detection
        if bar_idx < 1:
            return False
        
        # Get current values
        a_curr = self.get_value(a, bar_idx)
        if a_curr is None:
            return False
        
        # Get previous values
        a_prev = self.get_value(a, bar_idx - 1)
        if a_prev is None:
            return False
        
        # Handle 'b' as either indicator name or numeric value
        if isinstance(b, str):
            b_curr = self.get_value(b, bar_idx)
            b_prev = self.get_value(b, bar_idx - 1)
            if b_curr is None or b_prev is None:
                return False
        else:
            # 'b' is a numeric value
            b_curr = float(b)
            b_prev = float(b)
        
        # Check crossover condition: was below, now at or above
        return a_prev < b_prev and a_curr >= b_curr
    
    def crosses_below(self, a: str, b: Union[str, float], bar_idx: int) -> bool:
        """
        Check if indicator 'a' crosses below indicator/value 'b' at bar_idx.
        
        A cross below occurs when:
        - a[bar_idx-1] > b[bar_idx-1] (a was above b in previous bar)
        - a[bar_idx] <= b[bar_idx] (a is now at or below b in current bar)
        
        Args:
            a: Name of first indicator (e.g., 'ema_9')
            b: Name of second indicator or numeric value (e.g., 'ema_21' or 70.0)
            bar_idx: Index of the bar to check (0-based)
            
        Returns:
            True if 'a' crosses below 'b', False otherwise
            
        Examples:
            >>> strategy.crosses_below('ema_9', 'ema_21', 100)
            True  # EMA 9 just crossed below EMA 21
            >>> strategy.crosses_below('rsi_14', 70, 50)
            True  # RSI just crossed below 70 (overbought threshold)
        """
        # Need at least 2 bars for crossover detection
        if bar_idx < 1:
            return False
        
        # Get current values
        a_curr = self.get_value(a, bar_idx)
        if a_curr is None:
            return False
        
        # Get previous values
        a_prev = self.get_value(a, bar_idx - 1)
        if a_prev is None:
            return False
        
        # Handle 'b' as either indicator name or numeric value
        if isinstance(b, str):
            b_curr = self.get_value(b, bar_idx)
            b_prev = self.get_value(b, bar_idx - 1)
            if b_curr is None or b_prev is None:
                return False
        else:
            # 'b' is a numeric value
            b_curr = float(b)
            b_prev = float(b)
        
        # Check crossover condition: was above, now at or below
        return a_prev > b_prev and a_curr <= b_curr
    
    def between(self, value: str, bounds: Tuple[float, float], bar_idx: int) -> bool:
        """
        Check if an indicator value is between two bounds (inclusive).
        
        Args:
            value: Name of the indicator to check (e.g., 'rsi_14')
            bounds: Tuple of (lower_bound, upper_bound)
            bar_idx: Index of the bar to check (0-based)
            
        Returns:
            True if value is between bounds (inclusive), False otherwise
            
        Examples:
            >>> strategy.between('rsi_14', (40, 60), 100)
            True  # RSI is between 40 and 60 (neutral zone)
            >>> strategy.between('close', (1200, 1300), 50)
            False  # Price is outside the range
        """
        # Validate bounds
        if not isinstance(bounds, (tuple, list)) or len(bounds) != 2:
            return False
        
        lower, upper = bounds
        
        # Get indicator value
        val = self.get_value(value, bar_idx)
        if val is None:
            return False
        
        # Check if value is within bounds (inclusive)
        return lower <= val <= upper
