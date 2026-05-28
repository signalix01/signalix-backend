#!/bin/bash

# Quick Start Script for Performance Benchmarking
# This script sets up and runs all performance tests

set -e  # Exit on error

echo "======================================================================="
echo "SIGNALIX PERFORMANCE BENCHMARKING - QUICK START"
echo "======================================================================="
echo ""

# Check if we're in the right directory
if [ ! -f "gateway.py" ]; then
    echo "❌ Error: Please run this script from the alphaedge-backend directory"
    echo "   cd alphaedge-backend && bash performance_tests/quick_start.sh"
    exit 1
fi

# Step 1: Check Python version
echo "Step 1: Checking Python version..."
python_version=$(python --version 2>&1 | awk '{print $2}')
echo "✅ Python version: $python_version"
echo ""

# Step 2: Install dependencies
echo "Step 2: Installing dependencies..."
if [ -f "requirements-test.txt" ]; then
    pip install -r requirements-test.txt > /dev/null 2>&1
    echo "✅ Dependencies installed"
else
    echo "❌ requirements-test.txt not found"
    exit 1
fi
echo ""

# Step 3: Verify setup
echo "Step 3: Verifying setup..."
python performance_tests/verify_setup.py
verify_result=$?

if [ $verify_result -ne 0 ]; then
    echo ""
    echo "❌ Setup verification failed. Please fix the issues above."
    echo ""
    echo "Common fixes:"
    echo "  - Start backend: uvicorn gateway:app --reload"
    echo "  - Start Redis: redis-server"
    echo "  - Start PostgreSQL: pg_ctl start"
    echo "  - Start Celery: celery -A services.backtesting.celery_app worker"
    exit 1
fi
echo ""

# Step 4: Create reports directory
echo "Step 4: Creating reports directory..."
mkdir -p performance_tests/reports
echo "✅ Reports directory ready"
echo ""

# Step 5: Run benchmarks
echo "Step 5: Running performance benchmarks..."
echo "This may take 10-15 minutes..."
echo ""

python performance_tests/run_all_benchmarks.py
benchmark_result=$?

echo ""
echo "======================================================================="
if [ $benchmark_result -eq 0 ]; then
    echo "✅ ALL BENCHMARKS COMPLETED SUCCESSFULLY"
else
    echo "❌ SOME BENCHMARKS FAILED"
fi
echo "======================================================================="
echo ""

# Step 6: Show report location
echo "Performance report generated at:"
echo "  alphaedge-backend/PERFORMANCE_REPORT.md"
echo ""
echo "HTML reports available at:"
echo "  performance_tests/reports/"
echo ""

# Step 7: Open report (optional)
if command -v open &> /dev/null; then
    read -p "Open performance report? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        open PERFORMANCE_REPORT.md
    fi
elif command -v xdg-open &> /dev/null; then
    read -p "Open performance report? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        xdg-open PERFORMANCE_REPORT.md
    fi
fi

exit $benchmark_result
