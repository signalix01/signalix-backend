"""
Simplified Checkpoint Task 37 Verification

Focuses on core functionality without external dependencies (Redis, APIs).
"""

import sys
import asyncio
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from services.alerts.detectors.zscore import ZScoreDetector
from services.alerts.detectors.cusum import CUSUMDetector
from services.alerts.detectors.isolation_forest import IsolationForestDetector
from services.alerts.detectors.flash_detector import FlashDetector, TickData


def generate_test_data(days=7):
    """Generate synthetic BANKNIFTY data with known anomalies"""
    bars_per_day = 375  # Market hours: 9:15-15:30
    base_price = 45000
    
    timestamps = []
    current_date = datetime.now() - timedelta(days=days)
    for day in range(days):
        date = current_date + timedelta(days=day)
        if date.weekday() >= 5:  # Skip weekends
            continue
        for minute in range(bars_per_day):
            hour = 9 + minute // 60
            min_val = minute % 60
            if hour == 9 and min_val < 15:
                continue
            timestamps.append(date.replace(hour=hour, minute=min_val, second=0))
    
    prices = []
    volumes = []
    
    for i, ts in enumerate(timestamps):
        # Normal price movement
        if i == 0:
            price = base_price
        else:
            price = prices[-1] + np.random.normal(0, 50)
        
        # Inject anomalies
        if i == bars_per_day * 2 + 100:  # Day 2: Price spike
            price += 500
        
        if bars_per_day * 3 + 50 <= i < bars_per_day * 3 + 60:  # Day 3: Volume surge
            volume = np.random.uniform(5000, 8000)
        else:
            volume = np.random.uniform(1000, 2000)
        
        if bars_per_day * 4 + 200 <= i < bars_per_day * 4 + 205:  # Day 4: Flash crash
            price -= (base_price * 0.05) / 5
        
        if i >= bars_per_day * 5:  # Day 5+: Sustained upward trend
            price += 20
        
        prices.append(price)
        volumes.append(volume)
    
    df = pd.DataFrame({
        'timestamp': timestamps,
        'open': prices,
        'high': [p + np.random.uniform(10, 50) for p in prices],
        'low': [p - np.random.uniform(10, 50) for p in prices],
        'close': prices,
        'volume': volumes
    })
    
    return df


async def main():
    print("=" * 80)
    print("CHECKPOINT TASK 37: SIMPLIFIED VERIFICATION")
    print("=" * 80)
    print()
    
    # Generate test data
    print("Generating synthetic BANKNIFTY data...")
    data = generate_test_data(days=7)
    print(f"Generated {len(data)} bars\n")
    
    results = {"passed": 0, "failed": 0}
    
    # Test 1: ZScore Detector
    print("1. Testing ZScore Detector...")
    try:
        detector = ZScoreDetector(window_size=20, alert_threshold=3.0, critical_threshold=4.0)
        price_events = detector.detect(
            series=data['close'].values,
            timestamps=data['timestamp'].astype(str).tolist(),
            metric_name='close',
            instrument='BANKNIFTY'
        )
        volume_events = detector.detect(
            series=data['volume'].values,
            timestamps=data['timestamp'].astype(str).tolist(),
            metric_name='volume',
            instrument='BANKNIFTY'
        )
        total = len(price_events) + len(volume_events)
        print(f"   ✓ Detected {len(price_events)} price + {len(volume_events)} volume anomalies = {total} total")
        results["passed"] += 1
    except Exception as e:
        print(f"   ✗ Failed: {e}")
        results["failed"] += 1
    
    # Test 2: CUSUM Detector
    print("\n2. Testing CUSUM Detector...")
    try:
        detector = CUSUMDetector(h=5.0, k=0.5)
        events = detector.detect_batch(
            series=data['close'].values,
            timestamps=data['timestamp'].astype(str).tolist(),
            instrument='BANKNIFTY'
        )
        print(f"   ✓ Detected {len(events)} regime changes")
        results["passed"] += 1
    except Exception as e:
        print(f"   ✗ Failed: {e}")
        results["failed"] += 1
    
    # Test 3: Isolation Forest Detector
    print("\n3. Testing Isolation Forest Detector...")
    try:
        detector = IsolationForestDetector(contamination=0.02)
        
        # Use only the data we have (don't split if too small)
        if len(data) >= 100:
            train_size = int(len(data) * 0.8)
            train_data = data.iloc[:train_size].copy()
            test_data = data.iloc[train_size:].copy()
        else:
            train_data = data.copy()
            test_data = data.copy()
        
        # Train
        detector.train(train_data, instrument='BANKNIFTY')
        
        # Detect on test data
        events = detector.detect_batch(
            test_data,
            instrument='BANKNIFTY',
            asset_class='fo',
            train_first=False
        )
        print(f"   ✓ Detected {len(events)} ML-identified anomalies")
        results["passed"] += 1
    except Exception as e:
        print(f"   ✗ Failed: {e}")
        results["failed"] += 1
    
    # Test 4: Flash Detector
    print("\n4. Testing Flash Detector...")
    try:
        detector = FlashDetector(threshold_pct=5.0, window_minutes=5)
        
        # Convert to TickData
        ticks = [
            TickData(
                timestamp=row['timestamp'],
                price=row['close'],
                volume=row['volume'],
                instrument='BANKNIFTY'
            )
            for _, row in data.iterrows()
        ]
        
        events = []
        for i in range(5, len(ticks)):
            window = ticks[i-5:i+1]
            event = detector.check_with_metadata(
                window,
                instrument='BANKNIFTY',
                asset_class='fo',
                exchange='NSE'
            )
            if event:
                events.append(event)
        
        print(f"   ✓ Detected {len(events)} flash crash/rally events")
        results["passed"] += 1
    except Exception as e:
        print(f"   ✗ Failed: {e}")
        results["failed"] += 1
    
    # Test 5: Minimum anomaly threshold
    print("\n5. Checking minimum anomaly threshold...")
    total_anomalies = (
        len(price_events) + len(volume_events) +
        len(events) if 'events' in locals() else 0
    )
    if total_anomalies >= 3:
        print(f"   ✓ Total anomalies: {total_anomalies} (requirement: >= 3)")
        results["passed"] += 1
    else:
        print(f"   ✗ Total anomalies: {total_anomalies} (requirement: >= 3)")
        results["failed"] += 1
    
    # Summary
    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    total_tests = results["passed"] + results["failed"]
    print(f"Total Tests: {total_tests}")
    print(f"Passed: {results['passed']}")
    print(f"Failed: {results['failed']}")
    print(f"Success Rate: {results['passed'] / total_tests * 100:.1f}%")
    print()
    
    if results["failed"] == 0:
        print("✓ ALL TESTS PASSED")
        return 0
    else:
        print("✗ SOME TESTS FAILED")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
