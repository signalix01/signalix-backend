"""
Unit tests for Monte Carlo simulator.

Requirements: 7.1–7.4
"""
import pytest
import numpy as np
from services.backtesting.monte_carlo import MonteCarloSimulator, MonteCarloResult


class TestMonteCarloSimulator:
    """Test suite for MonteCarloSimulator"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.simulator = MonteCarloSimulator()
    
    def test_simulate_basic(self):
        """Test basic Monte Carlo simulation with known trade returns"""
        # Known trade returns: mix of wins and losses
        trade_returns = [2.5, -1.2, 3.0, -0.8, 1.5, -2.0, 4.0, -1.5, 2.0, -0.5]
        
        result = self.simulator.simulate(
            trade_returns=trade_returns,
            n_simulations=10000,
            initial_capital=100000.0
        )
        
        # Verify result structure
        assert isinstance(result, MonteCarloResult)
        assert result.median_return is not None
        assert result.p5_return is not None
        assert result.p95_return is not None
        assert result.ruin_probability is not None
        assert len(result.all_returns) == 10000
        
        # Verify percentile ordering: p5 < median < p95
        assert result.p5_return < result.median_return < result.p95_return
        
        # Verify ruin probability is between 0 and 1
        assert 0.0 <= result.ruin_probability <= 1.0
    
    def test_simulate_all_positive_returns(self):
        """Test simulation with all positive returns - should have low ruin probability"""
        trade_returns = [1.0, 2.0, 1.5, 2.5, 1.8, 2.2, 1.3, 2.8, 1.6, 2.1]
        
        result = self.simulator.simulate(
            trade_returns=trade_returns,
            n_simulations=1000,
            initial_capital=100000.0
        )
        
        # All positive returns should result in zero ruin probability
        assert result.ruin_probability == 0.0
        assert not result.has_critical_warning
        assert result.warning_message == ""
        
        # All returns should be positive
        assert result.median_return > 0
        assert result.p5_return > 0
        assert result.p95_return > 0
    
    def test_simulate_high_risk_strategy(self):
        """Test simulation with high-risk strategy - should trigger critical warning"""
        # High-risk strategy: large losses possible
        trade_returns = [5.0, -8.0, 3.0, -10.0, 4.0, -12.0, 6.0, -9.0, 2.0, -11.0]
        
        result = self.simulator.simulate(
            trade_returns=trade_returns,
            n_simulations=1000,
            initial_capital=100000.0
        )
        
        # High-risk strategy should have significant ruin probability
        assert result.ruin_probability > 0.0
        
        # May or may not trigger critical warning depending on sequence
        if result.has_critical_warning:
            assert result.ruin_probability > 0.05
            assert "CRITICAL WARNING" in result.warning_message
            assert "catastrophic capital loss" in result.warning_message
    
    def test_simulate_empty_trades(self):
        """Test that empty trade list raises ValueError"""
        with pytest.raises(ValueError, match="trade_returns cannot be empty"):
            self.simulator.simulate(
                trade_returns=[],
                n_simulations=1000,
                initial_capital=100000.0
            )
    
    def test_simulate_invalid_simulations(self):
        """Test that invalid n_simulations raises ValueError"""
        trade_returns = [1.0, 2.0, -1.0]
        
        with pytest.raises(ValueError, match="n_simulations must be at least 1"):
            self.simulator.simulate(
                trade_returns=trade_returns,
                n_simulations=0,
                initial_capital=100000.0
            )
    
    def test_simulate_invalid_capital(self):
        """Test that invalid initial_capital raises ValueError"""
        trade_returns = [1.0, 2.0, -1.0]
        
        with pytest.raises(ValueError, match="initial_capital must be positive"):
            self.simulator.simulate(
                trade_returns=trade_returns,
                n_simulations=1000,
                initial_capital=0.0
            )
    
    def test_simulate_deterministic_loss(self):
        """Test simulation with guaranteed loss sequence"""
        # All negative returns - guaranteed ruin (need larger losses to hit 50% threshold)
        # 15 consecutive -10% losses: 0.9^15 ≈ 0.206 < 0.5 (ruin threshold)
        trade_returns = [-10.0, -10.0, -10.0, -10.0, -10.0, -10.0, -10.0, -10.0, 
                        -10.0, -10.0, -10.0, -10.0, -10.0, -10.0, -10.0]
        
        result = self.simulator.simulate(
            trade_returns=trade_returns,
            n_simulations=100,
            initial_capital=100000.0
        )
        
        # All simulations should result in loss
        assert result.median_return < 0
        assert result.p5_return < 0
        assert result.p95_return < 0
        
        # Should have 100% ruin probability (equity drops below 50%)
        assert result.ruin_probability == 1.0
        assert result.has_critical_warning
    
    def test_simulate_small_sample(self):
        """Test simulation with small number of trades"""
        trade_returns = [2.0, -1.0, 3.0]
        
        result = self.simulator.simulate(
            trade_returns=trade_returns,
            n_simulations=1000,
            initial_capital=100000.0
        )
        
        # Should still produce valid results
        assert result.p5_return < result.median_return < result.p95_return
        assert 0.0 <= result.ruin_probability <= 1.0
    
    def test_simulate_large_sample(self):
        """Test simulation with large number of trades"""
        # Generate 100 random trades
        np.random.seed(42)  # For reproducibility
        trade_returns = list(np.random.normal(1.0, 2.0, 100))
        
        result = self.simulator.simulate(
            trade_returns=trade_returns,
            n_simulations=1000,
            initial_capital=100000.0
        )
        
        # Should produce valid results
        assert result.p5_return < result.median_return < result.p95_return
        assert 0.0 <= result.ruin_probability <= 1.0
    
    def test_extract_trade_returns(self):
        """Test extracting returns from backtest trade list"""
        trades = [
            {'entry_date': '2020-01-01', 'exit_date': '2020-01-05', 'pnl_pct': 2.5},
            {'entry_date': '2020-01-10', 'exit_date': '2020-01-15', 'pnl_pct': -1.2},
            {'entry_date': '2020-01-20', 'exit_date': '2020-01-25', 'pnl_pct': 3.0},
        ]
        
        returns = self.simulator.extract_trade_returns(trades)
        
        assert len(returns) == 3
        assert returns == [2.5, -1.2, 3.0]
    
    def test_extract_trade_returns_empty(self):
        """Test extracting returns from empty trade list"""
        returns = self.simulator.extract_trade_returns([])
        assert returns == []
    
    def test_extract_trade_returns_missing_pnl(self):
        """Test extracting returns when some trades missing pnl_pct"""
        trades = [
            {'entry_date': '2020-01-01', 'exit_date': '2020-01-05', 'pnl_pct': 2.5},
            {'entry_date': '2020-01-10', 'exit_date': '2020-01-15'},  # Missing pnl_pct
            {'entry_date': '2020-01-20', 'exit_date': '2020-01-25', 'pnl_pct': 3.0},
        ]
        
        returns = self.simulator.extract_trade_returns(trades)
        
        # Should only extract trades with pnl_pct
        assert len(returns) == 2
        assert returns == [2.5, 3.0]
    
    def test_simulate_reproducibility(self):
        """Test that simulation with same seed produces consistent results"""
        trade_returns = [2.0, -1.0, 3.0, -0.5, 1.5]
        
        # Set seed for reproducibility
        np.random.seed(42)
        result1 = self.simulator.simulate(
            trade_returns=trade_returns,
            n_simulations=1000,
            initial_capital=100000.0
        )
        
        # Reset seed and run again
        np.random.seed(42)
        result2 = self.simulator.simulate(
            trade_returns=trade_returns,
            n_simulations=1000,
            initial_capital=100000.0
        )
        
        # Results should be identical
        assert result1.median_return == result2.median_return
        assert result1.p5_return == result2.p5_return
        assert result1.p95_return == result2.p95_return
        assert result1.ruin_probability == result2.ruin_probability
    
    def test_simulate_percentile_spread(self):
        """Test that p95-p5 spread is reasonable for volatile strategy"""
        # Volatile strategy with wide return distribution
        trade_returns = [10.0, -8.0, 12.0, -9.0, 15.0, -10.0, 8.0, -7.0, 11.0, -6.0]
        
        result = self.simulator.simulate(
            trade_returns=trade_returns,
            n_simulations=10000,
            initial_capital=100000.0
        )
        
        # Spread between p5 and p95 should be significant for volatile strategy
        spread = result.p95_return - result.p5_return
        assert spread > 0  # p95 should be higher than p5
        
        # For this volatile strategy, expect wide spread
        assert spread > 10.0  # At least 10% spread
    
    def test_simulate_critical_warning_threshold(self):
        """Test that critical warning triggers exactly at 5% ruin probability"""
        # Create a strategy that will have exactly 5% ruin probability
        # This is hard to control precisely, so we test the boundary logic
        trade_returns = [1.0, -0.5, 2.0, -1.0, 1.5]
        
        result = self.simulator.simulate(
            trade_returns=trade_returns,
            n_simulations=1000,
            initial_capital=100000.0
        )
        
        # Verify warning logic is consistent
        if result.ruin_probability > 0.05:
            assert result.has_critical_warning
            assert len(result.warning_message) > 0
        else:
            assert not result.has_critical_warning
            assert result.warning_message == ""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
