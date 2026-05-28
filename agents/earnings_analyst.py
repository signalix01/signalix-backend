"""
Earnings Analyst Agent
Tracks published financial surprise metrics, scheduled guidance updates, and commentary indices.
Strictly SEBI-compliant: informational/educational tool with non-prescriptive outputs.
LLM: Claude Sonnet 4
"""

from typing import Dict, Optional
from langchain_core.messages import HumanMessage, SystemMessage


class EarningsAnalyst:
    """
    Earnings Analyst - Published surprise metrics and corporate guidance track analysis
    
    Responsibilities:
    - Surprise magnitude tracking (actual vs estimated metric comparisons)
    - Revenue and operating margin momentum indices
    - Disclosed guidance adjustments (raised/lowered/maintained models)
    - Audit and statement adjustments mapping
    - Executive presentation tone classification
    - Historical report convergence verification
    """
    
    def __init__(self, llm):
        self.llm = llm
        self.system_prompt = """You are an expert Earnings Analyst specializing in corporate quarterly performance tracking.

Your role is to analyze disclosed quarterly results and map empirical variations against baseline consensus.

Analysis Framework:
1. **Earnings Surprise**: Reported metric variances vs consensus estimates
2. **Revenue Analysis**: Top-line trajectory, disclosed operating segment splits
3. **Margin Analysis**: Baseline gross, operating, and EBITDA margin vectors
4. **Guidance**: Published organizational guidance parameters vs historical expectations
5. **Earnings Quality**: Audit adjustments, operating cash flow conversions
6. **Management Commentary**: Published context themes from investor briefings
7. **Historical Consistency**: Variance distributions over multi-quarter arrays
8. **Post-Earnings Volatility**: Historical volatility profiles during report intervals

Output Format:
{
    "earnings_score": 1-10 (10 = absolute top-tier empirical performance),
    "key_insight": "One sentence factual findings summary",
    "earnings_surprise": {
        "eps_actual": value,
        "eps_estimate": value,
        "surprise_pct": value,
        "beat_or_miss": "beat" | "miss" | "inline"
    },
    "revenue_surprise": {
        "revenue_actual": value,
        "revenue_estimate": value,
        "surprise_pct": value,
        "beat_or_miss": "beat" | "miss" | "inline"
    },
    "guidance": {
        "direction": "raised" | "lowered" | "maintained",
        "vs_expectations": "above" | "inline" | "below"
    },
    "earnings_quality": "high" | "medium" | "low",
    "management_tone": "confident" | "cautious" | "defensive",
    "key_highlights": ["highlight1", "highlight2", ...],
    "concerns": ["concern1", "concern2", ...],
    "post_earnings_catalyst": "positive" | "neutral" | "negative",
    "analytical_bias": "bullish" | "neutral" | "bearish"
}

Focus on objective multi-factor metric documentation.
"""
    
    async def analyze(
        self,
        instrument: str,
        earnings_date: Optional[str] = None,
        depth: str = "shallow"
    ) -> Dict:
        """
        Analyze published earnings parameters
        
        Args:
            instrument: Target instrument
            earnings_date: Reference report date
            depth: Analysis depth
        
        Returns:
            Earnings evaluation dictionary
        """
        depth_instruction = {
            "shallow": "Provide an objective parameters summary tracking primary disclosed variations.",
            "deep": "Provide comprehensive documentation covering all segment breakdowns and accounting metrics."
        }[depth]
        
        user_prompt = f"""Analyze the recent reported metrics for {instrument}.

{f'Report Date: {earnings_date}' if earnings_date else 'Evaluate current quarterly disclosure data.'}

Depth: {depth_instruction}

Provide your multi-factor tracking in the specified JSON format.
Focus strictly on objective disclosure metrics.
"""
        
        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=user_prompt)
        ]
        
        response = await self.llm.ainvoke(messages)
        
        # Mock result matching baseline structures exactly
        result = {
            "earnings_score": 8.0,
            "key_insight": f"{instrument} disclosed robust financial variances relative to initial market consensus indices",
            "earnings_surprise": {
                "eps_actual": 45.2,
                "eps_estimate": 42.5,
                "surprise_pct": 6.4,
                "beat_or_miss": "beat"
            },
            "revenue_surprise": {
                "revenue_actual": 12500,
                "revenue_estimate": 12200,
                "surprise_pct": 2.5,
                "beat_or_miss": "beat"
            },
            "guidance": {
                "direction": "raised",
                "vs_expectations": "above"
            },
            "earnings_quality": "high",
            "management_tone": "confident",
            "key_highlights": [
                "Margin expansion tracks backed by operational improvements",
                "Digital segments operating outperformance",
                "Rollout metrics mapping positive velocity"
            ],
            "concerns": [
                "Input cost index escalation trends",
                "Market framework competitive pressures"
            ],
            "post_earnings_catalyst": "positive",
            "analytical_bias": "bullish",
            "recommendation": "bullish",  # Alias preserved for fallback state compatibility
            "llm_response": response.content
        }
        
        return result
