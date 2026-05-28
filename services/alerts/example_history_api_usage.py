"""
Example usage of Alert History API

This file demonstrates how to use the alert history API endpoints.
"""
import httpx
import asyncio
from datetime import datetime, timedelta


# Base URL (adjust based on your deployment)
BASE_URL = "http://localhost:8080"  # API Gateway
# or
# BASE_URL = "http://localhost:8005"  # Direct to alerts service


async def example_get_recent_events():
    """
    Example 1: Get recent anomaly events
    """
    print("\n=== Example 1: Get Recent Events ===")
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{BASE_URL}/api/v1/alerts/events",
            params={
                "page": 1,
                "page_size": 10
            },
            headers={
                "Authorization": "Bearer YOUR_JWT_TOKEN"
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"Total events: {data['total']}")
            print(f"Page: {data['page']} of {data['total_pages']}")
            print(f"\nEvents:")
            for event in data['events']:
                print(f"  - {event['instrument']}: {event['anomaly_type']} ({event['severity']})")
                print(f"    Detected at: {event['detected_at']}")
                print(f"    Description: {event['description']}")
        else:
            print(f"Error: {response.status_code}")
            print(response.json())


async def example_filter_by_severity():
    """
    Example 2: Get only critical severity events
    """
    print("\n=== Example 2: Filter by Severity ===")
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{BASE_URL}/api/v1/alerts/events",
            params={
                "severity": "critical",
                "page": 1,
                "page_size": 20
            },
            headers={
                "Authorization": "Bearer YOUR_JWT_TOKEN"
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"Critical events found: {data['total']}")
            for event in data['events']:
                print(f"  - {event['instrument']}: {event['description']}")
        else:
            print(f"Error: {response.status_code}")


async def example_filter_by_instrument():
    """
    Example 3: Get events for specific instrument
    """
    print("\n=== Example 3: Filter by Instrument ===")
    
    instrument = "AAPL"
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{BASE_URL}/api/v1/alerts/events",
            params={
                "instrument": instrument,
                "page": 1,
                "page_size": 10
            },
            headers={
                "Authorization": "Bearer YOUR_JWT_TOKEN"
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"Events for {instrument}: {data['total']}")
            for event in data['events']:
                print(f"  - {event['anomaly_type']}: {event['description']}")
                print(f"    Price: ${event['price']}, Volume: {event['volume']}")
        else:
            print(f"Error: {response.status_code}")


async def example_filter_by_date_range():
    """
    Example 4: Get events from last 7 days
    """
    print("\n=== Example 4: Filter by Date Range ===")
    
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=7)
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{BASE_URL}/api/v1/alerts/events",
            params={
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "page": 1,
                "page_size": 50
            },
            headers={
                "Authorization": "Bearer YOUR_JWT_TOKEN"
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"Events in last 7 days: {data['total']}")
            
            # Group by anomaly type
            by_type = {}
            for event in data['events']:
                anomaly_type = event['anomaly_type']
                by_type[anomaly_type] = by_type.get(anomaly_type, 0) + 1
            
            print("\nBreakdown by type:")
            for anomaly_type, count in by_type.items():
                print(f"  - {anomaly_type}: {count}")
        else:
            print(f"Error: {response.status_code}")


async def example_get_event_detail():
    """
    Example 5: Get full event detail with raw data
    """
    print("\n=== Example 5: Get Event Detail ===")
    
    # First, get a list of events
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{BASE_URL}/api/v1/alerts/events",
            params={"page": 1, "page_size": 1},
            headers={"Authorization": "Bearer YOUR_JWT_TOKEN"}
        )
        
        if response.status_code == 200:
            data = response.json()
            if data['events']:
                event_id = data['events'][0]['id']
                
                # Get full detail
                detail_response = await client.get(
                    f"{BASE_URL}/api/v1/alerts/events/{event_id}",
                    headers={"Authorization": "Bearer YOUR_JWT_TOKEN"}
                )
                
                if detail_response.status_code == 200:
                    detail = detail_response.json()
                    print(f"Event ID: {detail['id']}")
                    print(f"Instrument: {detail['instrument']}")
                    print(f"Type: {detail['anomaly_type']}")
                    print(f"Severity: {detail['severity']}")
                    print(f"Description: {detail['description']}")
                    print(f"\nRaw Data:")
                    print(detail['raw_data'])
                else:
                    print(f"Error getting detail: {detail_response.status_code}")
            else:
                print("No events found")
        else:
            print(f"Error: {response.status_code}")


