"""
Backtest Service - FastAPI Application

Main entry point for the Backtest Service.
Provides REST API for backtesting strategies using vectorized and event-driven engines.

Requirements: Phase 1.4 - Wire backtest-service
"""

from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import os
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
import asyncio
from pydantic import BaseModel

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import backtesting components
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtesting.vectorised_engine import VectorizedEngine
from backtesting.event_engine import EventDrivenEngine
from backtesting.walk_forward import WalkForwardAnalyzer
from backtesting.monte_carlo import MonteCarloSimulator
from backtesting.regime_analyzer import RegimeAnalyzer
from backtesting.models import BacktestConfig, BacktestResult

# Global service instances
vectorized_engine: Optional[VectorizedEngine] = None
event_engine: Optional[EventDrivenEngine] = None
walk_forward_analyzer: Optional[WalkForwardAnalyzer] = None
monte_carlo_simulator: Optional[MonteCarloSimulator] = None
regime_analyzer: Optional[RegimeAnalyzer] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global vectorized_engine, event_engine, walk_forward_analyzer, monte_carlo_simulator, regime_analyzer
    
    logger.info("Starting Backtest Service...")
    
    # Initialize backtesting engines
    vectorized_engine = VectorizedEngine()
    event_engine = EventDrivenEngine()
    walk_forward_analyzer = WalkForwardAnalyzer()
    monte_carlo_simulator = MonteCarloSimulator()
    regime_analyzer = RegimeAnalyzer()
    
    logger.info("Backtest Service started successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Backtest Service...")
    logger.info("Backtest Service shut down")


# Create FastAPI app
app = FastAPI(
    title="Backtest Service",
    description="SignalixAI Backtest Service for strategy testing with vectorized and event-driven engines",
    version="1.0.0",
    lifespan=lifespan
)

# CORS configuration
ALLOWED_ORIGINS = [
    origin.strip() for origin in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",") if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Pydantic models for API
class BacktestRequest(BaseModel):
    symbol: str
    start_date: str
    end_date: str
    strategy_type: str
    parameters: Dict[str, Any]
    initial_capital: float = 100000
    position_size: float = 0.1
    commission: float = 0.001
    engine: str = "vectorized"  # vectorized or event_driven


class WalkForwardRequest(BaseModel):
    symbol: str
    start_date: str
    end_date: str
    strategy_type: str
    parameters: Dict[str, Any]
    train_size: int = 252
    test_size: int = 63
    n_splits: int = 5


class MonteCarloRequest(BaseModel):
    backtest_result: Dict[str, Any]
    n_simulations: int = 1000
    confidence_level: float = 0.95


class RegimeRequest(BaseModel):
    symbol: str
    lookback_period: int = 252
    n_regimes: int = 3


# Health check endpoint
@app.get("/health")
async def health_check():
    """Service health check endpoint."""
    return {
        "status": "healthy",
        "service": "backtest-service",
        "timestamp": datetime.utcnow().isoformat(),
        "components": {
            "vectorized_engine": vectorized_engine is not None,
            "event_engine": event_engine is not None,
            "walk_forward_analyzer": walk_forward_analyzer is not None,
            "monte_carlo_simulator": monte_carlo_simulator is not None,
            "regime_analyzer": regime_analyzer is not None
        }
    }


@app.post("/api/v1/backtest/run")
async def run_backtest(request: BacktestRequest, background_tasks: BackgroundTasks):
    """
    Run a backtest with the specified configuration.
    
    Supports both vectorized and event-driven engines.
    """
    try:
        logger.info(f"Running backtest for {request.symbol} using {request.engine} engine")
        
        config = {
            "symbol": request.symbol,
            "start_date": request.start_date,
            "end_date": request.end_date,
            "strategy_type": request.strategy_type,
            "parameters": request.parameters,
            "initial_capital": request.initial_capital,
            "position_size": request.position_size,
            "commission": request.commission
        }
        
        if request.engine == "event_driven":
            result = await event_engine.run_backtest(config)
        else:
            result = await vectorized_engine.run_backtest(config)
        
        return {
            "success": True,
            "backtest_id": result.get("backtest_id"),
            "symbol": request.symbol,
            "engine": request.engine,
            "summary": {
                "total_return": result.get("total_return", 0),
                "sharpe_ratio": result.get("sharpe_ratio", 0),
                "max_drawdown": result.get("max_drawdown", 0),
                "win_rate": result.get("win_rate", 0),
                "total_trades": result.get("total_trades", 0)
            },
            "result": result
        }
        
    except Exception as e:
        logger.error(f"Backtest failed: {e}")
        raise HTTPException(status_code=500, detail=f"Backtest failed: {str(e)}")


@app.post("/api/v1/backtest/walk-forward")
async def run_walk_forward(request: WalkForwardRequest):
    """
    Run walk-forward optimization.
    
    Performs rolling window backtesting to validate strategy robustness.
    """
    try:
        logger.info(f"Running walk-forward analysis for {request.symbol}")
        
        result = await walk_forward_analyzer.run_walk_forward(
            symbol=request.symbol,
            start_date=request.start_date,
            end_date=request.end_date,
            strategy_type=request.strategy_type,
            parameters=request.parameters,
            train_size=request.train_size,
            test_size=request.test_size,
            n_splits=request.n_splits
        )
        
        return {
            "success": True,
            "symbol": request.symbol,
            "strategy_type": request.strategy_type,
            "n_splits": request.n_splits,
            "summary": {
                "avg_train_return": result.get("avg_train_return", 0),
                "avg_test_return": result.get("avg_test_return", 0),
                "robustness_score": result.get("robustness_score", 0),
                "overfitting_risk": result.get("overfitting_risk", "unknown")
            },
            "splits": result.get("splits", []),
            "result": result
        }
        
    except Exception as e:
        logger.error(f"Walk-forward analysis failed: {e}")
        raise HTTPException(status_code=500, detail=f"Walk-forward analysis failed: {str(e)}")


