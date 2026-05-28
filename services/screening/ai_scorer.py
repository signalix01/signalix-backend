"""
Gemini 2.5 Flash AI Scoring Layer for AI Screening Engine

This module implements the third layer of the screening pipeline:
AI-powered scoring using Gemini 2.5 Flash to analyze top candidates
and provide BUY/SELL/HOLD signals with confidence scores.

Requirements: 9.2, 9.8
"""
import logging
import json
import os
from typing import List, Optional, Dict, Any
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

from services.screening.models import ScreeningCriteria, ScreenedInstrument

logger = logging.getLogger(__name__)


class AIScorer:
    """
    Gemini 2.5 Flash AI scoring layer for screening engine
    
    Sends top 50 instruments to Gemini 2.5 Flash in a single batch prompt
    for cost efficiency. Parses JSON response and updates instruments with
    AI signals and confidence scores.
    
    Cost: ~$0.002 per full screening run (50 instruments)
    Gemini 2.5 Flash pricing: $0.15/$0.60 per MTok (input/output)
    
    Performance target: < 30 seconds for 50 instruments
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize AI scorer with Gemini API
        
        Args:
            api_key: Google API key (defaults to GOOGLE_API_KEY env var)
        """
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        
        if not self.api_key:
            logger.warning("GOOGLE_API_KEY not set - AI scoring will be disabled")
            self.enabled = False
        else:
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel(
                "gemini-2.0-flash-exp",
                generation_config={
                    "temperature": 0.3,  # Lower temperature for more consistent scoring
                    "top_p": 0.95,
                    "top_k": 40,
                    "max_output_tokens": 8192,
                },
                safety_settings={
                    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
                }
            )
            self.enabled = True
            logger.info("Gemini 2.5 Flash AI scorer initialized")
    
    async def score(
        self,
        instruments: List[ScreenedInstrument],
        criteria: ScreeningCriteria
    ) -> List[ScreenedInstrument]:
        """
        Score instruments using Gemini 2.5 Flash AI
        
        Builds a single batch prompt for all instruments (max 50) and sends
        to Gemini API. Parses JSON response and updates each instrument with
        AI signal and confidence.
        
        If API call fails, returns instruments unchanged (graceful degradation).
        
        Args:
            instruments: List of instruments to score (max 50)
            criteria: Screening criteria for context
            
        Returns:
            List of ScreenedInstrument objects with AI scores populated
        """
        if not self.enabled:
            logger.warning("AI scoring disabled - returning instruments without AI scores")
            return instruments
        
        if not instruments:
            logger.warning("Empty instruments list provided to AI scorer")
            return instruments
        
        # Limit to top 50 for cost control
        instruments_to_score = instruments[:50]
        
        logger.info(
            f"AI scoring started",
            extra={
                "criteria_name": criteria.name,
                "instruments_count": len(instruments_to_score)
            }
        )
        
        try:
            # Build batch prompt
            prompt = self._build_batch_prompt(instruments_to_score, criteria)
            
            # Call Gemini API
            response = self.model.generate_content(prompt)
            
            # Track token usage and cost
            usage_metadata = response.usage_metadata
            input_tokens = usage_metadata.prompt_token_count
            output_tokens = usage_metadata.candidates_token_count
            cost_usd = self._calculate_cost(input_tokens, output_tokens)
            
            logger.info(
                f"Gemini API call completed",
                extra={
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cost_usd": cost_usd
                }
            )
            
            # Parse JSON response
            ai_scores = self._parse_response(response.text)
            
            # Update instruments with AI scores
            scored_instruments = self._merge_ai_scores(instruments_to_score, ai_scores)
            
            logger.info(
                f"AI scoring completed",
                extra={
                    "criteria_name": criteria.name,
                    "instruments_scored": len(scored_instruments),
                    "cost_usd": cost_usd
                }
            )
            
            return scored_instruments
            
        except Exception as e:
            logger.error(
                f"AI scoring failed - returning instruments without AI scores",
                extra={"error": str(e)}
            )
            # Graceful degradation: return instruments without AI scores
            return instruments
    
    def _build_batch_prompt(
        self,
        instruments: List[ScreenedInstrument],
        criteria: ScreeningCriteria
    ) -> str:
        """
        Build a single batch prompt for all instruments
        
        Args:
            instruments: List of instruments to score
            criteria: Screening criteria for context
            
        Returns:
            Formatted prompt string
        """
        # Extract instrument data for prompt
        instruments_data = []
        for inst in instruments:
            instruments_data.append({
                "symbol": inst.symbol,
                "asset_class": inst.asset_class,
                "current_price": inst.current_price,
                "score": inst.score,
                "technical_score": inst.technical_score,
                "momentum_score": inst.momentum_score,
                "volume_score": inst.volume_score,
                "quick_stats": inst.quick_stats,
                "reasons": inst.reasons
            })
        
        prompt = f"""You are the AI Screener at Signalix, an institutional-grade trading platform. Your role is to evaluate financial instruments and provide actionable trading signals.

**Screening Criteria Context:**
- Name: {criteria.name}
- Description: {criteria.description}
- Asset Classes: {', '.join(criteria.asset_class)}

**Your Task:**
Evaluate the following {len(instruments)} instruments that have already passed technical screening. For each instrument, provide:
1. **signal**: One of "BUY", "SELL", or "HOLD"
2. **confidence**: A score from 0-100 indicating your confidence in the signal
3. **reason**: A concise 1-2 sentence explanation of your signal

**Evaluation Guidelines:**
- Consider the technical indicators (RSI, EMA position, ADX, volume ratio)
- Look for confluence of multiple bullish/bearish signals
- Higher confidence (80-100) requires strong confluence across multiple indicators
- Medium confidence (50-79) for mixed signals or single strong indicator
- Lower confidence (0-49) for weak or conflicting signals
- BUY signals: Look for oversold conditions with reversal signs, strong uptrends, high volume
- SELL signals: Look for overbought conditions, downtrends, distribution patterns
- HOLD signals: Neutral conditions, ranging markets, conflicting indicators

**Instruments Data:**
{json.dumps(instruments_data, indent=2)}

**Output Format:**
Return ONLY a valid JSON array with no additional text. Each object must have exactly these fields:
[
  {{
    "symbol": "SYMBOL1",
    "signal": "BUY",
    "confidence": 85,
    "reason": "Strong oversold reversal signal with high volume confirmation and price above 200 EMA."
  }},
  {{
    "symbol": "SYMBOL2",
    "signal": "HOLD",
    "confidence": 55,
    "reason": "Mixed signals - RSI neutral but volume declining, waiting for clearer direction."
  }}
]

Provide analysis for all {len(instruments)} instruments in the same order as provided above."""
        
        return prompt
    
    def _parse_response(self, response_text: str) -> List[Dict[str, Any]]:
        """
        Parse JSON response from Gemini API
        
        Handles various response formats:
        - Clean JSON array
        - JSON wrapped in markdown code blocks
        - JSON with extra text before/after
        
        Args:
            response_text: Raw response text from Gemini
            
        Returns:
            List of dicts with symbol, signal, confidence, reason
            
        Raises:
            ValueError: If response cannot be parsed as valid JSON
        """
        try:
            # Try direct JSON parse first
            return json.loads(response_text)
        except json.JSONDecodeError:
            # Try extracting JSON from markdown code blocks
            if "```json" in response_text:
                start = response_text.find("```json") + 7
                end = response_text.find("```", start)
                json_str = response_text[start:end].strip()
                return json.loads(json_str)
            elif "```" in response_text:
                start = response_text.find("```") + 3
                end = response_text.find("```", start)
                json_str = response_text[start:end].strip()
                return json.loads(json_str)
            else:
                # Try to find JSON array in text
                start = response_text.find("[")
                end = response_text.rfind("]") + 1
                if start != -1 and end > start:
                    json_str = response_text[start:end]
                    return json.loads(json_str)
                else:
                    raise ValueError(f"Could not extract JSON from response: {response_text[:200]}")
    
    def _merge_ai_scores(
        self,
        instruments: List[ScreenedInstrument],
        ai_scores: List[Dict[str, Any]]
    ) -> List[ScreenedInstrument]:
        """
        Merge AI scores back into instrument objects
        
        Args:
            instruments: Original instruments list
            ai_scores: Parsed AI scores from Gemini
            
        Returns:
            Updated instruments list with AI scores
        """
        # Create lookup dict by symbol
        ai_scores_dict = {score["symbol"]: score for score in ai_scores}
        
        # Update instruments
        for inst in instruments:
            if inst.symbol in ai_scores_dict:
                ai_score = ai_scores_dict[inst.symbol]
                inst.ai_signal = ai_score.get("signal")
                inst.ai_confidence = float(ai_score.get("confidence", 0))
                
                # Append AI reason to existing reasons
                ai_reason = ai_score.get("reason")
                if ai_reason:
                    inst.reasons.append(f"AI: {ai_reason}")
            else:
                logger.warning(f"No AI score found for symbol: {inst.symbol}")
        
        return instruments
    
    def _calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """
        Calculate cost of Gemini API call
        
        Gemini 2.5 Flash pricing (as of 2025):
        - Input: $0.15 per 1M tokens
        - Output: $0.60 per 1M tokens
        
        Args:
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            
        Returns:
            Cost in USD
        """
        input_cost = (input_tokens / 1_000_000) * 0.15
        output_cost = (output_tokens / 1_000_000) * 0.60
        total_cost = input_cost + output_cost
        
        return round(total_cost, 6)
