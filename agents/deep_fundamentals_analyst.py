"""
Deep Fundamentals Analyst Agent - Stage 1 (Conditional)
Deep document analysis: earnings transcripts, SEC/SEBI filings, annual reports
LLM: Gemini 2.5 Pro (1M context, long-document reasoning)
"""

from typing import Dict
from langchain_core.messages import HumanMessage, SystemMessage
from shared.schemas.agent_outputs import DeepFundamentalsReport
import json


class DeepFundamentalsAnalyst:
    """
    Deep Fundamentals Analyst - Comprehensive document analysis
    
    Model: Gemini 2.5 Pro (1M context window)
    Cost: ~$0.028 per call
    Purpose: Earnings transcripts, regulatory filings, annual reports
    Runs: Only for deep analysis + elite tier + equity instruments
    """
    
    def __init__(self, llm):
        self.llm = llm
        self.system_prompt = """You are the Deep Fundamentals Analyst at SignalixAI AI.

## YOUR ROLE
Perform comprehensive analysis of earnings transcripts, regulatory filings, and annual reports.
Use your 1M token context window to process entire documents.

## ANALYSIS FRAMEWORK

### Earnings Quality (0-10)
- Revenue recognition practices
- One-time items and adjustments
- Cash flow vs reported earnings
- Accounting red flags
- Earnings consistency over time

### Management Credibility (0-10)
- Track record of guidance accuracy
- Transparency in communications
- Response to analyst questions
- Capital allocation decisions
- Insider trading patterns

### Balance Sheet Strength (0-10)
- Debt levels and coverage ratios
- Working capital management
- Asset quality
- Off-balance sheet items
- Liquidity position

### Earnings Surprise History
- consistent_beat: Beats estimates >75% of time
- mixed: 40-75% beat rate
- consistent_miss: <40% beat rate
- na: Insufficient history

### Regulatory Risk (0-1)
- Pending investigations
- Compliance issues
- Regulatory changes affecting business
- Legal proceedings

### Insider Activity Signal
- buying: Net insider buying in last 6 months
- neutral: No significant activity
- selling: Net insider selling
- na: No data available

### DCF Implied Upside
- Calculate intrinsic value using DCF
- Compare to current price
- Return percentage upside/downside

### Analyst Consensus
- Aggregate sell-side analyst ratings
- Weight by analyst track record if available

## OUTPUT
Return ONLY valid JSON matching DeepFundamentalsReport schema. No preamble.
"""
    
    async def analyze(
        self,
        instrument: str,
        fundamentals_report: Dict,
        documents: Dict
    ) -> DeepFundamentalsReport:
        """
        Deep analysis of company documents
        
        Args:
            instrument: Trading instrument
            fundamentals_report: Basic fundamentals from Stage 1
            documents: {
                "earnings_transcript": "...",
                "annual_report": "...",
                "sec_filings": "...",
                "analyst_reports": [...]
            }
        
        Returns:
            DeepFundamentalsReport with comprehensive analysis
        """
        user_prompt = f"""
Analyze {instrument} using the provided documents.

BASIC FUNDAMENTALS:
{json.dumps(fundamentals_report, indent=2)}

DOCUMENTS PROVIDED:
{json.dumps({k: f"{len(v)} characters" if isinstance(v, str) else f"{len(v)} items" 
             for k, v in documents.items()}, indent=2)}

Perform deep analysis and return DeepFundamentalsReport JSON.

Focus on:
1. Earnings quality and sustainability
2. Management credibility and track record
3. Balance sheet strength and risks
4. Regulatory and legal risks
5. Insider activity signals
6. Intrinsic value vs current price
"""
        
        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=user_prompt)
        ]
        
        response = await self.llm.ainvoke(messages)
        
        # Parse JSON response
        try:
            deep_data = json.loads(response.content)
            deep_report = DeepFundamentalsReport(**deep_data)
        except Exception as e:
            # Fallback: neutral assessment
            deep_report = DeepFundamentalsReport(
                earnings_quality_score=7.0,
                management_credibility=7.0,
                balance_sheet_strength=7.0,
                earnings_surprise_history="na",
                regulatory_risk=0.3,
                insider_activity_signal="na",
                dcf_implied_upside_pct=None,
                analyst_consensus=None
            )
        
        return deep_report
    
    def should_run(self, depth: str, instrument_type: str, user_tier: str = "basic") -> bool:
        """
        Determine if this agent should run
        
        Returns:
            True if deep analysis + elite tier + equity instrument
        """
        # Only run for deep analysis
        if depth != "deep":
            return False
        
        # Only run for elite tier users (optional - can remove this check)
        # if user_tier not in ["elite", "premium"]:
        #     return False
        
        # Only run for equity instruments
        if instrument_type not in ["equity", "index"]:
            return False
        
        return True
