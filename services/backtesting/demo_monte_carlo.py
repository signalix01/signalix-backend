"""
Demonstration script for Monte Carlo simulator.

This script shows how to use the MonteCarloSimulator to assess strategy robustness
and understand the full distribution of possible outcomes.

Requirements: 7.1–7.4
"""
from services.backtesting.monte_carlo import MonteCarloSimulator


def demo_conservative_strategy():
    """Demo: Conservative strategy with consistent small wins"""
    print("=" * 70)
    print("DEMO 1: Conservative Strategy (Small consistent wins)")
    print("=" * 70)
    
    # Conservative strategy: small wins, occasional small losses
    trade_returns = [1.5, 1.2, -0.5, 1.8, 1.0, -0.3, 1.3, 1.6, -0.4, 1.1]
    
    simulator = MonteCarloSimulator()
    result = simulator.simulate(
        trade_returns=trade_returns,
        n_simulations=10000,
        initial_capital=100000.0
    )
    
    print(f"\nTrade Returns: {trade_returns}")
    print(f"Number of Simulations: 10,000")
    print(f"Initial Capital: Rs 1,00,000")
    print("\nResults:")
    print(f"  Median Return: {result.median_return:.2f}%")
    print(f"  5th Percentile (Worst Case): {result.p5_return:.2f}%")
    print(f"  95th Percentile (Best Case): {result.p95_return:.2f}%")
    print(f"  Ruin Probability: {result.ruin_probability*100:.2f}%")
    print(f"  Critical Warning: {result.has_critical_warning}")
    
    if result.warning_message:
        print(f"\n⚠️  {result.warning_message}")
    else:
        print("\n✅ Strategy shows low risk of catastrophic loss")
    print()


def demo_aggressive_strategy():
    """Demo: Aggressive strategy with large wins and losses"""
    print("=" * 70)
    print("DEMO 2: Aggressive Strategy (Large wins and losses)")
    print("=" * 70)
    
    # Aggressive strategy: big wins, big losses
    trade_returns = [8.0, -6.0, 10.0, -7.0, 12.0, -8.0, 9.0, -5.0, 11.0, -9.0]
    
    simulator = MonteCarloSimulator()
    result = simulator.simulate(
        trade_returns=trade_returns,
        n_simulations=10000,
        initial_capital=100000.0
    )
    
    print(f"\nTrade Returns: {trade_returns}")
    print(f"Number of Simulations: 10,000")
    print(f"Initial Capital: Rs 1,00,000")
    print("\nResults:")
    print(f"  Median Return: {result.median_return:.2f}%")
    print(f"  5th Percentile (Worst Case): {result.p5_return:.2f}%")
    print(f"  95th Percentile (Best Case): {result.p95_return:.2f}%")
    print(f"  Ruin Probability: {result.ruin_probability*100:.2f}%")
    print(f"  Critical Warning: {result.has_critical_warning}")
    
    if result.warning_message:
        print(f"\n⚠️  {result.warning_message}")
    else:
        print("\n✅ Strategy shows low risk of catastrophic loss")
    print()


def demo_high_risk_strategy():
    """Demo: High-risk strategy with potential for ruin"""
    print("=" * 70)
    print("DEMO 3: High-Risk Strategy (Potential for ruin)")
    print("=" * 70)
    
    # High-risk strategy: occasional huge losses
    trade_returns = [3.0, 2.0, -15.0, 4.0, 2.5, -12.0, 3.5, 2.0, -18.0, 3.0]
    
    simulator = MonteCarloSimulator()
    result = simulator.simulate(
        trade_returns=trade_returns,
        n_simulations=10000,
        initial_capital=100000.0
    )
    
    print(f"\nTrade Returns: {trade_returns}")
    print(f"Number of Simulations: 10,000")
    print(f"Initial Capital: Rs 1,00,000")
    print("\nResults:")
    print(f"  Median Return: {result.median_return:.2f}%")
    print(f"  5th Percentile (Worst Case): {result.p5_return:.2f}%")
    print(f"  95th Percentile (Best Case): {result.p95_return:.2f}%")
    print(f"  Ruin Probability: {result.ruin_probability*100:.2f}%")
    print(f"  Critical Warning: {result.has_critical_warning}")
    
    if result.warning_message:
        print(f"\n⚠️  {result.warning_message}")
    else:
        print("\n✅ Strategy shows low risk of catastrophic loss")
    print()


