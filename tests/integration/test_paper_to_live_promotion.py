"""
Integration tests for paper-to-live strategy promotion endpoint.

Tests the complete promotion workflow including all pre-flight checks:
1. Strategy must be in paper mode
2. Strategy must have been in paper mode >= 30 days
3. Paper mode must have positive return
4. Walk-forward validation must have passed
5. User must provide 4-digit PIN confirmation

Requirements: 15.2
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from httpx import AsyncClient
import uuid

from gateway import app
from shared.database.models import Strategy, BacktestResult, Base
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
import os


# Test database setup
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/signalixai_test")
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestAsyncSessionLocal = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture
async def db_session():
    """Create a test database session."""
    async with TestAsyncSessionLocal() as session:
        yield session


@pytest.fixture
def test_user_id():
    """Test user ID."""
    return "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def test_strategy_spec():
    """Sample strategy specification."""
    return {
        "strategy_id": str(uuid.uuid4()),
        "user_id": "00000000-0000-0000-0000-000000000001",
        "name": "Test Strategy",
        "description": "Test strategy for promotion",
        "asset_class": "equity",
        "instruments": ["NIFTY"],
        "entry_rules": [
            {
                "direction": "LONG",
                "condition_groups": [
                    {
                        "conditions": [
                            {
                                "left_operand": "rsi_14",
                                "operator": "<",
                                "right_operand": 30.0,
                                "time_frame": "1D"
                            }
                        ],
                        "gate": "AND"
                    }
                ],
                "confirmation_candles": 1
            }
        ],
        "exit_rules": [
            {
                "exit_type": "target",
                "target_pct": 5.0
            }
        ],
        "position_sizing": {
            "method": "pct_capital",
            "value": 5.0,
            "max_position_pct": 10.0,
            "max_concurrent_positions": 3
        },
        "market_filter": {
            "require_above_200ema": False,
            "min_adx": None,
            "max_vix": None,
            "require_positive_breadth": False
        },
        "indicators_config": {
            "rsi_14": {"period": 14}
        },
        "risk_per_trade_pct": 1.0,
        "max_daily_loss_pct": 2.0,
        "regime_awareness": True,
        "status": "paper",
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat()
    }


@pytest.fixture
def create_test_strategy(db_session, test_user_id, test_strategy_spec):
    """Create a test strategy in the database."""
    async def _create(
        status="paper",
        days_in_paper=30,
        has_backtest=True,
        backtest_return=10.0,
        wf_consistency_score=0.8
    ):
        strategy_id = uuid.uuid4()
        
        # Calculate updated_at based on days_in_paper
        updated_at = datetime.utcnow() - timedelta(days=days_in_paper)
        
        strategy = Strategy(
            id=strategy_id,
            user_id=uuid.UUID(test_user_id),
            template_id=None,
            name="Test Strategy",
            description="Test strategy for promotion",
            spec=test_strategy_spec,
            compiled_hash="test_hash_123",
            status=status,
            created_at=updated_at,
            updated_at=updated_at
        )
        
        db_session.add(strategy)
        await db_session.commit()
        
        # Create backtest result if requested
        if has_backtest:
            backtest = BacktestResult(
                id=uuid.uuid4(),
                strategy_id=strategy_id,
                user_id=uuid.UUID(test_user_id),
                instrument="NIFTY",
                asset_class="equity",
                start_date=datetime.utcnow() - timedelta(days=365),
                end_date=datetime.utcnow(),
                mode="vectorised",
                total_return_pct=backtest_return,
                cagr_pct=backtest_return,
                sharpe_ratio=1.5,
                sortino_ratio=2.0,
                calmar_ratio=1.2,
                max_drawdown_pct=10.0,
                avg_drawdown_pct=5.0,
                max_drawdown_duration_days=30,
                total_trades=100,
                win_rate_pct=60.0,
                avg_win_pct=2.5,
                avg_loss_pct=-1.5,
                profit_factor=1.8,
                expectancy_per_trade=50.0,
                avg_hold_days=5.0,
                max_consecutive_losses=3,
                kelly_fraction=0.15,
                half_kelly=0.075,
                wf_train_return=12.0,
                wf_validate_return=10.0,
                wf_test_return=8.0,
                wf_consistency_score=wf_consistency_score,
                trending_bull_return=15.0,
                trending_bear_return=-5.0,
                ranging_return=5.0,
                volatile_return=8.0,
                mc_median_return=10.0,
                mc_5th_percentile_return=2.0,
                mc_95th_percentile_return=18.0,
                mc_ruin_probability=0.02,
                result_data={},
                status='complete',
                created_at=datetime.utcnow(),
                completed_at=datetime.utcnow()
            )
            
            db_session.add(backtest)
            await db_session.commit()
        
        return str(strategy_id)
    
    return _create


class TestPaperToLivePromotion:
    """Test paper-to-live promotion endpoint."""
    
    @pytest.mark.asyncio
    async def test_successful_promotion(self, create_test_strategy):
        """Test successful promotion with all checks passing."""
        strategy_id = await create_test_strategy(
            status="paper",
            days_in_paper=35,  # > 30 days
            has_backtest=True,
            backtest_return=15.0,  # Positive
            wf_consistency_score=0.85  # > 0.7
        )
        
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/algo/strategies/{strategy_id}/live",
                json={"pin": "1234"}
            )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["status"] == "live"
        assert data["strategy_id"] == strategy_id
        assert "promoted to live trading successfully" in data["message"].lower()
    
    @pytest.mark.asyncio
    async def test_rejection_insufficient_paper_days(self, create_test_strategy):
        """Test rejection when strategy has been in paper mode < 30 days."""
        strategy_id = await create_test_strategy(
            status="paper",
            days_in_paper=25,  # < 30 days
            has_backtest=True,
            backtest_return=15.0,
            wf_consistency_score=0.85
        )
        
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/algo/strategies/{strategy_id}/live",
                json={"pin": "1234"}
            )
        
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        detail = data["detail"]
        assert detail["error"] == "Insufficient paper trading duration"
        assert detail["days_in_paper_mode"] == 25
        assert detail["required_days"] == 30
        assert detail["days_remaining"] == 5
        assert "minimum 30 days required" in detail["message"].lower()
        assert "continue paper trading" in detail["action"].lower()
    
    @pytest.mark.asyncio
    async def test_rejection_invalid_status(self, create_test_strategy):
        """Test rejection when strategy is not in paper mode."""
        strategy_id = await create_test_strategy(
            status="draft",  # Not paper
            days_in_paper=35,
            has_backtest=True,
            backtest_return=15.0,
            wf_consistency_score=0.85
        )
        
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/algo/strategies/{strategy_id}/live",
                json={"pin": "1234"}
            )
        
        assert response.status_code == 400
        data = response.json()
        detail = data["detail"]
        assert detail["error"] == "Invalid strategy status"
        assert detail["current_status"] == "draft"
        assert detail["required_status"] == "paper"
        assert "must be in paper trading mode" in detail["message"].lower()
    
    @pytest.mark.asyncio
    async def test_rejection_no_backtest(self, create_test_strategy):
        """Test rejection when strategy has no backtest results."""
        strategy_id = await create_test_strategy(
            status="paper",
            days_in_paper=35,
            has_backtest=False  # No backtest
        )
        
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/algo/strategies/{strategy_id}/live",
                json={"pin": "1234"}
            )
        
        assert response.status_code == 400
        data = response.json()
        detail = data["detail"]
        assert detail["error"] == "No backtest results found"
        assert "must have at least one completed backtest" in detail["message"].lower()
        assert "run a backtest" in detail["action"].lower()
    
    @pytest.mark.asyncio
    async def test_rejection_negative_returns(self, create_test_strategy):
        """Test rejection when strategy has negative returns."""
        strategy_id = await create_test_strategy(
            status="paper",
            days_in_paper=35,
            has_backtest=True,
            backtest_return=-5.0,  # Negative
            wf_consistency_score=0.85
        )
        
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/algo/strategies/{strategy_id}/live",
                json={"pin": "1234"}
            )
        
        assert response.status_code == 400
        data = response.json()
        detail = data["detail"]
        assert detail["error"] == "Negative or zero returns"
        assert detail["total_return_pct"] == -5.0
        assert "must demonstrate positive returns" in detail["message"].lower()
        assert "optimize strategy" in detail["action"].lower()
    
    @pytest.mark.asyncio
    async def test_rejection_failed_walk_forward(self, create_test_strategy):
        """Test rejection when walk-forward validation failed."""
        strategy_id = await create_test_strategy(
            status="paper",
            days_in_paper=35,
            has_backtest=True,
            backtest_return=15.0,
            wf_consistency_score=0.5  # < 0.7
        )
        
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/algo/strategies/{strategy_id}/live",
                json={"pin": "1234"}
            )
        
        assert response.status_code == 400
        data = response.json()
        detail = data["detail"]
        assert detail["error"] == "Walk-forward validation failed"
        assert detail["wf_consistency_score"] == 0.5
        assert detail["required_score"] == 0.7
        assert "consistency score >= 0.7" in detail["message"].lower()
        assert "simplify strategy rules" in detail["action"].lower()
    
    @pytest.mark.asyncio
    async def test_rejection_invalid_pin_format(self, create_test_strategy):
        """Test rejection when PIN is not 4 digits."""
        strategy_id = await create_test_strategy(
            status="paper",
            days_in_paper=35,
            has_backtest=True,
            backtest_return=15.0,
            wf_consistency_score=0.85
        )
        
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/algo/strategies/{strategy_id}/live",
                json={"pin": "abcd"}  # Not digits
            )
        
        assert response.status_code == 403
        data = response.json()
        detail = data["detail"]
        assert detail["error"] == "Invalid PIN format"
        assert "must be exactly 4 digits" in detail["message"].lower()
    
    @pytest.mark.asyncio
    async def test_rejection_pin_too_short(self, create_test_strategy):
        """Test rejection when PIN is less than 4 digits."""
        strategy_id = await create_test_strategy(
            status="paper",
            days_in_paper=35,
            has_backtest=True,
            backtest_return=15.0,
            wf_consistency_score=0.85
        )
        
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/algo/strategies/{strategy_id}/live",
                json={"pin": "123"}  # Too short
            )
        
        # Should fail validation at Pydantic level
        assert response.status_code == 422
    
    @pytest.mark.asyncio
    async def test_rejection_strategy_not_found(self):
        """Test rejection when strategy doesn't exist."""
        fake_strategy_id = str(uuid.uuid4())
        
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/algo/strategies/{fake_strategy_id}/live",
                json={"pin": "1234"}
            )
        
        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()
    
    @pytest.mark.asyncio
    async def test_edge_case_exactly_30_days(self, create_test_strategy):
        """Test promotion with exactly 30 days in paper mode."""
        strategy_id = await create_test_strategy(
            status="paper",
            days_in_paper=30,  # Exactly 30 days
            has_backtest=True,
            backtest_return=15.0,
            wf_consistency_score=0.85
        )
        
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/algo/strategies/{strategy_id}/live",
                json={"pin": "1234"}
            )
        
        # Should succeed with exactly 30 days
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
    
    @pytest.mark.asyncio
    async def test_edge_case_zero_return(self, create_test_strategy):
        """Test rejection with exactly zero return."""
        strategy_id = await create_test_strategy(
            status="paper",
            days_in_paper=35,
            has_backtest=True,
            backtest_return=0.0,  # Zero return
            wf_consistency_score=0.85
        )
        
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/algo/strategies/{strategy_id}/live",
                json={"pin": "1234"}
            )
        
        # Should fail - requires positive return
        assert response.status_code == 400
        data = response.json()
        detail = data["detail"]
        assert detail["error"] == "Negative or zero returns"
    
    @pytest.mark.asyncio
    async def test_edge_case_wf_score_exactly_threshold(self, create_test_strategy):
        """Test promotion with WF consistency score exactly at threshold."""
        strategy_id = await create_test_strategy(
            status="paper",
            days_in_paper=35,
            has_backtest=True,
            backtest_return=15.0,
            wf_consistency_score=0.7  # Exactly at threshold
        )
        
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/algo/strategies/{strategy_id}/live",
                json={"pin": "1234"}
            )
        
        # Should succeed with exactly 0.7
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
    
    @pytest.mark.asyncio
    async def test_multiple_promotion_attempts(self, create_test_strategy):
        """Test that promoting an already live strategy fails."""
        strategy_id = await create_test_strategy(
            status="paper",
            days_in_paper=35,
            has_backtest=True,
            backtest_return=15.0,
            wf_consistency_score=0.85
        )
        
        async with AsyncClient(app=app, base_url="http://test") as client:
            # First promotion should succeed
            response1 = await client.post(
                f"/api/v1/algo/strategies/{strategy_id}/live",
                json={"pin": "1234"}
            )
            assert response1.status_code == 200
            
            # Second promotion should fail (already live)
            response2 = await client.post(
                f"/api/v1/algo/strategies/{strategy_id}/live",
                json={"pin": "1234"}
            )
            assert response2.status_code == 400
            data = response2.json()
            detail = data["detail"]
            assert detail["error"] == "Invalid strategy status"
            assert detail["current_status"] == "live"


