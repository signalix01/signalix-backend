"""
Greeks Calculator

Calculates option Greeks using Black-Scholes model and Newton-Raphson for implied volatility.
Requirements: 38.1, 38.2, 38.3, 38.4, 38.5, 38.7
"""

import math
from dataclasses import dataclass
from typing import Optional, List
from datetime import date, datetime
from scipy.stats import norm
from scipy.optimize import newton


@dataclass
class BlackScholesGreeks:
    """Greeks calculation result"""
    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float
    implied_volatility: Optional[float] = None
    theoretical_price: Optional[float] = None


class GreeksCalculator:
    """
    Options Greeks calculator using Black-Scholes model
    
    Supports:
    - European options via Black-Scholes closed-form formulas
    - American options via Binomial Tree approximation
    - Implied volatility via Newton-Raphson method
    
    Requirements: 38.1, 38.2, 38.3, 38.4, 38.5, 38.7
    """
    
    # Default risk-free rate (RBI T-bill rate ~6%)
    DEFAULT_RISK_FREE_RATE = 0.06
    
    # Convergence tolerance for implied volatility
    IV_TOLERANCE = 1e-6
    MAX_IV_ITERATIONS = 100
    
    def __init__(self, risk_free_rate: float = DEFAULT_RISK_FREE_RATE):
        self.risk_free_rate = risk_free_rate
    
    def calculate_greeks(
        self,
        option_type: str,  # "CALL" or "PUT"
        strike: float,
        spot: float,
        time_to_expiry: float,  # in years
        implied_vol: float,
        market_price: Optional[float] = None
    ) -> BlackScholesGreeks:
        """
        Calculate all Greeks for an option
        
        Args:
            option_type: "CALL" or "PUT"
            strike: Strike price
            spot: Spot price
            time_to_expiry: Time to expiry in years
            implied_vol: Implied volatility (0.0 to 1.0)
            market_price: Market price (for IV calculation if vol not provided)
        
        Returns:
            BlackScholesGreeks with all calculated values
        
        Requirements: 38.1, 38.2, 38.3, 38.4, 38.5
        """
        # Calculate d1 and d2
        d1, d2 = self._calculate_d1_d2(
            spot, strike, time_to_expiry, implied_vol, self.risk_free_rate
        )
        
        # Calculate Greeks
        delta = self._calculate_delta(option_type, d1)
        gamma = self._calculate_gamma(spot, time_to_expiry, implied_vol, d1)
        theta = self._calculate_theta(option_type, spot, strike, time_to_expiry, implied_vol, d1, d2)
        vega = self._calculate_vega(spot, time_to_expiry, d1)
        rho = self._calculate_rho(option_type, strike, time_to_expiry, d2)
        
        # Calculate theoretical price
        theoretical_price = self._calculate_price(
            option_type, spot, strike, time_to_expiry, implied_vol, d1, d2
        )
        
        return BlackScholesGreeks(
            delta=delta,
            gamma=gamma,
            theta=theta,
            vega=vega,
            rho=rho,
            implied_volatility=implied_vol,
            theoretical_price=theoretical_price
        )
    
    def _calculate_d1_d2(
        self,
        spot: float,
        strike: float,
        time_to_expiry: float,
        volatility: float,
        risk_free_rate: float
    ) -> tuple:
        """Calculate d1 and d2 for Black-Scholes"""
        if time_to_expiry <= 0 or volatility <= 0:
            # Handle edge case
            if spot > strike:
                d1 = float('inf')
                d2 = float('inf')
            elif spot < strike:
                d1 = float('-inf')
                d2 = float('-inf')
            else:
                d1 = 0
                d2 = 0
            return d1, d2
        
        d1 = (math.log(spot / strike) + 
              (risk_free_rate + 0.5 * volatility ** 2) * time_to_expiry) / \
             (volatility * math.sqrt(time_to_expiry))
        
        d2 = d1 - volatility * math.sqrt(time_to_expiry)
        
        return d1, d2
    
    def _calculate_delta(self, option_type: str, d1: float) -> float:
        """Calculate Delta"""
        nd1 = norm.cdf(d1)
        
        if option_type.upper() == "CALL":
            return nd1
        else:  # PUT
            return nd1 - 1
    
    def _calculate_gamma(
        self,
        spot: float,
        time_to_expiry: float,
        volatility: float,
        d1: float
    ) -> float:
        """Calculate Gamma (same for calls and puts)"""
        if time_to_expiry <= 0 or volatility <= 0:
            return 0.0
        
        return norm.pdf(d1) / (spot * volatility * math.sqrt(time_to_expiry))
    
    def _calculate_theta(
        self,
        option_type: str,
        spot: float,
        strike: float,
        time_to_expiry: float,
        volatility: float,
        d1: float,
        d2: float
    ) -> float:
        """Calculate Theta (daily time decay)"""
        if time_to_expiry <= 0:
            return 0.0
        
        nd1 = norm.cdf(d1)
        nd2 = norm.cdf(d2)
        n_prime_d1 = norm.pdf(d1)
        
        common_term = -(spot * n_prime_d1 * volatility) / (2 * math.sqrt(time_to_expiry))
        
        if option_type.upper() == "CALL":
            theta = common_term - self.risk_free_rate * strike * math.exp(-self.risk_free_rate * time_to_expiry) * nd2
        else:  # PUT
            theta = common_term + self.risk_free_rate * strike * math.exp(-self.risk_free_rate * time_to_expiry) * (1 - nd2)
        
        return theta / 365  # Per day
    
    def _calculate_vega(
        self,
        spot: float,
        time_to_expiry: float,
        d1: float
    ) -> float:
        """Calculate Vega (sensitivity to 1% change in volatility)"""
        if time_to_expiry <= 0:
            return 0.0
        
        n_prime_d1 = norm.pdf(d1)
        vega = spot * n_prime_d1 * math.sqrt(time_to_expiry)
        return vega / 100  # Per 1% vol change
    
    def _calculate_rho(
        self,
        option_type: str,
        strike: float,
        time_to_expiry: float,
        d2: float
    ) -> float:
        """Calculate Rho (sensitivity to 1% interest rate change)"""
        if time_to_expiry <= 0:
            return 0.0
        
        nd2 = norm.cdf(d2)
        
        if option_type.upper() == "CALL":
            rho = strike * time_to_expiry * math.exp(-self.risk_free_rate * time_to_expiry) * nd2
        else:  # PUT
            rho = -strike * time_to_expiry * math.exp(-self.risk_free_rate * time_to_expiry) * (1 - nd2)
        
        return rho / 100  # Per 1% rate change
    
    def _calculate_price(
        self,
        option_type: str,
        spot: float,
        strike: float,
        time_to_expiry: float,
        volatility: float,
        d1: float,
        d2: float
    ) -> float:
        """Calculate theoretical option price"""
        if time_to_expiry <= 0:
            # At expiry
            if option_type.upper() == "CALL":
                return max(0, spot - strike)
            else:
                return max(0, strike - spot)
        
        nd1 = norm.cdf(d1)
        nd2 = norm.cdf(d2)
        
        if option_type.upper() == "CALL":
            price = spot * nd1 - strike * math.exp(-self.risk_free_rate * time_to_expiry) * nd2
        else:  # PUT
            price = strike * math.exp(-self.risk_free_rate * time_to_expiry) * (1 - nd2) - spot * (1 - nd1)
        
        return price
    
    def calculate_implied_volatility(
        self,
        option_type: str,
        strike: float,
        spot: float,
        time_to_expiry: float,
        market_price: float,
        initial_guess: float = 0.3
    ) -> Optional[float]:
        """
        Calculate implied volatility using Newton-Raphson method
        
        Args:
            option_type: "CALL" or "PUT"
            strike: Strike price
            spot: Spot price
            time_to_expiry: Time to expiry in years
            market_price: Observed market price
            initial_guess: Initial IV guess (default 30%)
        
        Returns:
            Implied volatility or None if calculation fails
        
        Requirements: 38.7
        """
        def price_diff(volatility):
            d1, d2 = self._calculate_d1_d2(
                spot, strike, time_to_expiry, volatility, self.risk_free_rate
            )
            return self._calculate_price(option_type, spot, strike, time_to_expiry, volatility, d1, d2) - market_price
        
        def vega_for_vol(volatility):
            d1, _ = self._calculate_d1_d2(
                spot, strike, time_to_expiry, volatility, self.risk_free_rate
            )
            return self._calculate_vega(spot, time_to_expiry, d1) * 100  # Scale back
        
        try:
            # Use Newton-Raphson method
            iv = newton(
                price_diff,
                initial_guess,
                fprime=vega_for_vol,
                tol=self.IV_TOLERANCE,
                maxiter=self.MAX_IV_ITERATIONS
            )
            
            # Sanity check
            if iv < 0 or iv > 5:  # IV > 500% is unrealistic
                return None
            
            return iv
            
        except Exception:
            return None
    
    def calculate_position_greeks(
        self,
        positions: List[dict]
    ) -> BlackScholesGreeks:
        """
        Calculate combined Greeks for multi-leg option positions
        
        Args:
            positions: List of dicts with keys:
                - option_type: "CALL" or "PUT"
                - strike: float
                - quantity: int (positive for long, negative for short)
                - greeks: BlackScholesGreeks object
        
        Returns:
            Combined Greeks
        
        Requirements: 38.9
        """
        total_delta = 0.0
        total_gamma = 0.0
        total_theta = 0.0
        total_vega = 0.0
        total_rho = 0.0
        
        for position in positions:
            greeks = position["greeks"]
            quantity = position["quantity"]
            
            # For shorts, multiply by -1
            multiplier = quantity
            
            total_delta += greeks.delta * multiplier
            total_gamma += greeks.gamma * multiplier
            total_theta += greeks.theta * multiplier
            total_vega += greeks.vega * multiplier
            total_rho += greeks.rho * multiplier
        
        return BlackScholesGreeks(
            delta=total_delta,
            gamma=total_gamma,
            theta=total_theta,
            vega=total_vega,
            rho=total_rho
        )
    
    def calculate_binomial_american(
        self,
        option_type: str,
        strike: float,
        spot: float,
        time_to_expiry: float,
        volatility: float,
        steps: int = 100
    ) -> BlackScholesGreeks:
        """
        Calculate price and Greeks for American options using Binomial Tree
        
        Requirements: 38.8
        """
        dt = time_to_expiry / steps
        u = math.exp(volatility * math.sqrt(dt))
        d = 1 / u
        p = (math.exp(self.risk_free_rate * dt) - d) / (u - d)
        
        # Build stock price tree
        stock_tree = [[0.0 for _ in range(i + 1)] for i in range(steps + 1)]
        stock_tree[0][0] = spot
        
        for i in range(1, steps + 1):
            for j in range(i + 1):
                stock_tree[i][j] = spot * (u ** j) * (d ** (i - j))
        
        # Calculate option values at expiry
        option_tree = [[0.0 for _ in range(i + 1)] for i in range(steps + 1)]
        
        for j in range(steps + 1):
            if option_type.upper() == "CALL":
                option_tree[steps][j] = max(0, stock_tree[steps][j] - strike)
            else:
                option_tree[steps][j] = max(0, strike - stock_tree[steps][j])
        
        # Backward induction
        for i in range(steps - 1, -1, -1):
            for j in range(i + 1):
                hold_value = math.exp(-self.risk_free_rate * dt) * (
                    p * option_tree[i + 1][j + 1] + (1 - p) * option_tree[i + 1][j]
                )
                
                if option_type.upper() == "CALL":
                    exercise_value = max(0, stock_tree[i][j] - strike)
                else:
                    exercise_value = max(0, strike - stock_tree[i][j])
                
                option_tree[i][j] = max(hold_value, exercise_value)
        
        price = option_tree[0][0]
        
        # Approximate Greeks using finite differences
        delta = (option_tree[1][1] - option_tree[1][0]) / (spot * (u - d))
        
        return BlackScholesGreeks(
            delta=delta,
            gamma=0.0,  # Would need more steps for accurate gamma
            theta=(option_tree[1][0] - option_tree[0][0]) / dt / 365,
            vega=0.0,  # Would need recalculation with different vol
            rho=0.0,   # Would need recalculation with different rate
            implied_volatility=volatility,
            theoretical_price=price
        )
