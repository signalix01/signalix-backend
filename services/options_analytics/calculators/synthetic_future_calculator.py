"""
Synthetic Future Calculator

Calculates synthetic futures from option prices using put-call parity.
Identifies arbitrage opportunities and fair value of futures.

Requirements: Options Analytics - Synthetic Future tool
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class SyntheticFuturePoint:
    """Single synthetic future data point."""
    strike: float
    call_price: float
    put_price: float
    synthetic_future_price: float
    actual_future_price: Optional[float] = None
    arbitrage_opportunity: bool = False
    arbitrage_profit: float = 0.0
    mispricing_pct: float = 0.0


@dataclass
class SyntheticFutureAnalysis:
    """Result of synthetic future calculation."""
    symbol: str
    expiry_date: str
    spot_price: float
    risk_free_rate: float
    days_to_expiry: int
    synthetic_points: List[SyntheticFuturePoint]
    
    # Fair value
    fair_future_price: float
    cost_of_carry: float
    
    # Arbitrage analysis
    arbitrage_opportunities: List[SyntheticFuturePoint]
    max_arbitrage_profit: float
    avg_mispricing: float
    
    # Market efficiency
    is_market_efficient: bool
    efficiency_score: float
    
    # Trading signals
    recommendation: str  # "no_action", "buy_synthetic", "sell_synthetic"
    confidence: float
    
    calculated_at: str


class SyntheticFutureCalculator:
    """Calculator for synthetic futures analysis."""
    
    def __init__(self):
        self.default_risk_free_rate = 0.06  # 6% risk-free rate (India)
    
    def calculate_synthetic_futures(
        self,
        symbol: str,
        spot_price: float,
        option_chain: List[Dict],
        expiry_date: str,
        days_to_expiry: int,
        actual_future_price: Optional[float] = None,
        risk_free_rate: Optional[float] = None
    ) -> SyntheticFutureAnalysis:
        """
        Calculate synthetic futures from option chain using put-call parity.
        
        Put-Call Parity: C - P = S - K / (1 + r)^T
        Synthetic Future: F = S * (1 + r)^T
        
        Args:
            symbol: Underlying symbol
            spot_price: Current spot price
            option_chain: List of option data with strike, price, etc.
            expiry_date: Option expiry date
            days_to_expiry: Days to expiry
            actual_future_price: Actual futures price (if available)
            risk_free_rate: Risk-free rate (default 6%)
            
        Returns:
            SyntheticFutureAnalysis with synthetic future data
        """
        try:
            if risk_free_rate is None:
                risk_free_rate = self.default_risk_free_rate
            
            # Calculate cost of carry
            cost_of_carry = self._calculate_cost_of_carry(
                spot_price, risk_free_rate, days_to_expiry
            )
            
            # Calculate fair future price
            fair_future_price = spot_price + cost_of_carry
            
            # Group options by strike
            strikes_data = self._group_by_strike(option_chain)
            
            # Calculate synthetic futures for each strike
            synthetic_points = []
            for strike, data in strikes_data.items():
                synthetic = self._calculate_synthetic_future(
                    strike=strike,
                    call_data=data.get('CALL'),
                    put_data=data.get('PUT'),
                    spot_price=spot_price,
                    risk_free_rate=risk_free_rate,
                    days_to_expiry=days_to_expiry,
                    actual_future_price=actual_future_price
                )
                if synthetic:
                    synthetic_points.append(synthetic)
            
            # Sort by strike
            synthetic_points.sort(key=lambda x: x.strike)
            
            # Identify arbitrage opportunities
            arbitrage_opportunities = [
                p for p in synthetic_points if p.arbitrage_opportunity
            ]
            
            # Calculate metrics
            max_arbitrage_profit = max([p.arbitrage_profit for p in arbititrary_opportunities], default=0.0)
            avg_mispricing = np.mean([p.mispricing_pct for p in synthetic_points]) if synthetic_points else 0.0
            
            # Determine market efficiency
            is_efficient = len(arbitrage_opportunities) == 0
            efficiency_score = self._calculate_efficiency_score(synthetic_points)
            
            # Generate trading recommendation
            recommendation, confidence = self._generate_recommendation(
                arbitrage_opportunities,
                actual_future_price,
                fair_future_price
            )
            
            return SyntheticFutureAnalysis(
                symbol=symbol,
                expiry_date=expiry_date,
                spot_price=spot_price,
                risk_free_rate=risk_free_rate,
                days_to_expiry=days_to_expiry,
                synthetic_points=synthetic_points,
                fair_future_price=fair_future_price,
                cost_of_carry=cost_of_carry,
                arbitrage_opportunities=arbitrage_opportunities,
                max_arbitrage_profit=max_arbitrage_profit,
                avg_mispricing=avg_mispricing,
                is_market_efficient=is_efficient,
                efficiency_score=efficiency_score,
                recommendation=recommendation,
                confidence=confidence,
                calculated_at=datetime.utcnow().isoformat()
            )
            
        except Exception as e:
            logger.error(f"Synthetic future calculation failed for {symbol}: {e}")
            raise
    
    def _calculate_cost_of_carry(
        self,
        spot_price: float,
        risk_free_rate: float,
        days_to_expiry: int
    ) -> float:
        """Calculate cost of carry."""
        years = days_to_expiry / 365.0
        return spot_price * risk_free_rate * years
    
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
    
    def _calculate_synthetic_future(
        self,
        strike: float,
        call_data: Optional[Dict],
        put_data: Optional[Dict],
        spot_price: float,
        risk_free_rate: float,
        days_to_expiry: int,
        actual_future_price: Optional[float]
    ) -> Optional[SyntheticFuturePoint]:
        """Calculate synthetic future for a single strike."""
        if not call_data or not put_data:
            return None
        
        call_price = call_data.get('last_price') or call_data.get('price', 0)
        put_price = put_data.get('last_price') or put_data.get('price', 0)
        
        if call_price <= 0 or put_price <= 0:
            return None
        
        # Put-Call Parity: C - P = S - K / (1 + r)^T
        # Rearranged: Synthetic Future = C - P + K
        years = days_to_expiry / 365.0
        discount_factor = 1 / (1 + risk_free_rate) ** years
        pv_strike = strike * discount_factor
        
        synthetic_future_price = call_price - put_price + pv_strike
        
        # Check for arbitrage if actual future price is available
        arbitrage_opportunity = False
        arbitrage_profit = 0.0
        mispricing_pct = 0.0
        
        if actual_future_price:
            mispricing = synthetic_future_price - actual_future_price
            mispricing_pct = (mispricing / actual_future_price) * 100
            
            # Arbitrage threshold: 0.5% mispricing
            if abs(mispricing_pct) > 0.5:
                arbitrage_opportunity = True
                arbitrage_profit = abs(mispricing)
        
        return SyntheticFuturePoint(
            strike=strike,
            call_price=call_price,
            put_price=put_price,
            synthetic_future_price=synthetic_future_price,
            actual_future_price=actual_future_price,
            arbitrage_opportunity=arbitrage_opportunity,
            arbitrage_profit=arbitrage_profit,
            mispricing_pct=mispricing_pct
        )
    
    def _calculate_efficiency_score(
        self,
        synthetic_points: List[SyntheticFuturePoint]
    ) -> float:
        """
        Calculate market efficiency score (0-1).
        
        Higher score indicates more efficient market (less arbitrage).
        """
        if not synthetic_points:
            return 0.5  # Neutral
        
        # Calculate variance in synthetic prices
        synthetic_prices = [p.synthetic_future_price for p in synthetic_points]
        variance = np.var(synthetic_prices) if len(synthetic_prices) > 1 else 0
        
        # Count arbitrage opportunities
        arb_count = sum(1 for p in synthetic_points if p.arbitrage_opportunity)
        
        # Efficiency score: lower variance and fewer arbitrage = higher efficiency
        variance_score = max(0, 1 - (variance / 100))  # Normalize variance
        arb_score = max(0, 1 - (arb_count / len(synthetic_points)))  # Fewer arb = higher score
        
        return (variance_score + arb_score) / 2
    
    def _generate_recommendation(
        self,
        arbitrage_opportunities: List[SyntheticFuturePoint],
        actual_future_price: Optional[float],
        fair_future_price: float
    ) -> Tuple[str, float]:
        """Generate trading recommendation."""
        if not arbitrage_opportunities:
            return "no_action", 0.5
        
        # Check direction of mispricing
        avg_mispricing = np.mean([p.mispricing_pct for p in arbitrage_opportunities])
        
        if avg_mispricing > 0:
            # Synthetic future > actual future: buy actual, sell synthetic
            return "sell_synthetic", 0.7
        else:
            # Synthetic future < actual future: buy synthetic, sell actual
            return "buy_synthetic", 0.7
    
    def validate_put_call_parity(
        self,
        strike: float,
        call_price: float,
        put_price: float,
        spot_price: float,
        risk_free_rate: float,
        days_to_expiry: int,
        tolerance: float = 0.02
    ) -> Dict:
        """
        Validate put-call parity for a specific strike.
        
        Returns validation result with deviation percentage.
        """
        years = days_to_expiry / 365.0
        discount_factor = 1 / (1 + risk_free_rate) ** years
        pv_strike = strike * discount_factor
        
        # Left side: C - P
        left_side = call_price - put_price
        
        # Right side: S - K/(1+r)^T
        right_side = spot_price - pv_strike
        
        # Calculate deviation
        deviation = left_side - right_side
        deviation_pct = (deviation / spot_price) * 100
        
        # Check if within tolerance
        is_valid = abs(deviation_pct) <= (tolerance * 100)
        
        return {
            "strike": strike,
            "left_side": left_side,
            "right_side": right_side,
            "deviation": deviation,
            "deviation_pct": deviation_pct,
            "is_valid": is_valid,
            "tolerance_pct": tolerance * 100
        }
    
    def calculate_basis_risk(
        self,
        synthetic_future_price: float,
        actual_future_price: float,
        spot_price: float
    ) -> Dict:
        """
        Calculate basis risk between synthetic and actual futures.
        
        Basis risk is the risk that the relationship between
        synthetic and actual futures changes.
        """
        basis = synthetic_future_price - actual_future_price
        basis_pct = (basis / spot_price) * 100
        
        return {
            "synthetic_future_price": synthetic_future_price,
            "actual_future_price": actual_future_price,
            "basis": basis,
            "basis_pct": basis_pct,
            "is_convergent": abs(basis_pct) < 0.5  # Convergent if basis < 0.5%
        }
