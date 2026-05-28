"""
Volatility Surface Calculator

3D IV surface calculation and analysis.
Mirrors OpenAlgo's vol_surface_service.py functionality.

Requirements: Volatility Surface analysis for options
"""

import numpy as np
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, date
from dataclasses import dataclass
from scipy import interpolate
from scipy.stats import norm
import logging

logger = logging.getLogger(__name__)


@dataclass
class VolPoint:
    """Volatility point on the surface"""
    strike: float
    expiry_days: int
    implied_vol: float
    moneyness: float  # Strike / Spot


@dataclass
class VolSlice:
    """Volatility slice for a specific expiry"""
    expiry_date: date
    days_to_expiry: int
    points: List[VolPoint]
    atm_vol: float
    skew_25d: float  # 25 delta put-call vol difference
    skew_10d: float  # 10 delta put-call vol difference


class VolatilitySurfaceCalculator:
    """
    Volatility Surface Calculator for 3D IV analysis.
    
    Features:
    - ATM volatility calculation per expiry
    - Volatility smile/skew analysis
    - Term structure analysis
    - Surface interpolation
    - Risk neutral density estimation
    """
    
    def __init__(self):
        self.cache = {}
    
    def calculate_surface(
        self,
        symbol: str,
        spot_price: float,
        options_data: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Calculate full volatility surface from options chain data.
        
        Args:
            symbol: Trading symbol
            spot_price: Current spot price
            options_data: List of option strikes with prices
            
        Returns:
            Volatility surface data with slices and metrics
        """
        try:
            # Group by expiry
            expiry_groups = self._group_by_expiry(options_data)
            
            slices = []
            for expiry_date, strikes in expiry_groups.items():
                days_to_expiry = (expiry_date - date.today()).days
                if days_to_expiry <= 0:
                    continue
                
                slice_data = self._calculate_slice(
                    expiry_date,
                    days_to_expiry,
                    spot_price,
                    strikes
                )
                slices.append(slice_data)
            
            # Sort by expiry
            slices.sort(key=lambda s: s.days_to_expiry)
            
            # Calculate term structure
            term_structure = self._calculate_term_structure(slices)
            
            # Calculate surface metrics
            surface_metrics = self._calculate_surface_metrics(slices)
            
            # Generate interpolated surface grid
            surface_grid = self._generate_surface_grid(slices)
            
            return {
                "symbol": symbol,
                "spot_price": spot_price,
                "calculated_at": datetime.utcnow().isoformat(),
                "slices": [
                    {
                        "expiry_date": s.expiry_date.isoformat(),
                        "days_to_expiry": s.days_to_expiry,
                        "atm_volatility": s.atm_vol,
                        "skew_25d": s.skew_25d,
                        "skew_10d": s.skew_10d,
                        "points": [
                            {
                                "strike": p.strike,
                                "moneyness": p.moneyness,
                                "implied_vol": p.implied_vol
                            }
                            for p in s.points
                        ]
                    }
                    for s in slices
                ],
                "term_structure": term_structure,
                "surface_metrics": surface_metrics,
                "surface_grid": surface_grid,
                "summary": {
                    "total_slices": len(slices),
                    "atm_vol_range": [
                        min(s.atm_vol for s in slices) if slices else 0,
                        max(s.atm_vol for s in slices) if slices else 0
                    ],
                    "avg_skew_25d": np.mean([s.skew_25d for s in slices]) if slices else 0
                }
            }
            
        except Exception as e:
            logger.error(f"Error calculating volatility surface: {e}")
            return {
                "symbol": symbol,
                "error": str(e),
                "spot_price": spot_price,
                "calculated_at": datetime.utcnow().isoformat()
            }
    
    def _group_by_expiry(
        self,
        options_data: List[Dict[str, Any]]
    ) -> Dict[date, List[Dict[str, Any]]]:
        """Group options data by expiry date."""
        groups = {}
        for opt in options_data:
            expiry = opt.get("expiry_date")
            if isinstance(expiry, str):
                expiry = datetime.strptime(expiry, "%Y-%m-%d").date()
            
            if expiry not in groups:
                groups[expiry] = []
            groups[expiry].append(opt)
        
        return groups
    
    def _calculate_slice(
        self,
        expiry_date: date,
        days_to_expiry: int,
        spot_price: float,
        strikes: List[Dict[str, Any]]
    ) -> VolSlice:
        """Calculate volatility slice for a single expiry."""
        points = []
        
        # Calculate IV for each strike
        for strike_data in strikes:
            strike = strike_data.get("strike_price", strike_data.get("strike"))
            
            # Get call and put data
            call_ltp = strike_data.get("call_ltp", strike_data.get("call_price", 0))
            put_ltp = strike_data.get("put_ltp", strike_data.get("put_price", 0))
            
            # Calculate IV for both call and put
            tte = days_to_expiry / 365.0
            
            call_iv = self._calculate_iv(
                spot_price, strike, tte, call_ltp, "call"
            ) if call_ltp > 0 else 0
            
            put_iv = self._calculate_iv(
                spot_price, strike, tte, put_ltp, "put"
            ) if put_ltp > 0 else 0
            
            # Use average of call and put IV
            avg_iv = (call_iv + put_iv) / 2 if call_iv > 0 and put_iv > 0 else max(call_iv, put_iv)
            
            if avg_iv > 0:
                points.append(VolPoint(
                    strike=strike,
                    expiry_days=days_to_expiry,
                    implied_vol=avg_iv,
                    moneyness=strike / spot_price
                ))
        
        # Sort by strike
        points.sort(key=lambda p: p.strike)
        
        # Calculate ATM vol (closest to spot)
        atm_point = min(points, key=lambda p: abs(p.moneyness - 1.0)) if points else None
        atm_vol = atm_point.implied_vol if atm_point else 0.25
        
        # Calculate skew
        skew_25d = self._calculate_delta_skew(points, 0.25, spot_price, days_to_expiry)
        skew_10d = self._calculate_delta_skew(points, 0.10, spot_price, days_to_expiry)
        
        return VolSlice(
            expiry_date=expiry_date,
            days_to_expiry=days_to_expiry,
            points=points,
            atm_vol=atm_vol,
            skew_25d=skew_25d,
            skew_10d=skew_10d
        )
    
    def _calculate_iv(
        self,
        spot: float,
        strike: float,
        tte: float,
        price: float,
        option_type: str
    ) -> float:
        """Calculate implied volatility using Newton-Raphson method."""
        try:
            # Initial guess
            iv = 0.25
            
            for _ in range(100):
                d1 = (np.log(spot / strike) + (0.5 * iv ** 2) * tte) / (iv * np.sqrt(tte))
                d2 = d1 - iv * np.sqrt(tte)
                
                if option_type == "call":
                    price_calc = spot * norm.cdf(d1) - strike * norm.cdf(d2)
                    vega = spot * norm.pdf(d1) * np.sqrt(tte)
                else:
                    price_calc = strike * norm.cdf(-d2) - spot * norm.cdf(-d1)
                    vega = spot * norm.pdf(d1) * np.sqrt(tte)
                
                if abs(vega) < 1e-10:
                    break
                
                diff = price_calc - price
                if abs(diff) < 1e-6:
                    break
                
                iv = iv - diff / vega
                
                if iv <= 0:
                    iv = 0.001
                if iv > 5:
                    iv = 5
            
            return iv
            
        except Exception as e:
            logger.warning(f"IV calculation failed: {e}")
            return 0
    
    def _calculate_delta_skew(
        self,
        points: List[VolPoint],
        delta_target: float,
        spot: float,
        days: int
    ) -> float:
        """Calculate volatility skew at a specific delta."""
        if not points:
            return 0
        
        # Approximate delta from moneyness
        # Delta ≈ N(d1), where d1 depends on moneyness and vol
        
        # Find puts and calls at roughly target delta
        # 25 delta put ≈ 0.75 moneyness, 25 delta call ≈ 1.25 moneyness
        if delta_target == 0.25:
            put_moneyness_target = 0.95
            call_moneyness_target = 1.05
        elif delta_target == 0.10:
            put_moneyness_target = 0.90
            call_moneyness_target = 1.10
        else:
            put_moneyness_target = 1.0 - delta_target
            call_moneyness_target = 1.0 + delta_target
        
        put_point = min(
            [p for p in points if p.moneyness <= 1.0] or points,
            key=lambda p: abs(p.moneyness - put_moneyness_target)
        )
        
        call_point = min(
            [p for p in points if p.moneyness >= 1.0] or points,
            key=lambda p: abs(p.moneyness - call_moneyness_target)
        )
        
        # Skew = Put IV - Call IV (usually positive)
        return put_point.implied_vol - call_point.implied_vol
    
    def _calculate_term_structure(
        self,
        slices: List[VolSlice]
    ) -> Dict[str, Any]:
        """Calculate volatility term structure."""
        if not slices:
            return {}
        
        days = [s.days_to_expiry for s in slices]
        atm_vols = [s.atm_vol for s in slices]
        
        return {
            "shape": "contango" if atm_vols[-1] > atm_vols[0] else "backwardation",
            "short_term_vol": atm_vols[0],
            "long_term_vol": atm_vols[-1],
            "term_premium": atm_vols[-1] - atm_vols[0],
            "days_to_expiry": days,
            "atm_volatilities": atm_vols
        }
    
    def _calculate_surface_metrics(
        self,
        slices: List[VolSlice]
    ) -> Dict[str, Any]:
        """Calculate overall surface metrics."""
        if not slices:
            return {}
        
        all_vols = [p.implied_vol for s in slices for p in s.points]
        
        return {
            "min_volatility": min(all_vols) if all_vols else 0,
            "max_volatility": max(all_vols) if all_vols else 0,
            "avg_volatility": np.mean(all_vols) if all_vols else 0,
            "volatility_std": np.std(all_vols) if all_vols else 0,
            "avg_skew_25d": np.mean([s.skew_25d for s in slices]),
            "avg_skew_10d": np.mean([s.skew_10d for s in slices]),
            "surface_area": len(slices) * len(slices[0].points) if slices else 0
        }
    
    def _generate_surface_grid(
        self,
        slices: List[VolSlice],
        grid_size: int = 20
    ) -> Dict[str, Any]:
        """Generate interpolated surface grid for visualization."""
        if not slices or not slices[0].points:
            return {}
        
        # Extract data points
        days = []
        moneyness = []
        vols = []
        
        for s in slices:
            for p in s.points:
                days.append(s.days_to_expiry)
                moneyness.append(p.moneyness)
                vols.append(p.implied_vol)
        
        if len(days) < 4:
            return {
                "days": days,
                "moneyness": moneyness,
                "volatilities": vols
            }
        
        try:
            # Create grid
            days_grid = np.linspace(min(days), max(days), grid_size)
            moneyness_grid = np.linspace(min(moneyness), max(moneyness), grid_size)
            
            # Interpolate
            points = np.array([[d, m] for d, m in zip(days, moneyness)])
            values = np.array(vols)
            
            grid_x, grid_y = np.meshgrid(days_grid, moneyness_grid)
            
            # Use linear interpolation
            grid_z = interpolate.griddata(points, values, (grid_x, grid_y), method='linear')
            
            # Fill NaN with nearest
            grid_z = np.nan_to_num(grid_z, nan=np.mean(values))
            
            return {
                "days_grid": days_grid.tolist(),
                "moneyness_grid": moneyness_grid.tolist(),
                "volatility_surface": grid_z.tolist()
            }
            
        except Exception as e:
            logger.warning(f"Surface grid generation failed: {e}")
            return {
                "days": days,
                "moneyness": moneyness,
                "volatilities": vols
            }
    
    def get_volatility_for_strike_expiry(
        self,
        surface: Dict[str, Any],
        strike: float,
        days_to_expiry: int,
        spot_price: float
    ) -> Optional[float]:
        """Get interpolated volatility for a specific strike and expiry."""
        try:
            moneyness = strike / spot_price
            
            # Find nearest slice
            slices = surface.get("slices", [])
            if not slices:
                return None
            
            nearest_slice = min(slices, key=lambda s: abs(s["days_to_expiry"] - days_to_expiry))
            
            # Find or interpolate vol for moneyness
            points = nearest_slice.get("points", [])
            if not points:
                return nearest_slice.get("atm_volatility", 0.25)
            
            # Simple linear interpolation
            sorted_points = sorted(points, key=lambda p: p["moneyness"])
            
            for i in range(len(sorted_points) - 1):
                p1, p2 = sorted_points[i], sorted_points[i + 1]
                if p1["moneyness"] <= moneyness <= p2["moneyness"]:
                    # Linear interpolation
                    t = (moneyness - p1["moneyness"]) / (p2["moneyness"] - p1["moneyness"])
                    return p1["implied_vol"] + t * (p2["implied_vol"] - p1["implied_vol"])
            
            # Return nearest if out of range
            nearest = min(points, key=lambda p: abs(p["moneyness"] - moneyness))
            return nearest["implied_vol"]
            
        except Exception as e:
            logger.warning(f"Volatility lookup failed: {e}")
            return None
