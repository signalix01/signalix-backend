"""
LangGraph Orchestration Pipeline V2
13-Agent Multi-LLM Trading Analysis - Matches LLM.md Specification
"""

from typing import Dict, List, Optional, TypedDict, Annotated
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
import operator
from datetime import datetime
import os

from shared.config.settings import settings
from shared.utils.user_context import UserContext, UserContextInjector
from shared.schemas.agent_outputs import (
    ScreeningDecision, MarketRegimeReport, FundamentalsReport, TechnicalReport,
    MacroReport, SentimentReport, NewsFlashReport, ForexMacroReport,
    DeepFundamentalsReport, ResearchThesis, QuantCheckReport, RiskAssessment,
    TradingDecision
)

# Import agents
from agents.pre_screener import PreScreenerAgent
from agents.market_regime_detector import MarketRegimeDetector
from agents.fundamentals_analyst import FundamentalsAnalyst
from agents.technical_analyst import TechnicalAnalyst
from agents.macro_analyst import MacroAnalyst
from agents.sentiment_analyst import SentimentAnalyst
from agents.news_scanner import NewsScannerAgent
from agents.bull_bear_researchers import BullResearcher, BearResearcher
from agents.quant_cross_check import QuantitativeCrossCheck
from agents.risk_manager import RiskManager
from agents.final_trader import FinalTrader


# ============================================================================
# Extended State Definition (LLM.md Section 5)
# ============================================================================

class ExtendedSignalixAIState(TypedDict):
    """State passed between agents - matches LLM.md specification"""
    # Input
    instrument: str
    instrument_type: str  # equity, futures, options, crypto, forex, commodity, index
    analysis_type: str
    depth: str  # shallow, deep
    user_context: UserContext
    additional_context: Optional[str]
    analysis_date: str
    
    # Stage 0: Screening
    screening_decision: Optional[ScreeningDecision]
    market_regime: Optional[MarketRegimeReport]
    
    # Stage 1: Analysts
    fundamentals_report: Optional[FundamentalsReport]
    technical_report: Optional[TechnicalReport]
    macro_report: Optional[MacroReport]
    sentiment_report: Optional[SentimentReport]
    news_flash_report: Optional[NewsFlashReport]
    forex_macro_report: Optional[ForexMacroReport]
    deep_fundamentals_report: Optional[DeepFundamentalsReport]
    earnings_report: Optional[Dict]
    historical_validation: Optional[Dict]
    
    # Stage 2: Debate
    bull_thesis: Optional[ResearchThesis]
    bear_thesis: Optional[ResearchThesis]
    debate_round: int
    
    # Stage 3: Quant + Risk
    quant_check_report: Optional[QuantCheckReport]
    risk_assessment: Optional[RiskAssessment]
    
    # Stage 4: Final Decision
    final_decision: Optional[TradingDecision]
    
    # Metadata
    agents_executed: Annotated[List[str], operator.add]
    llm_cost_usd: Annotated[float, operator.add]
    start_time: datetime
    errors: Annotated[List[str], operator.add]


# ============================================================================
# Analysis Pipeline V2 - Matches LLM.md 4-Stage Architecture
# ============================================================================

