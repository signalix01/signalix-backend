"""
Multi-Strike OI Calculator

Analyzes open interest across multiple strikes to identify support/resistance levels,
institutional positioning, and potential market direction.

Requirements: Options Analytics - Multi-Strike OI tool
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class StrikeOI:
    """OI data for a single strike."""
    strike: float
    call_oi: int
    put_oi: int
    total_oi: int
    put_call_ratio: float
    max_pain_contribution: float


@dataclass
class OIAnalysis:
    """Result of multi-strike OI analysis."""
    symbol: str
    expiry_date: str
    spot_price: float
    strikes_data: List[StrikeOI]
    
    # Support and resistance levels
    support_levels: List[float]
    resistance_levels: List[float]
    max_pain_strike: float
    
    # Institutional positioning
    total_call_oi: int
    total_put_oi: int
    overall_pcr: float
    net_oi_bias: str  # "bullish", "bearish", "neutral"
    
    # Concentration analysis
    oi_concentration: Dict[str, float]  # Concentration at different strikes
    max_oi_strike: float
    max_oi_value: int
    
    # Market signals
    is_bullish_positioning: bool
    is_bearish_positioning: bool
    sentiment_score: float  # -1 (bearish) to 1 (bullish)
    
    calculated_at: str


class MultiStrikeOICalculator:
    """Calculator for multi-strike open interest analysis."""
    
    def __init__(self):
        pass
    
    def analyze_multi_strike_oi(
        self,
        symbol: str,
        spot_price: float,
        option_chain: List[Dict],
        expiry_date: str
    ) -> OIAnalysis:
        """
        Analyze OI across multiple strikes.
        
        Args:
            symbol: Underlying symbol
            spot_price: Current spot price
            option_chain: List of option data with strike, oi, etc.
            expiry_date: Option expiry date
            
        Returns:
            OIAnalysis with multi-strike OI analysis
        """
        try:
            # Group options by strike
            strikes_data = self._group_by_strike(option_chain)
            
            # Calculate OI for each strike
            strike_oi_list = []
            for strike, data in strikes_data.items():
                strike_oi = self._calculate_strike_oi(
                    strike=strike,
                    call_data=data.get('CALL'),
                    put_data=data.get('PUT')
                )
                if strike_oi:
                    strike_oi_list.append(strike_oi)
            
            # Sort by strike
            strike_oi_list.sort(key=lambda x: x.strike)
            
            # Calculate total OI
            total_call_oi = sum(s.call_oi for s in strike_oi_list)
            total_put_oi = sum(s.put_oi for s in strike_oi_list)
            overall_pcr = total_put_oi / total_call_oi if total_call_oi > 0 else 0
            
            # Determine net bias
            net_oi_bias = self._determine_net_bias(overall_pcr)
            
            # Find support and resistance levels
            support_levels = self._find_support_levels(strike_oi_list, spot_price)
            resistance_levels = self._find_resistance_levels(strike_oi_list, spot_price)
            
            # Find max pain strike
            max_pain_strike = self._calculate_max_pain(strike_oi_list)
            
            # Calculate OI concentration
            oi_concentration = self._calculate_oi_concentration(strike_oi_list)
            
            # Find max OI strike
            max_oi_strike, max_oi_value = self._find_max_oi_strike(strike_oi_list)
            
            # Determine positioning
            is_bullish = overall_pcr > 1.2
            is_bearish = overall_pcr < 0.8
            
            # Calculate sentiment score
            sentiment_score = self._calculate_sentiment_score(overall_pcr, strike_oi_list, spot_price)
            
            return OIAnalysis(
                symbol=symbol,
                expiry_date=expiry_date,
                spot_price=spot_price,
                strikes_data=strike_oi_list,
                support_levels=support_levels,
                resistance_levels=resistance_levels,
                max_pain_strike=max_pain_strike,
                total_call_oi=total_call_oi,
                total_put_oi=total_put_oi,
                overall_pcr=overall_pcr,
                net_oi_bias=net_oi_bias,
                oi_concentration=oi_concentration,
                max_oi_strike=max_oi_strike,
                max_oi_value=max_oi_value,
                is_bullish_positioning=is_bullish,
                is_bearish_positioning=is_bearish,
                sentiment_score=sentiment_score,
                calculated_at=datetime.utcnow().isoformat()
            )
            
        except Exception as e:
            logger.error(f"Multi-strike OI analysis failed for {symbol}: {e}")
            raise
    
    def _group_by_strike(
        self,
        option_chain: List[Dict]
    ) -> Dict[float, Dict]:
        """Group options by strike."""
        strikes = {}
        
        for opt in option_chain:
            strike = opt.get('strike')
            option_type = opt.get('option_type')
            
            if strike and option_type:
                if strike not in strikes:
                    strikes[strike] = {}
                strikes[strike][option_type] = opt
        
        return strikes
    
    def _calculate_strike_oi(
        self,
        strike: float,
        call_data: Optional[Dict],
        put_data: Optional[Dict]
    ) -> Optional[StrikeOI]:
        """Calculate OI for a single strike."""
        call_oi = call_data.get('open_interest', 0) if call_data else 0
        put_oi = put_data.get('open_interest', 0) if put_data else 0
        
        if call_oi == 0 and put_oi == 0:
            return None
        
        total_oi = call_oi + put_oi
        pcr = put_oi / call_oi if call_oi > 0 else 0
        
        # Max pain contribution (simplified)
        max_pain_contribution = total_oi / (strike * 100) if strike > 0 else 0
        
        return StrikeOI(
            strike=strike,
            call_oi=call_oi,
            put_oi=put_oi,
            total_oi=total_oi,
            put_call_ratio=pcr,
            max_pain_contribution=max_pain_contribution
        )
    
    def _determine_net_bias(
        self,
        overall_pcr: float
    ) -> str:
        """Determine net bias from PCR."""
        if overall_pcr > 1.2:
            return "bearish"  # More puts = bearish positioning
        elif overall_pcr < 0.8:
            return "bullish"  # More calls = bullish positioning
        else:
            return "neutral"
    
    def _find_support_levels(
        self,
        strike_oi_list: List[StrikeOI],
        spot_price: float
    ) -> List[float]:
        """
        Find support levels based on put OI below spot price.
        
        High put OI at lower strikes indicates support levels.
        """
        # Find strikes below spot price
        below_spot = [s for s in strike_oi_list if s.strike < spot_price]
        
        if not below_spot:
            return []
        
        # Sort by put OI descending
        below_spot.sort(key=lambda x: x.put_oi, reverse=True)
        
        # Top 3 support levels
        support_levels = [s.strike for s in below_spot[:3]]
        
        return support_levels
    
    def _find_resistance_levels(
        self,
        strike_oi_list: List[StrikeOI],
        spot_price: float
    ) -> List[float]:
        """
        Find resistance levels based on call OI above spot price.
        
        High call OI at higher strikes indicates resistance levels.
        """
        # Find strikes above spot price
        above_spot = [s for s in strike_oi_list if s.strike > spot_price]
        
        if not above_spot:
            return []
        
        # Sort by call OI descending
        above_spot.sort(key=lambda x: x.call_oi, reverse=True)
        
        # Top 3 resistance levels
        resistance_levels = [s.strike for s in above_spot[:3]]
        
        return resistance_levels
    
    def _calculate_max_pain(
        self,
        strike_oi_list: List[StrikeOI]
    ) -> float:
        """
        Calculate max pain strike.
        
        Max pain is the strike where option writers (market makers)
        lose the least money at expiry.
        """
        if not strike_oi_list:
            return 0.0
        
        # Simplified: strike with highest total OI
        max_pain = max(strike_oi_list, key=lambda x: x.total_oi)
        return max_pain.strike
    
    def _calculate_oi_concentration(
        self,
        strike_oi_list: List[StrikeOI]
    ) -> Dict[str, float]:
        """
        Calculate OI concentration across strikes.
        
        Measures how concentrated OI is at specific strikes.
        """
        if not strike_oi_list:
            return {}
        
        total_oi = sum(s.total_oi for s in strike_oi_list)
        
        if total_oi == 0:
            return {}
        
        # Calculate concentration at top 3, top 5, top 10 strikes
        sorted_by_oi = sorted(strike_oi_list, key=lambda x: x.total_oi, reverse=True)
        
        top_3_concentration = sum(s.total_oi for s in sorted_by_oi[:3]) / total_oi
        top_5_concentration = sum(s.total_oi for s in sorted_by_oi[:5]) / total_oi
        top_10_concentration = sum(s.total_oi for s in sorted_by_oi[:10]) / total_oi
        
        return {
            "top_3": top_3_concentration,
            "top_5": top_5_concentration,
            "top_10": top_10_concentration
        }
    
    def _find_max_oi_strike(
        self,
        strike_oi_list: List[StrikeOI]
    ) -> Tuple[float, int]:
        """Find strike with maximum OI."""
        if not strike_oi_list:
            return (0.0, 0)
        
        max_oi = max(strike_oi_list, key=lambda x: x.total_oi)
        return (max_oi.strike, max_oi.total_oi)
    
    def _calculate_sentiment_score(
        self,
        overall_pcr: float,
        strike_oi_list: List[StrikeOI],
        spot_price: float
    ) -> float:
        """
        Calculate sentiment score (-1 to 1).
        
        Positive = bullish, Negative = bearish
        """
        # Base sentiment from PCR
        # PCR < 1 = bullish (more calls), PCR > 1 = bearish (more puts)
        pcr_score = (1 - overall_pcr) / 2  # Normalize to -1 to 1 range
        
        # Adjust for OI distribution
        # High put OI below spot = bearish (support)
        # High call OI above spot = bearish (resistance)
        below_spot = [s for s in strike_oi_list if s.strike < spot_price]
        above_spot = [s for s in strike_oi_list if s.strike > spot_price]
        
        below_put_oi = sum(s.put_oi for s in below_spot)
        above_call_oi = sum(s.call_oi for s in above_spot)
        
        total_oi = sum(s.total_oi for s in strike_oi_list)
        
        if total_oi == 0:
            return 0.0
        
        # High below-spot put OI = bearish pressure
        below_pressure = (below_put_oi / total_oi) * 2  # Scale to -2 to 0
        
        # High above-spot call OI = bearish pressure
        above_pressure = (above_call_oi / total_oi) * 2  # Scale to -2 to 0
        
        # Combine scores
        sentiment = pcr_score - (below_pressure + above_pressure) / 4
        
        # Clamp to -1 to 1
        return max(min(sentiment, 1.0), -1.0)
    
    def compare_oi_changes(
        self,
        current_oi: OIAnalysis,
        previous_oi: OIAnalysis
    ) -> Dict:
        """
        Compare OI between two time periods.
        
        Identifies changes in positioning.
        """
        pcr_change = current_oi.overall_pcr - previous_oi.overall_pcr
        total_oi_change = (current_oi.total_call_oi + current_oi.total_put_oi) - \
                        (previous_oi.total_call_oi + previous_oi.total_put_oi)
        
        bias_changed = current_oi.net_oi_bias != previous_oi.net_oi_bias
        
        return {
            "pcr_change": pcr_change,
            "total_oi_change": total_oi_change,
            "bias_changed": bias_changed,
            "previous_bias": previous_oi.net_oi_bias,
            "current_bias": current_oi.net_oi_bias,
            "sentiment_change": current_oi.sentiment_score - previous_oi.sentiment_score,
            "is_significant_change": abs(pcr_change) > 0.2 or abs(total_oi_change) > 1000000
        }