class TestPromotionResponseFormat:
    """Test response format and structure."""
    
    @pytest.mark.asyncio
    async def test_success_response_structure(self, create_test_strategy):
        """Test that success response has correct structure."""
        strategy_id = await create_test_strategy(
            status="paper",
            days_in_paper=35,
            has_backtest=True,
            backtest_return=15.0,
            wf_consistency_score=0.85
        )
        
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/algo/strategies/{strategy_id}/live",
                json={"pin": "1234"}
            )
        
        assert response.status_code == 200
        data = response.json()
        
        # Check all required fields
        assert "success" in data
        assert "message" in data
        assert "strategy_id" in data
        assert "status" in data
        assert "celery_task_id" in data
        
        # Check types
        assert isinstance(data["success"], bool)
        assert isinstance(data["message"], str)
        assert isinstance(data["strategy_id"], str)
        assert isinstance(data["status"], str)
        
        # Check values
        assert data["success"] is True
        assert data["status"] == "live"
        assert data["strategy_id"] == strategy_id
    
    @pytest.mark.asyncio
    async def test_error_response_structure(self, create_test_strategy):
        """Test that error response has correct structure with actionable details."""
        strategy_id = await create_test_strategy(
            status="paper",
            days_in_paper=25,  # Will fail
            has_backtest=True,
            backtest_return=15.0,
            wf_consistency_score=0.85
        )
        
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/algo/strategies/{strategy_id}/live",
                json={"pin": "1234"}
            )
        
        assert response.status_code == 400
        data = response.json()
        
        # Check error structure
        assert "detail" in data
        detail = data["detail"]
        
        # Check all required error fields
        assert "error" in detail
        assert "message" in detail
        assert "action" in detail
        
        # Check types
        assert isinstance(detail["error"], str)
        assert isinstance(detail["message"], str)
        assert isinstance(detail["action"], str)
        
        # Check actionable guidance
        assert len(detail["action"]) > 0
        assert "days" in detail["action"].lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
