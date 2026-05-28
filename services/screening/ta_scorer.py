"""
TA-Lib Scoring Layer for AI Screening Engine

This module implements the second layer of the screening pipeline:
TA-Lib based scoring that computes composite scores for instruments
that passed the SQL pre-filter.

Requirements: 9.2
"""
import logging
from typing import List, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import asyncio
import numpy as np

from services.screening.models import ScreeningCriteria, ScreenedInstrument

logger = logging.getLogger(__name__)


class TAScorer:
    """
    TA-Lib based scoring layer for screening engine
    
    Fetches latest 60 bars from TimescaleDB for each symbol and computes
    a composite score based on technical indicators:
    - RSI score (30%)
    - Volume score (30%)
    - Trend score (25%)
    - Momentum score (15%)
    
    Performance target: < 10 seconds for 200 instruments
    """
    
    def __init__(self, session: AsyncSession):
        """
        Initialize TA scorer
        
        Args:
            session: Async database session
        """
        self.session = session
    
    async def score(
        self,
        symbols: List[str],
        criteria: ScreeningCriteria
    ) -> List[ScreenedInstrument]:
        """
        Score symbols using TA-Lib indicators from TimescaleDB
        
        For each symbol:
        1. Fetch latest 60 bars from ohlcv_1d table
        2. Compute composite score using weighted formula
        3. Generate human-readable reasons
        4. Include quick_stats with raw indicator values
        
        Args:
            symbols: List of symbols that passed SQL pre-filter
            criteria: Screening criteria for context
            
        Returns:
            List of ScreenedInstrument objects with scores and reasons
            
        Raises:
            Exception: If database query fails
        """
        if not symbols:
            logger.warning("Empty symbols list provided to TA scorer")
            return []
        
        logger.info(
            f"TA scoring started",
            extra={
                "criteria_name": criteria.name,
                "symbols_count": len(symbols)
            }
        )
        
        # Fetch data for all symbols in parallel
        tasks = [self._fetch_and_score_symbol(symbol, criteria) for symbol in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out None results and exceptions
        scored_instruments = []
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Error scoring symbol: {result}")
                continue
            if result is not None:
                scored_instruments.append(result)
        
        # Sort by composite score descending
        scored_instruments.sort(key=lambda x: x.score, reverse=True)
        
        logger.info(
            f"TA scoring completed",
            extra={
                "criteria_name": criteria.name,
                "input_symbols": len(symbols),
                "output_instruments": len(scored_instruments)
            }
        )
        
        return scored_instruments
    
    async def _fetch_and_score_symbol(
        self,
        symbol: str,
        criteria: ScreeningCriteria
    ) -> Optional[ScreenedInstrument]:
        """
        Fetch latest 60 bars for a symbol and compute its score
        
        Args:
            symbol: Symbol to score
            criteria: Screening criteria
            
        Returns:
            ScreenedInstrument or None if data unavailable
        """
        try:
            # Fetch latest 60 bars with all indicators
            query = text("""
                SELECT 
                    symbol,
                    timestamp,
                    open,
                    high,
                    low,
                    close,
                    volume,
                    rsi_14,
                    ema_5,
                    ema_9,
                    ema_21,
                    ema_50,
                    ema_200,
                    adx_14,
                    atr_14,
                    volume_ma_20,
                    exchange,
                    asset_class
                FROM ohlcv_1d
                WHERE symbol = :symbol
                ORDER BY timestamp DESC
                LIMIT 60
            """)
            
            result = await self.session.execute(query, {"symbol": symbol})
            rows = result.fetchall()
            
            if not rows or len(rows) < 10:
                logger.warning(f"Insufficient data for {symbol}: {len(rows) if rows else 0} bars")
                return None
            
            # Extract latest bar data
            latest = rows[0]
            
            # Extract values with None handling
            close = float(latest.close) if latest.close is not None else None
            rsi_14 = float(latest.rsi_14) if latest.rsi_14 is not None else None
            adx_14 = float(latest.adx_14) if latest.adx_14 is not None else None
            atr_14 = float(latest.atr_14) if latest.atr_14 is not None else None
            volume = float(latest.volume) if latest.volume is not None else None
            volume_ma_20 = float(latest.volume_ma_20) if latest.volume_ma_20 is not None else None
            ema_5 = float(latest.ema_5) if latest.ema_5 is not None else None
            ema_9 = float(latest.ema_9) if latest.ema_9 is not None else None
            ema_21 = float(latest.ema_21) if latest.ema_21 is not None else None
            ema_50 = float(latest.ema_50) if latest.ema_50 is not None else None
            ema_200 = float(latest.ema_200) if latest.ema_200 is not None else None
            
            # Skip if critical data is missing
            if close is None or rsi_14 is None:
                logger.warning(f"Missing critical data for {symbol}")
                return None
            
            # Compute component scores
            rsi_score = self._compute_rsi_score(rsi_14, criteria)
            volume_score = self._compute_volume_score(volume, volume_ma_20)
            trend_score = self._compute_trend_score(close, ema_5, ema_9, ema_21, ema_50, ema_200)
            momentum_score = self._compute_momentum_score(adx_14)
            
            # Compute composite score with weights
            composite_score = (
                (rsi_score * 0.30) +
                (volume_score * 0.30) +
                (trend_score * 0.25) +
                (momentum_score * 0.15)
            )
            
            # Ensure score is in 0-100 range
            composite_score = max(0.0, min(100.0, composite_score))
            
            # Compute volume ratio
            volume_ratio = (volume / volume_ma_20) if (volume and volume_ma_20 and volume_ma_20 > 0) else 1.0
            
            # Determine EMA position
            ema_position = self._determine_ema_position(close, ema_5, ema_9, ema_21, ema_50, ema_200)
            
            # Generate reasons
            reasons = self._generate_reasons(
                symbol=symbol,
                rsi_14=rsi_14,
                volume_ratio=volume_ratio,
                ema_position=ema_position,
                adx_14=adx_14,
                criteria=criteria
            )
            
            # Build quick_stats
            quick_stats = {
                "rsi": round(rsi_14, 2) if rsi_14 is not None else None,
                "adx": round(adx_14, 2) if adx_14 is not None else None,
                "atr": round(atr_14, 2) if atr_14 is not None else None,
                "volume_ratio": round(volume_ratio, 2),
                "ema_position": ema_position,
                "close": round(close, 2),
                "ema_5": round(ema_5, 2) if ema_5 is not None else None,
                "ema_9": round(ema_9, 2) if ema_9 is not None else None,
                "ema_21": round(ema_21, 2) if ema_21 is not None else None,
                "ema_50": round(ema_50, 2) if ema_50 is not None else None,
                "ema_200": round(ema_200, 2) if ema_200 is not None else None
            }
            
            # Create ScreenedInstrument
            return ScreenedInstrument(
                symbol=symbol,
                asset_class=latest.asset_class or "equity",
                exchange=latest.exchange or "NSE",
                current_price=close,
                score=round(composite_score, 2),
                technical_score=round((rsi_score + trend_score + momentum_score) / 3, 2),
                fundamental_score=0.0,  # Not computed in TA layer
                momentum_score=round(momentum_score, 2),
                volume_score=round(volume_score, 2),
                ai_signal=None,  # Computed in AI layer
                ai_confidence=None,  # Computed in AI layer
                reasons=reasons,
                quick_stats=quick_stats
            )
            
        except Exception as e:
            logger.error(f"Error scoring symbol {symbol}: {e}")
            return None
    
    def _compute_rsi_score(self, rsi: float, criteria: ScreeningCriteria) -> float:
        """
        Compute RSI score (0-100) based on RSI position relative to criteria bounds
        
        Logic:
        - If criteria has RSI bounds, score based on how well RSI fits within bounds
        - If no bounds, score based on standard RSI interpretation:
          - RSI < 30: oversold (high score for reversal)
          - RSI > 70: overbought (high score for momentum)
          - RSI 40-60: neutral (medium score)
        
        Args:
            rsi: Current RSI value
            criteria: Screening criteria with optional RSI bounds
            
        Returns:
            Score from 0-100
        """
        if rsi is None:
            return 50.0  # Neutral score if RSI unavailable
        
        # If criteria specifies RSI bounds, score based on position within bounds
        if criteria.min_rsi is not None or criteria.max_rsi is not None:
            min_rsi = criteria.min_rsi if criteria.min_rsi is not None else 0
            max_rsi = criteria.max_rsi if criteria.max_rsi is not None else 100
            
            # RSI within bounds gets high score
            if min_rsi <= rsi <= max_rsi:
                # Score based on how centered RSI is within bounds
                mid_point = (min_rsi + max_rsi) / 2
                distance_from_mid = abs(rsi - mid_point)
                range_size = (max_rsi - min_rsi) / 2
                if range_size > 0:
                    score = 100 - (distance_from_mid / range_size * 30)  # Max penalty 30 points
                else:
                    score = 100
                return max(70.0, min(100.0, score))
            else:
                # RSI outside bounds gets lower score
                return 40.0
        
        # No criteria bounds - use standard RSI interpretation
        if rsi <= 30:
            # Oversold - good for reversal plays
            return 100 - rsi  # RSI 20 = score 80, RSI 30 = score 70
        elif rsi >= 70:
            # Overbought - good for momentum plays
            return rsi + 10  # RSI 70 = score 80, RSI 80 = score 90
        elif 40 <= rsi <= 60:
            # Neutral zone
            return 60.0
        else:
            # Transitional zones (30-40, 60-70)
            if rsi < 40:
                return 50 + (40 - rsi)  # RSI 35 = score 55
            else:
                return 50 + (rsi - 60)  # RSI 65 = score 55
    
    def _compute_volume_score(
        self,
        volume: Optional[float],
        volume_ma_20: Optional[float]
    ) -> float:
        """
        Compute volume score (0-100) based on volume ratio
        
        Logic:
        - volume_ratio = current_volume / 20-day average
        - Higher ratio = higher score (indicates strong interest)
        - Ratio > 2.0 = score 100
        - Ratio 1.0 = score 50
        - Ratio < 0.5 = score 0
        
        Args:
            volume: Current volume
            volume_ma_20: 20-day average volume
            
        Returns:
            Score from 0-100
        """
        if volume is None or volume_ma_20 is None or volume_ma_20 == 0:
            return 50.0  # Neutral score if volume data unavailable
        
        volume_ratio = volume / volume_ma_20
        
        # Normalize to 0-100 scale
        if volume_ratio >= 2.0:
            return 100.0
        elif volume_ratio >= 1.0:
            # Linear scale from 50 to 100 for ratio 1.0 to 2.0
            return 50 + ((volume_ratio - 1.0) * 50)
        else:
            # Linear scale from 0 to 50 for ratio 0 to 1.0
            return volume_ratio * 50
    
    def _compute_trend_score(
        self,
        close: float,
        ema_5: Optional[float],
        ema_9: Optional[float],
        ema_21: Optional[float],
        ema_50: Optional[float],
        ema_200: Optional[float]
    ) -> float:
        """
        Compute trend score (0-100) based on EMA stack alignment
        
        Logic:
        - Perfect bullish stack: close > ema_5 > ema_9 > ema_21 > ema_50 > ema_200
        - Score based on how many EMAs are in correct order
        - 5/5 alignment = score 100
        - 0/5 alignment = score 0
        
        Args:
            close: Current close price
            ema_5, ema_9, ema_21, ema_50, ema_200: EMA values
            
        Returns:
            Score from 0-100
        """
        emas = [close, ema_5, ema_9, ema_21, ema_50, ema_200]
        
        # Filter out None values
        valid_emas = [ema for ema in emas if ema is not None]
        
        if len(valid_emas) < 2:
            return 50.0  # Neutral score if insufficient data
        
        # Count how many consecutive pairs are in descending order (bullish)
        aligned_count = 0
        total_pairs = len(valid_emas) - 1
        
        for i in range(total_pairs):
            if valid_emas[i] > valid_emas[i + 1]:
                aligned_count += 1
        
        # Normalize to 0-100 scale
        if total_pairs > 0:
            score = (aligned_count / total_pairs) * 100
        else:
            score = 50.0
        
        return score
    
    def _compute_momentum_score(self, adx: Optional[float]) -> float:
        """
        Compute momentum score (0-100) based on ADX
        
        Logic:
        - ADX measures trend strength (not direction)
        - ADX > 50 = very strong trend = score 100
        - ADX 25 = moderate trend = score 50
        - ADX < 20 = weak/no trend = score 0
        
        Args:
            adx: Current ADX value
            
        Returns:
            Score from 0-100
        """
        if adx is None:
            return 50.0  # Neutral score if ADX unavailable
        
        # Normalize ADX to 0-100 scale
        # ADX typically ranges from 0-100, but values > 50 are rare
        score = (adx / 50) * 100
        
        return max(0.0, min(100.0, score))
    
    def _determine_ema_position(
        self,
        close: float,
        ema_5: Optional[float],
        ema_9: Optional[float],
        ema_21: Optional[float],
        ema_50: Optional[float],
        ema_200: Optional[float]
    ) -> str:
        """
        Determine price position relative to EMAs
        
        Returns:
            String describing EMA position:
            - "above_all": Price above all EMAs
            - "above_200": Price above 200 EMA
            - "above_50": Price above 50 EMA
            - "below_all": Price below all EMAs
            - "mixed": Price between EMAs
        """
        if ema_200 is not None and close > ema_200:
            if ema_50 is not None and close > ema_50:
                if ema_21 is not None and close > ema_21:
                    if ema_9 is not None and close > ema_9:
                        if ema_5 is not None and close > ema_5:
                            return "above_all"
                    return "above_short_term"
                return "above_medium_term"
            return "above_200"
        elif ema_50 is not None and close > ema_50:
            return "above_50"
        elif ema_200 is not None and close < ema_200:
            if ema_50 is not None and close < ema_50:
                if ema_21 is not None and close < ema_21:
                    return "below_all"
            return "below_long_term"
        else:
            return "mixed"
    
    def _generate_reasons(
        self,
        symbol: str,
        rsi_14: Optional[float],
        volume_ratio: float,
        ema_position: str,
        adx_14: Optional[float],
        criteria: ScreeningCriteria
    ) -> List[str]:
        """
        Generate human-readable reasons why this instrument passed screening
        
        Args:
            symbol: Instrument symbol
            rsi_14: RSI value
            volume_ratio: Volume ratio vs 20-day average
            ema_position: EMA position description
            adx_14: ADX value
            criteria: Screening criteria
            
        Returns:
            List of reason strings
        """
        reasons = []
        
        # RSI reasons
        if rsi_14 is not None:
            if criteria.min_rsi is not None and criteria.max_rsi is not None:
                reasons.append(f"RSI at {rsi_14:.1f} within target range {criteria.min_rsi}-{criteria.max_rsi}")
            elif rsi_14 <= 30:
                reasons.append(f"RSI oversold at {rsi_14:.1f} - potential reversal")
            elif rsi_14 >= 70:
                reasons.append(f"RSI overbought at {rsi_14:.1f} - strong momentum")
            elif 40 <= rsi_14 <= 60:
                reasons.append(f"RSI neutral at {rsi_14:.1f}")
        
        # Volume reasons
        if volume_ratio >= 2.0:
            reasons.append(f"Exceptional volume: {volume_ratio:.1f}x average")
        elif volume_ratio >= 1.5:
            reasons.append(f"High volume: {volume_ratio:.1f}x average")
        elif volume_ratio >= 1.2:
            reasons.append(f"Above-average volume: {volume_ratio:.1f}x")
        
        # Trend reasons
        if ema_position == "above_all":
            reasons.append("Price above all EMAs - strong uptrend")
        elif ema_position == "above_200":
            reasons.append("Price above 200 EMA - long-term uptrend")
        elif ema_position == "above_50":
            reasons.append("Price above 50 EMA - medium-term uptrend")
        elif ema_position == "below_all":
            reasons.append("Price below all EMAs - strong downtrend")
        
        # Momentum reasons
        if adx_14 is not None:
            if adx_14 >= 40:
                reasons.append(f"Very strong trend: ADX {adx_14:.1f}")
            elif adx_14 >= 25:
                reasons.append(f"Strong trend: ADX {adx_14:.1f}")
            elif adx_14 < 20:
                reasons.append(f"Weak trend: ADX {adx_14:.1f} - ranging market")
        
        # If no reasons generated, add a generic one
        if not reasons:
            reasons.append(f"Passed screening criteria: {criteria.name}")
        
        return reasons
