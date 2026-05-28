"""
Integration tests for backtest Celery task + API workflow.

Tests the complete flow:
1. Submit backtest via API
2. Poll status endpoint
3. Retrieve full result
4. Verify concurrent limits

Requirements: 4.1, 4.2, 16.5, 16.6
"""
import pytest
import asyncio
import time
from datetime import datetime, timedelta
from services.backtesting.models import BacktestConfig, BacktestMode
from services.backtesting.tasks import run_backtest_sync
from services.backtesting.db_client import get_db_client
from services.backtesting.redis_client import get_redis_client
from services.algo_builder.models import (
    StrategySpec, EntryRule, ExitRule, PositionSizing,
    MarketFilter, ConditionBlock, ConditionGroup,
    PositionSizingMethod, CompareOperator, LogicGate
)
import uuid


@pytest.fixture
def sample_strategy_spec():
    """Create a sample strategy spec for testing"""
    return StrategySpec(
        strategy_id=str(uuid.uuid4()),
        user_id="test-user",
        name="Test Turtle Breakout",
        description="Simple turtle breakout for testing",
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
            ExitRule(
                exit_type="stop_loss",
                stop_loss_pct=2.0
            ),
            ExitRule(
                exit_type="target",
                target_pct=5.0
            )
        ],
        position_sizing=PositionSizing(
            method=PositionSizingMethod.PCT_CAPITAL,
            value=10.0,
            max_position_pct=10.0,
            max_concurrent_positions=1
        ),
        market_filter=MarketFilter(
            require_above_200ema=False
        ),
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


@pytest.fixture
def sample_backtest_config(sample_strategy_spec):
    """Create a sample backtest config"""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)  # 1 year
    
    return BacktestConfig(
        strategy_spec=sample_strategy_spec,
        instrument="BANKNIFTY",
        start_date=start_date.strftime("%Y-%m-%d"),
        end_date=end_date.strftime("%Y-%m-%d"),
        initial_capital=100000.0,
        mode=BacktestMode.VECTORISED,
        run_walk_forward=True,
        run_monte_carlo=False,  # Disable for faster testing
        run_regime_analysis=True
    )


def test_backtest_sync_execution(sample_backtest_config):
    """
    Test synchronous backtest execution.
    
    This tests the complete backtest flow without Celery:
    1. Submit backtest
    2. Wait for completion
    3. Retrieve result
    """
    # Submit backtest
    backtest_id = run_backtest_sync(sample_backtest_config, user_id="test-user")
    
    assert backtest_id is not None
    assert len(backtest_id) == 36  # UUID format
    
    # Retrieve result from database
    db_client = get_db_client()
    result = db_client.get_backtest_result(backtest_id)
    
    assert result is not None
    assert result.backtest_id == backtest_id
    assert result.instrument == "BANKNIFTY"
    assert result.total_trades >= 0
    assert result.sharpe_ratio is not None
    
    # Verify walk-forward results
    assert result.wf_train_return is not None
    assert result.wf_validate_return is not None
    assert result.wf_test_return is not None
    assert result.wf_consistency_score >= 0.0
    
    # Verify regime analysis results
    assert result.trending_bull_return is not None or result.ranging_return is not None
    
    print(f"\n✓ Backtest completed successfully")
    print(f"  Total trades: {result.total_trades}")
    print(f"  Total return: {result.total_return_pct:.2f}%")
    print(f"  Sharpe ratio: {result.sharpe_ratio:.2f}")
    print(f"  Max drawdown: {result.max_drawdown_pct:.2f}%")
    print(f"  WF consistency: {result.wf_consistency_score:.2f}")


