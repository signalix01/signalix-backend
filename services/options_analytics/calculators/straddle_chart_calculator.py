"""
Straddle Chart Calculator

Analyzes straddle positions across strikes to identify optimal entry/exit points
and visualize potential P&L scenarios.

Requirements: Options Analytics - Straddle Chart tool
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class StraddleDataPoint:
    """Single straddle data point."""
    strike: float
    call_price: float
    put_price: float
    total_cost: float
    break_even_upper: float
    break_even_lower: float
    max_loss: float
    iv: float


@dataclass
class StraddleAnalysis:
    """Result of straddle chart analysis."""
    symbol: str
    expiry_date: str
    spot_price: float
    straddles: List[StraddleDataPoint]
    
    # Optimal straddle
    optimal_strike: float
    optimal_straddle: StraddleDataPoint
    
    # Market metrics
    avg_straddle_cost: float
    cost_range: Tuple[float, float]
    iv_skew: float
    
    # Trading signals
    is_cheap_straddle: bool  # Cost below average
    is_expensive_straddle: bool  # Cost above average
    break_even_width: float  # Distance between break-evens
    
    # Volatility analysis
    expected_move: float  # Expected price move based on straddle cost
    probability_profit: float  # Estimated probability of profit
    
    calculated_at: str


class StraddleChartCalculator:
    """Calculator for straddle position analysis."""
    
    def __init__(self):
        self.risk_free_rate = 0.06  # 6% risk-free rate (India)
    
    def analyze_straddles(
        self,
        symbol: str,
        spot_price: float,
        option_chain: List[Dict],
        expiry_date: str,
        days_to_expiry: int
    ) -> StraddleAnalysis:
        """
        Analyze straddle positions across all strikes.
        
        Args:
            symbol: Underlying symbol
            spot_price: Current spot price
            option_chain: List of option data with strike, price, iv, etc.
            expiry_date: Option expiry date
            days_to_expiry: Days to expiry
            
        Returns:
            StraddleAnalysis with straddle chart data
        """
        try:
            # Group options by strike
            strikes_data = self._group_by_strike(option_chain)
            
            # Calculate straddle data for each strike
            straddles = []
            for strike, data in strikes_data.items():
                straddle = self._calculate_straddle(
                    strike=strike,
                    call_data=data.get('CALL'),
                    put_data=data.get('PUT'),
                    spot_price=spot_price
                )
                if straddle:
                    straddles.append(straddle)
            
            # Sort by strike
            straddles.sort(key=lambda x: x.strike)
            
            # Find optimal straddle (closest to ATM with reasonable cost)
            optimal_straddle = self._find_optimal_straddle(straddles, spot_price)
            
            # Calculate market metrics
            avg_cost = np.mean([s.total_cost for s in straddles]) if straddles else 0
            cost_range = (
                min([s.total_cost for s in straddles]) if straddles else 0,
                max([s.total_cost for s in straddles]) if straddles else 0
            )
            
            # Calculate IV skew
            iv_skew = self._calculate_iv_skew(straddles, spot_price)
            
            # Determine if straddles are cheap/expensive
            is_cheap = optimal_straddle.total_cost < avg_cost * 0.9
            is_expensive = optimal_straddle.total_cost > avg_cost * 1.1
            
            # Calculate break-even width
            break_even_width = optimal_straddle.break_even_upper - optimal_straddle.break_even_lower
            
            # Calculate expected move
            expected_move = self._calculate_expected_move(
                optimal_straddle.total_cost,
                spot_price,
                days_to_expiry
            )
            
            # Calculate probability of profit
            probability_profit = self._calculate_probability_profit(
                break_even_width,
                expected_move,
                days_to_expiry
            )
            
            return StraddleAnalysis(
                symbol=symbol,
                expiry_date=expiry_date,
                spot_price=spot_price,
                straddles=straddles,
                optimal_strike=optimal_straddle.strike,
                optimal_straddle=optimal_straddle,
                avg_straddle_cost=avg_cost,
                cost_range=cost_range,
                iv_skew=iv_skew,
                is_cheap_straddle=is_cheap,
                is_expensive_straddle=is_expensive,
                break_even_width=break_even_width,
                expected_move=expected_move,
                probability_profit=probability_profit,
                calculated_at=datetime.utcnow().isoformat()
            )
            
        except Exception as e:
            logger.error(f"Straddle analysis failed for {symbol}: {e}")
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
    
    def _calculate_straddle(
        self,
        strike: float,
        call_data: Optional[Dict],
        put_data: Optional[Dict],
        spot_price: float
    ) -> Optional[StraddleDataPoint]:
        """Calculate straddle data for a single strike."""
        if not call_data or not put_data:
            return None
        
        call_price = call_data.get('last_price') or call_data.get('price', 0)
        put_price = put_data.get('last_price') or put_data.get('price', 0)
        
        if call_price <= 0 or put_price <= 0:
            return None
        
        total_cost = call_price + put_price
        break_even_upper = strike + total_cost
        break_even_lower = strike - total_cost
        max_loss = total_cost
        
        # Average IV of call and put
        call_iv = call_data.get('iv', 0)
        put_iv = put_data.get('iv', 0)
        avg_iv = (call_iv + put_iv) / 2 if call_iv and put_iv else 0
        
        return StraddleDataPoint(
            strike=strike,
            call_price=call_price,
            put_price=put_price,
            total_cost=total_cost,
            break_even_upper=break_even_upper,
            break_even_lower=break_even_lower,
            max_loss=max_loss,
            iv=avg_iv
        )
    
    def _find_optimal_straddle(
        self,
        straddles: List[StraddleDataPoint],
        spot_price: float
    ) -> StraddleDataPoint:
        """Find optimal straddle (ATM with reasonable cost)."""
        if not straddles:
            raise ValueError("No straddles available")
        
        # Find straddles closest to ATM
        atm_straddles = sorted(
            straddles,
            key=lambda x: abs(x.strike - spot_price)
        )[:3]  # Top 3 closest to ATM
        
        # Choose the one with best cost-to-IV ratio
        best = min(
            atm_straddles,
            key=lambda x: x.total_cost / x.iv if x.iv > 0 else float('inf')
        )
        
        return best
    
    def _calculate_iv_skew(
        self,
        straddles: List[StraddleDataPoint],
        spot_price: float
    ) -> float:
        """Calculate IV skew across strikes."""
        if len(straddles) < 2:
            return 0.0
        
        # Calculate IV difference between OTM and ITM straddles
        otm_straddles = [s for s in straddles if s.strike > spot_price * 1.05]
        itm_straddles = [s for s in straddles if s.strike < spot_price * 0.95]
        
        if not otm_straddles or not itm_straddles:
            return 0.0
        
        avg_otm_iv = np.mean([s.iv for s in otm_straddles])
        avg_itm_iv = np.mean([s.iv for s in itm_straddles])
        
        return avg_otm_iv - avg_itm_iv
    
    def _calculate_expected_move(
        self,
        straddle_cost: float,
        spot_price: float,
        days_to_expiry: int
    ) -> float:
        """
        Calculate expected price move based on straddle cost.
        
        The straddle cost represents the market's expected move.
        """
        if days_to_expiry <= 0:
            return 0.0
        
        # Expected move as percentage of spot price
        expected_move_pct = (straddle_cost / spot_price) * 100
        
        # Annualize the move
        annualized_move = expected_move_pct * np.sqrt(365 / days_to_expiry)
        
        return annualized_move
    
    def _calculate_probability_profit(
        self,
        break_even_width: float,
        expected_move: float,
        days_to_expiry: int
    ) -> float:
        """
        Calculate estimated probability of profit.
        
        Based on historical analysis of straddle profitability.
        """
        if break_even_width <= 0 or expected_move <= 0:
            return 0.5  # Default 50%
        
        # If expected move is greater than break-even width, higher probability
        ratio = expected_move / break_even_width
        
        # Cap probability between 0.3 and 0.7
        probability = min(max(ratio * 0.5, 0.3), 0.7)
        
        return probability
    
    def calculate_pnl_scenario(
        self,
        straddle: StraddleDataPoint,
        spot_price_at_expiry: float
    ) -> Dict:
        """
        Calculate P&L for a straddle at expiry for a given spot price.
        
        Args:
            straddle: Straddle data
            spot_price_at_expiry: Spot price at expiry
            
        Returns:
            P&L breakdown
        """
        # Call P&L
        if spot_price_at_expiry > straddle.strike:
            call_pnl = spot_price_at_expiry - straddle.strike - straddle.call_price
        else:
            call_pnl = -straddle.call_price
        
        # Put P&L
        if spot_price_at_expiry < straddle.strike:
            put_pnl = straddle.strike - spot_price_at_expiry - straddle.put_price
        else:
            put_pnl = -straddle.put_price
        
        total_pnl = call_pnl + put_pnl
        
        return {
            "call_pnl": call_pnl,
            "put_pnl": put_pnl,
            "total_pnl": total_pnl,
            "is_profitable": total_pnl > 0,
            "return_pct": (total_pnl / straddle.total_cost) * 100 if straddle.total_cost > 0 else 0
        }
    
    def generate_pnl_curve(
        self,
        straddle: StraddleDataPoint,
        spot_price_range: Tuple[float, float],
        num_points: int = 50
    ) -> List[Dict]:
        """
        Generate P&L curve across a range of spot prices.
        
        Useful for charting the straddle payoff diagram.
        """
        price_start, price_end = spot_price_range
        price_step = (price_end - price_start) / (num_points - 1)
        
        pnl_curve = []
        for i in range(num_points):
            spot = price_start + (i * price_step)
            pnl = self.calculate_pnl_scenario(straddle, spot)
            pnl_curve.append({
                "spot_price": spot,
                "pnl": pnl["total_pnl"],
                "return_pct": pnl["return_pct"],
                "is_profitable": pnl["is_profitable"]
            })
        
        return pnl_curve
    
    def compare_straddles(
        self,
        straddle1: StraddleDataPoint,
        straddle2: StraddleDataPoint
    ) -> Dict:
        """
        Compare two straddles and highlight differences.
        
        Useful for choosing between different strikes.
        """
        cost_diff = straddle2.total_cost - straddle1.total_cost
        be_width_diff = (straddle2.break_even_upper - straddle2.break_even_lower) - \
                       (straddle1.break_even_upper - straddle1.break_even_lower)
        
        return {
            "strike1": straddle1.strike,
            "strike2": straddle2.strike,
            "cost_difference": cost_diff,
            "cost_difference_pct": (cost_diff / straddle1.total_cost) * 100,
            "break_even_width_difference": be_width_diff,
            "iv_difference": straddle2.iv - straddle1.iv,
            "recommendation": self._recommend_straddle(straddle1, straddle2)
        }
    
    def _recommend_straddle(
        self,
        straddle1: StraddleDataPoint,
        straddle2: StraddleDataPoint
    ) -> str:
        """Recommend which straddle to choose."""
        # Prefer cheaper straddle with similar IV
        if abs(straddle1.iv - straddle2.iv) < 0.02:
            return straddle1.strike if straddle1.total_cost < straddle2.total_cost else straddle2.strike
        
        # Prefer higher IV if cost difference is small
        if abs(straddle1.total_cost - straddle2.total_cost) / straddle1.total_cost < 0.1:
            return straddle1.strike if straddle1.iv > straddle2.iv else straddle2.strike
        
        # Default to cheaper
        return straddle1.strike if straddle1.total_cost < straddle2.total_cost else straddle2.strike
