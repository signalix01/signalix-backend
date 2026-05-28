"""
Options Strategy Builder

Multi-leg options strategy builder with payoff calculation,
breakeven analysis, and margin requirements.

Requirements: 7.6, 26.1, 26.2, 26.3, 26.4, 45.1, 45.2
"""

import math
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional, Any
from datetime import date
from enum import Enum as PyEnum


class OptionType(str, PyEnum):
    CALL = "CALL"
    PUT = "PUT"


class PositionType(str, PyEnum):
    LONG = "LONG"
    SHORT = "SHORT"


class StrategyType(str, PyEnum):
    SINGLE = "SINGLE"
    STRADDLE = "STRADDLE"
    STRANGLE = "STRANGLE"
    BULL_CALL_SPREAD = "BULL_CALL_SPREAD"
    BEAR_PUT_SPREAD = "BEAR_PUT_SPREAD"
    IRON_CONDOR = "IRON_CONDOR"
    BUTTERFLY = "BUTTERFLY"
    CALENDAR_SPREAD = "CALENDAR_SPREAD"
    CUSTOM = "CUSTOM"


@dataclass
class StrategyLeg:
    """Individual leg of an options strategy"""
    leg_number: int
    option_type: OptionType
    position_type: PositionType
    strike: float
    quantity: int
    entry_price: float
    expiry: date
    
    def is_long(self) -> bool:
        return self.position_type == PositionType.LONG
    
    def is_call(self) -> bool:
        return self.option_type == OptionType.CALL


@dataclass
class PayoffResult:
    """Strategy payoff calculation result"""
    strategy_type: StrategyType
    symbol: str
    expiry: date
    
    # Payoff data
    payoff_by_price: Dict[float, float]  # price -> payoff
    prices_range: List[float]  # Price points for payoff calculation
    
    # Metrics
    max_profit: Optional[float]
    max_loss: Optional[float]
    breakeven_points: List[float]
    
    # Margin
    margin_required: float
    
    # Net premium
    net_premium_paid: float  # Positive = debit, negative = credit
    
    # Legs info
    legs: List[StrategyLeg]


