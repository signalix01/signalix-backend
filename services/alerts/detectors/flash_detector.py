"""
Flash Crash/Rally Detector

Implements real-time flash crash and flash rally detection using sliding window analysis.
Requirements: 11.6

Algorithm:
- Monitors tick data in a 5-minute sliding window
- Detects price moves > 5% from any point in the window
- Uses Redis sorted sets for efficient tick data storage (10-minute TTL)
- Generates CRITICAL severity events for both flash crashes and rallies

Detection Logic:
- Flash Crash: Price drops > 5% from the highest point in the last 5 minutes
- Flash Rally: Price rises > 5% from the lowest point in the last 5 minutes

Redis Integration (for production use):
The detector is designed to work with tick data stored in Redis sorted sets:
- Key pattern: `ticks:{instrument}` (e.g., `ticks:BANKNIFTY`)
- Score: Unix timestamp in milliseconds
- Value: JSON-encoded tick data (price, volume, timestamp)
- TTL: 10 minutes (600 seconds) to automatically expire old data
- The AnomalyOrchestrator (task 31) will handle Redis integration and call this detector

Example Redis commands:
  ZADD ticks:BANKNIFTY 1704960000000 '{"price": 45000.0, "volume": 1000}'
  ZRANGEBYSCORE ticks:BANKNIFTY -inf +inf WITHSCORES
  EXPIRE ticks:BANKNIFTY 600
"""

from typing import List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass
import uuid

from shared.database.models import AnomalyEvent, AnomalyType, AnomalySeverity


@dataclass
class TickData:
    """
    Represents a single tick (trade) data point.
    
    Attributes:
        timestamp: ISO timestamp string or datetime object
        price: Trade price
        volume: Trade volume (optional)
        instrument: Instrument symbol
    """
    timestamp: datetime
    price: float
    volume: Optional[float] = None
    instrument: Optional[str] = None


