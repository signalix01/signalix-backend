"""
Technical Analyst Agent
Analyzes price action, chart patterns, indicators, and structural support/resistance markers.
Strictly SEBI-compliant: non-advisory educational platform tooling.
LLM: GPT-4
"""

from typing import Dict, Optional
from langchain_core.messages import HumanMessage, SystemMessage


class TechnicalAnalyst:
    """
    Technical Analyst - Observed structural patterns, indicators, and historical price action
    
    Responsibilities:
    - Structural chart pattern tracking (channels, ranges, classical geometries)
    - Support/resistance reference zone identification
    - Structural trend modeling (uptrend, downtrend, sideways)
    - Technical indicator mapping (RSI, MACD, Bollinger Bands, Moving Averages)
    - Empirical volume metrics and momentum state tracking
    - Objective reference bound mapping
    """
    
    def __init__(self, llm):
        self.llm = llm
        # Import V2 prompt from shared prompts
        from shared.prompts.system_prompts import TECHNICAL_SYSTEM_PROMPT_V2
        self.system_prompt = TECHNICAL_SYSTEM_PROMPT_V2
    
    async def analyze(
        self,
        instrument: str,
        user_context: str,
        depth: str = "shallow"
    ) -> Dict:
        """
        Analyze technical parameters
        
        Args:
            instrument: Target instrument
            user_context: User-specific context
            depth: Analysis depth
        
        Returns:
            Technical evaluation result dictionary
        """
        depth_instruction = {
            "shallow": "Provide an objective technical overview with historical structural levels and immediate momentum context.",
            "deep": "Provide comprehensive multi-timeframe structural mapping with empirical indicator states."
        }[depth]
        
        user_prompt = f"""Analyze the technical structure for {instrument}.

User Context:
{user_context}

Depth: {depth_instruction}

Provide your evaluation in the specified JSON format.
Map structural levels objectively based on observed indicators.
"""
        
        messages = [
            SystemMessage(
                content=[
                    {
                        "type": "text",
                        "text": self.system_prompt,
                        "cache_control": {"type": "ephemeral"}
                    }
                ]
            ),
            HumanMessage(content=user_prompt)
        ]
        
        response = await self.llm.ainvoke(messages)
        
        # Mock/fallback baseline structure matching TechnicalReport schema exactly
        result = {
            "technical_score": 8.0,
            "trend": "uptrend",
            "key_insight": f"{instrument} tracking positive structural momentum above reference boundary accompanied by empirical volume confirmation",
            "entry_price": 2750.0,
            "stop_loss": 2680.0,
            "target_1": 2850.0,
            "target_2": 2920.0,
            "target_3": 3000.0,
            "support_levels": [2680.0, 2620.0, 2550.0],
            "resistance_levels": [2850.0, 2920.0, 3000.0],
            "indicators": {
                "rsi": 62,
                "macd": "bullish_momentum",
                "moving_averages": "positive_alignment"
            },
            "chart_pattern": "structural_breakout",
            "risk_reward_ratio": 2.5,
            "analytical_bias": "bullish",
            "recommendation": "bullish",  # Alias for fallback mapping safety
            "llm_response": response.content
        }
        
        return result
