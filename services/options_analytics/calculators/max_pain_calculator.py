"""
Max Pain Calculator

Calculates the max pain price for options - the strike price where 
option writers have minimum total loss.

Requirements: 4.1, 4.2, 4.3, 4.5, 4.6, 4.7
"""

import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, List, Tuple, Optional


@dataclass
class StrikeLoss:
    """Loss data for a strike price"""
    strike: float
    call_loss: float
    put_loss: float
    total_loss: float


@dataclass
class MaxPainResult:
    """Max pain calculation result"""
    symbol: str
    expiry_date: date
    max_pain_price: float
    current_price: float
    deviation_percent: float
    loss_by_strike: Dict[float, StrikeLoss]
    calculated_at: datetime


class MaxPainCalculator:
    """
    Max Pain Calculator for options
    
    Calculates the strike price where option writers have minimum total loss.
    This is considered a potential price target as market tends to move towards
    max pain at expiry.
    
    Requirements: 4.1, 4.2, 4.3, 4.5, 4.6, 4.7
    """
    
    def __init__(self):
        pass
    
    def calculate_max_pain(
        self,
        symbol: str,
        expiry_date: date,
        current_price: float,
        strikes_data: List[Dict]
    ) -> MaxPainResult:
        """
        Calculate max pain price
        
        Args:
            symbol: Underlying symbol
            expiry_date: Option expiry date
            current_price: Current spot price
            strikes_data: List of strike data with:
                - strike: float
                - call_oi: int (call open interest)
                - put_oi: int (put open interest)
        
        Returns:
            MaxPainResult with calculation details
        
        Requirements: 4.2, 4.3
        """
        # Extract unique strikes
        strikes = sorted(set(d["strike"] for d in strikes_data))
        
        if not strikes:
            raise ValueError("No strike data provided")
        
        # Build strike info map
        strike_info = {}
        for d in strikes_data:
            s = d["strike"]
            if s not in strike_info:
                strike_info[s] = {"call_oi": 0, "put_oi": 0}
            strike_info[s]["call_oi"] += d.get("call_oi", 0)
            strike_info[s]["put_oi"] += d.get("put_oi", 0)
        
        # Calculate loss at each strike
        loss_by_strike = {}
        
        for candidate_strike in strikes:
            total_loss = 0.0
            call_loss = 0.0
            put_loss = 0.0
            
            for strike, info in strike_info.items():
                call_oi = info["call_oi"]
                put_oi = info["put_oi"]
                
                # Calculate loss for call writers
                if strike <= candidate_strike:
                    # Calls are ITM - writers lose
                    call_loss += call_oi * (candidate_strike - strike)
                
                # Calculate loss for put writers
                if strike >= candidate_strike:
                    # Puts are ITM - writers lose
                    put_loss += put_oi * (strike - candidate_strike)
            
            total_loss = call_loss + put_loss
            
            loss_by_strike[candidate_strike] = StrikeLoss(
                strike=candidate_strike,
                call_loss=call_loss,
                put_loss=put_loss,
                total_loss=total_loss
            )
        
        # Find strike with minimum total loss (max pain)
        min_loss = float('inf')
        max_pain_strike = strikes[0]
        
        for strike, loss_data in loss_by_strike.items():
            if loss_data.total_loss < min_loss:
                min_loss = loss_data.total_loss
                max_pain_strike = strike
            elif loss_data.total_loss == min_loss:
                # If tie, choose strike closer to current price
                if abs(strike - current_price) < abs(max_pain_strike - current_price):
                    max_pain_strike = strike
        
        # Calculate deviation
        deviation_percent = ((max_pain_strike - current_price) / current_price) * 100
        
        return MaxPainResult(
            symbol=symbol,
            expiry_date=expiry_date,
            max_pain_price=max_pain_strike,
            current_price=current_price,
            deviation_percent=deviation_percent,
            loss_by_strike=loss_by_strike,
            calculated_at=datetime.utcnow()
        )
    
    def calculate_total_loss(
        self,
        strike: float,
        chain_data: List[Dict]
    ) -> Tuple[float, float, float]:
        """
        Calculate total loss at a specific strike price
        
        Args:
            strike: The strike price to calculate loss at
            chain_data: List of option data with strike, call_oi, put_oi
        
        Returns:
            Tuple of (call_loss, put_loss, total_loss)
        """
        call_loss = 0.0
        put_loss = 0.0
        
        for data in chain_data:
            option_strike = data["strike"]
            call_oi = data.get("call_oi", 0)
            put_oi = data.get("put_oi", 0)
            
            # Call loss
            if option_strike <= strike:
                call_loss += call_oi * (strike - option_strike)
            
            # Put loss
            if option_strike >= strike:
                put_loss += put_oi * (option_strike - strike)
        
        return call_loss, put_loss, call_loss + put_loss
    
    def get_max_pain_range(
        self,
        result: MaxPainResult,
        threshold_percent: float = 5.0
    ) -> List[float]:
        """
        Get range of strikes near max pain
        
        Args:
            result: MaxPainResult
            threshold_percent: Include strikes within this % of min loss
        
        Returns:
            List of strike prices near max pain
        """
        min_loss = min(ld.total_loss for ld in result.loss_by_strike.values())
        threshold = min_loss * (1 + threshold_percent / 100)
        
        nearby_strikes = [
            strike for strike, loss_data in result.loss_by_strike.items()
            if loss_data.total_loss <= threshold
        ]
        
        return sorted(nearby_strikes)
    
    def format_result(self, result: MaxPainResult) -> Dict:
        """
        Format max pain result for API response
        
        Requirements: 4.5
        """
        return {
            "symbol": result.symbol,
            "expiry_date": result.expiry_date.isoformat(),
            "max_pain_price": result.max_pain_price,
            "current_price": result.current_price,
            "deviation_percent": round(result.deviation_percent, 2),
            "deviation_amount": round(result.max_pain_price - result.current_price, 2),
            "loss_by_strike": {
                str(strike): {
                    "call_loss": round(data.call_loss, 2),
                    "put_loss": round(data.put_loss, 2),
                    "total_loss": round(data.total_loss, 2)
                }
                for strike, data in result.loss_by_strike.items()
            },
            "calculated_at": result.calculated_at.isoformat()
        }
