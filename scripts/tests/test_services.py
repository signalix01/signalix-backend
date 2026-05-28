"""
Simple script to test all backend services
"""
import httpx
import asyncio
from typing import Dict, List

SERVICES = [
    {"name": "Auth Service", "port": 8000, "path": "/health"},
    {"name": "User Service", "port": 8001, "path": "/health"},
    {"name": "Analysis Service", "port": 8002, "path": "/health"},
    {"name": "Market Data Service", "port": 8003, "path": "/health"},
    {"name": "Portfolio Service", "port": 8004, "path": "/health"},
    {"name": "Notification Service", "port": 8005, "path": "/health"},
    {"name": "Subscription Service", "port": 8006, "path": "/health"},
    {"name": "Analytics Service", "port": 8007, "path": "/health"},
    {"name": "Backtest Service", "port": 8008, "path": "/health"},
    {"name": "Pricing Service", "port": 8009, "path": "/health"},
]

async def test_service(service: Dict) -> Dict:
    """Test a single service"""
    url = f"http://localhost:{service['port']}{service['path']}"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url)
            return {
                "name": service["name"],
                "port": service["port"],
                "status": "✅ RUNNING" if response.status_code == 200 else f"⚠️ ERROR {response.status_code}",
                "response": response.json() if response.status_code == 200 else None
            }
    except httpx.ConnectError:
        return {
            "name": service["name"],
            "port": service["port"],
            "status": "❌ NOT RUNNING",
            "response": None
        }
    except Exception as e:
        return {
            "name": service["name"],
            "port": service["port"],
            "status": f"❌ ERROR: {str(e)}",
            "response": None
        }

async def test_all_services():
    """Test all services"""
    print("=" * 80)
    print("SignalixAI Backend Services Health Check")
    print("=" * 80)
    print()
    
    results = await asyncio.gather(*[test_service(service) for service in SERVICES])
    
    running_count = 0
    for result in results:
        print(f"{result['status']:<20} {result['name']:<30} Port: {result['port']}")
        if "RUNNING" in result['status']:
            running_count += 1
            if result['response']:
                print(f"  Response: {result['response']}")
        print()
    
    print("=" * 80)
    print(f"Summary: {running_count}/{len(SERVICES)} services running")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(test_all_services())
