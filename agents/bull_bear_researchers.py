"""
Bull and Bear Researcher Agents - Stage 2
Multi-round debate mechanism for thesis validation
LLM: Claude Sonnet 4.6
"""

from typing import Dict, Optional
from langchain_core.messages import HumanMessage, SystemMessage
from shared.schemas.agent_outputs import ResearchThesis
from shared.prompts.system_prompts import BULL_RESEARCHER_PROMPT_V2, BEAR_RESEARCHER_PROMPT_V2
import json


class BullResearcher:
    """
    Bull Researcher - Builds strongest bullish thesis
    
    Model: Claude Sonnet 4.6
    Purpose: Professional advocacy for long side with evidence-based arguments
    """
    
    def __init__(self, llm):
        self.llm = llm
        self.system_prompt = BULL_RESEARCHER_PROMPT_V2
    
    async def research(
        self,
        instrument: str,
        fundamentals: Dict,
        technical: Dict,
        macro: Dict,
        sentiment: Dict,
        debate_round: int = 1,
        bear_thesis: Optional[Dict] = None
    ) -> ResearchThesis:
        """
        Build bullish investment thesis
        
        Args:
            instrument: Trading instrument
            fundamentals: Fundamentals analysis
            technical: Technical analysis
            macro: Macro analysis
            sentiment: Sentiment analysis
            debate_round: Current debate round (1, 2, or 3)
            bear_thesis: Bear's thesis from previous round (for rebuttal)
        
        Returns:
            ResearchThesis with bull arguments
        """
        user_prompt = f"""
Build the STRONGEST POSSIBLE bullish thesis for {instrument}.

DEBATE ROUND: {debate_round}

=== ANALYST REPORTS ===

Fundamentals:
{json.dumps(fundamentals, indent=2)}

Technical:
{json.dumps(technical, indent=2)}

Macro:
{json.dumps(macro, indent=2)}

Sentiment:
{json.dumps(sentiment, indent=2)}

{f'''
=== BEAR THESIS (from previous round) ===
{json.dumps(bear_thesis, indent=2)}

You MUST address their strongest argument in your rebuttal.
''' if bear_thesis else ''}

Return ResearchThesis JSON with your bull arguments.
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
        
        # Parse JSON response
        try:
            thesis_data = json.loads(response.content)
            thesis = ResearchThesis(**thesis_data, side="bull", debate_round=debate_round)
        except Exception as e:
            # Fallback thesis
            thesis = ResearchThesis(
                side="bull",
                overall_conviction=0.6,
                key_arguments=[
                    {"argument": "Positive fundamentals", "evidence": "From analyst reports", "conviction": 0.6}
                ],
                debate_round=debate_round
            )
        
        return thesis


class BearResearcher:
    """
    Bear Researcher - Builds strongest bearish thesis
    
    Model: Claude Sonnet 4.6
    Purpose: Professional advocacy for short side with evidence-based arguments
    """
    
    def __init__(self, llm):
        self.llm = llm
        self.system_prompt = BEAR_RESEARCHER_PROMPT_V2
    
    async def research(
        self,
        instrument: str,
        fundamentals: Dict,
        technical: Dict,
        macro: Dict,
        sentiment: Dict,
        debate_round: int = 1,
        bull_thesis: Optional[Dict] = None
    ) -> ResearchThesis:
        """
        Build bearish investment thesis
        
        Args:
            instrument: Trading instrument
            fundamentals: Fundamentals analysis
            technical: Technical analysis
            macro: Macro analysis
            sentiment: Sentiment analysis
            debate_round: Current debate round (1, 2, or 3)
            bull_thesis: Bull's thesis from previous round (for rebuttal)
        
        Returns:
            ResearchThesis with bear arguments
        """
        user_prompt = f"""
Build the STRONGEST POSSIBLE bearish thesis for {instrument}.

DEBATE ROUND: {debate_round}

=== ANALYST REPORTS ===

Fundamentals:
{json.dumps(fundamentals, indent=2)}

Technical:
{json.dumps(technical, indent=2)}

Macro:
{json.dumps(macro, indent=2)}

Sentiment:
{json.dumps(sentiment, indent=2)}

{f'''
=== BULL THESIS (from previous round) ===
{json.dumps(bull_thesis, indent=2)}

You MUST address their strongest argument in your rebuttal.
''' if bull_thesis else ''}

Return ResearchThesis JSON with your bear arguments.
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
        
        # Parse JSON response
        try:
            thesis_data = json.loads(response.content)
            thesis = ResearchThesis(**thesis_data, side="bear", debate_round=debate_round)
        except Exception as e:
            # Fallback thesis
            thesis = ResearchThesis(
                side="bear",
                overall_conviction=0.4,
                key_arguments=[
                    {"argument": "Risk factors present", "evidence": "From analyst reports", "conviction": 0.4}
                ],
                debate_round=debate_round
            )
        
        return thesis
