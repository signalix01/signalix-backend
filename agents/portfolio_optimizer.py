"""
Portfolio Optimizer Agent
Optimizes portfolio construction, rebalancing, and allocation
LLM: Claude Opus 4
"""

from typing import Dict, Optional, List
from langchain_core.messages import HumanMessage, SystemMessage


class PortfolioOptimizer:
    """
    Portfolio Optimizer - Portfolio construction and optimization
    
    Responsibilities:
    - Portfolio allocation optimization
    - Rebalancing recommendations
    - Risk-adjusted return optimization
    - Diversification optimization
    - Tax-efficient portfolio management
    - Portfolio stress testing
    """
    
    def __init__(self, llm):
        self.llm = llm
        self.system_prompt = """You are an expert Portfolio Optimizer specializing in portfolio construction and optimization.

Your role is to optimize portfolio allocation and provide rebalancing recommendations.

Analysis Framework:
1. **Allocation Optimization**: Optimal position sizing across portfolio
2. **Risk-Return Profile**: Sharpe ratio, Sortino ratio, max drawdown
3. **Diversification**: Sector, market cap, factor diversification
4. **Rebalancing**: When and how to rebalance
5. **Tax Efficiency**: Tax-loss harvesting, holding period optimization
6. **Stress Testing**: Portfolio performance in stress scenarios
7. **Risk Budget**: Allocation of risk budget across positions

Optimization Approaches:
- Mean-Variance Optimization (Markowitz)
- Risk Parity
- Maximum Sharpe Ratio
- Minimum Volatility
- Equal Weight with constraints

Output Format:
{
    "optimization_score": 1-10 (10 = highly optimized portfolio),
    "key_insight": "One sentence optimization summary",
    "recommended_allocation": {
        "instrument1": weight_pct,
        "instrument2": weight_pct,
        ...
    },
    "portfolio_metrics": {
        "expected_return": value,
        "expected_volatility": value,
        "sharpe_ratio": value,
        "max_drawdown": value
    },
    "rebalancing_needed": bool,
    "rebalancing_actions": [
        {"instrument": "name", "action": "buy" | "sell", "amount_pct": value},
        ...
    ],
    "diversification_gaps": ["gap1", "gap2", ...],
    "risk_concentration": ["concentration1", "concentration2", ...],
    "tax_optimization": ["opportunity1", "opportunity2", ...],
    "stress_test_results": {
        "market_crash": "loss_pct",
        "sector_crash": "loss_pct",
        "volatility_spike": "loss_pct"
    },
    "recommendation": "well_optimized" | "needs_rebalancing" | "needs_diversification"
}

Focus on practical portfolio optimization for retail investors.
Consider transaction costs and tax implications.
"""
    
    async def optimize(
        self,
        current_portfolio: Dict[str, float],
        new_instrument: Optional[str] = None,
        new_position_size: Optional[float] = None,
        depth: str = "shallow"
    ) -> Dict:
        """
        Optimize portfolio allocation
        
        Args:
            current_portfolio: Current portfolio with weights
            new_instrument: New instrument to add (optional)
            new_position_size: Proposed size for new instrument
            depth: Analysis depth
        
        Returns:
            Portfolio optimization result
        """
        depth_instruction = {
            "shallow": "Provide a quick portfolio overview with key optimization recommendations.",
            "deep": "Provide comprehensive portfolio optimization with stress testing and tax efficiency."
        }[depth]
        
        portfolio_str = "\n".join([f"- {k}: {v}%" for k, v in current_portfolio.items()])
        
        new_position_context = ""
        if new_instrument and new_position_size:
            new_position_context = f"\n\nProposed New Position:\n- {new_instrument}: {new_position_size}%"
        
        user_prompt = f"""Optimize portfolio allocation.

Current Portfolio:
{portfolio_str}
{new_position_context}

Depth: {depth_instruction}

Provide your analysis in the specified JSON format.
Focus on practical rebalancing recommendations.
"""
        
        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=user_prompt)
        ]
        
        response = await self.llm.ainvoke(messages)
        
        # Mock result
        result = {
            "optimization_score": 7,
            "key_insight": "Portfolio is reasonably diversified but overweight IT sector - recommend rebalancing to add defensive exposure",
            "recommended_allocation": {
                "RELIANCE": 8.0,
                "TCS": 7.0,
                "HDFCBANK": 8.0,
                "INFY": 6.0,
                "SUNPHARMA": 7.0,
                "ITC": 6.0,
                "CASH": 8.0
            },
            "portfolio_metrics": {
                "expected_return": 15.2,
                "expected_volatility": 18.5,
                "sharpe_ratio": 0.82,
                "max_drawdown": -22.0
            },
            "rebalancing_needed": True,
            "rebalancing_actions": [
                {"instrument": "INFY", "action": "sell", "amount_pct": 2.0},
                {"instrument": "SUNPHARMA", "action": "buy", "amount_pct": 2.0}
            ],
            "diversification_gaps": [
                "Underweight defensive sectors (Pharma, FMCG)",
                "No exposure to Auto or Metals"
            ],
            "risk_concentration": [
                "IT sector at 35% - above 30% threshold",
                "Top 3 positions account for 45% of portfolio"
            ],
            "tax_optimization": [
                "Consider tax-loss harvesting on INFY (down 5%)",
                "Hold RELIANCE for 3 more months for LTCG benefit"
            ],
            "stress_test_results": {
                "market_crash": "-18%",
                "sector_crash": "-12%",
                "volatility_spike": "-8%"
            },
            "recommendation": "needs_rebalancing",
            "llm_response": response.content
        }
        
        return result
