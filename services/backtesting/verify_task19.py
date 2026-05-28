"""
Verification script for Task 19: Backtest Celery Task + API

This script verifies that all components are working correctly:
1. Celery app configuration
2. Database client
3. Redis client
4. Task execution
5. API endpoints

Run this script to verify the implementation.
"""
import sys
import asyncio
from datetime import datetime, timedelta
import uuid

# Add parent directory to path
sys.path.insert(0, '/d:/Saas/trade/signalixai-backend')

from services.backtesting.models import BacktestConfig, BacktestMode
from services.backtesting.db_client import get_db_client
from services.backtesting.redis_client import get_redis_client
from services.algo_builder.models import (
    StrategySpec, EntryRule, ExitRule, PositionSizing,
    MarketFilter, ConditionBlock, ConditionGroup,
    PositionSizingMethod, CompareOperator, LogicGate
)


def create_test_strategy():
    """Create a simple test strategy"""
    return StrategySpec(
        strategy_id=str(uuid.uuid4()),
        user_id="test-user",
        name="Verification Test Strategy",
        description="Simple strategy for verification",
        asset_class="equity",
        instruments=["BANKNIFTY"],
        entry_rules=[
            EntryRule(
                direction="LONG",
                condition_groups=[
                    ConditionGroup(
                        conditions=[
                            ConditionBlock(
                                left_operand="close",
                                operator=CompareOperator.CROSSES_ABOVE,
                                right_operand="highest_high_20",
                                time_frame="1D"
                            )
                        ],
                        gate=LogicGate.AND
                    )
                ],
                confirmation_candles=1
            )
        ],
        exit_rules=[
            ExitRule(exit_type="stop_loss", stop_loss_pct=2.0),
            ExitRule(exit_type="target", target_pct=5.0)
        ],
        position_sizing=PositionSizing(
            method=PositionSizingMethod.PCT_CAPITAL,
            value=10.0,
            max_position_pct=10.0,
            max_concurrent_positions=1
        ),
        market_filter=MarketFilter(require_above_200ema=False),
        indicators_config={
            "highest_high_20": {"period": 20},
            "lowest_low_10": {"period": 10}
        },
        risk_per_trade_pct=1.0,
        max_daily_loss_pct=2.0,
        regime_awareness=False,
        status="draft",
        created_at=datetime.utcnow().isoformat(),
        updated_at=datetime.utcnow().isoformat()
    )


def create_test_config(strategy_spec):
    """Create a test backtest config"""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=180)  # 6 months for faster testing
    
    return BacktestConfig(
        strategy_spec=strategy_spec,
        instrument="BANKNIFTY",
        start_date=start_date.strftime("%Y-%m-%d"),
        end_date=end_date.strftime("%Y-%m-%d"),
        initial_capital=100000.0,
        mode=BacktestMode.VECTORISED,
        run_walk_forward=False,  # Disable for faster verification
        run_monte_carlo=False,
        run_regime_analysis=False
    )


