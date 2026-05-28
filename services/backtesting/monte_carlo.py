"""
Monte Carlo simulator for backtesting validation.

Implements Richard Dennis approach: understand the full distribution of outcomes,
not just the expected value.

Requirements: 7.1–7.4
"""
import numpy as np
from typing import List
from pydantic import BaseModel, Field


class MonteCarloResult(BaseModel):
    """Results from Monte Carlo simulation"""
    median_return: float = Field(..., description="Median return across all simulations (%)")
    p5_return: float = Field(..., description="5th percentile return (%)")
    p95_return: float = Field(..., description="95th percentile return (%)")
    ruin_probability: float = Field(..., description="P(capital < 50% of initial)")
    all_returns: List[float] = Field(..., description="All simulation returns for histogram")
    has_critical_warning: bool = Field(..., description="True if ruin_probability > 0.05")
    warning_message: str = Field(default="", description="Warning message if critical")


class MonteCarloSimulator:
    """
    Monte Carlo simulator for strategy robustness testing.
    
    Randomly resamples trade return sequence to generate distribution of outcomes.
    Key outputs: median return, 5th/95th percentile, ruin probability.
    """
    
    def simulate(
        self,
        trade_returns: List[float],
        n_simulations: int = 10000,
        initial_capital: float = 100000.0
    ) -> MonteCarloResult:
        """
        Run Monte Carlo simulation by resampling trade returns.
        
        Args:
            trade_returns: List of trade returns in percentage (e.g., [2.5, -1.2, 3.0])
            n_simulations: Number of simulations to run (default: 10,000)
            initial_capital: Starting capital for ruin probability calculation
            
        Returns:
            MonteCarloResult with distribution statistics and ruin probability
            
        Raises:
            ValueError: If trade_returns is empty or n_simulations < 1
        """
        if not trade_returns:
            raise ValueError("trade_returns cannot be empty")
        if n_simulations < 1:
            raise ValueError("n_simulations must be at least 1")
        if initial_capital <= 0:
            raise ValueError("initial_capital must be positive")
        
        simulation_returns = []
        ruin_count = 0
        ruin_threshold = initial_capital * 0.5  # 50% drawdown = ruin
        
        # Convert to numpy array for faster sampling
        trade_returns_array = np.array(trade_returns)
        n_trades = len(trade_returns)
        
        for _ in range(n_simulations):
            # Randomly resample trade return sequence with replacement
            shuffled = np.random.choice(trade_returns_array, size=n_trades, replace=True)
            
            # Track equity path for this simulation
            equity = initial_capital
            min_equity = equity
            
            for ret in shuffled:
                # Apply return: equity *= (1 + ret/100)
                equity *= (1 + ret / 100.0)
                min_equity = min(min_equity, equity)
            
            # Calculate final return percentage
            final_return_pct = ((equity - initial_capital) / initial_capital) * 100.0
            simulation_returns.append(final_return_pct)
            
            # Check for ruin (equity fell below 50% of initial at any point)
            if min_equity < ruin_threshold:
                ruin_count += 1
        
        # Calculate statistics
        median_return = float(np.median(simulation_returns))
        p5_return = float(np.percentile(simulation_returns, 5))
        p95_return = float(np.percentile(simulation_returns, 95))
        ruin_probability = ruin_count / n_simulations
        
        # Check for critical warning
        has_critical_warning = ruin_probability > 0.05
        warning_message = ""
        if has_critical_warning:
            warning_message = (
                f"CRITICAL WARNING: Monte Carlo analysis shows {ruin_probability*100:.1f}% "
                f"probability of catastrophic capital loss (>50% drawdown). "
                f"Reduce position size or tighten stop losses."
            )
        
        return MonteCarloResult(
            median_return=median_return,
            p5_return=p5_return,
            p95_return=p95_return,
            ruin_probability=ruin_probability,
            all_returns=simulation_returns,
            has_critical_warning=has_critical_warning,
            warning_message=warning_message
        )
    
    def extract_trade_returns(self, trades: List[dict]) -> List[float]:
        """
        Extract trade returns from backtest trade list.
        
        Args:
            trades: List of trade dicts with 'pnl_pct' field
            
        Returns:
            List of trade returns in percentage
        """
        if not trades:
            return []
        
        returns = []
        for trade in trades:
            if 'pnl_pct' in trade:
                returns.append(float(trade['pnl_pct']))
        
        return returns
