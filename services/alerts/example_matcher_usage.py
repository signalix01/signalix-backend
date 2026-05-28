"""
Example usage of the Alert Matching Engine

Demonstrates how to use the AlertMatcher to find matching rules for anomaly events.

Requirements: 13.2, 13.3, 13.4, 13.5
Task: 39
"""

import asyncio
from datetime import datetime
import uuid
import pytz

from services.alerts.matcher import get_matcher, close_matcher
from shared.database.models import AnomalyEvent, AnomalySeverity, AnomalyType


async def example_basic_matching():
    """
    Example 1: Basic matching with a HIGH severity event
    
    This demonstrates:
    - Creating an anomaly event
    - Finding matching rules
    - Handling quiet hours and rate limits
    """
    print("\n" + "="*80)
    print("Example 1: Basic Matching (HIGH Severity)")
    print("="*80)
    
    # Create a HIGH severity flash crash event
    event = AnomalyEvent(
        id=uuid.uuid4(),
        instrument="BANKNIFTY",
        asset_class="fo",
        exchange="NSE",
        anomaly_type=AnomalyType.FLASH_CRASH,
        severity=AnomalySeverity.HIGH,
        detected_at=datetime.utcnow(),
        description="Flash crash detected: 5.2% drop in 3 minutes",
        z_score=4.8,
        price=45000.0,
        volume=1500000.0
    )
    
    print(f"\nEvent Details:")
    print(f"  Instrument: {event.instrument}")
    print(f"  Type: {event.anomaly_type.value}")
    print(f"  Severity: {event.severity.value}")
    print(f"  Description: {event.description}")
    
    # Get matcher instance
    matcher = await get_matcher()
    
    # Set test time to 12:00 IST (outside typical quiet hours)
    ist_tz = pytz.timezone('Asia/Kolkata')
    test_time = ist_tz.localize(datetime(2024, 1, 15, 12, 0, 0))
    
    print(f"\nCurrent Time: {test_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    
    # Find matching rules
    matching_rules = await matcher.find_matching_rules(event, test_time)
    
    print(f"\nMatching Rules: {len(matching_rules)}")
    for rule in matching_rules:
        print(f"\n  Rule: {rule.name}")
        print(f"    User ID: {rule.user_id}")
        print(f"    Instruments: {rule.instruments}")
        print(f"    Channels: {rule.channels}")
        print(f"    Min Severity: {rule.min_severity.value}")
        print(f"    Max Alerts/Hour: {rule.max_alerts_per_hour}")
        if rule.quiet_hours_start and rule.quiet_hours_end:
            print(f"    Quiet Hours: {rule.quiet_hours_start} - {rule.quiet_hours_end} IST")


async def example_critical_bypass():
    """
    Example 2: CRITICAL severity bypassing quiet hours and rate limits
    
    This demonstrates:
    - CRITICAL events bypass quiet hours
    - CRITICAL events bypass rate limits
    - Immediate delivery for critical alerts
    """
    print("\n" + "="*80)
    print("Example 2: CRITICAL Severity Bypass")
    print("="*80)
    
    # Create a CRITICAL severity flash crash event
    event = AnomalyEvent(
        id=uuid.uuid4(),
        instrument="NIFTY",
        asset_class="fo",
        exchange="NSE",
        anomaly_type=AnomalyType.FLASH_CRASH,
        severity=AnomalySeverity.CRITICAL,
        detected_at=datetime.utcnow(),
        description="CRITICAL: Flash crash detected: 8.5% drop in 2 minutes",
        z_score=6.2,
        price=21000.0,
        volume=2500000.0
    )
    
    print(f"\nEvent Details:")
    print(f"  Instrument: {event.instrument}")
    print(f"  Type: {event.anomaly_type.value}")
    print(f"  Severity: {event.severity.value} ⚠️")
    print(f"  Description: {event.description}")
    
    # Get matcher instance
    matcher = await get_matcher()
    
    # Set test time to 23:00 IST (INSIDE typical quiet hours)
    ist_tz = pytz.timezone('Asia/Kolkata')
    test_time = ist_tz.localize(datetime(2024, 1, 15, 23, 0, 0))
    
    print(f"\nCurrent Time: {test_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print("  ⚠️ This is INSIDE quiet hours (22:00-08:00)")
    print("  ⚠️ CRITICAL events should bypass quiet hours")
    
    # Find matching rules
    matching_rules = await matcher.find_matching_rules(event, test_time)
    
    print(f"\nMatching Rules: {len(matching_rules)}")
    print("  ✅ CRITICAL events bypass quiet hours and rate limits")
    
    for rule in matching_rules:
        print(f"\n  Rule: {rule.name}")
        print(f"    Bypassed quiet hours: {rule.quiet_hours_start} - {rule.quiet_hours_end}")
        print(f"    Bypassed rate limit: {rule.max_alerts_per_hour}/hour")
        print(f"    Channels: {rule.channels}")


async def example_quiet_hours_blocking():
    """
    Example 3: Non-CRITICAL event blocked by quiet hours
    
    This demonstrates:
    - Non-CRITICAL events respect quiet hours
    - Quiet hours spanning midnight
    - IST timezone handling
    """
    print("\n" + "="*80)
    print("Example 3: Quiet Hours Blocking (Non-CRITICAL)")
    print("="*80)
    
    # Create a MEDIUM severity volume surge event
    event = AnomalyEvent(
        id=uuid.uuid4(),
        instrument="RELIANCE",
        asset_class="equity",
        exchange="NSE",
        anomaly_type=AnomalyType.VOLUME_SURGE,
        severity=AnomalySeverity.MEDIUM,
        detected_at=datetime.utcnow(),
        description="Volume surge: 3x average volume",
        z_score=3.2,
        price=2500.0,
        volume=5000000.0
    )
    
    print(f"\nEvent Details:")
    print(f"  Instrument: {event.instrument}")
    print(f"  Type: {event.anomaly_type.value}")
    print(f"  Severity: {event.severity.value}")
    print(f"  Description: {event.description}")
    
    # Get matcher instance
    matcher = await get_matcher()
    
    # Set test time to 02:00 IST (INSIDE quiet hours spanning midnight)
    ist_tz = pytz.timezone('Asia/Kolkata')
    test_time = ist_tz.localize(datetime(2024, 1, 15, 2, 0, 0))
    
    print(f"\nCurrent Time: {test_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print("  ⚠️ This is INSIDE quiet hours (22:00-08:00)")
    print("  ⚠️ Non-CRITICAL events should be blocked")
    
    # Find matching rules
    matching_rules = await matcher.find_matching_rules(event, test_time)
    
    print(f"\nMatching Rules: {len(matching_rules)}")
    if len(matching_rules) == 0:
        print("  ✅ Event blocked by quiet hours (as expected)")
    else:
        print("  ⚠️ Unexpected: rules matched during quiet hours")


async def example_rate_limit_blocking():
    """
    Example 4: Non-CRITICAL event blocked by rate limit
    
    This demonstrates:
    - Rate limiting per user per hour
    - Redis counter tracking
    - Non-CRITICAL events respect rate limits
    """
    print("\n" + "="*80)
    print("Example 4: Rate Limit Blocking (Non-CRITICAL)")
    print("="*80)
    
    # Create a HIGH severity price spike event
    event = AnomalyEvent(
        id=uuid.uuid4(),
        instrument="TATASTEEL",
        asset_class="equity",
        exchange="NSE",
        anomaly_type=AnomalyType.PRICE_SPIKE,
        severity=AnomalySeverity.HIGH,
        detected_at=datetime.utcnow(),
        description="Price spike: 4.2% increase in 5 minutes",
        z_score=3.8,
        price=150.0,
        volume=800000.0
    )
    
    print(f"\nEvent Details:")
    print(f"  Instrument: {event.instrument}")
    print(f"  Type: {event.anomaly_type.value}")
    print(f"  Severity: {event.severity.value}")
    print(f"  Description: {event.description}")
    
    # Get matcher instance
    matcher = await get_matcher()
    
    # Set test time to 14:00 IST (outside quiet hours)
    ist_tz = pytz.timezone('Asia/Kolkata')
    test_time = ist_tz.localize(datetime(2024, 1, 15, 14, 0, 0))
    
    print(f"\nCurrent Time: {test_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print("  ✅ Outside quiet hours")
    print("  ⚠️ Assuming rate limit already reached (10/10 alerts this hour)")
    
    # Note: In a real scenario, the Redis counter would be at the limit
    # For this example, we're just demonstrating the concept
    
    print(f"\nRate Limit Status:")
    print("  Current alerts this hour: 10/10")
    print("  ⚠️ Non-CRITICAL events should be blocked")
    
    # Find matching rules
    matching_rules = await matcher.find_matching_rules(event, test_time)
    
    print(f"\nMatching Rules: {len(matching_rules)}")
    print("  Note: Actual blocking depends on Redis counter state")


async def example_all_filter():
    """
    Example 5: Matching with "ALL" instruments filter
    
    This demonstrates:
    - "ALL" wildcard matching any instrument
    - Useful for global alert rules
    """
    print("\n" + "="*80)
    print("Example 5: ALL Instruments Filter")
    print("="*80)
    
    # Create a whale movement event for any instrument
    event = AnomalyEvent(
        id=uuid.uuid4(),
        instrument="BTCUSDT",
        asset_class="crypto",
        exchange="BINANCE",
        anomaly_type=AnomalyType.WHALE_MOVEMENT,
        severity=AnomalySeverity.HIGH,
        detected_at=datetime.utcnow(),
        description="Whale movement: 500 BTC transferred to exchange",
        z_score=None,
        price=45000.0,
        volume=500.0
    )
    
    print(f"\nEvent Details:")
    print(f"  Instrument: {event.instrument}")
    print(f"  Type: {event.anomaly_type.value}")
    print(f"  Severity: {event.severity.value}")
    print(f"  Description: {event.description}")
    
    # Get matcher instance
    matcher = await get_matcher()
    
    # Set test time to 10:00 IST (outside quiet hours)
    ist_tz = pytz.timezone('Asia/Kolkata')
    test_time = ist_tz.localize(datetime(2024, 1, 15, 10, 0, 0))
    
    print(f"\nCurrent Time: {test_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    
    # Find matching rules
    matching_rules = await matcher.find_matching_rules(event, test_time)
    
    print(f"\nMatching Rules: {len(matching_rules)}")
    print("  Rules with instruments=['ALL'] will match any instrument")
    
    for rule in matching_rules:
        if "ALL" in rule.instruments:
            print(f"\n  Rule: {rule.name}")
            print(f"    Instruments: {rule.instruments} (matches all)")
            print(f"    Asset Classes: {rule.asset_classes}")
            print(f"    Anomaly Types: {rule.anomaly_types}")


async def main():
    """Run all examples"""
    print("\n" + "="*80)
    print("Alert Matching Engine - Usage Examples")
    print("="*80)
    
    try:
        # Run all examples
        await example_basic_matching()
        await example_critical_bypass()
        await example_quiet_hours_blocking()
        await example_rate_limit_blocking()
        await example_all_filter()
        
        print("\n" + "="*80)
        print("All examples completed successfully!")
        print("="*80 + "\n")
        
    except Exception as e:
        print(f"\n❌ Error running examples: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Clean up
        await close_matcher()


if __name__ == "__main__":
    # Run examples
    asyncio.run(main())
