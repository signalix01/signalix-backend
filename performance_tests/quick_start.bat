@echo off
REM Quick Start Script for Performance Benchmarking (Windows)
REM This script sets up and runs all performance tests

echo =======================================================================
echo SIGNALIX PERFORMANCE BENCHMARKING - QUICK START
echo =======================================================================
echo.

REM Check if we're in the right directory
if not exist "gateway.py" (
    echo Error: Please run this script from the alphaedge-backend directory
    echo    cd alphaedge-backend ^&^& performance_tests\quick_start.bat
    exit /b 1
)

REM Step 1: Check Python version
echo Step 1: Checking Python version...
python --version
if errorlevel 1 (
    echo Error: Python not found
    exit /b 1
)
echo.

REM Step 2: Install dependencies
echo Step 2: Installing dependencies...
if exist "requirements-test.txt" (
    pip install -r requirements-test.txt >nul 2>&1
    echo Dependencies installed
) else (
    echo Error: requirements-test.txt not found
    exit /b 1
)
echo.

REM Step 3: Verify setup
echo Step 3: Verifying setup...
python performance_tests\verify_setup.py
if errorlevel 1 (
    echo.
    echo Setup verification failed. Please fix the issues above.
    echo.
    echo Common fixes:
    echo   - Start backend: uvicorn gateway:app --reload
    echo   - Start Redis: redis-server
    echo   - Start PostgreSQL: pg_ctl start
    echo   - Start Celery: celery -A services.backtesting.celery_app worker
    exit /b 1
)
echo.

REM Step 4: Create reports directory
echo Step 4: Creating reports directory...
if not exist "performance_tests\reports" mkdir performance_tests\reports
echo Reports directory ready
echo.

REM Step 5: Run benchmarks
echo Step 5: Running performance benchmarks...
echo This may take 10-15 minutes...
echo.

python performance_tests\run_all_benchmarks.py
set benchmark_result=%errorlevel%

echo.
echo =======================================================================
if %benchmark_result% equ 0 (
    echo ALL BENCHMARKS COMPLETED SUCCESSFULLY
) else (
    echo SOME BENCHMARKS FAILED
)
echo =======================================================================
echo.

REM Step 6: Show report location
echo Performance report generated at:
echo   alphaedge-backend\PERFORMANCE_REPORT.md
echo.
echo HTML reports available at:
echo   performance_tests\reports\
echo.

REM Step 7: Open report (optional)
set /p open_report="Open performance report? (y/n) "
if /i "%open_report%"=="y" (
    start PERFORMANCE_REPORT.md
)

exit /b %benchmark_result%
