"""
Database client for backtest operations.

This module provides database operations for storing and retrieving backtest results.

Requirements: 4.1, 4.2, 16.5, 16.6
"""
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy import create_engine, desc, and_
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool
from shared.config.settings import settings
from shared.database.models import BacktestResult as BacktestResultModel, Base
from services.backtesting.models import BacktestResult, BacktestConfig
import logging

logger = logging.getLogger(__name__)


class BacktestDBClient:
    """
    Database client for backtest operations.
    
    Handles storing and retrieving backtest results from PostgreSQL.
    """
    
    def __init__(self):
        """Initialize database client"""
        # Create engine
        if "sqlite" in settings.DATABASE_URL:
            self.engine = create_engine(
                settings.DATABASE_URL,
                poolclass=NullPool,
                connect_args={"check_same_thread": False}
            )
        else:
            self.engine = create_engine(
                settings.DATABASE_URL,
                pool_size=10,
                max_overflow=20,
                pool_timeout=30
            )
        
        # Create session factory
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine
        )
    
    def get_session(self) -> Session:
        """Get a new database session"""
        return self.SessionLocal()
    
    def create_pending_backtest(
        self,
        backtest_id: str,
        config: BacktestConfig,
        user_id: str
    ) -> BacktestResultModel:
        """
        Create a pending backtest record.
        
        Args:
            backtest_id: Unique backtest identifier
            config: Backtest configuration
            user_id: User identifier
            
        Returns:
            BacktestResultModel database record
        """
        session = self.get_session()
        try:
            record = BacktestResultModel(
                id=uuid.UUID(backtest_id),
                strategy_id=uuid.UUID(config.strategy_spec.strategy_id),
                user_id=uuid.UUID(user_id),
                instrument=config.instrument,
                asset_class=config.strategy_spec.asset_class,
                start_date=datetime.fromisoformat(config.start_date),
                end_date=datetime.fromisoformat(config.end_date),
                mode=config.mode.value,
                status='pending',
                created_at=datetime.utcnow()
            )
            
            session.add(record)
            session.commit()
            session.refresh(record)
            
            logger.info(f"Created pending backtest record: {backtest_id}")
            return record
            
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to create pending backtest: {e}")
            raise
        finally:
            session.close()
    
    def update_backtest_status(
        self,
        backtest_id: str,
        status: str,
        error_message: Optional[str] = None
    ):
        """
        Update backtest status.
        
        Args:
            backtest_id: Backtest identifier
            status: New status (pending/running/complete/failed)
            error_message: Optional error message if failed
        """
        session = self.get_session()
        try:
            record = session.query(BacktestResultModel).filter(
                BacktestResultModel.id == uuid.UUID(backtest_id)
            ).first()
            
            if record:
                record.status = status
                if error_message:
                    record.error_message = error_message
                if status == 'complete':
                    record.completed_at = datetime.utcnow()
                
                session.commit()
                logger.info(f"Updated backtest {backtest_id} status to: {status}")
            else:
                logger.warning(f"Backtest {backtest_id} not found for status update")
                
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to update backtest status: {e}")
            raise
        finally:
            session.close()
    
    def store_backtest_result(
        self,
        backtest_id: str,
        result: BacktestResult
    ):
        """
        Store complete backtest result.
        
        Args:
            backtest_id: Backtest identifier
            result: Complete backtest result
        """
        session = self.get_session()
        try:
            record = session.query(BacktestResultModel).filter(
                BacktestResultModel.id == uuid.UUID(backtest_id)
            ).first()
            
            if not record:
                logger.error(f"Backtest {backtest_id} not found")
                raise ValueError(f"Backtest {backtest_id} not found")
            
            # Update all fields
            record.total_return_pct = result.total_return_pct
            record.cagr_pct = result.cagr_pct
            record.sharpe_ratio = result.sharpe_ratio
            record.sortino_ratio = result.sortino_ratio
            record.calmar_ratio = result.calmar_ratio
            record.max_drawdown_pct = result.max_drawdown_pct
            record.avg_drawdown_pct = result.avg_drawdown_pct
            record.max_drawdown_duration_days = result.max_drawdown_duration_days
            
            record.total_trades = result.total_trades
            record.win_rate_pct = result.win_rate_pct
            record.avg_win_pct = result.avg_win_pct
            record.avg_loss_pct = result.avg_loss_pct
            record.profit_factor = result.profit_factor
            record.expectancy_per_trade = result.expectancy_per_trade
            record.avg_hold_days = result.avg_hold_days
            record.max_consecutive_losses = result.max_consecutive_losses
            
            record.kelly_fraction = result.kelly_fraction
            record.half_kelly = result.half_kelly
            
            record.wf_train_return = result.wf_train_return
            record.wf_validate_return = result.wf_validate_return
            record.wf_test_return = result.wf_test_return
            record.wf_consistency_score = result.wf_consistency_score
            
            record.trending_bull_return = result.trending_bull_return
            record.trending_bear_return = result.trending_bear_return
            record.ranging_return = result.ranging_return
            record.volatile_return = result.volatile_return
            
            record.mc_median_return = result.mc_median_return
            record.mc_5th_percentile_return = result.mc_5th_percentile_return
            record.mc_95th_percentile_return = result.mc_95th_percentile_return
            record.mc_ruin_probability = result.mc_ruin_probability
            
            # Store full result data as JSONB
            record.result_data = result.dict()
            
            record.status = 'complete'
            record.completed_at = datetime.utcnow()
            
            session.commit()
            logger.info(f"Stored complete backtest result: {backtest_id}")
            
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to store backtest result: {e}")
            raise
        finally:
            session.close()
    
    def get_backtest_result(self, backtest_id: str) -> Optional[BacktestResult]:
        """
        Retrieve backtest result.
        
        Args:
            backtest_id: Backtest identifier
            
        Returns:
            BacktestResult if found and complete, None otherwise
        """
        session = self.get_session()
        try:
            record = session.query(BacktestResultModel).filter(
                BacktestResultModel.id == uuid.UUID(backtest_id)
            ).first()
            
            if not record or record.status != 'complete':
                return None
            
            # Reconstruct BacktestResult from database record
            if record.result_data:
                return BacktestResult(**record.result_data)
            else:
                # Fallback: construct from individual fields
                return BacktestResult(
                    backtest_id=str(record.id),
                    strategy_id=str(record.strategy_id),
                    instrument=record.instrument,
                    period=f"{record.start_date.date()} to {record.end_date.date()}",
                    mode=record.mode,
                    total_return_pct=record.total_return_pct or 0.0,
                    cagr_pct=record.cagr_pct or 0.0,
                    sharpe_ratio=record.sharpe_ratio or 0.0,
                    sortino_ratio=record.sortino_ratio or 0.0,
                    calmar_ratio=record.calmar_ratio or 0.0,
                    max_drawdown_pct=record.max_drawdown_pct or 0.0,
                    avg_drawdown_pct=record.avg_drawdown_pct or 0.0,
                    max_drawdown_duration_days=record.max_drawdown_duration_days or 0,
                    total_trades=record.total_trades or 0,
                    win_rate_pct=record.win_rate_pct or 0.0,
                    avg_win_pct=record.avg_win_pct or 0.0,
                    avg_loss_pct=record.avg_loss_pct or 0.0,
                    profit_factor=record.profit_factor or 0.0,
                    expectancy_per_trade=record.expectancy_per_trade or 0.0,
                    avg_hold_days=record.avg_hold_days or 0.0,
                    max_consecutive_losses=record.max_consecutive_losses or 0,
                    kelly_fraction=record.kelly_fraction or 0.0,
                    half_kelly=record.half_kelly or 0.0,
                    wf_consistency_score=record.wf_consistency_score or 0.0,
                    trades=[],
                    equity_curve=[],
                    drawdown_curve=[]
                )
                
        except Exception as e:
            logger.error(f"Failed to retrieve backtest result: {e}")
            return None
        finally:
            session.close()
    
    def get_backtest_status(self, backtest_id: str) -> Optional[Dict[str, Any]]:
        """
        Get backtest status.
        
        Args:
            backtest_id: Backtest identifier
            
        Returns:
            Status dict or None if not found
        """
        session = self.get_session()
        try:
            record = session.query(BacktestResultModel).filter(
                BacktestResultModel.id == uuid.UUID(backtest_id)
            ).first()
            
            if not record:
                return None
            
            return {
                'backtest_id': str(record.id),
                'status': record.status,
                'created_at': record.created_at.isoformat(),
                'completed_at': record.completed_at.isoformat() if record.completed_at else None,
                'error_message': record.error_message
            }
            
        except Exception as e:
            logger.error(f"Failed to get backtest status: {e}")
            return None
        finally:
            session.close()
    
    def get_user_backtest_history(
        self,
        user_id: str,
        page: int = 1,
        limit: int = 20,
        status_filter: Optional[str] = None
    ) -> tuple[List[BacktestResultModel], int]:
        """
        Get user's backtest history.
        
        Args:
            user_id: User identifier
            page: Page number (1-indexed)
            limit: Items per page
            status_filter: Optional status filter
            
        Returns:
            Tuple of (results list, total count)
        """
        session = self.get_session()
        try:
            query = session.query(BacktestResultModel).filter(
                BacktestResultModel.user_id == uuid.UUID(user_id)
            )
            
            if status_filter:
                query = query.filter(BacktestResultModel.status == status_filter)
            
            # Get total count
            total = query.count()
            
            # Paginate
            results = query.order_by(
                desc(BacktestResultModel.created_at)
            ).offset((page - 1) * limit).limit(limit).all()
            
            return results, total
            
        except Exception as e:
            logger.error(f"Failed to get backtest history: {e}")
            return [], 0
        finally:
            session.close()


# Global database client instance
_db_client: Optional[BacktestDBClient] = None


def get_db_client() -> BacktestDBClient:
    """
    Get or create the global database client instance.
    
    Returns:
        BacktestDBClient instance
    """
    global _db_client
    
    if _db_client is None:
        _db_client = BacktestDBClient()
    
    return _db_client
