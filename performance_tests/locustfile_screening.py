"""
Locust load testing script for AI Screening Engine

Tests:
- 100 concurrent screening requests
- Verifies screening SQL pre-filter completes in < 500ms under load

Usage:
    locust -f locustfile_screening.py --host=http://localhost:8000
"""

from locust import HttpUser, task, between, events
import json
import time
from datetime import datetime

# Track SQL pre-filter timing
sql_filter_times = []


class ScreeningUser(HttpUser):
    """Simulates a user running screening requests"""
    
    wait_time = between(1, 3)  # Wait 1-3 seconds between requests
    
    def on_start(self):
        """Called when a simulated user starts"""
        # Login to get auth token (if needed)
        # For now, we'll use a test token or skip auth
        self.client.headers = {
            "Content-Type": "application/json",
            # Add auth header if needed: "Authorization": "Bearer test_token"
        }
    
    @task(3)
    def run_simple_screening(self):
        """Run a simple technical screening (most common use case)"""
        criteria = {
            "name": "Load Test - Simple RSI Oversold",
            "description": "Find oversold stocks with RSI < 30",
            "asset_class": ["equity"],
            "min_rsi": None,
            "max_rsi": 30,
            "require_above_ema": None,
            "min_volume_ratio": 1.5,
            "min_ai_confidence": None  # Skip AI scoring for load test
        }
        
        start_time = time.time()
        with self.client.post(
            "/api/v1/screening/run",
            json=criteria,
            catch_response=True,
            name="/screening/run [simple]"
        ) as response:
            elapsed = (time.time() - start_time) * 1000  # Convert to ms
            
            if response.status_code == 200:
                result = response.json()
                
                # Extract SQL pre-filter time if available
                if "sql_filter_duration_ms" in result:
                    sql_time = result["sql_filter_duration_ms"]
                    sql_filter_times.append(sql_time)
                    
                    # Verify < 500ms requirement
                    if sql_time > 500:
                        response.failure(f"SQL pre-filter took {sql_time}ms (> 500ms target)")
                    else:
                        response.success()
                else:
                    response.success()
            else:
                response.failure(f"Got status code {response.status_code}")
    
    @task(2)
    def run_complex_screening(self):
        """Run a complex multi-criteria screening"""
        criteria = {
            "name": "Load Test - Complex Multi-Criteria",
            "description": "Complex screening with multiple filters",
            "asset_class": ["equity", "fo"],
            "min_rsi": 40,
            "max_rsi": 60,
            "require_above_ema": 200,
            "min_adx": 25,
            "min_volume_ratio": 2.0,
            "price_breakout_days": 52,
            "min_ai_confidence": None  # Skip AI scoring for load test
        }
        
        start_time = time.time()
        with self.client.post(
            "/api/v1/screening/run",
            json=criteria,
            catch_response=True,
            name="/screening/run [complex]"
        ) as response:
            elapsed = (time.time() - start_time) * 1000
            
            if response.status_code == 200:
                result = response.json()
                
                if "sql_filter_duration_ms" in result:
                    sql_time = result["sql_filter_duration_ms"]
                    sql_filter_times.append(sql_time)
                    
                    if sql_time > 500:
                        response.failure(f"SQL pre-filter took {sql_time}ms (> 500ms target)")
                    else:
                        response.success()
                else:
                    response.success()
            else:
                response.failure(f"Got status code {response.status_code}")
    
    @task(1)
    def get_screening_templates(self):
        """Get available screening templates"""
        with self.client.get(
            "/api/v1/screening/templates",
            catch_response=True,
            name="/screening/templates"
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Got status code {response.status_code}")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Called when the load test stops - print SQL filter statistics"""
    if sql_filter_times:
        avg_time = sum(sql_filter_times) / len(sql_filter_times)
        max_time = max(sql_filter_times)
        min_time = min(sql_filter_times)
        
        # Calculate p95
        sorted_times = sorted(sql_filter_times)
        p95_index = int(len(sorted_times) * 0.95)
        p95_time = sorted_times[p95_index] if p95_index < len(sorted_times) else max_time
        
        print("\n" + "="*60)
        print("SQL PRE-FILTER PERFORMANCE STATISTICS")
        print("="*60)
        print(f"Total requests: {len(sql_filter_times)}")
        print(f"Average time: {avg_time:.2f}ms")
        print(f"Min time: {min_time:.2f}ms")
        print(f"Max time: {max_time:.2f}ms")
        print(f"P95 time: {p95_time:.2f}ms")
        print(f"Target: < 500ms")
        print(f"Status: {'✅ PASS' if p95_time < 500 else '❌ FAIL'}")
        print("="*60)