class FlashDetector:
    """
    Flash crash/rally detector using sliding window analysis on tick data.
    
    Detects rapid price movements (> 5% in < 5 minutes) that indicate
    flash crashes (sudden drops) or flash rallies (sudden spikes).
    
    All detected events are marked as CRITICAL severity as they represent
    extreme market conditions requiring immediate attention.
    """
    
    def __init__(self, threshold_pct: float = 5.0, window_minutes: int = 5):
        """
        Initialize the Flash Detector.
        
        Args:
            threshold_pct: Percentage move threshold for detection (default: 5.0%)
            window_minutes: Time window in minutes for analysis (default: 5)
        """
        self.threshold_pct = threshold_pct
        self.window_minutes = window_minutes
        self.threshold_fraction = threshold_pct / 100.0
    
    def check(self, ticks: List[TickData], window_minutes: Optional[int] = None) -> Optional[AnomalyEvent]:
        """
        Check tick data for flash crash or flash rally events.
        
        Analyzes the provided tick data to detect if the price has moved
        more than the threshold percentage from any point in the window.
        
        Args:
            ticks: List of TickData objects, should be sorted by timestamp (oldest first)
            window_minutes: Override the default window size (optional)
        
        Returns:
            AnomalyEvent if a flash crash/rally is detected, None otherwise
        """
        if not ticks or len(ticks) < 2:
            # Need at least 2 ticks to detect a movement
            return None
        
        window_min = window_minutes if window_minutes is not None else self.window_minutes
        
        # Get the most recent tick (current price)
        current_tick = ticks[-1]
        current_price = current_tick.price
        current_time = current_tick.timestamp
        
        # Calculate the window start time
        window_start = current_time - timedelta(minutes=window_min)
        
        # Filter ticks within the window
        window_ticks = [t for t in ticks if t.timestamp >= window_start]
        
        if len(window_ticks) < 2:
            # Not enough data in the window
            return None
        
        # Find the highest and lowest prices in the window
        prices = [t.price for t in window_ticks]
        highest_price = max(prices)
        lowest_price = min(prices)
        
        # Find when the highest and lowest prices occurred
        highest_tick = next(t for t in window_ticks if t.price == highest_price)
        lowest_tick = next(t for t in window_ticks if t.price == lowest_price)
        
        # Calculate percentage moves from extremes
        drop_from_high = (highest_price - current_price) / highest_price
        rise_from_low = (current_price - lowest_price) / lowest_price
        
        # Check for flash crash (drop > threshold from high)
        if drop_from_high > self.threshold_fraction:
            return self._create_flash_crash_event(
                current_tick=current_tick,
                highest_price=highest_price,
                highest_time=highest_tick.timestamp,
                drop_pct=drop_from_high * 100,
                window_minutes=window_min,
                window_ticks=len(window_ticks)
            )
        
        # Check for flash rally (rise > threshold from low)
        if rise_from_low > self.threshold_fraction:
            return self._create_flash_rally_event(
                current_tick=current_tick,
                lowest_price=lowest_price,
                lowest_time=lowest_tick.timestamp,
                rise_pct=rise_from_low * 100,
                window_minutes=window_min,
                window_ticks=len(window_ticks)
            )
        
        # No flash event detected
        return None
    
    def _create_flash_crash_event(
        self,
        current_tick: TickData,
        highest_price: float,
        highest_time: datetime,
        drop_pct: float,
        window_minutes: int,
        window_ticks: int
    ) -> AnomalyEvent:
        """Create an AnomalyEvent for a flash crash."""
        time_elapsed = (current_tick.timestamp - highest_time).total_seconds() / 60.0
        
        description = (
            f"Flash crash detected: price dropped {drop_pct:.2f}% "
            f"from {highest_price:.2f} to {current_tick.price:.2f} "
            f"in {time_elapsed:.1f} minutes"
        )
        
        return AnomalyEvent(
            id=uuid.uuid4(),
            instrument=current_tick.instrument or "UNKNOWN",
            asset_class="equity",  # Default, should be provided by caller
            exchange=None,
            anomaly_type=AnomalyType.FLASH_CRASH,
            severity=AnomalySeverity.CRITICAL,
            detected_at=current_tick.timestamp,
            description=description,
            z_score=None,  # Not applicable for flash detection
            price=current_tick.price,
            volume=current_tick.volume,
            raw_data={
                "flash_type": "crash",
                "current_price": current_tick.price,
                "highest_price": highest_price,
                "highest_time": highest_time.isoformat(),
                "drop_pct": drop_pct,
                "time_elapsed_minutes": time_elapsed,
                "window_minutes": window_minutes,
                "window_ticks": window_ticks,
                "threshold_pct": self.threshold_pct
            }
        )
    
    def _create_flash_rally_event(
        self,
        current_tick: TickData,
        lowest_price: float,
        lowest_time: datetime,
        rise_pct: float,
        window_minutes: int,
        window_ticks: int
    ) -> AnomalyEvent:
        """Create an AnomalyEvent for a flash rally."""
        time_elapsed = (current_tick.timestamp - lowest_time).total_seconds() / 60.0
        
        description = (
            f"Flash rally detected: price rose {rise_pct:.2f}% "
            f"from {lowest_price:.2f} to {current_tick.price:.2f} "
            f"in {time_elapsed:.1f} minutes"
        )
        
        return AnomalyEvent(
            id=uuid.uuid4(),
            instrument=current_tick.instrument or "UNKNOWN",
            asset_class="equity",  # Default, should be provided by caller
            exchange=None,
            anomaly_type=AnomalyType.FLASH_RALLY,
            severity=AnomalySeverity.CRITICAL,
            detected_at=current_tick.timestamp,
            description=description,
            z_score=None,  # Not applicable for flash detection
            price=current_tick.price,
            volume=current_tick.volume,
            raw_data={
                "flash_type": "rally",
                "current_price": current_tick.price,
                "lowest_price": lowest_price,
                "lowest_time": lowest_time.isoformat(),
                "rise_pct": rise_pct,
                "time_elapsed_minutes": time_elapsed,
                "window_minutes": window_minutes,
                "window_ticks": window_ticks,
                "threshold_pct": self.threshold_pct
            }
        )
    
    def check_with_metadata(
        self,
        ticks: List[TickData],
        instrument: str,
        asset_class: str = "equity",
        exchange: Optional[str] = None,
        window_minutes: Optional[int] = None
    ) -> Optional[AnomalyEvent]:
        """
        Check tick data for flash events with full metadata.
        
        This is a convenience method that ensures the returned AnomalyEvent
        has complete instrument metadata.
        
        Args:
            ticks: List of TickData objects
            instrument: Instrument symbol
            asset_class: Asset class (equity, fo, crypto, etc.)
            exchange: Exchange name (NSE, BSE, etc.)
            window_minutes: Override the default window size (optional)
        
        Returns:
            AnomalyEvent with complete metadata if detected, None otherwise
        """
        event = self.check(ticks, window_minutes)
        
        if event:
            # Update metadata
            event.instrument = instrument
            event.asset_class = asset_class
            event.exchange = exchange
        
        return event