def demo_turtle_trading_style():
    """Demo: Turtle Trading style - many small losses, few big wins"""
    print("=" * 70)
    print("DEMO 4: Turtle Trading Style (Richard Dennis)")
    print("=" * 70)
    
    # Turtle style: 40% win rate, but winners are 3x losers
    trade_returns = [
        -1.0, -1.0, 3.0,  # 2 losses, 1 win
        -1.0, -1.0, -1.0, 4.0,  # 3 losses, 1 big win
        -1.0, -1.0, 3.5,  # 2 losses, 1 win
        -1.0, -1.0, -1.0, 5.0,  # 3 losses, 1 huge win
    ]
    
    simulator = MonteCarloSimulator()
    result = simulator.simulate(
        trade_returns=trade_returns,
        n_simulations=10000,
        initial_capital=100000.0
    )
    
    print(f"\nTrade Returns: {trade_returns}")
    print(f"Number of Trades: {len(trade_returns)}")
    print(f"Win Rate: {sum(1 for r in trade_returns if r > 0) / len(trade_returns) * 100:.1f}%")
    print(f"Number of Simulations: 10,000")
    print(f"Initial Capital: Rs 1,00,000")
    print("\nResults:")
    print(f"  Median Return: {result.median_return:.2f}%")
    print(f"  5th Percentile (Worst Case): {result.p5_return:.2f}%")
    print(f"  95th Percentile (Best Case): {result.p95_return:.2f}%")
    print(f"  Ruin Probability: {result.ruin_probability*100:.2f}%")
    print(f"  Critical Warning: {result.has_critical_warning}")
    
    if result.warning_message:
        print(f"\n⚠️  {result.warning_message}")
    else:
        print("\n✅ Strategy shows low risk of catastrophic loss")
    
    print("\n💡 Insight: Even with 40% win rate, strategy is profitable because")
    print("   winners are much larger than losers (positive expectancy)")
    print()


def main():
    """Run all demonstrations"""
    print("\n")
    print("╔" + "=" * 68 + "╗")
    print("║" + " " * 15 + "MONTE CARLO SIMULATOR DEMONSTRATION" + " " * 18 + "║")
    print("║" + " " * 10 + "Edward Thorp: Understand the full distribution" + " " * 11 + "║")
    print("╚" + "=" * 68 + "╝")
    print("\n")
    
    demo_conservative_strategy()
    demo_aggressive_strategy()
    demo_high_risk_strategy()
    demo_turtle_trading_style()
    
    print("=" * 70)
    print("KEY TAKEAWAYS")
    print("=" * 70)
    print("""
1. Monte Carlo simulation reveals the RANGE of possible outcomes, not just
   the average expected return.

2. The 5th percentile shows your worst-case scenario - what happens in the
   bottom 5% of outcomes. This is crucial for risk management.

3. Ruin probability (>50% drawdown) is the ultimate risk metric. If this
   exceeds 5%, the strategy is too risky for most traders.

4. A strategy can have positive expected value but still carry significant
   ruin risk if it has occasional large losses.

5. The Turtle Trading approach (many small losses, few big wins) can be
   profitable despite low win rate, as long as winners are much larger
   than losers.

6. Use Monte Carlo analysis BEFORE deploying any strategy live. It's the
   difference between gambling and systematic trading.
""")
    print("=" * 70)


if __name__ == "__main__":
    main()
