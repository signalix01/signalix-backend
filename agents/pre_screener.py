"""
Pre-Screener Agent - Stage 0
Fast gate decision: should instrument enter full pipeline?
LLM: Claude Haiku 4.5 (ultra-fast, ultra-cheap)
"""

from typing import Dict
from langchain_core.messages import HumanMessage, SystemMessage
from shared.schemas.agent_outputs import ScreeningDecision
from shared.prompts.system_prompts import PRE_SCREENER_PROMPT
import json


class PreScreenerAgent:
    """
    Pre-Screener - Fast gate decision
    
    Cost: <$0.001 per call
    Speed: ~200ms
    Purpose: Save $0.40+ by rejecting invalid instruments before full pipeline
    """
    
    def __init__(self, llm):
        self.llm = llm
        self.system_prompt = PRE_SCREENER_PROMPT
    
    async def screen(
        self,
        instrument: str,
        instrument_type: str,
        market_session_data: Dict,
        data_availability: Dict
    ) -> ScreeningDecision:
        """
        Fast screening decision
        
        Args:
            instrument: Trading instrument
            instrument_type: equity, futures, options, crypto, forex, commodity
            market_session_data: {is_open, last_update_time, exchange_status}
            data_availability: {historical_days, data_quality_score, missing_fields}
        
        Returns:
            ScreeningDecision
        """
        user_prompt = f"""
Instrument: {instrument}
Type: {instrument_type}
Market session status: {json.dumps(market_session_data)}
Data availability: {json.dumps(data_availability)}

Should this proceed to full 13-agent analysis? Return ScreeningDecision JSON.
"""
        
        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=user_prompt)
        ]
        
        response = await self.llm.ainvoke(messages)
        
        # Parse JSON response
        try:
            content = response.content.strip()
            if content.startswith('```json'):
                content = content[7:]
            if content.startswith('```'):
                content = content[3:]
            if content.endswith('```'):
                content = content[:-3]
            content = content.strip()
            
            decision_data = json.loads(content)
            
            # Clean decision_data to ensure Pydantic types are correct
            if decision_data.get("instrument_type_confirmed") is None:
                decision_data["instrument_type_confirmed"] = instrument_type
            if decision_data.get("pass_screening") is None:
                decision_data["pass_screening"] = True
                
            decision = ScreeningDecision(**decision_data)
        except Exception as e:
            # Fallback: reject on parse error
            decision = ScreeningDecision(
                pass_screening=False,
                confidence_floor_met=False,
                instrument_type_confirmed=instrument_type,
                market_session_valid=False,
                data_quality_score=0.0,
                skip_reason=f"Parse error: {str(e)}"
            )
        
        return decision
