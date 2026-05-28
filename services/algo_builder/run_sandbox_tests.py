"""Test runner for sandbox module

This script runs all sandbox tests and reports results.

Usage:
    python run_sandbox_tests.py
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if __name__ == "__main__":
    try:
        import pytest
        
        print("=" * 70)
        print("Running Sandbox Tests")
        print("=" * 70)
        print()
        
        # Run tests with verbose output
        exit_code = pytest.main([
            "test_sandbox.py",
            "-v",
            "--tb=short",
            "--color=yes"
        ])
        
        print()
        print("=" * 70)
        if exit_code == 0:
            print("✓ All sandbox tests passed!")
        else:
            print("✗ Some tests failed. See output above.")
        print("=" * 70)
        
        sys.exit(exit_code)
        
    except ImportError:
        print("Error: pytest is not installed.")
        print("Install it with: pip install pytest")
        sys.exit(1)