@app.post("/api/v1/backtest/monte-carlo")
async def run_monte_carlo(request: MonteCarloRequest):
    """
    Run Monte Carlo simulation on backtest results.
    
    Simulates multiple equity curves to assess strategy robustness.
    """
    try:
        logger.info(f"Running Monte Carlo simulation with {request.n_simulations} simulations")
        
        result = await monte_carlo_simulator.run_simulation(
            backtest_result=request.backtest_result,
            n_simulations=request.n_simulations,
            confidence_level=request.confidence_level
        )
        
        return {
            "success": True,
            "n_simulations": request.n_simulations,
            "confidence_level": request.confidence_level,
            "summary": {
                "probability_of_profit": result.get("probability_of_profit", 0),
                "expected_return": result.get("expected_return", 0),
                "worst_case_drawdown": result.get("worst_case_drawdown", 0),
                "var_95": result.get("var_95", 0)
            },
            "result": result
        }
        
    except Exception as e:
        logger.error(f"Monte Carlo simulation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Monte Carlo simulation failed: {str(e)}")


@app.post("/api/v1/backtest/regime-analysis")
async def run_regime_analysis(request: RegimeRequest):
    """
    Analyze market regimes for a symbol.
    
    Identifies different market states (bull, bear, sideways) using Hidden Markov Models.
    """
    try:
        logger.info(f"Running regime analysis for {request.symbol}")
        
        result = await regime_analyzer.analyze(
            symbol=request.symbol,
            lookback_period=request.lookback_period,
            n_regimes=request.n_regimes
        )
        
        return {
            "success": True,
            "symbol": request.symbol,
            "n_regimes": request.n_regimes,
            "current_regime": result.get("current_regime"),
            "regime_probabilities": result.get("regime_probabilities", {}),
            "regime_history": result.get("regime_history", []),
            "regime_stats": result.get("regime_stats", {}),
            "result": result
        }
        
    except Exception as e:
        logger.error(f"Regime analysis failed: {e}")
        raise HTTPException(status_code=500, detail=f"Regime analysis failed: {str(e)}")


@app.get("/api/v1/backtest/engines")
async def list_engines():
    """List available backtesting engines and their capabilities."""
    return {
        "engines": [
            {
                "id": "vectorized",
                "name": "Vectorized Engine",
                "description": "Fast vectorized backtesting using pandas/numpy",
                "best_for": ["Rapid prototyping", "Parameter optimization", "Large datasets"],
                "features": ["Event-based simulation", "Multiple strategies", "Performance metrics"]
            },
            {
                "id": "event_driven",
                "name": "Event-Driven Engine",
                "description": "Realistic event-driven simulation matching live trading",
                "best_for": ["Production validation", "Complex strategies", "Realistic simulation"],
                "features": ["Tick-level simulation", "Market impact modeling", "Slippage simulation"]
            }
        ],
        "analysis_tools": [
            {
                "id": "walk_forward",
                "name": "Walk-Forward Optimization",
                "description": "Rolling window backtesting to validate strategy robustness"
            },
            {
                "id": "monte_carlo",
                "name": "Monte Carlo Simulation",
                "description": "Simulate multiple equity curves to assess strategy robustness"
            },
            {
                "id": "regime_analysis",
                "name": "Market Regime Analysis",
                "description": "Identify market states using Hidden Markov Models"
            }
        ]
    }


@app.get("/api/v1/backtest/strategies")
async def list_strategies():
    """List available strategy types for backtesting."""
    return {
        "strategies": [
            {
                "id": "sma_crossover",
                "name": "SMA Crossover",
                "description": "Simple moving average crossover strategy",
                "parameters": {
                    "fast_period": {"type": "int", "default": 10, "min": 5, "max": 50},
                    "slow_period": {"type": "int", "default": 30, "min": 10, "max": 200}
                }
            },
            {
                "id": "rsi",
                "name": "RSI Strategy",
                "description": "Relative Strength Index based strategy",
                "parameters": {
                    "period": {"type": "int", "default": 14, "min": 5, "max": 50},
                    "overbought": {"type": "int", "default": 70, "min": 50, "max": 90},
                    "oversold": {"type": "int", "default": 30, "min": 10, "max": 50}
                }
            },
            {
                "id": "bollinger_bands",
                "name": "Bollinger Bands",
                "description": "Mean reversion using Bollinger Bands",
                "parameters": {
                    "period": {"type": "int", "default": 20, "min": 10, "max": 50},
                    "std_dev": {"type": "float", "default": 2.0, "min": 1.0, "max": 3.0}
                }
            },
            {
                "id": "momentum",
                "name": "Momentum Strategy",
                "description": "Price momentum based strategy",
                "parameters": {
                    "lookback": {"type": "int", "default": 20, "min": 5, "max": 100},
                    "threshold": {"type": "float", "default": 0.05, "min": 0.01, "max": 0.2}
                }
            }
        ]
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("BACKTEST_SERVICE_PORT", "8020"))
    uvicorn.run(app, host="0.0.0.0", port=port)
