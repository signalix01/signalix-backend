"""
Market Regime Detector Agent - Stage 0
Detects current market regime to inform ALL downstream agents
LLM: Gemini 2.5 Flash with Google Search grounding
"""

from typing import Dict
from langchain_core.messages import HumanMessage, SystemMessage
from shared.schemas.agent_outputs import MarketRegimeReport
from shared.prompts.system_prompts import MARKET_REGIME_PROMPT
import json


class MarketRegimeDetector:
    """
    Market Regime Detector - Classifies current market environment
    
    Model: Gemini 2.5 Flash with Google Search
    Cost: ~$0.0003 per call
    Purpose: Adaptive position sizing based on market conditions
    """
    
    def __init__(self, llm):
        self.llm = llm
        self.system_prompt = MARKET_REGIME_PROMPT
    
    async def detect_regime(
        self,
        instrument: str,
        instrument_type: str,
        macro_data: Dict
    ) -> MarketRegimeReport:
        """
        Detect current market regime
        
        Args:
            instrument: Trading instrument
            instrument_type: equity, crypto, forex, etc.
            macro_data: {vix, dxy, sp500, nifty, fii_flow, etc.}
        
        Returns:
            MarketRegimeReport with position_size_multiplier
        """
        user_prompt = f"""
You are the Market Regime Detector for SignalixAI AI.
Analyze the current global market regime using the data provided and real-time search.

MACRO DATA: {json.dumps(macro_data)}
TARGET INSTRUMENT: {instrument} ({instrument_type})

Search for current: India VIX level, FII activity today, DXY trend, S&P 500 trend.
Then classify the regime and return MarketRegimeReport JSON.
"""
        
        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=user_prompt)
        ]
        
        response = await self.llm.ainvoke(messages)
        
        # Parse JSON response
        try:
            regime_data = json.loads(response.content)
            regime = MarketRegimeReport(**regime_data)
        except Exception as e:
            # Fallback: neutral regime
            regime = MarketRegimeReport(
                regime="ranging",
                vix_level=macro_data.get("vix", 18.0),
                vix_regime="normal",
                global_risk_sentiment="neutral",
                forex_dollar_index=macro_data.get("dxy", 104.0),
                regime_confidence=0.5,
                position_size_multiplier=0.8
            )
        
        return regime