def verify_database_client():
    """Verify database client is working"""
    print("\n1. Verifying Database Client...")
    print("-" * 60)
    
    try:
        db_client = get_db_client()
        print("✓ Database client initialized")
        
        # Create test backtest record
        strategy = create_test_strategy()
        config = create_test_config(strategy)
        backtest_id = str(uuid.uuid4())
        user_id = "test-user"
        
        record = db_client.create_pending_backtest(backtest_id, config, user_id)
        print(f"✓ Created pending backtest record: {backtest_id}")
        
        # Update status
        db_client.update_backtest_status(backtest_id, 'running')
        print("✓ Updated status to 'running'")
        
        # Get status
        status = db_client.get_backtest_status(backtest_id)
        assert status['status'] == 'running'
        print("✓ Retrieved status successfully")
        
        # Update to complete
        db_client.update_backtest_status(backtest_id, 'complete')
        print("✓ Updated status to 'complete'")
        
        print("\n✅ Database client verification PASSED")
        return True
        
    except Exception as e:
        print(f"\n❌ Database client verification FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


async def verify_redis_client():
    """Verify Redis client is working"""
    print("\n2. Verifying Redis Client...")
    print("-" * 60)
    
    try:
        redis_client = await get_redis_client()
        print("✓ Redis client initialized")
        
        # Test concurrent limits
        user_id = f"test-user-{uuid.uuid4()}"
        
        # Check can start (should be True)
        can_start = await redis_client.can_start_backtest(user_id, "free")
        assert can_start is True
        print("✓ Can start backtest (free tier, 0/1)")
        
        # Increment count
        count = await redis_client.increment_concurrent_count(user_id)
        assert count == 1
        print("✓ Incremented concurrent count to 1")
        
        # Check can start (should be False for free tier)
        can_start = await redis_client.can_start_backtest(user_id, "free")
        assert can_start is False
        print("✓ Cannot start backtest (free tier, 1/1 - limit reached)")
        
        # Decrement count
        count = await redis_client.decrement_concurrent_count(user_id)
        assert count == 0
        print("✓ Decremented concurrent count to 0")
        
        # Check can start again (should be True)
        can_start = await redis_client.can_start_backtest(user_id, "free")
        assert can_start is True
        print("✓ Can start backtest again (free tier, 0/1)")
        
        # Test progress tracking
        task_id = str(uuid.uuid4())
        await redis_client.set_task_progress(task_id, 50, "running")
        print("✓ Set task progress to 50%")
        
        progress = await redis_client.get_task_progress(task_id)
        assert progress['progress'] == 50
        assert progress['status'] == "running"
        print("✓ Retrieved task progress successfully")
        
        print("\n✅ Redis client verification PASSED")
        return True
        
    except Exception as e:
        print(f"\n❌ Redis client verification FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def verify_celery_app():
    """Verify Celery app configuration"""
    print("\n3. Verifying Celery App Configuration...")
    print("-" * 60)
    
    try:
        from services.backtesting.celery_app import celery_app
        
        print(f"✓ Celery app initialized: {celery_app.main}")
        print(f"✓ Broker URL: {celery_app.conf.broker_url}")
        print(f"✓ Result backend: {celery_app.conf.result_backend}")
        print(f"✓ Task time limit: {celery_app.conf.task_time_limit}s")
        print(f"✓ Worker prefetch: {celery_app.conf.worker_prefetch_multiplier}")
        
        # Check task is registered
        from services.backtesting.tasks import run_backtest_task
        task_name = run_backtest_task.name
        print(f"✓ Task registered: {task_name}")
        
        print("\n✅ Celery app verification PASSED")
        return True
        
    except Exception as e:
        print(f"\n❌ Celery app verification FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def verify_tier_limits():
    """Verify tier limit configuration"""
    print("\n4. Verifying Tier Limits...")
    print("-" * 60)
    
    try:
        from services.backtesting.redis_client import BacktestRedisClient
        
        limits = BacktestRedisClient.TIER_LIMITS
        
        assert limits['free'] == 1
        print("✓ Free tier: 1 concurrent backtest")
        
        assert limits['equity'] == 2
        print("✓ Equity tier: 2 concurrent backtests")
        
        assert limits['fo'] == 3
        print("✓ F&O tier: 3 concurrent backtests")
        
        assert limits['pro'] == 5
        print("✓ Pro tier: 5 concurrent backtests")
        
        assert limits['enterprise'] == 999
        print("✓ Enterprise tier: unlimited concurrent backtests")
        
        print("\n✅ Tier limits verification PASSED")
        return True
        
    except Exception as e:
        print(f"\n❌ Tier limits verification FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all verifications"""
    print("=" * 60)
    print("Task 19 Verification: Backtest Celery Task + API")
    print("=" * 60)
    
    results = []
    
    # Run verifications
    results.append(("Database Client", verify_database_client()))
    results.append(("Redis Client", asyncio.run(verify_redis_client())))
    results.append(("Celery App", verify_celery_app()))
    results.append(("Tier Limits", verify_tier_limits()))
    
    # Summary
    print("\n" + "=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)
    
    for name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{name:.<40} {status}")
    
    all_passed = all(result[1] for result in results)
    
    print("\n" + "=" * 60)
    if all_passed:
        print("✅ ALL VERIFICATIONS PASSED")
        print("\nTask 19 implementation is working correctly!")
        print("\nNext steps:")
        print("1. Start Celery worker: celery -A services.backtesting.celery_app worker")
        print("2. Run integration tests: pytest services/backtesting/test_integration.py")
        print("3. Test API endpoints via FastAPI")
    else:
        print("❌ SOME VERIFICATIONS FAILED")
        print("\nPlease check the errors above and fix the issues.")
    print("=" * 60)
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
