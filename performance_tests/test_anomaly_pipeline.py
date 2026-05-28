"""
Performance test for Anomaly Detection Pipeline

Tests:
- Inject 1,000 bars in 60 seconds
- Verify all processed within 30 seconds

Requirements: 16.4 (Anomaly detection pipeline performance)
"""

import asyncio
import time
from datetime import datetime, timedelta
import random
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.alerts.detectors.statistical_detector import StatisticalAnomalyDetector
from services.alerts.anomaly_orchestrator import AnomalyOrchestrator
from shared.database.connection import get_db


async def generate_test_bars(num_bars: int = 1000):
    """Generate synthetic OHLCV bars for testing"""
    bars = []
    base_price = 1000.0
    base_volume = 100000
    
    for i in range(num_bars):
        # Simulate realistic price movement
        price_change = random.uniform(-0.02, 0.02)  # ±2% change
        close = base_price * (1 + price_change)
        
        # OHLC
        high = close * random.uniform(1.0, 1.01)
        low = close * random.uniform(0.99, 1.0)
        open_price = random.uniform(low, high)
        
        # Volume with occasional spikes
        volume_multiplier = random.uniform(0.8, 1.2)
        if random.random() < 0.05:  # 5% chance of volume spike
            volume_multiplier = random.uniform(2.0, 5.0)
        volume = int(base_volume * volume_multiplier)
        
        bar = {
            "symbol": f"TEST_{i % 10}",  # 10 different symbols
            "timestamp": datetime.utcnow() - timedelta(seconds=num_bars - i),
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume
        }
        
        bars.append(bar)
        base_price = close  # Update base for next bar
    
    return bars


async def inject_bars_over_time(bars: list, duration_seconds: int = 60):
    """Inject bars over specified duration"""
    interval = duration_seconds / len(bars)
    injected_bars = []
    
    print(f"Injecting {len(bars)} bars over {duration_seconds} seconds...")
    print(f"Injection rate: {len(bars) / duration_seconds:.2f} bars/second")
    
    start_time = time.time()
    
    for i, bar in enumerate(bars):
        injected_bars.append(bar)
        
        # Progress indicator
        if (i + 1) % 100 == 0:
            elapsed = time.time() - start_time
            print(f"  Injected {i + 1}/{len(bars)} bars ({elapsed:.1f}s elapsed)")
        
        # Wait for next injection
        if i < len(bars) - 1:
            await asyncio.sleep(interval)
    
    injection_time = time.time() - start_time
    print(f"✅ All {len(bars)} bars injected in {injection_time:.2f}s")
    
    return injected_bars, injection_time


async def process_bars_with_detector(bars: list):
    """Process bars through anomaly detector"""
    detector = StatisticalAnomalyDetector()
    detected_anomalies = []
    
    print(f"\nProcessing {len(bars)} bars through anomaly detector...")
    start_time = time.time()
    
    for i, bar in enumerate(bars):
        # Detect anomalies
        anomalies = await detector.detect_price_anomalies(
            symbol=bar["symbol"],
            current_price=bar["close"],
            historical_prices=[b["close"] for b in bars[max(0, i-20):i]],  # 20-bar lookback
            volume=bar["volume"],
            historical_volumes=[b["volume"] for b in bars[max(0, i-20):i]]
        )
        
        if anomalies:
            detected_anomalies.extend(anomalies)
        
        # Progress indicator
        if (i + 1) % 100 == 0:
            elapsed = time.time() - start_time
            print(f"  Processed {i + 1}/{len(bars)} bars ({elapsed:.1f}s elapsed)")
    
    processing_time = time.time() - start_time
    print(f"✅ All {len(bars)} bars processed in {processing_time:.2f}s")
    print(f"   Detected {len(detected_anomalies)} anomalies")
    
    return detected_anomalies, processing_time


async def test_anomaly_pipeline_performance():
    """Main test function"""
    print("="*70)
    print("ANOMALY DETECTION PIPELINE PERFORMANCE TEST")
    print("="*70)
    print()
    
    # Test parameters
    num_bars = 1000
    injection_duration = 60  # seconds
    processing_target = 30  # seconds
    
    print(f"Test Parameters:")
    print(f"  Bars to inject: {num_bars}")
    print(f"  Injection duration: {injection_duration}s")
    print(f"  Processing target: < {processing_target}s")
    print()
    
    # Generate test data
    print("Generating test bars...")
    bars = await generate_test_bars(num_bars)
    print(f"✅ Generated {len(bars)} test bars")
    print()
    
    # Inject bars over time
    injected_bars, injection_time = await inject_bars_over_time(bars, injection_duration)
    
    # Process bars through detector
    anomalies, processing_time = await process_bars_with_detector(injected_bars)
    
    # Calculate metrics
    print("\n" + "="*70)
    print("RESULTS")
    print("="*70)
    print(f"Injection Time: {injection_time:.2f}s (target: {injection_duration}s)")
    print(f"Processing Time: {processing_time:.2f}s (target: < {processing_target}s)")
    print(f"Anomalies Detected: {len(anomalies)}")
    print(f"Processing Rate: {num_bars / processing_time:.2f} bars/second")
    print()
    
    # Determine pass/fail
    injection_pass = abs(injection_time - injection_duration) < 5  # Within 5s tolerance
    processing_pass = processing_time < processing_target
    
    print("Test Results:")
    print(f"  Injection timing: {'✅ PASS' if injection_pass else '❌ FAIL'}")
    print(f"  Processing speed: {'✅ PASS' if processing_pass else '❌ FAIL'}")
    print()
    
    overall_pass = injection_pass and processing_pass
    print(f"Overall: {'✅ PASS' if overall_pass else '❌ FAIL'}")
    print("="*70)
    
    return {
        "pass": overall_pass,
        "injection_time": injection_time,
        "processing_time": processing_time,
        "anomalies_detected": len(anomalies),
        "processing_rate": num_bars / processing_time
    }


if __name__ == "__main__":
    # Run the test
    result = asyncio.run(test_anomaly_pipeline_performance())
    
    # Exit with appropriate code
    sys.exit(0 if result["pass"] else 1)
