"""
Comprehensive Performance Benchmark Runner

Executes all performance tests and generates PERFORMANCE_REPORT.md

Tests:
1. Screening SQL pre-filter (100 concurrent requests, < 500ms target)
2. Backtest horizontal scaling (10 concurrent tasks, all complete)
3. Anomaly detection pipeline (1,000 bars in 60s, process in < 30s)
4. Alert delivery (100 critical events, p95 < 5s)

Usage:
    python run_all_benchmarks.py
"""

import subprocess
import sys
import os
import json
import time
from datetime import datetime
from typing import Dict, Any


class BenchmarkRunner:
    """Orchestrates all performance benchmarks"""
    
    def __init__(self):
        self.results = {}
        self.start_time = None
        self.end_time = None
    
    def run_locust_test(self, locustfile: str, test_name: str, users: int, duration: str) -> Dict[str, Any]:
        """Run a Locust load test"""
        print(f"\n{'='*70}")
        print(f"Running {test_name}")
        print(f"{'='*70}\n")
        
        cmd = [
            "locust",
            "-f", locustfile,
            "--headless",
            "--users", str(users),
            "--spawn-rate", str(min(users, 10)),
            "--run-time", duration,
            "--host", "http://localhost:8000",
            "--html", f"performance_tests/reports/{test_name.replace(' ', '_').lower()}.html",
            "--csv", f"performance_tests/reports/{test_name.replace(' ', '_').lower()}"
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            # Parse output for results
            output = result.stdout + result.stderr
            
            return {
                "success": result.returncode == 0,
                "output": output,
                "command": " ".join(cmd)
            }
        
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "output": "Test timed out after 5 minutes",
                "command": " ".join(cmd)
            }
        except Exception as e:
            return {
                "success": False,
                "output": f"Error running test: {str(e)}",
                "command": " ".join(cmd)
            }
    
    def run_python_test(self, script: str, test_name: str) -> Dict[str, Any]:
        """Run a Python performance test"""
        print(f"\n{'='*70}")
        print(f"Running {test_name}")
        print(f"{'='*70}\n")
        
        cmd = [sys.executable, script]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            return {
                "success": result.returncode == 0,
                "output": result.stdout + result.stderr,
                "command": " ".join(cmd)
            }
        
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "output": "Test timed out after 5 minutes",
                "command": " ".join(cmd)
            }
        except Exception as e:
            return {
                "success": False,
                "output": f"Error running test: {str(e)}",
                "command": " ".join(cmd)
            }
    
    def run_all_tests(self):
        """Run all performance benchmarks"""
        self.start_time = datetime.utcnow()
        
        print("="*70)
        print("PERFORMANCE BENCHMARK SUITE")
        print("="*70)
        print(f"Start time: {self.start_time.isoformat()}")
        print()
        
        # Create reports directory
        os.makedirs("performance_tests/reports", exist_ok=True)
        
        # Test 1: Screening SQL pre-filter (100 concurrent requests)
        self.results["screening_load_test"] = self.run_locust_test(
            locustfile="performance_tests/locustfile_screening.py",
            test_name="Screening Load Test",
            users=100,
            duration="2m"
        )
        
        # Test 2: Backtest horizontal scaling (10 concurrent tasks)
        self.results["backtest_load_test"] = self.run_locust_test(
            locustfile="performance_tests/locustfile_backtest.py",
            test_name="Backtest Load Test",
            users=10,
            duration="5m"
        )
        
        # Test 3: Anomaly detection pipeline
        self.results["anomaly_pipeline_test"] = self.run_python_test(
            script="performance_tests/test_anomaly_pipeline.py",
            test_name="Anomaly Pipeline Test"
        )
        
        # Test 4: Alert delivery
        self.results["alert_delivery_test"] = self.run_python_test(
            script="performance_tests/test_alert_delivery.py",
            test_name="Alert Delivery Test"
        )
        
        self.end_time = datetime.utcnow()
        
        print("\n" + "="*70)
        print("ALL TESTS COMPLETED")
        print("="*70)
        print(f"End time: {self.end_time.isoformat()}")
        print(f"Total duration: {(self.end_time - self.start_time).total_seconds():.2f}s")
        print()
    
    def generate_report(self):
        """Generate PERFORMANCE_REPORT.md"""
        report_path = "signalixai-backend/PERFORMANCE_REPORT.md"
        
        with open(report_path, "w") as f:
            f.write("# Performance Benchmark Report\n\n")
            f.write(f"**Generated:** {datetime.utcnow().isoformat()}Z\n\n")
            f.write(f"**Test Duration:** {(self.end_time - self.start_time).total_seconds():.2f} seconds\n\n")
            
            f.write("## Executive Summary\n\n")
            
            # Count passes/fails
            total_tests = len(self.results)
            passed_tests = sum(1 for r in self.results.values() if r["success"])
            
            f.write(f"- **Total Tests:** {total_tests}\n")
            f.write(f"- **Passed:** {passed_tests}\n")
            f.write(f"- **Failed:** {total_tests - passed_tests}\n")
            f.write(f"- **Success Rate:** {(passed_tests / total_tests * 100):.1f}%\n\n")
            
            # Overall status
            if passed_tests == total_tests:
                f.write("**Overall Status:** ✅ **PASS** - All performance targets met\n\n")
            else:
                f.write("**Overall Status:** ❌ **FAIL** - Some performance targets not met\n\n")
            
            f.write("---\n\n")
            
            # Test 1: Screening Load Test
            f.write("## Test 1: Screening SQL Pre-Filter Performance\n\n")
            f.write("**Objective:** Verify screening SQL pre-filter completes in < 500ms under load\n\n")
            f.write("**Test Configuration:**\n")
            f.write("- Concurrent users: 100\n")
            f.write("- Test duration: 2 minutes\n")
            f.write("- Target: SQL pre-filter < 500ms\n\n")
            
            result = self.results["screening_load_test"]
            f.write(f"**Result:** {'✅ PASS' if result['success'] else '❌ FAIL'}\n\n")
            f.write("**Output:**\n```\n")
            f.write(result["output"][-2000:])  # Last 2000 chars
            f.write("\n```\n\n")
            
            # Test 2: Backtest Load Test
            f.write("## Test 2: Backtest Horizontal Scaling\n\n")
            f.write("**Objective:** Verify 10 concurrent backtest tasks complete without errors\n\n")
            f.write("**Test Configuration:**\n")
            f.write("- Concurrent users: 10\n")
            f.write("- Test duration: 5 minutes\n")
            f.write("- Target: All 10 complete successfully\n\n")
            
            result = self.results["backtest_load_test"]
            f.write(f"**Result:** {'✅ PASS' if result['success'] else '❌ FAIL'}\n\n")
            f.write("**Output:**\n```\n")
            f.write(result["output"][-2000:])
            f.write("\n```\n\n")
            
            # Test 3: Anomaly Pipeline
            f.write("## Test 3: Anomaly Detection Pipeline Performance\n\n")
            f.write("**Objective:** Process 1,000 bars injected over 60 seconds within 30 seconds\n\n")
            f.write("**Test Configuration:**\n")
            f.write("- Bars to inject: 1,000\n")
            f.write("- Injection duration: 60 seconds\n")
            f.write("- Processing target: < 30 seconds\n\n")
            
            result = self.results["anomaly_pipeline_test"]
            f.write(f"**Result:** {'✅ PASS' if result['success'] else '❌ FAIL'}\n\n")
            f.write("**Output:**\n```\n")
            f.write(result["output"])
            f.write("\n```\n\n")
            
            # Test 4: Alert Delivery
            f.write("## Test 4: Alert Delivery Performance\n\n")
            f.write("**Objective:** Deliver 100 critical events with p95 latency < 5 seconds\n\n")
            f.write("**Test Configuration:**\n")
            f.write("- Events to inject: 100\n")
            f.write("- Severity: CRITICAL\n")
            f.write("- P95 latency target: < 5 seconds\n\n")
            
            result = self.results["alert_delivery_test"]
            f.write(f"**Result:** {'✅ PASS' if result['success'] else '❌ FAIL'}\n\n")
            f.write("**Output:**\n```\n")
            f.write(result["output"])
            f.write("\n```\n\n")
            
            # Requirements mapping
            f.write("---\n\n")
            f.write("## Requirements Validation\n\n")
            f.write("| Requirement | Test | Status |\n")
            f.write("|-------------|------|--------|\n")
            f.write("| 16.4 - Anomaly detection pipeline performance | Test 3 | ")
            f.write("✅ PASS" if self.results["anomaly_pipeline_test"]["success"] else "❌ FAIL")
            f.write(" |\n")
            f.write("| 16.5 - Alert delivery latency | Test 4 | ")
            f.write("✅ PASS" if self.results["alert_delivery_test"]["success"] else "❌ FAIL")
            f.write(" |\n")
            f.write("| 14.5 - Alert delivery reliability | Test 4 | ")
            f.write("✅ PASS" if self.results["alert_delivery_test"]["success"] else "❌ FAIL")
            f.write(" |\n\n")
            
            # Recommendations
            f.write("## Recommendations\n\n")
            
            if passed_tests == total_tests:
                f.write("All performance targets have been met. The system is ready for production deployment.\n\n")
            else:
                f.write("Some performance targets were not met. Consider the following:\n\n")
                
                if not self.results["screening_load_test"]["success"]:
                    f.write("- **Screening:** Optimize SQL queries, add database indexes, or increase database resources\n")
                
                if not self.results["backtest_load_test"]["success"]:
                    f.write("- **Backtesting:** Scale Celery workers horizontally, optimize backtest algorithms\n")
                
                if not self.results["anomaly_pipeline_test"]["success"]:
                    f.write("- **Anomaly Detection:** Optimize detector algorithms, add caching, scale processing workers\n")
                
                if not self.results["alert_delivery_test"]["success"]:
                    f.write("- **Alert Delivery:** Optimize delivery channels, add message queuing, scale delivery workers\n")
            
            f.write("\n---\n\n")
            f.write(f"*Report generated by Performance Benchmark Suite v1.0*\n")
        
        print(f"✅ Performance report generated: {report_path}")
        return report_path


def main():
    """Main entry point"""
    runner = BenchmarkRunner()
    
    try:
        # Run all tests
        runner.run_all_tests()
        
        # Generate report
        report_path = runner.generate_report()
        
        print("\n" + "="*70)
        print("BENCHMARK SUITE COMPLETE")
        print("="*70)
        print(f"Report: {report_path}")
        print()
        
        # Exit with success if all tests passed
        all_passed = all(r["success"] for r in runner.results.values())
        sys.exit(0 if all_passed else 1)
    
    except KeyboardInterrupt:
        print("\n\n❌ Benchmark suite interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Benchmark suite failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
