"""
Example Usage: US Equity Whale Tracker

Demonstrates how to use the US Equity Whale Tracker to monitor
dark pool prints and unusual options sweeps.

Requirements: 12.1
"""

import asyncio
import os
from us_equity_whale import USEquityWhaleTracker


async def main():
    """
    Example: Poll US equity whale activity once
    """
    # Initialize tracker with API keys from environment
    tracker = USEquityWhaleTracker(
        unusual_whales_api_key=os.getenv("UNUSUAL_WHALES_API_KEY"),
        polygon_api_key=os.getenv("POLYGON_API_KEY")
    )
    
    print("=" * 80)
    print("US Equity Whale Tracker - Example Usage")
    print("=" * 80)
    print()
    
    # Check if we're in market hours
    if tracker.is_market_hours():
        print("✓ US market is currently open")
    else:
        print("✗ US market is currently closed")
    print()
    
    # Poll for dark pool prints
    print("Polling for dark pool prints...")
    dark_pool_events = await tracker.poll_dark_pool_prints()
    
    if dark_pool_events:
        print(f"Found {len(dark_pool_events)} dark pool whale events:")
        for event in dark_pool_events:
            print(f"  - {event.description}")
            print(f"    Severity: {event.severity.value}")
            print(f"    Value: ${event.raw_data['value_usd']:,.0f}")
            print()
    else:
        print("No qualifying dark pool prints found (>= $10M)")
    print()
    
    # Poll for options sweeps
    print("Polling for unusual options sweeps...")
    options_events = await tracker.poll_options_sweeps()
    
    if options_events:
        print(f"Found {len(options_events)} options sweep whale events:")
        for event in options_events:
            print(f"  - {event.description}")
            print(f"    Severity: {event.severity.value}")
            print(f"    Premium: ${event.raw_data['premium']:,.0f}")
            print()
    else:
        print("No qualifying options sweeps found (>= $1M)")
    print()
    
    print("=" * 80)
    print(f"Total whale events detected: {len(dark_pool_events) + len(options_events)}")
    print("=" * 80)


async def continuous_monitoring():
    """
    Example: Run continuous monitoring (runs indefinitely)
    
    This would typically be run as a background service/task.
    """
    tracker = USEquityWhaleTracker(
        unusual_whales_api_key=os.getenv("UNUSUAL_WHALES_API_KEY"),
        polygon_api_key=os.getenv("POLYGON_API_KEY")
    )
    
    print("Starting continuous US equity whale monitoring...")
    print("Press Ctrl+C to stop")
    print()
    
    # Create a stop event for graceful shutdown
    stop_event = asyncio.Event()
    
    try:
        await tracker.run_continuous_polling(stop_event=stop_event)
    except KeyboardInterrupt:
        print("\nStopping monitoring...")
        stop_event.set()


if __name__ == "__main__":
    # Run single poll example
    asyncio.run(main())
    
    # Uncomment to run continuous monitoring:
    # asyncio.run(continuous_monitoring())
