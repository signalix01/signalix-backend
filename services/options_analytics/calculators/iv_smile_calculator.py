"""
IV Smile Calculator

Calculates and analyzes the implied volatility smile/skew across option strikes.
Identifies volatility anomalies and market sentiment indicators.

Requirements: Options Analytics - IV Smile tool
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class IVSmilePoint:
    """Single point on the IV smile curve."""
    strike: float
    iv: float
    moneyness: float  # strike / spot_price
    delta: Optional[float] = None
    option_type: str = "CALL"


@dataclass
class IVSmileResult:
    """Result of IV smile calculation."""
    symbol: str
    expiry_date: str
    spot_price: float
    atm_strike: float
    atm_iv: float
    smile_points: List[IVSmilePoint]
    
    # Smile metrics
    skew: float  # 25-delta risk reversal
    kurtosis: float  # Smile curvature
    smile_slope: float  # Overall slope
    
    # Anomaly detection
    is_smile_inverted: bool  # Put IV > Call IV
    is_volatility_surface_stressed: bool
    anomaly_score: float
    
    # Market sentiment
    sentiment: str  # "bullish", "bearish", "neutral"
    confidence: float
    
    calculated_at: str


class IVSmileCalculator:
    """Calculator for implied volatility smile analysis."""
    
    def __init__(self):
        self.risk_free_rate = 0.06  # 6% risk-free rate (India)
    
    def calculate_smile(
        self,
        symbol: str,
        spot_price: float,
        option_chain: List[Dict],
        expiry_date: str
    ) -> IVSmileResult:
        """
        Calculate IV smile from option chain data.
        
        Args:
            symbol: Underlying symbol
            spot_price: Current spot price
            option_chain: List of option data with strike, iv, type, etc.
            expiry_date: Option expiry date
            
        Returns:
            IVSmileResult with smile analysis
        """
        try:
            # Separate calls and puts
            calls = [opt for opt in option_chain if opt.get('option_type') == 'CALL']
            puts = [opt for opt in option_chain if opt.get('option_type') == 'PUT']
            
            # Calculate moneyness and create smile points
            call_points = self._create_smile_points(calls, spot_price, "CALL")
            put_points = self._create_smile_points(puts, spot_price, "PUT")
            
            # Find ATM (at-the-money) strike and IV
            atm_strike = self._find_atm_strike(spot_price, call_points + put_points)
            atm_iv = self._get_atm_iv(atm_strike, call_points + put_points)
            
            # Calculate smile metrics
            skew = self._calculate_skew(call_points, put_points, spot_price)
            kurtosis = self._calculate_kurtosis(call_points + put_points, spot_price)
            smile_slope = self._calculate_smile_slope(call_points + put_points, spot_price)
            
            # Detect anomalies
            is_inverted = self._detect_inverted_smile(call_points, put_points)
            is_stressed = self._detect_volatility_stress(call_points + put_points)
            anomaly_score = self._calculate_anomaly_score(skew, kurtosis, smile_slope)
            
            # Determine market sentiment
            sentiment, confidence = self._determine_sentiment(
                skew, is_inverted, is_stressed
            )
            
            return IVSmileResult(
                symbol=symbol,
                expiry_date=expiry_date,
                spot_price=spot_price,
                atm_strike=atm_strike,
                atm_iv=atm_iv,
                smile_points=call_points + put_points,
                skew=skew,
                kurtosis=kurtosis,
                smile_slope=smile_slope,
                is_smile_inverted=is_inverted,
                is_volatility_surface_stressed=is_stressed,
                anomaly_score=anomaly_score,
                sentiment=sentiment,
                confidence=confidence,
                calculated_at=datetime.utcnow().isoformat()
            )
            
        except Exception as e:
            logger.error(f"IV smile calculation failed for {symbol}: {e}")
            raise
    
    def _create_smile_points(
        self,
        options: List[Dict],
        spot_price: float,
        option_type: str
    ) -> List[IVSmilePoint]:
        """Create IV smile points from option data."""
        points = []
        
        for opt in options:
            strike = opt.get('strike')
            iv = opt.get('iv')
            
            if strike and iv and iv > 0:
                moneyness = strike / spot_price
                delta = opt.get('delta')
                
                points.append(IVSmilePoint(
                    strike=strike,
                    iv=iv,
                    moneyness=moneyness,
                    delta=delta,
                    option_type=option_type
                ))
        
        # Sort by moneyness
        points.sort(key=lambda x: x.moneyness)
        return points
    
    def _find_atm_strike(
        self,
        spot_price: float,
        smile_points: List[IVSmilePoint]
    ) -> float:
        """Find the ATM strike closest to spot price."""
        if not smile_points:
            return spot_price
        
        # Find strike closest to spot
        closest = min(smile_points, key=lambda x: abs(x.strike - spot_price))
        return closest.strike
    
    def _get_atm_iv(
        self,
        atm_strike: float,
        smile_points: List[IVSmilePoint]
    ) -> float:
        """Get IV at ATM strike."""
        # Find points closest to ATM
        nearby = [p for p in smile_points if abs(p.strike - atm_strike) <= 50]
        
        if not nearby:
            return 0.0
        
        # Average IV of nearby points
        return sum(p.iv for p in nearby) / len(nearby)
    
    def _calculate_skew(
        self,
        call_points: List[IVSmilePoint],
        put_points: List[IVSmilePoint],
        spot_price: float
    ) -> float:
        """
        Calculate 25-delta risk reversal (skew).
        
        Skew = IV(25-delta put) - IV(25-delta call)
        Positive skew indicates bearish sentiment (puts more expensive)
        """
        # Find 25-delta put (OTM put)
        otm_puts = [p for p in put_points if p.delta and p.delta < 0.3]
        put_25 = min(otm_puts, key=lambda x: abs(x.delta - 0.25)) if otm_puts else None
        
        # Find 25-delta call (OTM call)
        otm_calls = [p for p in call_points if p.delta and p.delta < 0.3]
        call_25 = min(otm_calls, key=lambda x: abs(x.delta - 0.25)) if otm_calls else None
        
        if put_25 and call_25:
            return put_25.iv - call_25.iv
        
        # Fallback: use OTM strikes (90% and 110% of spot)
        otm_put = [p for p in put_points if p.moneyness < 0.95]
        otm_call = [p for p in call_points if p.moneyness > 1.05]
        
        if otm_put and otm_call:
            return otm_put[0].iv - otm_call[0].iv
        
        return 0.0
    
    def _calculate_kurtosis(
        self,
        smile_points: List[IVSmilePoint],
        spot_price: float
    ) -> float:
        """
        Calculate smile curvature (kurtosis).
        
        Measures how convex the IV smile is.
        """
        if len(smile_points) < 3:
            return 0.0
        
        # Calculate IV deviations from ATM
        atm_iv = self._get_atm_iv(spot_price, smile_points)
        deviations = [(p.iv - atm_iv) for p in smile_points]
        
        # Calculate kurtosis (4th moment)
        if not deviations:
            return 0.0
        
        std_dev = np.std(deviations) if len(deviations) > 1 else 1.0
        if std_dev == 0:
            return 0.0
        
        kurtosis = np.mean([(d / std_dev) ** 4 for d in deviations])
        
        # Excess kurtosis (subtract 3 for normal distribution)
        return kurtosis - 3
    
    def _calculate_smile_slope(
        self,
        smile_points: List[IVSmilePoint],
        spot_price: float
    ) -> float:
        """
        Calculate overall slope of the IV smile.
        
        Positive slope: IV increases with strike (bearish)
        Negative slope: IV decreases with strike (bullish)
        """
        if len(smile_points) < 2:
            return 0.0
        
        # Fit linear regression to IV vs moneyness
        moneyness = np.array([p.moneyness for p in smile_points])
        iv_values = np.array([p.iv for p in smile_points])
        
        try:
            slope, _ = np.polyfit(moneyness, iv_values, 1)
            return slope
        except:
            return 0.0
    
    def _detect_inverted_smile(
        self,
        call_points: List[IVSmilePoint],
        put_points: List[IVSmilePoint]
    ) -> bool:
        """
        Detect if smile is inverted (put IV > call IV at same strikes).
        """
        if not call_points or not put_points:
            return False
        
        # Compare IV at similar moneyness levels
        for call in call_points[:5]:  # Check ITM/ATM calls
            matching_puts = [p for p in put_points if abs(p.moneyness - call.moneyness) < 0.02]
            
            if matching_puts:
                avg_put_iv = sum(p.iv for p in matching_puts) / len(matching_puts)
                if avg_put_iv > call.iv * 1.05:  # 5% threshold
                    return True
        
        return False
    
    def _detect_volatility_stress(
        self,
        smile_points: List[IVSmilePoint]
    ) -> bool:
        """
        Detect if volatility surface is stressed (unusually high IV or skew).
        """
        if not smile_points:
            return False
        
        # Check for very high IV levels
        iv_values = [p.iv for p in smile_points]
        avg_iv = np.mean(iv_values)
        
        if avg_iv > 0.40:  # IV > 40% indicates stress
            return True
        
        # Check for extreme skew
        if len(iv_values) > 2:
            iv_range = max(iv_values) - min(iv_values)
            if iv_range > 0.30:  # IV range > 30% indicates stress
                return True
        
        return False
    
    def _calculate_anomaly_score(
        self,
        skew: float,
        kurtosis: float,
        smile_slope: float
    ) -> float:
        """
        Calculate overall anomaly score (0-1).
        
        Higher score indicates more unusual IV smile.
        """
        score = 0.0
        
        # Skew anomaly (normal range: -0.05 to 0.10)
        if skew < -0.05 or skew > 0.15:
            score += min(abs(skew) / 0.20, 1.0) * 0.4
        
        # Kurtosis anomaly (normal range: -1 to 2)
        if kurtosis < -1 or kurtosis > 3:
            score += min(abs(kurtosis) / 4.0, 1.0) * 0.3
        
        # Slope anomaly (normal range: -0.10 to 0.10)
        if abs(smile_slope) > 0.10:
            score += min(abs(smile_slope) / 0.20, 1.0) * 0.3
        
        return min(score, 1.0)
    
    def _determine_sentiment(
        self,
        skew: float,
        is_inverted: bool,
        is_stressed: bool
    ) -> Tuple[str, float]:
        """
        Determine market sentiment from IV smile.
        
        Returns:
            Tuple of (sentiment, confidence)
        """
        if is_stressed:
            return "stressed", 0.8
        
        if is_inverted and skew > 0.10:
            return "bearish", 0.7
        
        if skew < -0.05:
            return "bullish", 0.6
        
        return "neutral", 0.5
    
    def compare_smiles(
        self,
        smile1: IVSmileResult,
        smile2: IVSmileResult
    ) -> Dict:
        """
        Compare two IV smiles and highlight differences.
        
        Useful for tracking changes over time or comparing expiries.
        """
        skew_change = smile2.skew - smile1.skew
        iv_change = smile2.atm_iv - smile1.atm_iv
        sentiment_changed = smile1.sentiment != smile2.sentiment
        
        return {
            "skew_change": skew_change,
            "atm_iv_change": iv_change,
            "sentiment_changed": sentiment_changed,
            "previous_sentiment": smile1.sentiment,
            "current_sentiment": smile2.sentiment,
            "anomaly_score_change": smile2.anomaly_score - smile1.anomaly_score,
            "is_significant_change": abs(skew_change) > 0.05 or abs(iv_change) > 0.10
        }
