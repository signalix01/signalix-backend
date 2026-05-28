"""
GEX (Gamma Exposure) Calculator

Calculates net gamma exposure at each strike price to identify
potential support/resistance levels from market maker positioning.

Requirements: 5.1, 5.2, 5.3, 5.4, 5.6, 5.7
"""

import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, List, Tuple, Optional


@dataclass
class StrikeGEX:
    """GEX data for a strike price"""
    strike: float
    call_gex: float
    put_gex: float
    net_gex: float
    call_oi: int
    put_oi: int
    call_gamma: float
    put_gamma: float


@dataclass
class GEXResult:
    """GEX calculation result"""
    symbol: str
    expiry_date: date
    spot_price: float
    gex_by_strike: Dict[float, StrikeGEX]
    zero_gamma_level: float
    significant_levels: List[float]
    total_call_gex: float
    total_put_gex: float
    net_gex: float
    calculated_at: datetime


class GEXCalculator:
    """
    Gamma Exposure (GEX) Calculator
    
    Calculates net gamma exposure at each strike to identify:
    - Zero gamma level (where call and put gamma offset)
    - Significant gamma levels (high exposure areas)
    - Support/resistance levels based on dealer positioning
    
    GEX Formula: gamma * open_interest * spot_price^2
    - Call gamma: positive (dealers are short calls, need to hedge by buying)
    - Put gamma: negative (dealers are short puts, need to hedge by selling)
    
    Requirements: 5.1, 5.2, 5.3, 5.4, 5.6, 5.7
    """
    
    # Threshold for significant gamma level (in notional terms)
    DEFAULT_SIGNIFICANT_THRESHOLD = 10000000  # 10 million
    
    def __init__(self, significant_threshold: float = DEFAULT_SIGNIFICANT_THRESHOLD):
        self.significant_threshold = significant_threshold
    
    def calculate_gex(
        self,
        symbol: str,
        expiry_date: date,
        spot_price: float,
        strikes_data: List[Dict]
    ) -> GEXResult:
        """
        Calculate gamma exposure distribution
        
        Args:
            symbol: Underlying symbol
            expiry_date: Option expiry date
            spot_price: Current spot price
            strikes_data: List of strike data with:
                - strike: float
                - call_gamma: float
                - put_gamma: float
                - call_oi: int
                - put_oi: int
        
        Returns:
            GEXResult with gamma exposure analysis
        
        Requirements: 5.1, 5.2, 5.3
        """
        gex_by_strike = {}
        total_call_gex = 0.0
        total_put_gex = 0.0
        
        # Calculate GEX for each strike
        for data in strikes_data:
            strike = data["strike"]
            call_gamma = data.get("call_gamma", 0) or 0
            put_gamma = data.get("put_gamma", 0) or 0
            call_oi = data.get("call_oi", 0) or 0
            put_oi = data.get("put_oi", 0) or 0
            
            # Calculate GEX
            # Call gamma is positive (dealers short calls)
            call_gex = call_gamma * call_oi * (spot_price ** 2)
            
            # Put gamma is negative (dealers short puts)
            put_gex = -put_gamma * put_oi * (spot_price ** 2)
            
            net_gex = call_gex + put_gex
            
            gex_by_strike[strike] = StrikeGEX(
                strike=strike,
                call_gex=call_gex,
                put_gex=put_gex,
                net_gex=net_gex,
                call_oi=call_oi,
                put_oi=put_oi,
                call_gamma=call_gamma,
                put_gamma=put_gamma
            )
            
            total_call_gex += call_gex
            total_put_gex += put_gex
        
        net_gex = total_call_gex + total_put_gex
        
        # Identify zero gamma level
        zero_gamma = self._identify_zero_gamma_level(gex_by_strike, spot_price)
        
        # Identify significant levels
        significant_levels = self._identify_significant_levels(gex_by_strike)
        
        return GEXResult(
            symbol=symbol,
            expiry_date=expiry_date,
            spot_price=spot_price,
            gex_by_strike=gex_by_strike,
            zero_gamma_level=zero_gamma,
            significant_levels=significant_levels,
            total_call_gex=total_call_gex,
            total_put_gex=total_put_gex,
            net_gex=net_gex,
            calculated_at=datetime.utcnow()
        )
    
    def _identify_zero_gamma_level(
        self,
        gex_by_strike: Dict[float, StrikeGEX],
        spot_price: float
    ) -> float:
        """
        Identify the strike where cumulative GEX crosses zero
        
        This is the price level where dealer hedging pressure changes direction.
        
        Requirements: 5.4
        """
        if not gex_by_strike:
            return spot_price
        
        strikes = sorted(gex_by_strike.keys())
        cumulative_gex = 0.0
        
        # Sort by distance from spot
        for strike in strikes:
            cumulative_gex += gex_by_strike[strike].net_gex
            gex_by_strike[strike].cumulative_gex = cumulative_gex
        
        # Find where cumulative crosses zero
        prev_gex = 0.0
        zero_level = spot_price
        
        for strike in strikes:
            curr_gex = cumulative_gex - sum(
                gex_by_strike[s].net_gex for s in strikes if s < strike
            )
            
            if prev_gex * curr_gex < 0:  # Sign change
                # Linear interpolation to find exact crossing
                if abs(prev_gex - curr_gex) > 0:
                    ratio = abs(prev_gex) / abs(prev_gex - curr_gex)
                    zero_level = strike - (strike - (strikes[strikes.index(strike) - 1] if strikes.index(strike) > 0 else strike)) * ratio
                else:
                    zero_level = strike
                break
            
            prev_gex = curr_gex
        
        return zero_level
    
    def _identify_significant_levels(
        self,
        gex_by_strike: Dict[float, StrikeGEX]
    ) -> List[float]:
        """
        Identify strikes with significant gamma exposure
        
        Requirements: 5.7
        """
        significant = []
        
        for strike, data in gex_by_strike.items():
            if abs(data.net_gex) >= self.significant_threshold:
                significant.append(strike)
        
        return sorted(significant)
    
    def get_gex_interpretation(self, result: GEXResult) -> Dict:
        """
        Get interpretation of GEX data for trading insights
        """
        interpretation = {
            "market_bias": "neutral",
            "key_levels": {
                "zero_gamma": result.zero_gamma_level,
                "significant": result.significant_levels[:5]  # Top 5
            },
            "hedging_pressure": "neutral",
            "support_resistance": {}
        }
        
        # Determine market bias based on net GEX
        if result.net_gex > self.significant_threshold:
            interpretation["market_bias"] = "positive_gamma"
            interpretation["hedging_pressure"] = "sell_pressure"
            # Above zero gamma = path of least resistance up
        elif result.net_gex < -self.significant_threshold:
            interpretation["market_bias"] = "negative_gamma"
            interpretation["hedging_pressure"] = "buy_pressure"
            # Below zero gamma = path of least resistance down
        
        # Identify support and resistance from significant levels
        if result.significant_levels:
            # Levels below spot are support
            support_levels = [s for s in result.significant_levels if s < result.spot_price]
            # Levels above spot are resistance
            resistance_levels = [s for s in result.significant_levels if s > result.spot_price]
            
            interpretation["support_resistance"] = {
                "support": sorted(support_levels, reverse=True)[:3],
                "resistance": sorted(resistance_levels)[:3]
            }
        
        return interpretation
    
    def format_result(self, result: GEXResult) -> Dict:
        """Format GEX result for API response"""
        return {
            "symbol": result.symbol,
            "expiry_date": result.expiry_date.isoformat(),
            "spot_price": result.spot_price,
            "zero_gamma_level": result.zero_gamma_level,
            "significant_levels": result.significant_levels,
            "totals": {
                "call_gex": round(result.total_call_gex, 2),
                "put_gex": round(result.total_put_gex, 2),
                "net_gex": round(result.net_gex, 2)
            },
            "gex_by_strike": {
                str(strike): {
                    "call_gex": round(data.call_gex, 2),
                    "put_gex": round(data.put_gex, 2),
                    "net_gex": round(data.net_gex, 2),
                    "call_oi": data.call_oi,
                    "put_oi": data.put_oi,
                    "call_gamma": round(data.call_gamma, 6) if data.call_gamma else None,
                    "put_gamma": round(data.put_gamma, 6) if data.put_gamma else None
                }
                for strike, data in result.gex_by_strike.items()
            },
            "interpretation": self.get_gex_interpretation(result),
            "calculated_at": result.calculated_at.isoformat()
        }
