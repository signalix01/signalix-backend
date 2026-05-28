"""
Example Usage: Anomaly Event Deduplication Service

This example demonstrates how to integrate the DedupService into the
anomaly detection pipeline.

Requirements: 11.8
"""
import asyncio
from datetime import datetime
from uuid import uuid4

from services.alerts.deduplication import get_dedup_service
from shared.database.models import AnomalyEvent, AnomalyType, AnomalySeverity


async def process_anomaly_event(event: AnomalyEvent) -> bool:
    """
    Process an anomaly event with deduplication.
    
    This function would be called by the anomaly detection pipeline
    before emitting events to the alert delivery system.
    
    Args:
        event: Detected anomaly event
        
    Returns:
        True if event was emitted, False if suppressed
    """
    # Get deduplication service
    dedup_service = await get_dedup_service()
    
    # Check if event should be suppressed
    should_suppress = await dedup_service.should_suppress(event)
    
    if should_suppress:
        print(f"❌ Event suppressed: {event.instrument} - {event.anomaly_type.value}")
        return False
    
    # Event not suppressed - emit to alert delivery system
    print(f"✅ Event emitted: {event.instrument} - {event.anomaly_type.value} "
          f"(severity: {event.severity.value})")
    
    # Here you would:
    # 1. Store event to TimescaleDB
    # 2. Publish to Redis pub/sub channel
    # 3. Trigger alert delivery based on user rules
    
    return True


async def example_scenario():
    """
    Example scenario demonstrating deduplication behavior.
    """
    print("=" * 80)
    print("Anomaly Event Deduplication - Example Scenario")
    print("=" * 80)
    print()
    
    # Scenario 1: First event - should be emitted
    print("Scenario 1: First price spike event")
    print("-" * 40)
    event1 = AnomalyEvent(
        id=uuid4(),
        instrument="RELIANCE",
        asset_class="equity",
        exchange="NSE",
        anomaly_type=AnomalyType.PRICE_SPIKE,
        severity=AnomalySeverity.MEDIUM,
        detected_at=datetime.utcnow(),
        description="Price spike detected: +3.5%",
        z_score=3.5,
        price=2500.0
    )
    
    await process_anomaly_event(event1)
    print()
    
    # Scenario 2: Duplicate event within 15 minutes - should be suppressed
    print("Scenario 2: Duplicate event (same severity)")
    print("-" * 40)
    event2 = AnomalyEvent(
        id=uuid4(),
        instrument="RELIANCE",
        asset_class="equity",
        exchange="NSE",
        anomaly_type=AnomalyType.PRICE_SPIKE,
        severity=AnomalySeverity.MEDIUM,
        detected_at=datetime.utcnow(),
        description="Price spike detected: +3.7%",
        z_score=3.7,
        price=2520.0
    )
    
    await process_anomaly_event(event2)
    print()
    
    # Scenario 3: Severity escalation - should NOT be suppressed
    print("Scenario 3: Severity escalation (medium → high)")
    print("-" * 40)
    event3 = AnomalyEvent(
        id=uuid4(),
        instrument="RELIANCE",
        asset_class="equity",
        exchange="NSE",
        anomaly_type=AnomalyType.PRICE_SPIKE,
        severity=AnomalySeverity.HIGH,
        detected_at=datetime.utcnow(),
        description="Price spike intensified: +5.2%",
        z_score=4.5,
        price=2600.0
    )
    
    await process_anomaly_event(event3)
    print()
    
    # Scenario 4: Different instrument - should NOT be suppressed
    print("Scenario 4: Different instrument (TCS)")
    print("-" * 40)
    event4 = AnomalyEvent(
        id=uuid4(),
        instrument="TCS",
        asset_class="equity",
        exchange="NSE",
        anomaly_type=AnomalyType.PRICE_SPIKE,
        severity=AnomalySeverity.MEDIUM,
        detected_at=datetime.utcnow(),
        description="Price spike detected on TCS: +3.2%",
        z_score=3.2,
        price=3500.0
    )
    
    await process_anomaly_event(event4)
    print()
    
    # Scenario 5: Different anomaly type - should NOT be suppressed
    print("Scenario 5: Different anomaly type (volume surge)")
    print("-" * 40)
    event5 = AnomalyEvent(
        id=uuid4(),
        instrument="RELIANCE",
        asset_class="equity",
        exchange="NSE",
        anomaly_type=AnomalyType.VOLUME_SURGE,
        severity=AnomalySeverity.MEDIUM,
        detected_at=datetime.utcnow(),
        description="Volume surge detected: 5x average",
        z_score=4.0,
        volume=5000000.0
    )
    
    await process_anomaly_event(event5)
    print()
    
    print("=" * 80)
    print("Example completed")
    print("=" * 80)


if __name__ == "__main__":
    # Note: This example uses mocked Redis for demonstration
    # In production, ensure Redis is running and configured
    asyncio.run(example_scenario())