async def example_get_delivery_log():
    """
    Example 6: Get delivery log
    """
    print("\n=== Example 6: Get Delivery Log ===")
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{BASE_URL}/api/v1/alerts/delivery-log",
            params={
                "page": 1,
                "page_size": 20
            },
            headers={
                "Authorization": "Bearer YOUR_JWT_TOKEN"
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"Total delivery logs: {data['total']}")
            print(f"\nRecent deliveries:")
            for log in data['logs']:
                print(f"  - {log['channel']}: {log['status']}")
                print(f"    Event: {log['instrument']} - {log['anomaly_type']}")
                print(f"    Delivered at: {log['delivered_at']}")
                if log['detection_to_delivery_ms']:
                    print(f"    Latency: {log['detection_to_delivery_ms']}ms")
                if log['error_message']:
                    print(f"    Error: {log['error_message']}")
        else:
            print(f"Error: {response.status_code}")


async def example_filter_delivery_log():
    """
    Example 7: Filter delivery log by channel and status
    """
    print("\n=== Example 7: Filter Delivery Log ===")
    
    async with httpx.AsyncClient() as client:
        # Get failed email deliveries
        response = await client.get(
            f"{BASE_URL}/api/v1/alerts/delivery-log",
            params={
                "channel": "email",
                "status": "failed",
                "page": 1,
                "page_size": 10
            },
            headers={
                "Authorization": "Bearer YOUR_JWT_TOKEN"
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"Failed email deliveries: {data['total']}")
            for log in data['logs']:
                print(f"  - {log['instrument']}: {log['error_message']}")
                print(f"    Attempt: {log['attempt_number']}")
        else:
            print(f"Error: {response.status_code}")


async def example_combined_filters():
    """
    Example 8: Use multiple filters together
    """
    print("\n=== Example 8: Combined Filters ===")
    
    async with httpx.AsyncClient() as client:
        # Get high/critical price spikes in equity markets from last 24 hours
        start_date = datetime.utcnow() - timedelta(hours=24)
        
        response = await client.get(
            f"{BASE_URL}/api/v1/alerts/events",
            params={
                "asset_class": "equity",
                "anomaly_type": "price_spike",
                "severity": "high",
                "start_date": start_date.isoformat(),
                "page": 1,
                "page_size": 20
            },
            headers={
                "Authorization": "Bearer YOUR_JWT_TOKEN"
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"High-severity equity price spikes (last 24h): {data['total']}")
            for event in data['events']:
                print(f"  - {event['instrument']}: {event['description']}")
                print(f"    Price: ${event['price']}, Z-score: {event['z_score']}")
        else:
            print(f"Error: {response.status_code}")


async def example_pagination():
    """
    Example 9: Paginate through results
    """
    print("\n=== Example 9: Pagination ===")
    
    async with httpx.AsyncClient() as client:
        page = 1
        page_size = 5
        all_events = []
        
        while True:
            response = await client.get(
                f"{BASE_URL}/api/v1/alerts/events",
                params={
                    "page": page,
                    "page_size": page_size
                },
                headers={
                    "Authorization": "Bearer YOUR_JWT_TOKEN"
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                all_events.extend(data['events'])
                
                print(f"Fetched page {page}/{data['total_pages']} ({len(data['events'])} events)")
                
                if page >= data['total_pages']:
                    break
                
                page += 1
            else:
                print(f"Error: {response.status_code}")
                break
        
        print(f"\nTotal events fetched: {len(all_events)}")


async def main():
    """
    Run all examples
    """
    print("=" * 60)
    print("Alert History API - Usage Examples")
    print("=" * 60)
    
    # Note: These examples will fail without a running server and valid JWT token
    # Uncomment the examples you want to run
    
    # await example_get_recent_events()
    # await example_filter_by_severity()
    # await example_filter_by_instrument()
    # await example_filter_by_date_range()
    # await example_get_event_detail()
    # await example_get_delivery_log()
    # await example_filter_delivery_log()
    # await example_combined_filters()
    # await example_pagination()
    
    print("\n" + "=" * 60)
    print("Examples completed!")
    print("=" * 60)


if __name__ == "__main__":
    # Run examples
    asyncio.run(main())
    
    # Or run individual examples:
    # asyncio.run(example_get_recent_events())
