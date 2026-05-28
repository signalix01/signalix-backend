"""
Celery tasks for backtesting.

This module defines async tasks for running backtests.
Tasks are executed by Celery workers in production.

Requirements: 4.1, 4.2, 16.5, 16.6
"""
import json
import uuid
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from services.backtesting.models import BacktestConfig, BacktestResult, BacktestMode
from services.backtesting.data_pipeline import BacktestDataPipeline
from services.backtesting.vectorised_engine import VectorisedEngine
from services.backtesting.event_engine import EventDrivenEngine
from services.backtesting.walk_forward import WalkForwardValidator
from services.backtesting.monte_carlo import MonteCarloSimulator
from services.backtesting.regime_analyzer import RegimeAnalyzer, RegimeType
from services.algo_builder.compiler import StrategyCompiler
from services.algo_builder.sandbox import SandboxRunner
from services.backtesting.db_client import get_db_client
from services.backtesting.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name='services.backtesting.tasks.run_backtest_task')
def run_backtest_task(self, config_json: str, backtest_id: str, user_id: str) -> str:
    """
    Run a complete backtest with all validation steps.
    
    Task flow:
    1. Deserialize config
    2. Update status to 'running'
    3. Fetch data
    4. Compile strategy
    5. Run engine (vectorised or event-driven)
    6. Run walk-forward validation (if enabled)
    7. Run Monte Carlo simulation (if enabled)
    8. Run regime analysis (if enabled)
    9. Store result in database
    10. Update status to 'complete'
    
    Args:
        self: Celery task instance (for progress updates)
        config_json: JSON string of BacktestConfig
        backtest_id: Unique identifier for this backtest
        user_id: User identifier
        
    Returns:
        backtest_id: Unique identifier for this backtest
        
    Raises:
        Exception: If any step fails
    """
    db_client = get_db_client()
    
    try:
        # 1. Deserialize config
        config_dict = json.loads(config_json)
        config = BacktestConfig(**config_dict)
        
        logger.info(f"Starting backtest {backtest_id} for user {user_id}")
        
        # 2. Update status to 'running'
        db_client.update_backtest_status(backtest_id, 'running')
        self.update_state(state='PROGRESS', meta={'progress': 10, 'status': 'Fetching data'})
        
        # 3. Fetch data
        pipeline = BacktestDataPipeline()
        data = pipeline.get_backtest_data(
            instrument=config.instrument,
            start=config.start_date,
            end=config.end_date,
            timeframe='1D',  # Default to daily for now
            asset_class=config.strategy_spec.asset_class
        )
        
        logger.info(f"Fetched {len(data)} bars for {config.instrument}")
        self.update_state(state='PROGRESS', meta={'progress': 20, 'status': 'Compiling strategy'})
        
        # 4. Compile strategy (if not already compiled)
        compiler = StrategyCompiler()
        compiled_code = compiler.compile(config.strategy_spec)
        
        # Validate compiled code in sandbox
        sandbox = SandboxRunner()
        validation_result = sandbox.validate(compiled_code, data[:100])
        if not validation_result.success:
            raise ValueError(f"Strategy compilation failed: {validation_result.error}")
        
        logger.info(f"Strategy compiled and validated successfully")
        self.update_state(state='PROGRESS', meta={'progress': 30, 'status': 'Running backtest'})
        
        # 5. Run engine
        if config.mode == BacktestMode.VECTORISED:
            engine = VectorisedEngine()
        else:
            engine = EventDrivenEngine()
        
        result = engine.run(config.strategy_spec, data, config)
        result.backtest_id = backtest_id
        
        logger.info(
            f"Backtest complete: {result.total_trades} trades, "
            f"{result.total_return_pct:.2f}% return, "
            f"Sharpe: {result.sharpe_ratio:.2f}"
        )
        self.update_state(state='PROGRESS', meta={'progress': 50, 'status': 'Running validations'})
        
        # 6. Run walk-forward validation (if enabled)
        if config.run_walk_forward:
            logger.info("Running walk-forward validation")
            validator = WalkForwardValidator()
            wf_result = validator.validate(engine, config.strategy_spec, data, config)
            
            # Update result with walk-forward metrics
            result.wf_train_return = wf_result.train.total_return_pct
            result.wf_validate_return = wf_result.validate.total_return_pct
            result.wf_test_return = wf_result.test.total_return_pct
            result.wf_consistency_score = wf_result.consistency_score
            
            logger.info(
                f"Walk-forward complete: consistency score {wf_result.consistency_score:.2f}"
            )
        
        self.update_state(state='PROGRESS', meta={'progress': 70, 'status': 'Running Monte Carlo'})
        
        # 7. Run Monte Carlo simulation (if enabled)
        if config.run_monte_carlo:
            logger.info("Running Monte Carlo simulation")
            simulator = MonteCarloSimulator()
            trade_returns = simulator.extract_trade_returns(result.trades)
            
            if trade_returns:
                mc_result = simulator.simulate(
                    trade_returns=trade_returns,
                    n_simulations=config.monte_carlo_simulations,
                    initial_capital=config.initial_capital
                )
                
                # Update result with Monte Carlo metrics
                result.mc_median_return = mc_result.median_return
                result.mc_5th_percentile_return = mc_result.p5_return
                result.mc_95th_percentile_return = mc_result.p95_return
                result.mc_ruin_probability = mc_result.ruin_probability
                
                logger.info(
                    f"Monte Carlo complete: ruin probability {mc_result.ruin_probability:.4f}"
                )
        
        self.update_state(state='PROGRESS', meta={'progress': 85, 'status': 'Running regime analysis'})
        
        # 8. Run regime analysis (if enabled)
        if config.run_regime_analysis:
            logger.info("Running regime analysis")
            analyzer = RegimeAnalyzer()
            
            # Classify regimes (using VIX proxy if VIX data not available)
            regimes = analyzer.classify_regimes(data, vix_data=None)
            
            # Stratify results by regime
            regime_result = analyzer.stratify_results(
                trades=result.trades,
                regimes=regimes,
                initial_capital=config.initial_capital
            )
            
            # Update result with regime metrics
            if RegimeType.TRENDING_BULL in regime_result.regime_returns:
                result.trending_bull_return = regime_result.regime_returns[RegimeType.TRENDING_BULL]
            if RegimeType.TRENDING_BEAR in regime_result.regime_returns:
                result.trending_bear_return = regime_result.regime_returns[RegimeType.TRENDING_BEAR]
            if RegimeType.RANGING in regime_result.regime_returns:
                result.ranging_return = regime_result.regime_returns[RegimeType.RANGING]
            if RegimeType.VOLATILE in regime_result.regime_returns:
                result.volatile_return = regime_result.regime_returns[RegimeType.VOLATILE]
            
            logger.info("Regime analysis complete")
        
        self.update_state(state='PROGRESS', meta={'progress': 95, 'status': 'Storing results'})
        
        # 9. Store result in database
        db_client.store_backtest_result(backtest_id, result)
        
        # 10. Update status to 'complete'
        db_client.update_backtest_status(backtest_id, 'complete')
        
        logger.info(f"Backtest {backtest_id} completed successfully")
        self.update_state(state='SUCCESS', meta={'progress': 100, 'status': 'Complete'})
        
        return backtest_id
        
    except Exception as e:
        # Log error and update database
        error_msg = str(e)
        logger.error(f"Backtest {backtest_id} failed: {error_msg}", exc_info=True)
        
        try:
            db_client.update_backtest_status(backtest_id, 'failed', error_msg)
        except Exception as db_error:
            logger.error(f"Failed to update error status: {db_error}")
        
        # Update Celery task state
        self.update_state(
            state='FAILURE',
            meta={'progress': 0, 'status': 'Failed', 'error': error_msg}
        )
        
        raise


# Helper function for synchronous testing
def run_backtest_sync(config: BacktestConfig, user_id: str = "test-user") -> str:
    """
    Synchronous wrapper for testing without Celery.
    
    Args:
        config: Backtest configuration
        user_id: User identifier
        
    Returns:
        backtest_id
    """
    backtest_id = str(uuid.uuid4())
    db_client = get_db_client()
    
    # Create pending record
    db_client.create_pending_backtest(backtest_id, config, user_id)
    
    # Run task synchronously
    try:
        # Create a mock task instance for progress updates
        class MockTask:
            def update_state(self, state, meta):
                logger.info(f"Progress: {meta.get('progress')}% - {meta.get('status')}")
        
        mock_task = MockTask()
        result_id = run_backtest_task(mock_task, config.json(), backtest_id, user_id)
        return result_id
    except Exception as e:
        logger.error(f"Synchronous backtest failed: {e}")
        raise
