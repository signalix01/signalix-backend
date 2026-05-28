"""
Walk-Forward Validation for Backtesting.

Implements Edward Thorp's out-of-sample validation principle:
'A strategy not tested on unseen data is a curve-fit fantasy.'

This module splits data into train/validate/test periods and runs the strategy
on each period independently to detect overfitting.

Requirements: 6.1-6.6
"""
import pandas as pd
import numpy as np
from typing import Union, Optional
from pydantic import BaseModel, Field
import logging

from services.backtesting.models import BacktestConfig, BacktestResult
from services.algo_builder.models import StrategySpec

logger = logging.getLogger(__name__)


class WalkForwardResult(BaseModel):
    """Results from walk-forward validation"""
    train: BacktestResult = Field(..., description="Training period results")
    validation: BacktestResult = Field(..., description="Validation period results")
    test: BacktestResult = Field(..., description="Test period results (out-of-sample)")
    consistency_score: float = Field(..., description="0.0-1.0: consistency across periods")
    is_robust: bool = Field(..., description="True if strategy passes robustness checks")
    warnings: list[str] = Field(default_factory=list, description="Warning messages")
    overfitting_detected: bool = Field(default=False, description="True if overfitting suspected")
    
    class Config:
        arbitrary_types_allowed = True


class WalkForwardValidator:
    """
    Implements walk-forward validation to detect overfitting.
    
    The validator:
    - Splits data into train (70%), validate (15%), test (15%) periods
    - Runs the strategy on each period independently
    - Computes consistency score across all three periods
    - Flags strategies with inconsistent performance or suspected overfitting
    """
    
    def __init__(self):
        """Initialize the walk-forward validator"""
        pass
    
    def validate(
        self,
        engine: Union['VectorisedEngine', 'EventDrivenEngine'],
        spec: StrategySpec,
        data: pd.DataFrame,
        config: BacktestConfig
    ) -> WalkForwardResult:
        """
        Run walk-forward validation on the strategy.
        
        Args:
            engine: Backtesting engine (vectorised or event-driven)
            spec: Strategy specification
            data: Full DataFrame with OHLCV data and indicators
            config: Backtest configuration
            
        Returns:
            WalkForwardResult with results from all three periods
        """
        logger.info(f"Starting walk-forward validation for {spec.name}")
        
        # Split data into three periods
        train_data, validate_data, test_data = self._split_data(
            data, config.wf_train_pct, config.wf_validate_pct, config.wf_test_pct
        )
        
        logger.info(f"Data split: train={len(train_data)}, "
                   f"validate={len(validate_data)}, test={len(test_data)}")
        
        # Run backtest on each period
        train_result = self._run_period(
            engine, spec, train_data, config, "train"
        )
        
        validation_result = self._run_period(
            engine, spec, validate_data, config, "validation"
        )
        
        test_result = self._run_period(
            engine, spec, test_data, config, "test"
        )
        
        # Compute consistency score
        consistency_score = self._compute_consistency_score(
            train_result, validation_result, test_result
        )
        
        # Check for warnings and overfitting
        warnings = []
        overfitting_detected = False
        
        # Warning: Low consistency score
        if consistency_score < 0.7:
            warnings.append(
                "This strategy shows inconsistent performance across time periods. "
                "Consider simplifying the entry rules to avoid overfitting."
            )
        
        # Warning: Suspected overfitting
        if (train_result.sharpe_ratio > 2.0 and test_result.sharpe_ratio < 0.5):
            warnings.append(
                "CRITICAL: Highly suspected overfitting detected. "
                "Train period Sharpe > 2.0 but test period Sharpe < 0.5. "
                "This strategy is likely curve-fit to historical data."
            )
            overfitting_detected = True
        
        # Determine if strategy is robust
        is_robust = (
            consistency_score >= 0.7 and
            test_result.sharpe_ratio > 1.0 and
            not overfitting_detected
        )
        
        logger.info(f"Walk-forward validation complete: "
                   f"consistency_score={consistency_score:.3f}, "
                   f"is_robust={is_robust}")
        
        return WalkForwardResult(
            train=train_result,
            validation=validation_result,
            test=test_result,
            consistency_score=consistency_score,
            is_robust=is_robust,
            warnings=warnings,
            overfitting_detected=overfitting_detected
        )
    
    def _split_data(
        self,
        data: pd.DataFrame,
        train_pct: float,
        validate_pct: float,
        test_pct: float
    ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """
        Split data into train, validate, and test periods by index.
        
        Args:
            data: Full DataFrame
            train_pct: Percentage for training (e.g., 0.70)
            validate_pct: Percentage for validation (e.g., 0.15)
            test_pct: Percentage for testing (e.g., 0.15)
            
        Returns:
            Tuple of (train_data, validate_data, test_data)
        """
        n = len(data)
        
        # Calculate split indices
        train_end = int(n * train_pct)
        validate_end = int(n * (train_pct + validate_pct))
        
        # Split data
        train_data = data.iloc[:train_end].copy()
        validate_data = data.iloc[train_end:validate_end].copy()
        test_data = data.iloc[validate_end:].copy()
        
        return train_data, validate_data, test_data
    
    def _run_period(
        self,
        engine: Union['VectorisedEngine', 'EventDrivenEngine'],
        spec: StrategySpec,
        data: pd.DataFrame,
        config: BacktestConfig,
        period_name: str
    ) -> BacktestResult:
        """
        Run backtest on a single period.
        
        Args:
            engine: Backtesting engine
            spec: Strategy specification
            data: Period data
            config: Backtest configuration
            period_name: Name of the period (for logging)
            
        Returns:
            BacktestResult for this period
        """
        logger.info(f"Running {period_name} period backtest...")
        
        # Update config dates for this period
        period_config = config.copy()
        period_config.start_date = data.index[0].strftime('%Y-%m-%d')
        period_config.end_date = data.index[-1].strftime('%Y-%m-%d')
        
        # Run backtest
        result = engine.run(spec=spec, data=data, config=period_config)
        
        # Update period identifier in result
        result.period = f"{period_name}: {period_config.start_date} to {period_config.end_date}"
        
        logger.info(f"{period_name.capitalize()} period complete: "
                   f"return={result.total_return_pct:.2f}%, "
                   f"sharpe={result.sharpe_ratio:.2f}")
        
        return result
    
    def _compute_consistency_score(
        self,
        train_result: BacktestResult,
        validation_result: BacktestResult,
        test_result: BacktestResult
    ) -> float:
        """
        Compute consistency score across all three periods.
        
        Formula:
        - If all periods have positive returns:
          consistency_score = max(0, 1 - abs((train_sharpe - test_sharpe) / train_sharpe))
        - Otherwise: 0.0
        
        Args:
            train_result: Training period results
            validation_result: Validation period results
            test_result: Test period results
            
        Returns:
            Consistency score (0.0-1.0)
        """
        # Check if all periods are positive
        all_positive = (
            train_result.total_return_pct > 0 and
            validation_result.total_return_pct > 0 and
            test_result.total_return_pct > 0
        )
        
        if not all_positive:
            logger.warning("Not all periods have positive returns - consistency score = 0.0")
            return 0.0
        
        # Calculate degradation from train to test
        if train_result.sharpe_ratio == 0:
            # Avoid division by zero
            logger.warning("Train Sharpe ratio is 0 - consistency score = 0.0")
            return 0.0
        
        degradation = abs(
            (train_result.sharpe_ratio - test_result.sharpe_ratio) / train_result.sharpe_ratio
        )
        
        # Consistency score: 1.0 means no degradation, 0.0 means complete degradation
        consistency_score = max(0.0, 1.0 - degradation)
        
        logger.info(f"Consistency calculation: "
                   f"train_sharpe={train_result.sharpe_ratio:.3f}, "
                   f"test_sharpe={test_result.sharpe_ratio:.3f}, "
                   f"degradation={degradation:.3f}, "
                   f"consistency={consistency_score:.3f}")
        
        return consistency_score
