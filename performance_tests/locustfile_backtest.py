"""
Locust load testing script for Backtesting Engine

Tests:
- 10 concurrent backtest tasks
- Verifies all 10 complete without errors (test horizontal scaling)

Usage:
    locust -f locustfile_backtest.py --host=http://localhost:8000 --users=10 --spawn-rate=2
"""

from locust import HttpUser, task, between, events
import json
import time
from datetime import datetime, timedelta

# Track backtest completion
backtest_results = {
    "completed": 0,
    "failed": 0,
    "task_ids": [],
    "durations": []
}


class BacktestUser(HttpUser):
    """Simulates a user running backtest requests"""
    
    wait_time = between(2, 5)  # Wait 2-5 seconds between requests
    
    def on_start(self):
        """Called when a simulated user starts"""
        self.client.headers = {
            "Content-Type": "application/json",
        }
    
    @task
    def run_backtest(self):
        """Submit a backtest task"""
        # Create a simple strategy spec for testing
        strategy_spec = {
            "strategy_id": f"load_test_{int(time.time() * 1000)}",
            "user_id": "load_test_user",
            "name": "Load Test Strategy",
            "description": "Simple RSI strategy for load testing",
            "asset_class": "equity",
            "instruments": ["RELIANCE"],
            "entry_rules": [{
                "direction": "LONG",
                "condition_groups": [{
                    "conditions": [{
                        "left_operand": "rsi_14",
                        "operator": "<",
                        "right_operand": 30,
                        "time_frame": "1D"
                    }],
                    "gate": "AND"
                }],
                "confirmation_candles": 1
            }],
            "exit_rules": [{
                "exit_type": "target",
                "target_pct": 5.0,
                "stop_loss_pct": 2.0
            }],
            "position_sizing": {
                "method": "pct_capital",
                "value": 10.0,
                "max_position_pct": 10.0,
                "max_concurrent_positions": 3
            },
            "market_filter": {
                "require_above_200ema": False
            },
            "indicators_config": {
                "rsi_14": {"period": 14}
            },
            "risk_per_trade_pct": 1.0,
            "max_daily_loss_pct": 2.0,
            "regime_awareness": False,
            "status": "draft",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
        
        # Backtest config
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=365)  # 1 year backtest
        
        config = {
            "strategy_spec": strategy_spec,
            "instrument": "RELIANCE",
            "start_date": start_date.strftime("%Y-%m-%d"),
            "end_date": end_date.strftime("%Y-%m-%d"),
            "initial_capital": 100000,
            "mode": "vectorised",  # Use fast mode for load testing
            "run_walk_forward": False,  # Disable for faster execution
            "run_monte_carlo": False,
            "run_regime_analysis": False
        }
        
        start_time = time.time()
        
        # Submit backtest
        with self.client.post(
            "/api/v1/backtest/run",
            json=config,
            catch_response=True,
            name="/backtest/run [submit]"
        ) as response:
            if response.status_code == 200:
                result = response.json()
                task_id = result.get("task_id")
                
                if task_id:
                    backtest_results["task_ids"].append(task_id)
                    response.success()
                    
                    # Poll for completion
                    self.poll_backtest_status(task_id, start_time)
                else:
                    response.failure("No task_id in response")
                    backtest_results["failed"] += 1
            else:
                response.failure(f"Got status code {response.status_code}")
                backtest_results["failed"] += 1
    
    def poll_backtest_status(self, task_id: str, start_time: float):
        """Poll backtest status until completion"""
        max_polls = 60  # Max 60 polls (5 minutes with 5s intervals)
        poll_count = 0
        
        while poll_count < max_polls:
            time.sleep(5)  # Wait 5 seconds between polls
            poll_count += 1
            
            with self.client.get(
                f"/api/v1/backtest/status/{task_id}",
                catch_response=True,
                name="/backtest/status [poll]"
            ) as response:
                if response.status_code == 200:
                    result = response.json()
                    status = result.get("status")
                    
                    if status == "completed":
                        duration = time.time() - start_time
                        backtest_results["completed"] += 1
                        backtest_results["durations"].append(duration)
                        response.success()
                        return
                    elif status == "failed":
                        backtest_results["failed"] += 1
                        response.failure(f"Backtest failed: {result.get('error')}")
                        return
                    elif status in ["pending", "running"]:
                        # Still processing
                        response.success()
                        continue
                    else:
                        response.failure(f"Unknown status: {status}")
                        backtest_results["failed"] += 1
                        return
                else:
                    response.failure(f"Status check failed: {response.status_code}")
        
        # Timeout
        backtest_results["failed"] += 1


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Called when the load test stops - print backtest statistics"""
    print("\n" + "="*60)
    print("BACKTEST LOAD TEST RESULTS")
    print("="*60)
    print(f"Total backtests submitted: {len(backtest_results['task_ids'])}")
    print(f"Completed successfully: {backtest_results['completed']}")
    print(f"Failed: {backtest_results['failed']}")
    
    if backtest_results["durations"]:
        avg_duration = sum(backtest_results["durations"]) / len(backtest_results["durations"])
        max_duration = max(backtest_results["durations"])
        min_duration = min(backtest_results["durations"])
        
        print(f"\nExecution Times:")
        print(f"  Average: {avg_duration:.2f}s")
        print(f"  Min: {min_duration:.2f}s")
        print(f"  Max: {max_duration:.2f}s")
    
    # Check if all 10 completed without errors
    success_rate = (backtest_results["completed"] / len(backtest_results["task_ids"]) * 100) if backtest_results["task_ids"] else 0
    
    print(f"\nSuccess Rate: {success_rate:.1f}%")
    print(f"Target: 100% (all 10 complete without errors)")
    print(f"Status: {'✅ PASS' if backtest_results['completed'] >= 10 and backtest_results['failed'] == 0 else '❌ FAIL'}")
    print("="*60)
