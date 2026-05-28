"""
Verify Performance Testing Setup

Checks that all required services and dependencies are available
before running performance benchmarks.

Usage:
    python performance_tests/verify_setup.py
"""

import sys
import os
import subprocess
from typing import List, Tuple


def check_python_package(package: str) -> Tuple[bool, str]:
    """Check if a Python package is installed"""
    try:
        __import__(package)
        return True, f"✅ {package} is installed"
    except ImportError:
        return False, f"❌ {package} is NOT installed"


def check_service(host: str, port: int, name: str) -> Tuple[bool, str]:
    """Check if a service is accessible"""
    import socket
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex((host, port))
        sock.close()
        
        if result == 0:
            return True, f"✅ {name} is accessible at {host}:{port}"
        else:
            return False, f"❌ {name} is NOT accessible at {host}:{port}"
    except Exception as e:
        return False, f"❌ {name} check failed: {e}"


def check_command(command: str) -> Tuple[bool, str]:
    """Check if a command is available"""
    try:
        result = subprocess.run(
            [command, "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            version = result.stdout.strip().split('\n')[0]
            return True, f"✅ {command} is available: {version}"
        else:
            return False, f"❌ {command} is NOT available"
    except FileNotFoundError:
        return False, f"❌ {command} is NOT installed"
    except Exception as e:
        return False, f"❌ {command} check failed: {e}"


def verify_setup():
    """Run all verification checks"""
    print("="*70)
    print("PERFORMANCE TESTING SETUP VERIFICATION")
    print("="*70)
    print()
    
    checks = []
    
    # Check Python packages
    print("Checking Python Dependencies...")
    print("-" * 70)
    
    packages = [
        "locust",
        "fastapi",
        "redis",
        "pandas",
        "numpy",
        "asyncio"
    ]
    
    for package in packages:
        success, message = check_python_package(package)
        checks.append(success)
        print(message)
    
    print()
    
    # Check services
    print("Checking Services...")
    print("-" * 70)
    
    services = [
        ("localhost", 8000, "Backend API"),
        ("localhost", 6379, "Redis"),
        ("localhost", 5432, "PostgreSQL")
    ]
    
    for host, port, name in services:
        success, message = check_service(host, port, name)
        checks.append(success)
        print(message)
    
    print()
    
    # Check commands
    print("Checking Commands...")
    print("-" * 70)
    
    commands = ["locust", "python"]
    
    for command in commands:
        success, message = check_command(command)
        checks.append(success)
        print(message)
    
    print()
    
    # Check directories
    print("Checking Directories...")
    print("-" * 70)
    
    dirs = [
        "performance_tests",
        "services/screening",
        "services/backtesting",
        "services/alerts"
    ]
    
    for dir_path in dirs:
        if os.path.isdir(dir_path):
            checks.append(True)
            print(f"✅ {dir_path} exists")
        else:
            checks.append(False)
            print(f"❌ {dir_path} does NOT exist")
    
    print()
    
    # Summary
    print("="*70)
    print("VERIFICATION SUMMARY")
    print("="*70)
    
    total_checks = len(checks)
    passed_checks = sum(checks)
    failed_checks = total_checks - passed_checks
    
    print(f"Total checks: {total_checks}")
    print(f"Passed: {passed_checks}")
    print(f"Failed: {failed_checks}")
    print()
    
    if all(checks):
        print("✅ ALL CHECKS PASSED - Ready to run performance benchmarks")
        print()
        print("Run benchmarks with:")
        print("  python performance_tests/run_all_benchmarks.py")
        return 0
    else:
        print("❌ SOME CHECKS FAILED - Please fix issues before running benchmarks")
        print()
        print("Common fixes:")
        print("  - Install dependencies: pip install -r requirements-test.txt")
        print("  - Start backend: uvicorn gateway:app --reload")
        print("  - Start Redis: redis-server")
        print("  - Start PostgreSQL: pg_ctl start")
        return 1


if __name__ == "__main__":
    sys.exit(verify_setup())