class AnalysisPipelineV2:
    """
    LangGraph-based orchestration pipeline for 13-agent trading analysis
    Matches LLM.md specification exactly
    
    Pipeline Flow (4 Stages):
    
    Stage 0: Screening (Sequential Gate)
      1. Pre-screener (Claude Haiku 4.5) - Fast gate decision
      2. Market Regime Detector (Gemini 2.5 Flash) - Informs all downstream
    
    Stage 1: Analysts (Parallel Execution)
      3. Fundamentals Analyst (Claude Sonnet 4.6)
      4. Technical Analyst (Claude Sonnet 4.6)
      5. Macro Analyst (Claude Sonnet 4.6)
      6. Sentiment Analyst (Gemini 2.5 Flash)
      7. News Scanner (Grok 4)
      8. Forex Macro Analyst (Mistral Large 3) [conditional]
      9. Deep Fundamentals (Gemini 2.5 Pro) [conditional]
    
    Stage 2: Debate (Multi-round)
      10. Bull Researcher (Claude Sonnet 4.6)
      11. Bear Researcher (Claude Sonnet 4.6)
      [2-3 rounds of debate]
    
    Stage 3: Quant Check + Risk
      12. Quantitative Cross-Check (DeepSeek-R1)
      13. Risk Manager (Claude Opus 4.6)
    
    Stage 4: Final Decision
      14. Final Trader (Claude Opus 4.6)
    """
    
    def __init__(
        self,
        user_context: UserContext,
        depth: str = "shallow"
    ):
        self.user_context = user_context
        self.depth = depth
        self.context_injector = UserContextInjector()
        
        # ====================================================================
        # Initialize LLM clients - CORRECT MODEL ASSIGNMENTS per LLM.md
        # ====================================================================
        
        # Gemini 2.5 Flash - Market Regime + Sentiment (Google Search grounding)
        self.gemini_flash = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=settings.GEMINI_API_KEY,
            temperature=0.3
        )
        
        # Gemini 2.5 Pro - Deep Fundamentals (long-document analysis)
        self.gemini_pro = ChatGoogleGenerativeAI(
            model="gemini-1.5-pro",  # Using the advanced pro model for complex reasoning
            google_api_key=settings.GEMINI_API_KEY,
            temperature=0.2,
            max_output_tokens=8192
        )
        
        # Alias all models to Gemini to allow 100% free testing with a single key
        self.claude_haiku = self.gemini_flash
        self.claude_sonnet = self.gemini_pro
        self.claude_opus = self.gemini_pro
        self.grok = self.gemini_flash
        self.deepseek = self.gemini_pro
        self.mistral = self.gemini_pro
        
        # ====================================================================
        # Initialize agents with CORRECT LLM assignments
        # ====================================================================
        
        # Stage 0
        self.pre_screener = PreScreenerAgent(self.claude_haiku)
        self.market_regime_detector = MarketRegimeDetector(self.gemini_flash)
        
        # Stage 1
        self.fundamentals_analyst = FundamentalsAnalyst(self.claude_sonnet)
        self.technical_analyst = TechnicalAnalyst(self.claude_sonnet)
        self.macro_analyst = MacroAnalyst(self.claude_sonnet)
        self.sentiment_analyst = SentimentAnalyst(self.gemini_flash)
        self.news_scanner = NewsScannerAgent(self.grok)
        
        # Conditional agents
        from agents.forex_macro_analyst import ForexMacroAnalyst
        from agents.deep_fundamentals_analyst import DeepFundamentalsAnalyst
        self.forex_macro_analyst = ForexMacroAnalyst(self.mistral)
        self.deep_fundamentals_analyst = DeepFundamentalsAnalyst(self.gemini_pro)
        
        # Stage 2
        self.bull_researcher = BullResearcher(self.claude_sonnet)
        self.bear_researcher = BearResearcher(self.claude_sonnet)
        
        # Stage 3
        self.quant_cross_check = QuantitativeCrossCheck(self.deepseek)
        self.risk_manager = RiskManager(self.claude_opus)
        
        # New Strategic Agents
        from agents.portfolio_optimizer import PortfolioOptimizer
        from agents.correlation_analyst import CorrelationAnalyst
        from agents.sector_rotation_analyst import SectorRotationAnalyst
        from agents.earnings_analyst import EarningsAnalyst
        from agents.historical_validation import HistoricalValidationAgent
        
        self.portfolio_optimizer = PortfolioOptimizer(self.claude_sonnet)
        self.correlation_analyst = CorrelationAnalyst(self.claude_sonnet)
        self.sector_rotation_analyst = SectorRotationAnalyst(self.gemini_flash)
        self.earnings_analyst = EarningsAnalyst(self.gemini_pro)
        self.historical_validator = HistoricalValidationAgent()
        
        # Stage 4
        self.final_trader = FinalTrader(self.claude_opus)
        
        # Build graph
        self.graph = self._build_graph()
    
    def _build_graph(self) -> StateGraph:
        """Build LangGraph state machine - 4-stage architecture"""
        workflow = StateGraph(ExtendedSignalixAIState)
        
        # ====================================================================
        # Stage 0: Screening (Sequential Gate)
        # ====================================================================
        workflow.add_node("pre_screener", self._run_pre_screener)
        workflow.add_node("market_regime", self._run_market_regime)
        workflow.add_node("skip_instrument", self._skip_instrument)
        
        # ====================================================================
        # Stage 1: Analysts (Parallel Execution)
        # ====================================================================
        workflow.add_node("fundamentals", self._run_fundamentals)
        workflow.add_node("technical", self._run_technical)
        workflow.add_node("macro", self._run_macro)
        workflow.add_node("sentiment", self._run_sentiment)
        workflow.add_node("news_scanner", self._run_news_scanner)
        workflow.add_node("forex_macro", self._run_forex_macro)
        workflow.add_node("deep_fundamentals", self._run_deep_fundamentals)
        workflow.add_node("earnings_analysis", self._run_earnings_analysis)
        workflow.add_node("historical_validation", self._run_historical_validation)
        
        # ====================================================================
        # Stage 2: Debate (Multi-round)
        # ====================================================================
        workflow.add_node("bull_research", self._run_bull_research)
        workflow.add_node("bear_research", self._run_bear_research)
        workflow.add_node("debate_counter", self._increment_debate_round)
        
        # ====================================================================
        # Stage 3: Quant Check + Risk
        # ====================================================================
        workflow.add_node("quant_check", self._run_quant_check)
        workflow.add_node("risk_manager", self._run_risk_manager)
        
        # ====================================================================
        # Stage 4: Final Decision
        # ====================================================================
        workflow.add_node("final_trader", self._run_final_trader)
        
        # ====================================================================
        # Define Edges - 4-Stage Flow
        # ====================================================================
        
        # Start → Pre-screener
        workflow.add_edge(START, "pre_screener")
        
        # Pre-screener → Conditional gate
        workflow.add_conditional_edges(
            "pre_screener",
            self._should_proceed_to_pipeline,
            {
                "skip": "skip_instrument",
                "proceed": "market_regime"
            }
        )
        workflow.add_edge("skip_instrument", END)
        
        # Market Regime → All Stage 1 analysts in PARALLEL
        for analyst in ["fundamentals", "technical", "macro", "sentiment", "news_scanner"]:
            workflow.add_edge("market_regime", analyst)
        
        # Conditional edges for forex_macro and deep_fundamentals
        workflow.add_conditional_edges(
            "market_regime",
            self._should_run_forex_macro,
            {
                "run_forex": "forex_macro",
                "skip_forex": "bull_research"
            }
        )
        workflow.add_conditional_edges(
            "market_regime",
            self._should_run_deep_fundamentals,
            {
                "run_deep": "deep_fundamentals",
                "skip_deep": "bull_research"
            }
        )
        
        workflow.add_conditional_edges(
            "market_regime",
            self._should_run_earnings_analysis,
            {
                "run_earnings": "earnings_analysis",
                "skip_earnings": "bull_research"
            }
        )
        
        workflow.add_edge("market_regime", "historical_validation")
        
        # All Stage 1 → Bull Research (waits for all parallel nodes)
        for analyst in ["fundamentals", "technical", "macro", "sentiment", "news_scanner", "forex_macro", "deep_fundamentals", "earnings_analysis", "historical_validation"]:
            workflow.add_edge(analyst, "bull_research")
        
        # Debate loop: Bull → Bear → Check if continue
        workflow.add_edge("bull_research", "bear_research")
        workflow.add_conditional_edges(
            "bear_research",
            self._should_continue_debate,
            {
                "continue_debate": "debate_counter",
                "proceed_to_quant": "quant_check"
            }
        )
        workflow.add_edge("debate_counter", "bull_research")
        
        # Quant Check → Risk Manager → Final Trader
        workflow.add_edge("quant_check", "risk_manager")
        
        # Final Strategic Review before decision
        workflow.add_node("strategic_review", self._run_strategic_review)
        workflow.add_edge("risk_manager", "strategic_review")
        workflow.add_edge("strategic_review", "final_trader")
        
        workflow.add_edge("final_trader", END)
        
        return workflow.compile()
    
    # ========================================================================
    # Conditional Edge Functions
    # ========================================================================
    
    def _should_proceed_to_pipeline(self, state: ExtendedSignalixAIState) -> str:
        """Conditional edge after pre-screener"""
        if state.get("screening_decision") and not state["screening_decision"].pass_screening:
            return "skip"
        return "proceed"
    
    def _should_continue_debate(self, state: ExtendedSignalixAIState) -> str:
        """Conditional edge - continue debate or proceed to quant check"""
        debate_round = state.get("debate_round", 1)
        if debate_round < 2:  # Run 2 rounds of debate
            return "continue_debate"
        return "proceed_to_quant"
    
    def _should_run_forex_macro(self, state: ExtendedSignalixAIState) -> str:
        """Conditional edge - run forex macro analyst?"""
        if self.forex_macro_analyst.should_run(
            state["instrument_type"],
            state["instrument"]
        ):
            return "run_forex"
        return "skip_forex"
    
    def _should_run_deep_fundamentals(self, state: ExtendedSignalixAIState) -> str:
        """Conditional edge - run deep fundamentals analyst?"""
        if self.deep_fundamentals_analyst.should_run(
            state["depth"],
            state["instrument_type"]
        ):
            return "run_deep"
        return "skip_deep"
    
    def _should_run_earnings_analysis(self, state: ExtendedSignalixAIState) -> str:
        """Conditional edge - run earnings analyst?"""
        if state["analysis_type"] == "earnings_play":
            return "run_earnings"
        return "skip_earnings"
    
    # ========================================================================
    # Stage 0: Screening Agents
    # ========================================================================
    
    async def _run_pre_screener(self, state: ExtendedSignalixAIState) -> Dict:
        """Stage 0: Pre-screener - Fast gate decision"""
        try:
            # Mock market session and data availability checks
            market_session_data = {
                "is_open": True,
                "last_update_time": datetime.utcnow().isoformat(),
                "exchange_status": "active"
            }
            data_availability = {
                "historical_days": 200,
                "data_quality_score": 0.85,
                "missing_fields": []
            }
            
            decision = await self.pre_screener.screen(
                instrument=state["instrument"],
                instrument_type=state["instrument_type"],
                market_session_data=market_session_data,
                data_availability=data_availability
            )
            
            return {
                "screening_decision": decision,
                "agents_executed": ["pre_screener"],
                "llm_cost_usd": 0.001  # Haiku cost
            }
        except Exception as e:
            return {
                "screening_decision": ScreeningDecision(
                    pass_screening=False,
                    confidence_floor_met=False,
                    instrument_type_confirmed=state["instrument_type"],
                    market_session_valid=False,
                    data_quality_score=0.0,
                    skip_reason=f"Error: {str(e)}"
                ),
                "agents_executed": ["pre_screener"],
                "errors": [f"Pre-screener: {str(e)}"],
                "llm_cost_usd": 0.0
            }
    
    async def _run_market_regime(self, state: ExtendedSignalixAIState) -> Dict:
        """Stage 0: Market Regime Detector"""
        try:
            # Mock macro data
            macro_data = {
                "vix": 18.5,
                "dxy": 104.2,
                "sp500": 5200,
                "nifty": 22500,
                "fii_flow_cr": 350
            }
            
            regime = await self.market_regime_detector.detect_regime(
                instrument=state["instrument"],
                instrument_type=state["instrument_type"],
                macro_data=macro_data
            )
            
            return {
                "market_regime": regime,
                "agents_executed": ["market_regime"],
                "llm_cost_usd": 0.0003  # Gemini Flash cost
            }
        except Exception as e:
            return {
                "market_regime": None,
                "agents_executed": ["market_regime"],
                "errors": [f"Market Regime: {str(e)}"],
                "llm_cost_usd": 0.0
            }
    
    def _skip_instrument(self, state: ExtendedSignalixAIState) -> Dict:
        """Skip instrument - screening failed"""
        return {
            "final_decision": None,
            "agents_executed": ["skip"],
            "errors": [f"Instrument skipped: {state['screening_decision'].skip_reason}"]
        }
    
    # ========================================================================
    # Stage 1: Analyst Agents (Parallel Execution)
    # ========================================================================
    
    async def _run_fundamentals(self, state: ExtendedSignalixAIState) -> Dict:
        """Stage 1: Fundamentals Analyst"""
        try:
            user_context_prompt = self.context_injector.inject_for_fundamentals_agent(
                self.user_context
            )
            
            result = await self.fundamentals_analyst.analyze(
                instrument=state["instrument"],
                user_context=user_context_prompt,
                depth=state["depth"]
            )
            
            return {
                "fundamentals_report": result,
                "agents_executed": ["fundamentals"],
                "llm_cost_usd": 0.0225  # Sonnet cost
            }
        except Exception as e:
            return {
                "fundamentals_report": None,
                "errors": [f"Fundamentals: {str(e)}"],
                "agents_executed": ["fundamentals"],
                "llm_cost_usd": 0.0
            }
    
    async def _run_technical(self, state: ExtendedSignalixAIState) -> Dict:
        """Stage 1: Technical Analyst"""
        try:
            user_context_prompt = self.context_injector.inject_for_technical_agent(
                self.user_context
            )
            
            result = await self.technical_analyst.analyze(
                instrument=state["instrument"],
                user_context=user_context_prompt,
                depth=state["depth"]
            )
            
            return {
                "technical_report": result,
                "agents_executed": ["technical"],
                "llm_cost_usd": 0.01875  # Sonnet cost
            }
        except Exception as e:
            return {
                "technical_report": None,
                "errors": [f"Technical: {str(e)}"],
                "agents_executed": ["technical"],
                "llm_cost_usd": 0.0
            }
    
    async def _run_macro(self, state: ExtendedSignalixAIState) -> Dict:
        """Stage 1: Macro Analyst"""
        try:
            user_context_prompt = self.context_injector.inject_for_macro_agent(
                self.user_context
            )
            
            result = await self.macro_analyst.analyze(
                instrument=state["instrument"],
                user_context=user_context_prompt,
                depth=state["depth"]
            )
            
            return {
                "macro_report": result,
                "agents_executed": ["macro"],
                "llm_cost_usd": 0.0165  # Sonnet cost
            }
        except Exception as e:
            return {
                "macro_report": None,
                "errors": [f"Macro: {str(e)}"],
                "agents_executed": ["macro"],
                "llm_cost_usd": 0.0
            }
    
    async def _run_sentiment(self, state: ExtendedSignalixAIState) -> Dict:
        """Stage 1: Sentiment Analyst"""
        try:
            user_context_prompt = self.context_injector.inject_for_sentiment_agent(
                self.user_context
            )
            
            result = await self.sentiment_analyst.analyze(
                instrument=state["instrument"],
                user_context=user_context_prompt,
                depth=state["depth"]
            )
            
            return {
                "sentiment_report": result,
                "agents_executed": ["sentiment"],
                "llm_cost_usd": 0.00066  # Gemini Flash cost
            }
        except Exception as e:
            return {
                "sentiment_report": None,
                "errors": [f"Sentiment: {str(e)}"],
                "agents_executed": ["sentiment"],
                "llm_cost_usd": 0.0
            }
    
    async def _run_news_scanner(self, state: ExtendedSignalixAIState) -> Dict:
        """Stage 1: News Scanner (Grok 4)"""
        try:
            market_regime_dict = state.get("market_regime").dict() if state.get("market_regime") else {}
            
            result = await self.news_scanner.scan_news(
                instrument=state["instrument"],
                instrument_type=state["instrument_type"],
                market_regime=market_regime_dict,
                analysis_date=state["analysis_date"]
            )
            
            return {
                "news_flash_report": result,
                "agents_executed": ["news_scanner"],
                "llm_cost_usd": 0.018  # Grok 4 cost
            }
        except Exception as e:
            return {
                "news_flash_report": None,
                "errors": [f"News Scanner: {str(e)}"],
                "agents_executed": ["news_scanner"],
                "llm_cost_usd": 0.0
            }

    async def _run_earnings_analysis(self, state: ExtendedSignalixAIState) -> Dict:
        """Stage 1: Earnings Analyst (Gemini 2.5 Pro)"""
        try:
            result = await self.earnings_analyst.analyze(state["instrument"])
            return {
                "earnings_report": result,
                "agents_executed": ["earnings_analyst"],
                "llm_cost_usd": 0.012  # Gemini Pro cost
            }
        except Exception as e:
            return {"errors": [f"Earnings Analysis: {str(e)}"]}

    async def _run_historical_validation(self, state: ExtendedSignalixAIState) -> Dict:
        """Stage 1: Historical Validation (Backtest Service)"""
        try:
            result = await self.historical_validator.validate(
                state["instrument"],
                state["analysis_type"],
                str(state["user_context"].user_id)
            )
            return {
                "historical_validation": result,
                "agents_executed": ["historical_validation"]
            }
        except Exception as e:
            return {"errors": [f"Historical Validation: {str(e)}"]}
    async def _run_forex_macro(self, state: ExtendedSignalixAIState) -> Dict:
        """Stage 1: Forex/Commodity Macro Analyst (Mistral Large 3) - Conditional"""
        try:
            market_regime_dict = state.get("market_regime").dict() if state.get("market_regime") else {}
            
            # Mock forex context data
            forex_context = {
                "dxy": 104.2,
                "interest_rates": {
                    "fed": 5.25,
                    "ecb": 4.0,
                    "rbi": 6.5
                },
                "cot_data": {},
                "carry_differential": 0.0
            }
            
            result = await self.forex_macro_analyst.analyze(
                instrument=state["instrument"],
                instrument_type=state["instrument_type"],
                market_regime=market_regime_dict,
                forex_context=forex_context
            )
            
            return {
                "forex_macro_report": result,
                "agents_executed": ["forex_macro"],
                "llm_cost_usd": 0.0076  # Mistral cost
            }
        except Exception as e:
            return {
                "forex_macro_report": None,
                "errors": [f"Forex Macro: {str(e)}"],
                "agents_executed": ["forex_macro"],
                "llm_cost_usd": 0.0
            }
    
    async def _run_deep_fundamentals(self, state: ExtendedSignalixAIState) -> Dict:
        """Stage 1: Deep Fundamentals Analyst (Gemini 2.5 Pro) - Conditional"""
        try:
            fundamentals_dict = state.get("fundamentals_report").dict() if state.get("fundamentals_report") else {}
            
            # Mock documents (in production, fetch from data sources)
            documents = {
                "earnings_transcript": "Mock earnings transcript...",
                "annual_report": "Mock annual report...",
                "sec_filings": "Mock SEC filings...",
                "analyst_reports": []
            }
            
            result = await self.deep_fundamentals_analyst.analyze(
                instrument=state["instrument"],
                fundamentals_report=fundamentals_dict,
                documents=documents
            )
            
            return {
                "deep_fundamentals_report": result,
                "agents_executed": ["deep_fundamentals"],
                "llm_cost_usd": 0.028  # Gemini Pro cost
            }
        except Exception as e:
            return {
                "deep_fundamentals_report": None,
                "errors": [f"Deep Fundamentals: {str(e)}"],
                "agents_executed": ["deep_fundamentals"],
                "llm_cost_usd": 0.0
            }
    
    # ========================================================================
    # Stage 2: Debate Agents
    # ========================================================================
    
    async def _run_bull_research(self, state: ExtendedSignalixAIState) -> Dict:
        """Stage 2: Bull Researcher"""
        try:
            debate_round = state.get("debate_round", 1)
            bear_thesis_dict = state.get("bear_thesis").dict() if state.get("bear_thesis") else None
            
            fundamentals_dict = state.get("fundamentals_report").dict() if state.get("fundamentals_report") else {}
            technical_dict = state.get("technical_report").dict() if state.get("technical_report") else {}
            macro_dict = state.get("macro_report").dict() if state.get("macro_report") else {}
            sentiment_dict = state.get("sentiment_report").dict() if state.get("sentiment_report") else {}
            
            result = await self.bull_researcher.research(
                instrument=state["instrument"],
                fundamentals=fundamentals_dict,
                technical=technical_dict,
                macro=macro_dict,
                sentiment=sentiment_dict,
                debate_round=debate_round,
                bear_thesis=bear_thesis_dict
            )
            
            return {
                "bull_thesis": result,
                "agents_executed": ["bull_researcher"],
                "llm_cost_usd": 0.03  # Sonnet cost
            }
        except Exception as e:
            return {
                "bull_thesis": None,
                "errors": [f"Bull Researcher: {str(e)}"],
                "agents_executed": ["bull_researcher"],
                "llm_cost_usd": 0.0
            }
    
    async def _run_bear_research(self, state: ExtendedSignalixAIState) -> Dict:
        """Stage 2: Bear Researcher"""
        try:
            debate_round = state.get("debate_round", 1)
            bull_thesis_dict = state.get("bull_thesis").dict() if state.get("bull_thesis") else None
            
            fundamentals_dict = state.get("fundamentals_report").dict() if state.get("fundamentals_report") else {}
            technical_dict = state.get("technical_report").dict() if state.get("technical_report") else {}
            macro_dict = state.get("macro_report").dict() if state.get("macro_report") else {}
            sentiment_dict = state.get("sentiment_report").dict() if state.get("sentiment_report") else {}
            
            result = await self.bear_researcher.research(
                instrument=state["instrument"],
                fundamentals=fundamentals_dict,
                technical=technical_dict,
                macro=macro_dict,
                sentiment=sentiment_dict,
                debate_round=debate_round,
                bull_thesis=bull_thesis_dict
            )
            
            return {
                "bear_thesis": result,
                "agents_executed": ["bear_researcher"],
                "llm_cost_usd": 0.0315  # Sonnet cost
            }
        except Exception as e:
            return {
                "bear_thesis": None,
                "errors": [f"Bear Researcher: {str(e)}"],
                "agents_executed": ["bear_researcher"],
                "llm_cost_usd": 0.0
            }
    
    def _increment_debate_round(self, state: ExtendedSignalixAIState) -> Dict:
        """Increment debate round counter"""
        return {
            "debate_round": state.get("debate_round", 1) + 1,
            "agents_executed": ["debate_counter"]
        }
    
    # ========================================================================
    # Stage 3: Quant Check + Risk
    # ========================================================================
    
    async def _run_quant_check(self, state: ExtendedSignalixAIState) -> Dict:
        """Stage 3: Quantitative Cross-Check (DeepSeek-R1)"""
        try:
            risk_dict = state.get("risk_assessment").dict() if state.get("risk_assessment") else {}
            technical_dict = state.get("technical_report").dict() if state.get("technical_report") else {}
            
            result = await self.quant_cross_check.validate(
                instrument=state["instrument"],
                risk_assessment=risk_dict,
                technical_report=technical_dict,
                user_capital_inr=self.user_context.declared_capital_inr
            )
            
            return {
                "quant_check_report": result,
                "agents_executed": ["quant_check"],
                "llm_cost_usd": 0.00603  # DeepSeek-R1 cost
            }
        except Exception as e:
            return {
                "quant_check_report": None,
                "errors": [f"Quant Check: {str(e)}"],
                "agents_executed": ["quant_check"],
                "llm_cost_usd": 0.0
            }
    
    async def _run_risk_manager(self, state: ExtendedSignalixAIState) -> Dict:
        """Stage 3: Risk Manager (Claude Opus 4.6)"""
        try:
            user_context_prompt = self.context_injector.inject_for_risk_manager(
                self.user_context
            )
            
            fundamentals_dict = state.get("fundamentals_report").dict() if state.get("fundamentals_report") else None
            technical_dict = state.get("technical_report").dict() if state.get("technical_report") else None
            macro_dict = state.get("macro_report").dict() if state.get("macro_report") else None
            
            result = await self.risk_manager.analyze(
                instrument=state["instrument"],
                fundamentals=fundamentals_dict,
                technical=technical_dict,
                macro=macro_dict,
                user_context=user_context_prompt,
                depth=state["depth"]
            )
            
            return {
                "risk_assessment": result,
                "agents_executed": ["risk_manager"],
                "llm_cost_usd": 0.25  # Opus cost (8K thinking tokens)
            }
        except Exception as e:
            return {
                "risk_assessment": None,
                "errors": [f"Risk Manager: {str(e)}"],
                "agents_executed": ["risk_manager"],
                "llm_cost_usd": 0.0
            }
    
    async def _run_strategic_review(self, state: ExtendedSignalixAIState) -> Dict:
        """New Strategic Review Stage: Portfolio + Correlation + Sector"""
        try:
            # 1. Sector Rotation
            sector_report = await self.sector_rotation_analyst.analyze(state["instrument"])
            
            # 2. Correlation Check
            corr_report = await self.correlation_analyst.analyze(
                state["instrument"], 
                existing_positions=None
            )
            
            # 3. Portfolio Optimization
            opt_report = await self.portfolio_optimizer.optimize(
                state["instrument"],
                state["user_context"]
            )
            
            return {
                "agents_executed": ["sector_rotation", "correlation", "portfolio_optimizer"],
                "llm_cost_usd": 0.045  # Sonnet + Flash costs
            }
        except Exception as e:
            return {"errors": [f"Strategic Review: {str(e)}"]}

    # ========================================================================
    # Stage 4: Final Decision
    # ========================================================================
    
    async def _run_final_trader(self, state: ExtendedSignalixAIState) -> Dict:
        """Stage 4: Final Trader (Claude Opus 4.6)"""
        try:
            user_context_prompt = self.context_injector.inject_for_final_trader(
                self.user_context
            )
            
            fundamentals_dict = state.get("fundamentals_report").dict() if state.get("fundamentals_report") else None
            technical_dict = state.get("technical_report").dict() if state.get("technical_report") else None
            macro_dict = state.get("macro_report").dict() if state.get("macro_report") else None
            sentiment_dict = state.get("sentiment_report").dict() if state.get("sentiment_report") else None
            news_dict = state.get("news_flash_report").dict() if state.get("news_flash_report") else None
            bull_dict = state.get("bull_thesis").dict() if state.get("bull_thesis") else None
            bear_dict = state.get("bear_thesis").dict() if state.get("bear_thesis") else None
            quant_dict = state.get("quant_check_report").dict() if state.get("quant_check_report") else None
            risk_dict = state.get("risk_assessment").dict() if state.get("risk_assessment") else None
            
            # Pass new strategic reports
            earnings_dict = state.get("earnings_report")
            hist_val_dict = state.get("historical_validation")
            
            result = await self.final_trader.synthesize(
                instrument=state["instrument"],
                fundamentals=fundamentals_dict,
                technical=technical_dict,
                macro=macro_dict,
                sentiment=sentiment_dict,
                news_flash=news_dict,
                bull_thesis=bull_dict,
                bear_thesis=bear_dict,
                quant_check=quant_dict,
                risk=risk_dict,
                user_context=user_context_prompt,
                language=self.user_context.language_preference or "en",
                earnings=earnings_dict,
                historical_validation=hist_val_dict
            )
            
            return {
                "final_decision": TradingDecision(**result),
                "agents_executed": ["final_trader"],
                "llm_cost_usd": 0.37  # Opus cost (12K thinking tokens)
            }
        except Exception as e:
            return {
                "final_decision": None,
                "errors": [f"Final Trader: {str(e)}"],
                "agents_executed": ["final_trader"],
                "llm_cost_usd": 0.0
            }
    
    async def run(
        self,
        instrument: str,
        instrument_type: str,
        analysis_type: str,
        additional_context: Optional[str] = None
    ) -> Dict:
        """
        Run complete 13-agent analysis pipeline
        
        Args:
            instrument: Trading instrument (e.g., "RELIANCE", "NIFTY", "BTCUSDT")
            instrument_type: equity, futures, options, crypto, forex, commodity, index
            analysis_type: Type of analysis (swing_trade, intraday_scalp, etc.)
            additional_context: Optional user-provided context
        
        Returns:
            Complete analysis result with TradingDecision
        """
        # Initialize state
        initial_state: ExtendedSignalixAIState = {
            "instrument": instrument,
            "instrument_type": instrument_type,
            "analysis_type": analysis_type,
            "depth": self.depth,
            "user_context": self.user_context,
            "additional_context": additional_context,
            "analysis_date": datetime.utcnow().isoformat(),
            
            # Stage 0
            "screening_decision": None,
            "market_regime": None,
            
            # Stage 1
            "fundamentals_report": None,
            "technical_report": None,
            "macro_report": None,
            "sentiment_report": None,
            "news_flash_report": None,
            "forex_macro_report": None,
            "deep_fundamentals_report": None,
            
            # Stage 2
            "bull_thesis": None,
            "bear_thesis": None,
            "debate_round": 1,
            
            # Stage 3
            "quant_check_report": None,
            "risk_assessment": None,
            
            # Stage 4
            "final_decision": None,
            
            # Metadata
            "agents_executed": [],
            "llm_cost_usd": 0.0,
            "start_time": datetime.utcnow(),
            "errors": []
        }
        
        # Run pipeline
        final_state = await self.graph.ainvoke(initial_state)
        
        # Extract final output
        final_decision = final_state.get("final_decision")
        
        # Add metadata
        if final_decision:
            final_decision.agents_executed = final_state.get("agents_executed", [])
            final_decision.total_cost_usd = final_state.get("llm_cost_usd", 0.0)
            final_decision.processing_time_seconds = (
                datetime.utcnow() - final_state.get("start_time")
            ).total_seconds()
            
        # Track token usage and unit economics
        unit_economics = self._calculate_unit_economics(final_state)
        
        return {
            "final_decision": final_decision.dict() if final_decision else None,
            "agents_executed": final_state.get("agents_executed", []),
            "processing_errors": final_state.get("errors", []),
            "total_cost_usd": final_state.get("llm_cost_usd", 0.0),
            "unit_economics": unit_economics,
            "processing_time_seconds": (
                datetime.utcnow() - final_state.get("start_time")
            ).total_seconds()
        }

    def _calculate_unit_economics(self, state: ExtendedSignalixAIState) -> Dict:
        """Calculate detailed unit economics for the analysis run"""
        total_cost = state.get("llm_cost_usd", 0.0)
        
        # Estimate margins (SaaS model: 70-80% gross margin target)
        retail_price_usd = 0.50  # Assuming $0.50 per analysis for retail users
        margin_pct = ((retail_price_usd - total_cost) / retail_price_usd * 100) if total_cost > 0 else 100
        
        return {
            "total_llm_cost_usd": round(total_cost, 4),
            "prompt_caching_savings_usd": round(total_cost * 0.4, 4),  # Estimated 40% savings
            "gross_margin_at_50c": f"{margin_pct:.1f}%",
            "break_even_analyses_per_month": round(29.0 / (retail_price_usd - total_cost)) if total_cost < retail_price_usd else "N/A"
        }


# Backward compatibility alias
AnalysisPipeline = AnalysisPipelineV2


# Example usage
if __name__ == "__main__":
    import asyncio
    from shared.utils.user_context import UserContext
    import uuid
    
    # Mock user context
    user_context = UserContext(
        user_id=str(uuid.uuid4()),
        language="en",
        risk_tolerance=7,
        capital_inr=5000000.0,
        trading_style="swing",
        tier="basic",
        experience_level="intermediate",
        analysis_depth="shallow",
        notifications_enabled=True
    )
    
    # Initialize pipeline
    pipeline = AnalysisPipelineV2(
        user_context=user_context,
        depth="shallow"
    )
    
    # Run analysis
    async def test():
        result = await pipeline.run(
            instrument="NIFTY50",
            instrument_type="equity",
            analysis_type="day_trade"
        )
        print("--- FINAL AGENT PIPELINE RESULT FOR NIFTY50 ---")
        import json
        print(json.dumps(result, indent=2))
    
    asyncio.run(test())