class StrategyBuilder:
    """
    Multi-leg Options Strategy Builder
    
    Supports strategies:
    - Single long/short calls and puts
    - Straddles and strangles
    - Vertical spreads (bull call, bear put)
    - Iron condors
    - Butterflies
    - Calendar spreads
    - Custom combinations
    
    Requirements: 7.6, 26.1, 26.2, 26.3, 26.4, 45.1, 45.2
    """
    
    # Price range for payoff calculation (ATM ± 20%)
    PRICE_RANGE_PERCENT = 0.20
    PRICE_POINTS = 41  # Number of price points to calculate
    
    def __init__(self):
        pass
    
    def build_strategy(
        self,
        strategy_type: StrategyType,
        symbol: str,
        expiry: date,
        legs: List[Dict[str, Any]],
        spot_price: float
    ) -> PayoffResult:
        """
        Build a strategy and calculate payoff
        
        Args:
            strategy_type: Type of strategy
            symbol: Underlying symbol
            expiry: Option expiry date
            legs: List of leg configurations
            spot_price: Current spot price for payoff range
        
        Returns:
            PayoffResult with full analysis
        
        Requirements: 26.1, 26.2, 26.3, 26.4
        """
        # Build leg objects
        strategy_legs = []
        for i, leg_data in enumerate(legs, 1):
            leg = StrategyLeg(
                leg_number=i,
                option_type=OptionType(leg_data["option_type"]),
                position_type=PositionType(leg_data["position_type"]),
                strike=leg_data["strike"],
                quantity=leg_data.get("quantity", 1),
                entry_price=leg_data["entry_price"],
                expiry=expiry
            )
            strategy_legs.append(leg)
        
        # Calculate payoff
        return self.calculate_payoff(
            strategy_type, symbol, expiry, strategy_legs, spot_price
        )
    
    def calculate_payoff(
        self,
        strategy_type: StrategyType,
        symbol: str,
        expiry: date,
        legs: List[StrategyLeg],
        spot_price: float
    ) -> PayoffResult:
        """
        Calculate strategy payoff at various price points
        
        Requirements: 26.1, 26.2
        """
        # Generate price range
        min_price = spot_price * (1 - self.PRICE_RANGE_PERCENT)
        max_price = spot_price * (1 + self.PRICE_RANGE_PERCENT)
        price_step = (max_price - min_price) / (self.PRICE_POINTS - 1)
        
        prices = [min_price + i * price_step for i in range(self.PRICE_POINTS)]
        
        # Calculate payoff at each price
        payoff_by_price = {}
        
        for price in prices:
            total_payoff = 0.0
            
            for leg in legs:
                leg_payoff = self._calculate_leg_payoff(leg, price)
                total_payoff += leg_payoff
            
            payoff_by_price[price] = total_payoff
        
        # Calculate metrics
        payoffs = list(payoff_by_price.values())
        max_profit = max(payoffs) if payoffs else 0
        max_loss = min(payoffs) if payoffs else 0
        
        # Find breakeven points
        breakeven_points = self._find_breakeven_points(payoff_by_price)
        
        # Calculate margin
        margin_required = self._calculate_margin(legs)
        
        # Calculate net premium
        net_premium = sum(
            leg.entry_price * leg.quantity * (1 if leg.is_long() else -1)
            for leg in legs
        )
        
        return PayoffResult(
            strategy_type=strategy_type,
            symbol=symbol,
            expiry=expiry,
            payoff_by_price=payoff_by_price,
            prices_range=prices,
            max_profit=max_profit if max_profit > 0 else None,
            max_loss=abs(max_loss) if max_loss < 0 else None,
            breakeven_points=breakeven_points,
            margin_required=margin_required,
            net_premium_paid=net_premium,
            legs=legs
        )
    
    def _calculate_leg_payoff(self, leg: StrategyLeg, underlying_price: float) -> float:
        """Calculate payoff for a single leg at given underlying price"""
        if leg.is_call():
            intrinsic_value = max(0, underlying_price - leg.strike)
        else:
            intrinsic_value = max(0, leg.strike - underlying_price)
        
        if leg.is_long():
            # Long: payoff = intrinsic - premium paid
            return (intrinsic_value - leg.entry_price) * leg.quantity
        else:
            # Short: payoff = premium received - intrinsic
            return (leg.entry_price - intrinsic_value) * leg.quantity
    
    def _find_breakeven_points(self, payoff_by_price: Dict[float, float]) -> List[float]:
        """Find price points where payoff crosses zero"""
        breakevens = []
        prices = sorted(payoff_by_price.keys())
        
        for i in range(len(prices) - 1):
            price1 = prices[i]
            price2 = prices[i + 1]
            payoff1 = payoff_by_price[price1]
            payoff2 = payoff_by_price[price2]
            
            # Check if payoff crosses zero between these points
            if payoff1 * payoff2 < 0:
                # Linear interpolation to find exact crossing
                if abs(payoff2 - payoff1) > 0:
                    ratio = abs(payoff1) / abs(payoff2 - payoff1)
                    breakeven = price1 + (price2 - price1) * ratio
                    breakevens.append(breakeven)
        
        return sorted(breakevens)
    
    def _calculate_margin(self, legs: List[StrategyLeg]) -> float:
        """
        Calculate margin requirement for the strategy
        
        Requirements: 45.1, 45.2
        """
        margin = 0.0
        
        # Separate long and short legs
        long_legs = [leg for leg in legs if leg.is_long()]
        short_legs = [leg for leg in legs if not leg.is_long()]
        
        # For shorts, calculate margin
        for short_leg in short_legs:
            if short_leg.is_call():
                # Short call margin: (Strike * qty) + (Premium * qty)
                leg_margin = short_leg.strike * short_leg.quantity * 0.15  # 15% of strike
            else:
                # Short put margin: (Strike * qty) + (Premium * qty)
                leg_margin = short_leg.strike * short_leg.quantity * 0.15
            
            margin += leg_margin
        
        # For spreads, reduce margin
        if len(long_legs) > 0 and len(short_legs) > 0:
            # It's a spread - reduce margin
            margin = margin * 0.5
        
        return margin
    
    def create_predefined_strategy(
        self,
        strategy_type: StrategyType,
        symbol: str,
        expiry: date,
        spot_price: float,
        **kwargs
    ) -> PayoffResult:
        """
        Create a predefined strategy with common parameters
        
        Args:
            strategy_type: Type of strategy to create
            symbol: Underlying symbol
            expiry: Expiry date
            spot_price: Current spot price
            **kwargs: Strategy-specific parameters
        
        Returns:
            PayoffResult for the strategy
        """
        legs = []
        
        if strategy_type == StrategyType.STRADDLE:
            atm_strike = kwargs.get("strike", round(spot_price / 50) * 50)
            premium_call = kwargs.get("call_premium", 50)
            premium_put = kwargs.get("put_premium", 45)
            
            legs = [
                {"option_type": "CALL", "position_type": "LONG", "strike": atm_strike, 
                 "quantity": 1, "entry_price": premium_call},
                {"option_type": "PUT", "position_type": "LONG", "strike": atm_strike, 
                 "quantity": 1, "entry_price": premium_put},
            ]
        
        elif strategy_type == StrategyType.STRANGLE:
            otm_call_strike = kwargs.get("call_strike", round(spot_price * 1.02 / 50) * 50)
            otm_put_strike = kwargs.get("put_strike", round(spot_price * 0.98 / 50) * 50)
            premium_call = kwargs.get("call_premium", 35)
            premium_put = kwargs.get("put_premium", 30)
            
            legs = [
                {"option_type": "CALL", "position_type": "LONG", "strike": otm_call_strike, 
                 "quantity": 1, "entry_price": premium_call},
                {"option_type": "PUT", "position_type": "LONG", "strike": otm_put_strike, 
                 "quantity": 1, "entry_price": premium_put},
            ]
        
        elif strategy_type == StrategyType.BULL_CALL_SPREAD:
            lower_strike = kwargs.get("lower_strike", round(spot_price / 50) * 50)
            upper_strike = kwargs.get("upper_strike", lower_strike + 100)
            lower_premium = kwargs.get("lower_premium", 60)
            upper_premium = kwargs.get("upper_premium", 25)
            
            legs = [
                {"option_type": "CALL", "position_type": "LONG", "strike": lower_strike, 
                 "quantity": 1, "entry_price": lower_premium},
                {"option_type": "CALL", "position_type": "SHORT", "strike": upper_strike, 
                 "quantity": 1, "entry_price": upper_premium},
            ]
        
        elif strategy_type == StrategyType.IRON_CONDOR:
            atm_strike = round(spot_price / 50) * 50
            lower_put = kwargs.get("lower_put", atm_strike - 200)
            upper_put = kwargs.get("upper_put", atm_strike - 100)
            lower_call = kwargs.get("lower_call", atm_strike + 100)
            upper_call = kwargs.get("upper_call", atm_strike + 200)
            
            legs = [
                {"option_type": "PUT", "position_type": "SHORT", "strike": upper_put, 
                 "quantity": 1, "entry_price": 40},
                {"option_type": "PUT", "position_type": "LONG", "strike": lower_put, 
                 "quantity": 1, "entry_price": 15},
                {"option_type": "CALL", "position_type": "SHORT", "strike": lower_call, 
                 "quantity": 1, "entry_price": 45},
                {"option_type": "CALL", "position_type": "LONG", "strike": upper_call, 
                 "quantity": 1, "entry_price": 20},
            ]
        
        return self.build_strategy(strategy_type, symbol, expiry, legs, spot_price)
    
    def format_result(self, result: PayoffResult) -> Dict:
        """Format payoff result for API response"""
        return {
            "strategy_type": result.strategy_type.value,
            "symbol": result.symbol,
            "expiry": result.expiry.isoformat(),
            "metrics": {
                "max_profit": round(result.max_profit, 2) if result.max_profit else None,
                "max_loss": round(result.max_loss, 2) if result.max_loss else None,
                "breakeven_points": [round(bp, 2) for bp in result.breakeven_points],
                "margin_required": round(result.margin_required, 2),
                "net_premium_paid": round(result.net_premium_paid, 2),
                "risk_reward_ratio": round(result.max_profit / result.max_loss, 2) 
                    if (result.max_profit and result.max_loss and result.max_loss > 0) else None
            },
            "payoff_data": [
                {
                    "price": round(price, 2),
                    "payoff": round(payoff, 2)
                }
                for price, payoff in sorted(result.payoff_by_price.items())
            ],
            "legs": [
                {
                    "leg_number": leg.leg_number,
                    "option_type": leg.option_type.value,
                    "position_type": leg.position_type.value,
                    "strike": leg.strike,
                    "quantity": leg.quantity,
                    "entry_price": leg.entry_price
                }
                for leg in result.legs
            ]
        }
