"""
OI (Open Interest) Tracker

Tracks open interest changes across option strikes to identify
institutional positioning and sentiment shifts.

Requirements: 6.1, 6.2, 6.3, 6.5, 6.6
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any
from enum import Enum as PyEnum


class OIPattern(str, PyEnum):
    """Open Interest change patterns"""
    BULLISH_BUILDUP = "BULLISH_BUILDUP"
    BEARISH_BUILDUP = "BEARISH_BUILDUP"
    BULLISH_UNWINDING = "BULLISH_UNWINDING"
    BEARISH_UNWINDING = "BEARISH_UNWINDING"
    NEUTRAL = "NEUTRAL"


@dataclass
class OIChange:
    """OI change data for a strike"""
    symbol: str
    expiry_date: Any  # date
    strike: float
    option_type: str  # "CALL" or "PUT"
    current_oi: int
    previous_oi: int
    absolute_change: int
    percent_change: float
    pattern: OIPattern
    price_change: float  # Underlying price change during interval
    interval: str  # "1m", "5m", "1h", "1d"
    calculated_at: datetime


@dataclass
class OIAlert:
    """Alert for significant OI change"""
    symbol: str
    alert_type: str
    message: str
    changes: List[OIChange]
    severity: str  # "info", "warning", "critical"
    created_at: datetime


class OITracker:
    """
    Open Interest Tracker
    
    Monitors OI changes to identify:
    - Institutional positioning
    - Sentiment shifts
    - Buildup and unwinding patterns
    - Significant OI changes for alerts
    
    Requirements: 6.1, 6.2, 6.3, 6.5, 6.6
    """
    
    # Default alert threshold (10%)
    DEFAULT_ALERT_THRESHOLD = 10.0
    
    # Time intervals supported
    INTERVALS = ["1m", "5m", "15m", "1h", "4h", "1d"]
    
    def __init__(self, alert_threshold: float = DEFAULT_ALERT_THRESHOLD):
        self.alert_threshold = alert_threshold
        self._oi_history: Dict[str, Dict] = {}  # Cache for OI history
    
    def track_oi_changes(
        self,
        symbol: str,
        expiry_date: Any,
        current_data: List[Dict],
        previous_data: List[Dict],
        price_change: float = 0.0,
        interval: str = "5m"
    ) -> List[OIChange]:
        """
        Track OI changes across all strikes
        
        Args:
            symbol: Underlying symbol
            expiry_date: Option expiry date
            current_data: Current OI data with strike, option_type, oi
            previous_data: Previous OI data
            price_change: Change in underlying price during interval
            interval: Time interval string
        
        Returns:
            List of OIChange objects
        
        Requirements: 6.1, 6.2, 6.3
        """
        changes = []
        
        # Build lookup for previous data
        prev_lookup = {}
        for data in previous_data:
            key = (data["strike"], data["option_type"])
            prev_lookup[key] = data.get("oi", 0)
        
        # Calculate changes
        for data in current_data:
            strike = data["strike"]
            option_type = data["option_type"]
            current_oi = data.get("oi", 0)
            
            key = (strike, option_type)
            previous_oi = prev_lookup.get(key, 0)
            
            # Calculate change
            abs_change = current_oi - previous_oi
            pct_change = (abs_change / previous_oi * 100) if previous_oi > 0 else 0.0
            
            # Identify pattern
            pattern = self.classify_pattern(abs_change, price_change, option_type)
            
            change = OIChange(
                symbol=symbol,
                expiry_date=expiry_date,
                strike=strike,
                option_type=option_type,
                current_oi=current_oi,
                previous_oi=previous_oi,
                absolute_change=abs_change,
                percent_change=pct_change,
                pattern=pattern,
                price_change=price_change,
                interval=interval,
                calculated_at=datetime.utcnow()
            )
            
            changes.append(change)
        
        return changes
    
    def classify_pattern(
        self,
        oi_change: int,
        price_change: float,
        option_type: str
    ) -> OIPattern:
        """
        Classify OI change pattern
        
        Requirements: 6.5
        """
        if abs(oi_change) < 100:  # Minimal change
            return OIPattern.NEUTRAL
        
        oi_increasing = oi_change > 0
        price_increasing = price_change > 0
        
        if option_type == "CALL":
            # Call OI buildup with price increase = bullish
            if oi_increasing and price_increasing:
                return OIPattern.BULLISH_BUILDUP
            # Call OI buildup with price decrease = bearish
            elif oi_increasing and not price_increasing:
                return OIPattern.BEARISH_BUILDUP
            # Call OI unwinding with price increase = bearish
            elif not oi_increasing and price_increasing:
                return OIPattern.BEARISH_UNWINDING
            # Call OI unwinding with price decrease = bullish
            else:
                return OIPattern.BULLISH_UNWINDING
        else:  # PUT
            # Put OI buildup with price decrease = bullish
            if oi_increasing and not price_increasing:
                return OIPattern.BULLISH_BUILDUP
            # Put OI buildup with price increase = bearish
            elif oi_increasing and price_increasing:
                return OIPattern.BEARISH_BUILDUP
            # Put OI unwinding with price decrease = bearish
            elif not oi_increasing and not price_increasing:
                return OIPattern.BEARISH_UNWINDING
            # Put OI unwinding with price increase = bullish
            else:
                return OIPattern.BULLISH_UNWINDING
    
    def generate_alerts(
        self,
        changes: List[OIChange],
        threshold: Optional[float] = None
    ) -> List[OIAlert]:
        """
        Generate alerts for significant OI changes
        
        Requirements: 6.6
        """
        threshold = threshold or self.alert_threshold
        alerts = []
        
        # Filter significant changes
        significant_changes = [
            c for c in changes 
            if abs(c.percent_change) >= threshold
        ]
        
        if not significant_changes:
            return alerts
        
        # Group by pattern
        pattern_groups: Dict[OIPattern, List[OIChange]] = {}
        for change in significant_changes:
            if change.pattern not in pattern_groups:
                pattern_groups[change.pattern] = []
            pattern_groups[change.pattern].append(change)
        
        # Generate alerts for each significant pattern
        for pattern, pattern_changes in pattern_groups.items():
            if len(pattern_changes) >= 2:  # Multiple strikes showing same pattern
                # Sort by absolute change
                pattern_changes.sort(key=lambda x: abs(x.absolute_change), reverse=True)
                
                # Get top changes
                top_changes = pattern_changes[:5]
                strikes_str = ", ".join([f"{c.strike:.0f}" for c in top_changes])
                
                if pattern == OIPattern.BULLISH_BUILDUP:
                    alert_type = "bullish_buildup"
                    message = f"Bullish buildup detected at strikes {strikes_str}. OI increasing with price rise."
                    severity = "warning"
                elif pattern == OIPattern.BEARISH_BUILDUP:
                    alert_type = "bearish_buildup"
                    message = f"Bearish buildup detected at strikes {strikes_str}. OI increasing with price fall."
                    severity = "warning"
                elif pattern == OIPattern.BULLISH_UNWINDING:
                    alert_type = "bullish_unwinding"
                    message = f"Short covering detected at strikes {strikes_str}. OI decreasing with price rise."
                    severity = "info"
                elif pattern == OIPattern.BEARISH_UNWINDING:
                    alert_type = "bearish_unwinding"
                    message = f"Long unwinding detected at strikes {strikes_str}. OI decreasing with price fall."
                    severity = "info"
                else:
                    continue
                
                alert = OIAlert(
                    symbol=top_changes[0].symbol,
                    alert_type=alert_type,
                    message=message,
                    changes=top_changes,
                    severity=severity,
                    created_at=datetime.utcnow()
                )
                
                alerts.append(alert)
        
        return alerts
    
    def get_top_buildup(
        self,
        changes: List[OIChange],
        top_n: int = 5
    ) -> Tuple[List[OIChange], List[OIChange]]:
        """
        Get top OI buildup and unwinding strikes
        
        Returns:
            Tuple of (top_buildup, top_unwinding)
        """
        # Filter for significant patterns
        buildup = [c for c in changes if c.pattern in [
            OIPattern.BULLISH_BUILDUP, OIPattern.BEARISH_BUILDUP
        ]]
        unwinding = [c for c in changes if c.pattern in [
            OIPattern.BULLISH_UNWINDING, OIPattern.BEARISH_UNWINDING
        ]]
        
        # Sort by absolute change
        buildup.sort(key=lambda x: x.absolute_change, reverse=True)
        unwinding.sort(key=lambda x: abs(x.absolute_change), reverse=True)
        
        return buildup[:top_n], unwinding[:top_n]
    
    def calculate_pcr(
        self,
        call_oi: int,
        put_oi: int
    ) -> float:
        """Calculate Put-Call Ratio"""
        if call_oi == 0:
            return float('inf') if put_oi > 0 else 0.0
        return put_oi / call_oi
    
    def format_change(self, change: OIChange) -> Dict:
        """Format OI change for API response"""
        return {
            "symbol": change.symbol,
            "expiry_date": change.expiry_date.isoformat() if hasattr(change.expiry_date, 'isoformat') else str(change.expiry_date),
            "strike": change.strike,
            "option_type": change.option_type,
            "current_oi": change.current_oi,
            "previous_oi": change.previous_oi,
            "absolute_change": change.absolute_change,
            "percent_change": round(change.percent_change, 2),
            "pattern": change.pattern.value,
            "price_change": round(change.price_change, 4),
            "interval": change.interval,
            "calculated_at": change.calculated_at.isoformat()
        }
    
    def format_alert(self, alert: OIAlert) -> Dict:
        """Format OI alert for API response"""
        return {
            "symbol": alert.symbol,
            "alert_type": alert.alert_type,
            "message": alert.message,
            "changes": [self.format_change(c) for c in alert.changes],
            "severity": alert.severity,
            "created_at": alert.created_at.isoformat()
        }