@pytest.mark.asyncio
async def test_concurrent_backtest_limits():
    """
    Test tier-based concurrent backtest limits (Req 16.6).
    
    Tests:
    - Free tier: 1 concurrent backtest
    - Equity tier: 2 concurrent backtests
    - Pro tier: 5 concurrent backtests
    """
    redis_client = await get_redis_client()
    
    # Test free tier (limit: 1)
    user_id_free = "test-user-free"
    
    # Should allow first backtest
    can_start = await redis_client.can_start_backtest(user_id_free, "free")
    assert can_start is True
    
    # Increment count
    await redis_client.increment_concurrent_count(user_id_free)
    
    # Should block second backtest
    can_start = await redis_client.can_start_backtest(user_id_free, "free")
    assert can_start is False
    
    # Decrement count
    await redis_client.decrement_concurrent_count(user_id_free)
    
    # Should allow again
    can_start = await redis_client.can_start_backtest(user_id_free, "free")
    assert can_start is True
    
    print("\n✓ Free tier concurrent limit working correctly")
    
    # Test equity tier (limit: 2)
    user_id_equity = "test-user-equity"
    
    # Should allow 2 concurrent
    await redis_client.increment_concurrent_count(user_id_equity)
    can_start = await redis_client.can_start_backtest(user_id_equity, "equity")
    assert can_start is True
    
    await redis_client.increment_concurrent_count(user_id_equity)
    can_start = await redis_client.can_start_backtest(user_id_equity, "equity")
    assert can_start is False
    
    print("✓ Equity tier concurrent limit working correctly")
    
    # Test pro tier (limit: 5)
    user_id_pro = "test-user-pro"
    
    # Should allow 5 concurrent
    for i in range(5):
        can_start = await redis_client.can_start_backtest(user_id_pro, "pro")
        assert can_start is True
        await redis_client.increment_concurrent_count(user_id_pro)
    
    # Should block 6th
    can_start = await redis_client.can_start_backtest(user_id_pro, "pro")
    assert can_start is False
    
    print("✓ Pro tier concurrent limit working correctly")
    
    # Cleanup
    for i in range(5):
        await redis_client.decrement_concurrent_count(user_id_pro)


@pytest.mark.asyncio
async def test_task_progress_tracking():
    """
    Test task progress tracking in Redis.
    """
    redis_client = await get_redis_client()
    task_id = str(uuid.uuid4())
    
    # Set progress
    await redis_client.set_task_progress(task_id, 25, "running")
    
    # Get progress
    progress = await redis_client.get_task_progress(task_id)
    
    assert progress is not None
    assert progress['progress'] == 25
    assert progress['status'] == "running"
    
    # Update progress
    await redis_client.set_task_progress(task_id, 100, "complete")
    
    progress = await redis_client.get_task_progress(task_id)
    assert progress['progress'] == 100
    assert progress['status'] == "complete"
    
    print("\n✓ Task progress tracking working correctly")


def test_database_backtest_storage(sample_backtest_config):
    """
    Test database storage and retrieval of backtest results.
    """
    db_client = get_db_client()
    backtest_id = str(uuid.uuid4())
    user_id = "test-user"
    
    # Create pending record
    record = db_client.create_pending_backtest(backtest_id, sample_backtest_config, user_id)
    
    assert record is not None
    assert str(record.id) == backtest_id
    assert record.status == 'pending'
    
    # Update status to running
    db_client.update_backtest_status(backtest_id, 'running')
    
    status = db_client.get_backtest_status(backtest_id)
    assert status['status'] == 'running'
    
    # Update status to complete
    db_client.update_backtest_status(backtest_id, 'complete')
    
    status = db_client.get_backtest_status(backtest_id)
    assert status['status'] == 'complete'
    
    print("\n✓ Database backtest storage working correctly")


def test_backtest_history_pagination(sample_backtest_config):
    """
    Test paginated backtest history retrieval.
    """
    db_client = get_db_client()
    user_id = "test-user-history"
    
    # Create multiple backtest records
    backtest_ids = []
    for i in range(5):
        backtest_id = str(uuid.uuid4())
        db_client.create_pending_backtest(backtest_id, sample_backtest_config, user_id)
        backtest_ids.append(backtest_id)
    
    # Get history (page 1, limit 3)
    results, total = db_client.get_user_backtest_history(user_id, page=1, limit=3)
    
    assert total >= 5
    assert len(results) == 3
    
    # Get history (page 2, limit 3)
    results, total = db_client.get_user_backtest_history(user_id, page=2, limit=3)
    
    assert len(results) >= 2
    
    print(f"\n✓ Backtest history pagination working correctly (total: {total})")


if __name__ == "__main__":
    # Run tests
    print("Running integration tests...")
    print("=" * 60)
    
    # Create fixtures
    spec = sample_strategy_spec()
    config = sample_backtest_config(spec)
    
    # Run synchronous tests
    print("\n1. Testing synchronous backtest execution...")
    test_backtest_sync_execution(config)
    
    print("\n2. Testing database storage...")
    test_database_backtest_storage(config)
    
    print("\n3. Testing history pagination...")
    test_backtest_history_pagination(config)
    
    # Run async tests
    print("\n4. Testing concurrent limits...")
    asyncio.run(test_concurrent_backtest_limits())
    
    print("\n5. Testing progress tracking...")
    asyncio.run(test_task_progress_tracking())
    
    print("\n" + "=" * 60)
    print("✓ All integration tests passed!")
