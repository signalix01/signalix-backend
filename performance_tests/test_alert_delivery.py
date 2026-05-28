"""
Performance test for Alert Delivery Engine

Tests:
- Inject 100 critical events
- Verify p95 delivery < 5 seconds

Requirements: 14.5 (Alert delivery reliability), 16.5 (Alert delivery latency)
"""

import asyncio
import time
from datetime import datetime
import random
import sys
import os
from typing import List

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.alerts.delivery_engine import AlertDeliveryEngine
from shared.schemas.alert_schemas import AnomalyEvent, AlertSeverity, AnomalyType


async def generate_critical_events(num_events: int = 100) -> List[AnomalyEvent]:
    """Generate critical anomaly events for testing"""
    events = []
    
    anomaly_types = [
        AnomalyType.PRICE_SPIKE,
        AnomalyType.VOLUME_SURGE,
        AnomalyType.FLASH_CRASH,
        AnomalyType.WHALE_MOVEMENT,
        AnomalyType.VOLATILITY_EXPLOSION
    ]
    
    symbols = ["RELIANCE", "TCS", "INFY", "HDFC", "ICICI", "SBIN", "ITC", "BHARTI", "HIND", "KOTAK"]
    
    for i in range(num_events):
        event = AnomalyEvent(
            event_id=f"test_event_{i}",
            symbol=random.choice(symbols),
            asset_class="equity",
            exchange="NSE",
            anomaly_type=random.choice(anomaly_types),
            severity=AlertSeverity.CRITICAL,
            detected_at=datetime.utcnow(),
            description=f"Test critical event {i}",
            z_score=random.uniform(3.5, 5.0),
            current_value=random.uniform(1000, 2000),
            baseline_value=random.uniform(900, 1100),
            deviation_pct=random.uniform(10, 30),
            metadata={
                "test": True,
                "event_number": i
            }
        )
        events.append(event)
    
    return events


async def inject_and_measure_delivery(events: List[AnomalyEvent], delivery_engine: AlertDeliveryEngine):
    """Inject events and measure delivery latency"""
    delivery_times = []
    failed_deliveries = 0
    
    print(f"Injecting {len(events)} critical events...")
    start_time = time.time()
    
    for i, event in enumerate(events):
        event_start = time.time()
        
        try:
            # Deliver the event
            await delivery_engine.deliver_alert(
                event=event,
                user_id="test_user",
                channels=["in_app"],  # Use in-app for testing (fastest)
                bypass_quiet_hours=True  # Critical events bypass quiet hours
            )
            
            # Measure delivery time
            delivery_time = time.time() - event_start
            delivery_times.append(delivery_time)
            
            # Progress indicator
            if (i + 1) % 10 == 0:
                elapsed = time.time() - start_time
                avg_so_far = sum(delivery_times) / len(delivery_times)
                print(f"  Delivered {i + 1}/{len(events)} events ({elapsed:.1f}s elapsed, avg: {avg_so_far:.3f}s)")
        
        except Exception as e:
            print(f"  ❌ Failed to deliver event {i}: {e}")
            failed_deliveries += 1
    
    total_time = time.time() - start_time
    print(f"✅ Completed {len(events)} deliveries in {total_time:.2f}s")
    
    return delivery_times, failed_deliveries


def calculate_percentile(values: List[float], percentile: float) -> float:
    """Calculate percentile from list of values"""
    if not values:
        return 0.0
    
    sorted_values = sorted(values)
    index = int(len(sorted_values) * percentile)
    
    if index >= len(sorted_values):
        index = len(sorted_values) - 1
    
    return sorted_values[index]


async def test_alert_delivery_performance():
    """Main test function"""
    print("="*70)
    print("ALERT DELIVERY ENGINE PERFORMANCE TEST")
    print("="*70)
    print()
    
    # Test parameters
    num_events = 100
    p95_target = 5.0  # seconds
    
    print(f"Test Parameters:")
    print(f"  Events to inject: {num_events}")
    print(f"  Severity: CRITICAL")
    print(f"  P95 latency target: < {p95_target}s")
    print()
    
    # Initialize delivery engine
    print("Initializing delivery engine...")
    delivery_engine = AlertDeliveryEngine()
    print("✅ Delivery engine initialized")
    print()
    
    # Generate test events
    print("Generating critical events...")
    events = await generate_critical_events(num_events)
    print(f"✅ Generated {len(events)} critical events")
    print()
    
    # Inject and measure
    delivery_times, failed_deliveries = await inject_and_measure_delivery(events, delivery_engine)
    
    # Calculate statistics
    if delivery_times:
        avg_delivery = sum(delivery_times) / len(delivery_times)
        min_delivery = min(delivery_times)
        max_delivery = max(delivery_times)
        p50_delivery = calculate_percentile(delivery_times, 0.50)
        p95_delivery = calculate_percentile(delivery_times, 0.95)
        p99_delivery = calculate_percentile(delivery_times, 0.99)
        
        print("\n" + "="*70)
        print("RESULTS")
        print("="*70)
        print(f"Total Events: {num_events}")
        print(f"Successful Deliveries: {len(delivery_times)}")
        print(f"Failed Deliveries: {failed_deliveries}")
        print()
        print("Delivery Latency Statistics:")
        print(f"  Average: {avg_delivery:.3f}s")
        print(f"  Minimum: {min_delivery:.3f}s")
        print(f"  Maximum: {max_delivery:.3f}s")
        print(f"  P50 (median): {p50_delivery:.3f}s")
        print(f"  P95: {p95_delivery:.3f}s")
        print(f"  P99: {p99_delivery:.3f}s")
        print()
        
        # Determine pass/fail
        p95_pass = p95_delivery < p95_target
        no_failures = failed_deliveries == 0
        
        print("Test Results:")
        print(f"  P95 latency < {p95_target}s: {'✅ PASS' if p95_pass else '❌ FAIL'}")
        print(f"  No failed deliveries: {'✅ PASS' if no_failures else '❌ FAIL'}")
        print()
        
        overall_pass = p95_pass and no_failures
        print(f"Overall: {'✅ PASS' if overall_pass else '❌ FAIL'}")
        print("="*70)
        
        return {
            "pass": overall_pass,
            "total_events": num_events,
            "successful": len(delivery_times),
            "failed": failed_deliveries,
            "avg_latency": avg_delivery,
            "p95_latency": p95_delivery,
            "p99_latency": p99_delivery
        }
    else:
        print("\n❌ No successful deliveries recorded")
        return {
            "pass": False,
            "total_events": num_events,
            "successful": 0,
            "failed": failed_deliveries
        }


if __name__ == "__main__":
    # Run the test
    result = asyncio.run(test_alert_delivery_performance())
    
    # Exit with appropriate code
    sys.exit(0 if result["pass"] else 1)
