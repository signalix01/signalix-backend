"""
Forex/Commodity Macro Analyst Agent - Stage 1 (Conditional)
Specialist for forex pairs, commodities, and international markets
LLM: Mistral Large 3 (European expertise)
"""

from typing import Dict
from langchain_core.messages import HumanMessage, SystemMessage
from shared.schemas.agent_outputs import ForexMacroReport
from shared.prompts.system_prompts import FOREX_MACRO_PROMPT
import json


class ForexMacroAnalyst:
    """
    Forex/Commodity Macro Analyst - International markets specialist
    
    Model: Mistral Large 3
    Cost: ~$0.0076 per call
    Purpose: European/forex/commodity macro expertise
    Runs: Only for forex, crypto, commodity, and international equity instruments
    """
    
    def __init__(self, llm):
        self.llm = llm
        self.system_prompt = FOREX_MACRO_PROMPT
    
    async def analyze(
        self,
        instrument: str,
        instrument_type: str,
        market_regime: Dict,
        forex_context: Dict
    ) -> ForexMacroReport:
        """
        Analyze forex/commodity macro environment
        
        Args:
            instrument: Trading instrument (e.g., "EUR/USD", "GOLD", "BTCUSDT")
            instrument_type: forex, crypto, commodity, or international equity
            market_regime: Current market regime context
            forex_context: {dxy, interest_rates, cot_data, etc.}
        
        Returns:
            ForexMacroReport with carry trade conditions, geopolitical risk, etc.
        """
        user_prompt = f"""
Instrument: {instrument}
Type: {instrument_type}

FOREX/COMMODITY MACRO DATA: {json.dumps(forex_context, indent=2)}

MARKET REGIME: {json.dumps(market_regime, indent=2)}

Provide ForexMacroReport JSON with:
- Currency pair analysis (if forex)
- DXY trend impact
- Central bank stance comparison
- Commodity correlation (if applicable)
- Carry trade conditions
- Geopolitical risk assessment
"""
        
        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=user_prompt)
        ]
        
        response = await self.llm.ainvoke(messages)
        
        # Parse JSON response
        try:
            forex_data = json.loads(response.content)
            forex_report = ForexMacroReport(**forex_data)
        except Exception as e:
            # Fallback: neutral assessment
            forex_report = ForexMacroReport(
                primary_currency_pair=instrument if "/" in instrument else "N/A",
                dxy_trend="neutral",
                central_bank_stance={"fed": "neutral", "ecb": "neutral", "rbi": "neutral"},
                carry_trade_conditions="neutral",
                geopolitical_risk_score=0.5,
                macro_recommendation="neutral",
                confidence=0.5
            )
        
        return forex_report
    
    def should_run(self, instrument_type: str, instrument: str) -> bool:
        """
        Determine if this agent should run for the given instrument
        
        Returns:
            True if instrument is forex, crypto, commodity, or international equity
        """
        # Run for non-India instruments
        if instrument_type in ["forex", "crypto", "commodity"]:
            return True
        
        # Run for international equities (contains USD, EUR, etc.)
        if instrument_type == "equity" and any(curr in instrument.upper() for curr in ["USD", "EUR", "GBP", "JPY"]):
            return True
        
        # Skip for India-only instruments
        if "NSE" in instrument or "BSE" in instrument:
            return False
        
        return False
