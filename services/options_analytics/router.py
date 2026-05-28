"""
Options Analytics Service Router

FastAPI router for options chain data, Greeks, Max Pain, GEX, OI tracking,
and strategy builder.

Requirements: 4.1, 5.1, 6.1, 7.1, 19.1, 31.1
"""

import os
import uuid
from datetime import date, datetime, timedelta
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, Depends, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select, and_, desc, func
import redis.asyncio as redis

from services.options_analytics.models.options_models import (
    OptionsChain, OptionStrike, Greeks, OptionsStrategy, StrategyLeg,
    MaxPainResult, GEXResult, OIChange, HistoricalOptionsData,
    OptionType, PositionType, StrategyType, OIPattern, Base
)
from services.options_analytics.calculators.greeks_calculator import GreeksCalculator, BlackScholesGreeks
from services.options_analytics.calculators.max_pain_calculator import MaxPainCalculator
from services.options_analytics.calculators.gex_calculator import GEXCalculator
from services.options_analytics.calculators.oi_tracker import OITracker, OIPattern as TrackerPattern
from services.options_analytics.calculators.iv_smile_calculator import IVSmileCalculator
from services.options_analytics.calculators.straddle_chart_calculator import StraddleChartCalculator
from services.options_analytics.calculators.synthetic_future_calculator import SyntheticFutureCalculator
from services.options_analytics.calculators.multi_strike_oi_calculator import MultiStrikeOICalculator
from services.options_analytics.strategies.strategy_builder import StrategyBuilder
from services.options_analytics.cache_manager import CacheManager

logger = __import__("logging").getLogger(__name__)

router = APIRouter(prefix="/api/v1/options", tags=["options"])

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/signalixai")
engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Redis setup
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
redis_client = None

try:
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    logger.info("Redis client initialized for Options Analytics")
except Exception as e:
    logger.warning(f"Redis not available for Options Analytics: {e}")

# Initialize components
cache_manager = CacheManager(redis_client)
greeks_calculator = GreeksCalculator()
max_pain_calculator = MaxPainCalculator()
gex_calculator = GEXCalculator()
oi_tracker = OITracker()
iv_smile_calculator = IVSmileCalculator()
straddle_chart_calculator = StraddleChartCalculator()
synthetic_future_calculator = SyntheticFutureCalculator()
multi_strike_oi_calculator = MultiStrikeOICalculator()
strategy_builder = StrategyBuilder()

# ============================================================================
# Dependencies
# ============================================================================

async def get_db() -> AsyncSession:
    """Get database session"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

async def get_current_user_id() -> str:
    """Get current user ID (placeholder for auth)"""
    return "00000000-0000-0000-0000-000000000001"

# ============================================================================
# Request/Response Models
# ============================================================================

class OptionsChainRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=50)
    expiry_date: date

class GreeksRequest(BaseModel):
    symbol: str
    strike: float = Field(..., gt=0)
    option_type: str = Field(..., pattern="^(CALL|PUT)$")
    expiry_date: date
    spot_price: float = Field(..., gt=0)
    market_price: Optional[float] = None

class MaxPainResponse(BaseModel):
    symbol: str
    expiry_date: str
    max_pain_price: float
    current_price: float
    deviation_percent: float
    loss_by_strike: Dict[str, Any]

class GEXResponse(BaseModel):
    symbol: str
    expiry_date: str
    spot_price: float
    zero_gamma_level: float
    significant_levels: List[float]
    total_call_gex: float
    total_put_gex: float
    net_gex: float
    gex_by_strike: Dict[str, Any]

class StrategyLegInput(BaseModel):
    option_type: str
    position_type: str
    strike: float
    quantity: int = Field(default=1, ge=1)
    entry_price: float

class StrategyRequest(BaseModel):
    strategy_type: str
    symbol: str
    expiry_date: date
    spot_price: float
    legs: List[StrategyLegInput]

class StrategyResponse(BaseModel):
    strategy_type: str
    symbol: str
    expiry: str
    metrics: Dict[str, Any]
    payoff_data: List[Dict[str, float]]
    legs: List[Dict[str, Any]]

# ============================================================================
# API Endpoints
# ============================================================================

@router.get(
    "/chain/{symbol}",
    summary="Get options chain",
    description="Fetch options chain data for a symbol with optional filtering"
)
async def get_options_chain(
    symbol: str,
    expiry: Optional[str] = Query(None, description="Filter by expiry date (YYYY-MM-DD)"),
    min_strike: Optional[float] = Query(None, description="Minimum strike price"),
    max_strike: Optional[float] = Query(None, description="Maximum strike price")
):
    """
    Get options chain data for a symbol
    
    Requirements: 19.1, 19.2, 19.6, 19.7
    """
    try:
        from services.market_data_service.instrument_master import instrument_master
        import json
        
        # Ensure instrument master is loaded
        if not instrument_master.instruments:
            await instrument_master.download_master()
            
        opts = instrument_master.get_options_tokens(symbol.upper(), expiry)
        if not opts:
            # Try parsing expiry format (YYYY-MM-DD to DDMMMYYYY)
            if expiry:
                try:
                    # Convert 2024-05-30 to 30MAY2024
                    parsed_date = datetime.strptime(expiry, "%Y-%m-%d")
                    expiry_str = parsed_date.strftime("%d%b%Y").upper()
                    opts = instrument_master.get_options_tokens(symbol.upper(), expiry_str)
                except Exception:
                    pass
        
        if not opts:
            return {"chain": [], "spot_price": 0}
            
        # Group by strike
        strikes_map = {}
        for opt in opts:
            strike = float(opt.get("strike", 0)) / 100.0
            if strike <= 0:
                continue
                
            if min_strike and strike < min_strike: continue
            if max_strike and strike > max_strike: continue
            
            if strike not in strikes_map:
                strikes_map[strike] = {
                    "strike": strike,
                    "ce_ltp": 0, "ce_bid": 0, "ce_ask": 0, "ce_oi": 0, "ce_volume": 0, "ce_iv": 0,
                    "ce_delta": 0, "ce_gamma": 0, "ce_theta": 0, "ce_vega": 0,
                    "pe_ltp": 0, "pe_bid": 0, "pe_ask": 0, "pe_oi": 0, "pe_volume": 0, "pe_iv": 0,
                    "pe_delta": 0, "pe_gamma": 0, "pe_theta": 0, "pe_vega": 0,
                }
            
            symbol_name = opt.get("symbol", "")
            token = opt.get("token")
            is_ce = "CE" in symbol_name
            prefix = "ce_" if is_ce else "pe_"
            
            # Try to get live tick from memory store
            from services.market_data_service.options_stream_worker import options_stream_worker
            key = f"options_tick:{opt.get('name')}:{token}"
            tick = options_stream_worker.memory_store.get(key)
            if tick:
                strikes_map[strike][f"{prefix}ltp"] = tick.get("ltp", 0)
                strikes_map[strike][f"{prefix}volume"] = tick.get("volume", 0)
                strikes_map[strike][f"{prefix}oi"] = tick.get("oi", 0)
        
        # Build chain list
        chain = sorted(list(strikes_map.values()), key=lambda x: x["strike"])
        
        # Spot price simulation/lookup (hardcoded simulation if redis is missing)
        spot_price = 22500.0 if symbol.upper() == "NIFTY" else 50000.0
        
        # Identify ATM
        closest_diff = float('inf')
        atm_strike = None
        for c in chain:
            diff = abs(c["strike"] - spot_price)
            if diff < closest_diff:
                closest_diff = diff
                atm_strike = c["strike"]
                
        for c in chain:
            if c["strike"] == atm_strike:
                c["is_atm"] = True
        
        return {
            "spot_price": spot_price,
            "chain": chain
        }
        
    except Exception as e:
        logger.exception(f"Error fetching options chain: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.post(
    "/greeks/calculate",
    summary="Calculate Greeks",
    description="Calculate option Greeks using Black-Scholes model"
)
async def calculate_greeks(
    request: GreeksRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Calculate option Greeks
    
    Requirements: 38.1, 38.2, 38.3, 38.4, 38.5, 38.7
    """
    try:
        # Calculate time to expiry
        today = date.today()
        tte = (request.expiry_date - today).days / 365.0
        if tte <= 0:
            tte = 0.01  # Minimum 1 day
        
        # Check cache
        expiry_str = request.expiry_date.isoformat()
        cached = await cache_manager.get_greeks(
            request.symbol, request.strike, request.option_type,
            expiry_str, request.spot_price
        )
        if cached:
            return cached
        
        # If market price provided, calculate IV first
        implied_vol = 0.25  # Default assumption
        if request.market_price:
            calculated_iv = greeks_calculator.calculate_implied_volatility(
                request.option_type,
                request.strike,
                request.spot_price,
                tte,
                request.market_price
            )
            if calculated_iv:
                implied_vol = calculated_iv
        
        # Calculate Greeks
        greeks = greeks_calculator.calculate_greeks(
            request.option_type,
            request.strike,
            request.spot_price,
            tte,
            implied_vol,
            request.market_price
        )
        
        result = {
            "symbol": request.symbol,
            "strike": request.strike,
            "option_type": request.option_type,
            "expiry_date": expiry_str,
            "spot_price": request.spot_price,
            "delta": round(greeks.delta, 6),
            "gamma": round(greeks.gamma, 6),
            "theta": round(greeks.theta, 6),
            "vega": round(greeks.vega, 6),
            "rho": round(greeks.rho, 6),
            "implied_volatility": round(greeks.implied_volatility, 6) if greeks.implied_volatility else None,
            "theoretical_price": round(greeks.theoretical_price, 4) if greeks.theoretical_price else None,
            "calculated_at": datetime.utcnow().isoformat()
        }
        
        # Cache result
        await cache_manager.set_greeks(
            request.symbol, request.strike, request.option_type,
            expiry_str, request.spot_price, result
        )
        
        return result
        
    except Exception as e:
        logger.exception(f"Error calculating Greeks: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to calculate Greeks"
        )

@router.get(
    "/max-pain/{symbol}",
    summary="Calculate Max Pain",
    description="Calculate max pain price for options"
)
async def get_max_pain(
    symbol: str,
    expiry: str = Query(..., description="Expiry date (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db)
):
    """
    Calculate max pain price
    
    Requirements: 4.1, 4.2, 4.3, 4.7
    """
    try:
        # Check cache
        cached = await cache_manager.get_max_pain(symbol, expiry)
        if cached:
            return cached
        
        # Get options chain
        expiry_date = datetime.strptime(expiry, "%Y-%m-%d").date()
        
        result = await db.execute(
            select(OptionsChain).where(
                and_(
                    OptionsChain.symbol == symbol.upper(),
                    OptionsChain.expiry_date == expiry_date
                )
            ).order_by(desc(OptionsChain.timestamp)).limit(1)
        )
        chain = result.scalar_one_or_none()
        
        if not chain or not chain.strikes:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Options data not found for {symbol} {expiry}"
            )
        
        # Prepare strikes data
        strikes_data = []
        for strike in chain.strikes:
            strikes_data.append({
                "strike": strike.strike_price,
                "call_oi": strike.call_oi,
                "put_oi": strike.put_oi
            })
        
        # Calculate max pain
        result = max_pain_calculator.calculate_max_pain(
            symbol.upper(),
            expiry_date,
            float(chain.spot_price),
            strikes_data
        )
        
        response_data = max_pain_calculator.format_result(result)
        
        # Cache result
        await cache_manager.set_max_pain(symbol, expiry, response_data)
        
        return response_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error calculating max pain: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to calculate max pain"
        )

@router.get(
    "/gex/{symbol}",
    summary="Calculate GEX",
    description="Calculate Gamma Exposure (GEX) distribution"
)
async def get_gex(
    symbol: str,
    expiry: str = Query(..., description="Expiry date (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db)
):
    """
    Calculate Gamma Exposure
    
    Requirements: 5.1, 5.2, 5.3, 5.4, 5.7
    """
    try:
        # Check cache
        cached = await cache_manager.get_gex(symbol, expiry)
        if cached:
            return cached
        
        # Get options chain
        expiry_date = datetime.strptime(expiry, "%Y-%m-%d").date()
        
        result = await db.execute(
            select(OptionsChain).where(
                and_(
                    OptionsChain.symbol == symbol.upper(),
                    OptionsChain.expiry_date == expiry_date
                )
            ).order_by(desc(OptionsChain.timestamp)).limit(1)
        )
        chain = result.scalar_one_or_none()
        
        if not chain or not chain.strikes:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Options data not found for {symbol} {expiry}"
            )
        
        # Prepare strikes data with Greeks
        strikes_data = []
        for strike in chain.strikes:
            strikes_data.append({
                "strike": strike.strike_price,
                "call_gamma": strike.call_gamma or 0,
                "put_gamma": strike.put_gamma or 0,
                "call_oi": strike.call_oi,
                "put_oi": strike.put_oi
            })
        
        # Calculate GEX
        result = gex_calculator.calculate_gex(
            symbol.upper(),
            expiry_date,
            float(chain.spot_price),
            strikes_data
        )
        
        response_data = gex_calculator.format_result(result)
        
        # Cache result
        await cache_manager.set_gex(symbol, expiry, response_data)
        
        return response_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error calculating GEX: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to calculate GEX"
        )

@router.post(
    "/strategy/build",
    summary="Build Options Strategy",
    description="Build multi-leg options strategy with payoff calculation"
)
async def build_strategy(
    request: StrategyRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """
    Build options strategy and calculate payoff
    
    Requirements: 7.6, 26.1, 26.2, 26.3, 26.4
    """
    try:
        # Convert legs
        legs = [
            {
                "option_type": leg.option_type,
                "position_type": leg.position_type,
                "strike": leg.strike,
                "quantity": leg.quantity,
                "entry_price": leg.entry_price
            }
            for leg in request.legs
        ]
        
        # Build strategy
        result = strategy_builder.build_strategy(
            StrategyType(request.strategy_type),
            request.symbol.upper(),
            request.expiry_date,
            legs,
            request.spot_price
        )
        
        return strategy_builder.format_result(result)
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.exception(f"Error building strategy: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to build strategy"
        )

@router.get(
    "/strategy/predefined/{strategy_type}",
    summary="Create Predefined Strategy",
    description="Create a predefined strategy template"
)
async def create_predefined_strategy(
    strategy_type: str,
    symbol: str,
    expiry: str,
    spot_price: float,
    lower_strike: Optional[float] = None,
    upper_strike: Optional[float] = None
):
    """
    Create a predefined strategy
    
    Available types: STRADDLE, STRANGLE, BULL_CALL_SPREAD, IRON_CONDOR
    """
    try:
        expiry_date = datetime.strptime(expiry, "%Y-%m-%d").date()
        
        kwargs = {}
        if lower_strike:
            kwargs["lower_strike"] = lower_strike
        if upper_strike:
            kwargs["upper_strike"] = upper_strike
        
        result = strategy_builder.create_predefined_strategy(
            StrategyType(strategy_type.upper()),
            symbol.upper(),
            expiry_date,
            spot_price,
            **kwargs
        )
        
        return strategy_builder.format_result(result)
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid strategy type. Available: STRADDLE, STRANGLE, BULL_CALL_SPREAD, IRON_CONDOR"
        )
    except Exception as e:
        logger.exception(f"Error creating strategy: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create strategy"
        )

@router.get(
    "/expiries/{symbol}",
    summary="Get Available Expiries",
    description="Get list of available expiry dates for a symbol"
)
async def get_expiries(
    symbol: str
):
    """Get available expiry dates"""
    try:
        from services.market_data_service.instrument_master import instrument_master
        
        if not instrument_master.instruments:
            await instrument_master.download_master()
            
        opts = instrument_master.get_options_tokens(symbol.upper())
        # Parse unique expiries like "30MAY2024"
        raw_expiries = set()
        for opt in opts:
            expiry = opt.get("expiry")
            if expiry:
                raw_expiries.add(expiry)
                
        # Sort them
        sorted_expiries = []
        for exp in raw_expiries:
            try:
                dt = datetime.strptime(exp, "%d%b%Y")
                sorted_expiries.append((dt, dt.strftime("%Y-%m-%d")))
            except Exception:
                pass
                
        sorted_expiries.sort(key=lambda x: x[0])
        expiries = [x[1] for x in sorted_expiries]
        
        return {
            "symbol": symbol.upper(),
            "expiries": expiries,
            "count": len(expiries)
        }
        
    except Exception as e:
        logger.exception(f"Error fetching expiries: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch expiries"
        )

@router.get(
    "/cache/metrics",
    summary="Cache Metrics",
    description="Get options analytics cache metrics"
)
async def get_cache_metrics():
    """Get cache performance metrics"""
    return await cache_manager.get_metrics()


@router.get(
    "/oi-tracker/{symbol}",
    summary="OI Tracker",
    description="Track Open Interest changes with buildup patterns and PCR analysis"
)
async def get_oi_tracker(
    symbol: str,
    expiry: str = Query(..., description="Expiry date (YYYY-MM-DD)"),
    timeframe: str = Query(default="1h", description="Time interval: 5m, 15m, 1h, 1d"),
    db: AsyncSession = Depends(get_db)
):
    """
    Get OI tracker data with patterns and alerts
    
    Requirements: 6.1, 6.2, 6.3, 6.5, 6.6
    """
    try:
        # Get current options chain
        expiry_date = datetime.strptime(expiry, "%Y-%m-%d").date()
        
        result = await db.execute(
            select(OptionsChain).where(
                and_(
                    OptionsChain.symbol == symbol.upper(),
                    OptionsChain.expiry_date == expiry_date
                )
            ).order_by(desc(OptionsChain.timestamp)).limit(1)
        )
        chain = result.scalar_one_or_none()
        
        if not chain or not chain.strikes:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Options data not found for {symbol} {expiry}"
            )
        
        # Prepare current data
        current_data = []
        for strike in chain.strikes:
            current_data.append({
                "strike": strike.strike_price,
                "option_type": "CALL",
                "oi": strike.call_oi,
                "price": strike.call_ltp
            })
            current_data.append({
                "strike": strike.strike_price,
                "option_type": "PUT",
                "oi": strike.put_oi,
                "price": strike.put_ltp
            })
        
        # Calculate OI changes (simulate with random data for demo)
        # In production, this would compare with historical data
        import random
        changes = []
        total_ce_oi_change = 0
        total_pe_oi_change = 0
        
        for strike in chain.strikes:
            ce_change = random.randint(-50000, 50000)
            pe_change = random.randint(-50000, 50000)
            ce_price_change = random.uniform(-2, 2)
            pe_price_change = random.uniform(-2, 2)
            
            # Determine pattern
            def get_pattern(oi_change, price_change, option_type):
                if option_type == "CALL":
                    if oi_change > 0 and price_change > 0:
                        return "BULLISH_BUILDUP"
                    elif oi_change > 0 and price_change < 0:
                        return "BEARISH_BUILDUP"
                    elif oi_change < 0 and price_change < 0:
                        return "BULLISH_UNWINDING"
                    elif oi_change < 0 and price_change > 0:
                        return "BEARISH_UNWINDING"
                else:  # PUT
                    if oi_change > 0 and price_change < 0:
                        return "BEARISH_BUILDUP"
                    elif oi_change > 0 and price_change > 0:
                        return "BULLISH_BUILDUP"
                    elif oi_change < 0 and price_change > 0:
                        return "BEARISH_UNWINDING"
                    elif oi_change < 0 and price_change < 0:
                        return "BULLISH_UNWINDING"
                return "NEUTRAL"
            
            ce_pattern = get_pattern(ce_change, ce_price_change, "CALL")
            pe_pattern = get_pattern(pe_change, pe_price_change, "PUT")
            
            # Use CALL pattern as primary for the strike
            primary_pattern = ce_pattern
            
            # Calculate PCR for this strike
            pcr = strike.put_oi / max(strike.call_oi, 1)
            
            changes.append({
                "strike": float(strike.strike_price),
                "ce_oi_change": ce_change,
                "ce_oi_change_percent": round(ce_change / max(strike.call_oi, 1) * 100, 2),
                "pe_oi_change": pe_change,
                "pe_oi_change_percent": round(pe_change / max(strike.put_oi, 1) * 100, 2),
                "ce_price_change": round(ce_price_change, 2),
                "pe_price_change": round(pe_price_change, 2),
                "pattern": primary_pattern,
                "pcr": round(pcr, 2)
            })
            
            total_ce_oi_change += ce_change
            total_pe_oi_change += pe_change
        
        # Sort by absolute OI change to find top buildup/unwinding
        sorted_by_change = sorted(changes, key=lambda x: abs(x["ce_oi_change"]) + abs(x["pe_oi_change"]), reverse=True)
        top_buildup = [c["strike"] for c in sorted_by_change[:5] if c["pattern"] in ["BULLISH_BUILDUP", "BEARISH_BUILDUP"]]
        top_unwinding = [c["strike"] for c in sorted_by_change[:5] if c["pattern"] in ["BULLISH_UNWINDING", "BEARISH_UNWINDING"]]
        
        # Calculate overall PCR change
        total_pcr_change = round((total_pe_oi_change / max(total_ce_oi_change, 1)), 2)
        
        # Generate alerts for significant changes (>10%)
        alerts = []
        for c in changes:
            if abs(c["ce_oi_change_percent"]) > 10 or abs(c["pe_oi_change_percent"]) > 10:
                severity = "high" if abs(c["ce_oi_change_percent"]) > 20 or abs(c["pe_oi_change_percent"]) > 20 else "medium"
                alerts.append({
                    "strike": c["strike"],
                    "type": "OI_CHANGE",
                    "message": f"Significant OI change at strike {c['strike']}: CE {c['ce_oi_change_percent']:+.1f}%, PE {c['pe_oi_change_percent']:+.1f}%",
                    "severity": severity
                })
        
        return {
            "symbol": symbol.upper(),
            "expiry": expiry,
            "timeframe": timeframe,
            "changes": changes,
            "summary": {
                "total_ce_oi_change": total_ce_oi_change,
                "total_pe_oi_change": total_pe_oi_change,
                "pcr_change": total_pcr_change,
                "top_buildup_strikes": top_buildup,
                "top_unwinding_strikes": top_unwinding
            },
            "alerts": alerts,
            "calculated_at": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error calculating OI tracker: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to calculate OI tracker"
        )


# ============================================================================
# Phase 3.2: Volatility Surface Endpoints
# ============================================================================

from .volatility_surface import VolatilitySurfaceCalculator

vol_surface_calculator = VolatilitySurfaceCalculator()


@router.get(
    "/volatility-surface/{symbol}",
    summary="Volatility Surface",
    description="Calculate 3D implied volatility surface across strikes and expiries"
)
async def get_volatility_surface(
    symbol: str,
    spot_price: float,
    db: AsyncSession = Depends(get_db)
):
    """
    Get volatility surface analysis.
    
    Requirements: Phase 3.2 - Volatility Surface
    """
    try:
        # Fetch options chain data for all expiries
        result = await db.execute(
            select(OptionsChain).where(
                OptionsChain.symbol == symbol.upper()
            ).order_by(desc(OptionsChain.timestamp))
        )
        chains = result.scalars().all()
        
        if not chains:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Options data not found for {symbol}"
            )
        
        # Prepare data for calculation
        options_data = []
        for chain in chains:
            for strike in chain.strikes:
                options_data.append({
                    "symbol": symbol,
                    "expiry_date": chain.expiry_date,
                    "strike_price": strike.strike_price,
                    "call_price": strike.call_ltp,
                    "put_price": strike.put_ltp,
                    "call_oi": strike.call_oi,
                    "put_oi": strike.put_oi
                })
        
        # Calculate volatility surface
        surface = vol_surface_calculator.calculate_surface(
            symbol=symbol,
            spot_price=spot_price,
            options_data=options_data
        )
        
        return surface
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error calculating volatility surface: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to calculate volatility surface"
        )


@router.get(
    "/volatility-surface/{symbol}/term-structure",
    summary="Volatility Term Structure",
    description="Get ATM volatility term structure across expiries"
)
async def get_term_structure(
    symbol: str,
    spot_price: float,
    db: AsyncSession = Depends(get_db)
):
    """Get volatility term structure."""
    try:
        # Calculate full surface and extract term structure
        result = await db.execute(
            select(OptionsChain).where(
                OptionsChain.symbol == symbol.upper()
            ).order_by(desc(OptionsChain.timestamp))
        )
        chains = result.scalars().all()
        
        if not chains:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Options data not found for {symbol}"
            )
        
        options_data = []
        for chain in chains:
            for strike in chain.strikes:
                options_data.append({
                    "symbol": symbol,
                    "expiry_date": chain.expiry_date,
                    "strike_price": strike.strike_price,
                    "call_price": strike.call_ltp,
                    "put_price": strike.put_ltp
                })
        
        surface = vol_surface_calculator.calculate_surface(
            symbol=symbol,
            spot_price=spot_price,
            options_data=options_data
        )
        
        return {
            "symbol": symbol,
            "term_structure": surface.get("term_structure", {}),
            "surface_metrics": surface.get("surface_metrics", {})
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error calculating term structure: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to calculate term structure"
        )


# ============================================================================
# Phase 3.2: PnL Tracker Endpoints
# ============================================================================

from .pnl_tracker import PnLTrackerService, Position

pnl_tracker = PnLTrackerService()


@router.post(
    "/pnl-tracker/positions",
    summary="Add Position",
    description="Add a new options position for PnL tracking"
)
async def add_position(
    symbol: str,
    underlying: str,
    option_type: str,
    strike: float,
    expiry_date: str,
    position_type: str,
    quantity: int,
    entry_price: float,
    user_id: str = Depends(get_current_user_id)
):
    """Add a new position to track."""
    try:
        position = await pnl_tracker.add_position(
            user_id=user_id,
            symbol=symbol,
            underlying=underlying,
            option_type=option_type,
            strike=strike,
            expiry_date=expiry_date,
            position_type=position_type,
            quantity=quantity,
            entry_price=entry_price
        )
        return pnl_tracker.position_to_dict(position)
    except Exception as e:
        logger.exception(f"Error adding position: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to add position"
        )


@router.get(
    "/pnl-tracker/positions",
    summary="List Positions",
    description="List all tracked positions for a user"
)
async def list_positions(
    underlying: Optional[str] = None,
    open_only: bool = True,
    user_id: str = Depends(get_current_user_id)
):
    """List positions."""
    try:
        positions = await pnl_tracker.get_positions(
            user_id=user_id,
            underlying=underlying,
            open_only=open_only
        )
        return {
            "positions": [pnl_tracker.position_to_dict(p) for p in positions],
            "count": len(positions)
        }
    except Exception as e:
        logger.exception(f"Error listing positions: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list positions"
        )


@router.get(
    "/pnl-tracker/positions/{position_id}",
    summary="Position Detail",
    description="Get detailed position information"
)
async def get_position_detail(position_id: str):
    """Get position details."""
    try:
        detail = await pnl_tracker.get_position_detail(position_id)
        if not detail:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Position not found"
            )
        return detail
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting position detail: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get position detail"
        )


@router.post(
    "/pnl-tracker/positions/{position_id}/close",
    summary="Close Position",
    description="Close a position with exit price"
)
async def close_position(
    position_id: str,
    exit_price: float
):
    """Close a position."""
    try:
        position = await pnl_tracker.close_position(position_id, exit_price)
        if not position:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Position not found"
            )
        return pnl_tracker.position_to_dict(position)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error closing position: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to close position"
        )


# ============================================================================
# IV Smile Endpoints
# ============================================================================

class IVSmileRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=50)
    spot_price: float = Field(..., gt=0)
    expiry_date: date
    option_chain: List[Dict[str, Any]] = Field(..., min_items=1)


@router.post(
    "/iv-smile/calculate",
    summary="Calculate IV Smile",
    description="Calculate implied volatility smile/skew analysis from option chain"
)
async def calculate_iv_smile(request: IVSmileRequest):
    """Calculate IV smile for a symbol."""
    try:
        result = iv_smile_calculator.calculate_smile(
            symbol=request.symbol,
            spot_price=request.spot_price,
            option_chain=request.option_chain,
            expiry_date=request.expiry_date.isoformat()
        )
        
        return {
            "symbol": result.symbol,
            "expiry_date": result.expiry_date,
            "spot_price": result.spot_price,
            "atm_strike": result.atm_strike,
            "atm_iv": result.atm_iv,
            "smile_points": [
                {
                    "strike": p.strike,
                    "iv": p.iv,
                    "moneyness": p.moneyness,
                    "delta": p.delta,
                    "option_type": p.option_type
                }
                for p in result.smile_points
            ],
            "metrics": {
                "skew": result.skew,
                "kurtosis": result.kurtosis,
                "smile_slope": result.smile_slope
            },
            "anomaly_detection": {
                "is_smile_inverted": result.is_smile_inverted,
                "is_volatility_surface_stressed": result.is_volatility_surface_stressed,
                "anomaly_score": result.anomaly_score
            },
            "sentiment": {
                "sentiment": result.sentiment,
                "confidence": result.confidence
            },
            "calculated_at": result.calculated_at
        }
    except Exception as e:
        logger.exception(f"Error calculating IV smile: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to calculate IV smile: {str(e)}"
        )


@router.get(
    "/iv-smile/compare",
    summary="Compare IV Smiles",
    description="Compare two IV smiles to identify changes"
)
async def compare_iv_smiles(
    symbol: str,
    expiry_date1: date,
    expiry_date2: date,
    spot_price1: float,
    spot_price2: float
):
    """Compare IV smiles between two expiries."""
    try:
        # This would typically fetch from database/cache
        # For now, return a placeholder response
        return {
            "message": "IV smile comparison requires historical data",
            "symbol": symbol,
            "expiry_date1": expiry_date1.isoformat(),
            "expiry_date2": expiry_date2.isoformat()
        }
    except Exception as e:
        logger.exception(f"Error comparing IV smiles: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to compare IV smiles"
        )


@router.get(
    "/pnl-tracker/summary",
    summary="Portfolio Summary",
    description="Get portfolio PnL summary"
)
async def get_portfolio_summary(
    underlying: Optional[str] = None,
    user_id: str = Depends(get_current_user_id)
):
    """Get portfolio summary."""
    try:
        summary = await pnl_tracker.get_portfolio_summary(
            user_id=user_id,
            underlying=underlying
        )
        return {
            "summary": {
                "total_positions": summary.total_positions,
                "total_realized_pnl": summary.total_realized_pnl,
                "total_unrealized_pnl": summary.total_unrealized_pnl,
                "total_pnl": summary.total_pnl,
                "winning_positions": summary.winning_positions,
                "losing_positions": summary.losing_positions,
                "win_rate": summary.risk_metrics.get("win_rate", 0)
            },
            "greeks_exposure": {
                "net_delta": summary.net_delta,
                "net_gamma": summary.net_gamma,
                "net_theta": summary.net_theta,
                "net_vega": summary.net_vega
            },
            "risk_metrics": summary.risk_metrics
        }
    except Exception as e:
        logger.exception(f"Error getting portfolio summary: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get portfolio summary"
        )


# ============================================================================
# Straddle Chart Endpoints
# ============================================================================

class StraddleRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=50)
    spot_price: float = Field(..., gt=0)
    expiry_date: date
    option_chain: List[Dict[str, Any]] = Field(..., min_items=1)
    days_to_expiry: int = Field(..., gt=0)


@router.post(
    "/straddle/analyze",
    summary="Analyze Straddles",
    description="Analyze straddle positions across all strikes to identify optimal entry points"
)
async def analyze_straddles(request: StraddleRequest):
    """Analyze straddles for a symbol."""
    try:
        result = straddle_chart_calculator.analyze_straddles(
            symbol=request.symbol,
            spot_price=request.spot_price,
            option_chain=request.option_chain,
            expiry_date=request.expiry_date.isoformat(),
            days_to_expiry=request.days_to_expiry
        )
        
        return {
            "symbol": result.symbol,
            "expiry_date": result.expiry_date,
            "spot_price": result.spot_price,
            "straddles": [
                {
                    "strike": s.strike,
                    "call_price": s.call_price,
                    "put_price": s.put_price,
                    "total_cost": s.total_cost,
                    "break_even_upper": s.break_even_upper,
                    "break_even_lower": s.break_even_lower,
                    "max_loss": s.max_loss,
                    "iv": s.iv
                }
                for s in result.straddles
            ],
            "optimal_straddle": {
                "strike": result.optimal_straddle.strike,
                "call_price": result.optimal_straddle.call_price,
                "put_price": result.optimal_straddle.put_price,
                "total_cost": result.optimal_straddle.total_cost,
                "break_even_upper": result.optimal_straddle.break_even_upper,
                "break_even_lower": result.optimal_straddle.break_even_lower,
                "iv": result.optimal_straddle.iv
            },
            "market_metrics": {
                "avg_straddle_cost": result.avg_straddle_cost,
                "cost_range": result.cost_range,
                "iv_skew": result.iv_skew
            },
            "trading_signals": {
                "is_cheap_straddle": result.is_cheap_straddle,
                "is_expensive_straddle": result.is_expensive_straddle,
                "break_even_width": result.break_even_width,
                "expected_move": result.expected_move,
                "probability_profit": result.probability_profit
            },
            "calculated_at": result.calculated_at
        }
    except Exception as e:
        logger.exception(f"Error analyzing straddles: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to analyze straddles: {str(e)}"
        )


@router.post(
    "/straddle/pnl-scenario",
    summary="Calculate Straddle P&L Scenario",
    description="Calculate P&L for a straddle at expiry for a given spot price"
)
async def calculate_straddle_pnl(
    strike: float,
    call_price: float,
    put_price: float,
    spot_price_at_expiry: float
):
    """Calculate P&L scenario for a straddle."""
    try:
        # Create a temporary straddle data point
        from services.options_analytics.calculators.straddle_chart_calculator import StraddleDataPoint
        straddle = StraddleDataPoint(
            strike=strike,
            call_price=call_price,
            put_price=put_price,
            total_cost=call_price + put_price,
            break_even_upper=strike + call_price + put_price,
            break_even_lower=strike - call_price - put_price,
            max_loss=call_price + put_price,
            iv=0
        )
        
        pnl = straddle_chart_calculator.calculate_pnl_scenario(
            straddle, spot_price_at_expiry
        )
        
        return pnl
    except Exception as e:
        logger.exception(f"Error calculating straddle P&L: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to calculate straddle P&L"
        )


@router.post(
    "/straddle/pnl-curve",
    summary="Generate Straddle P&L Curve",
    description="Generate P&L curve across a range of spot prices for charting"
)
async def generate_straddle_pnl_curve(
    strike: float,
    call_price: float,
    put_price: float,
    spot_price_start: float,
    spot_price_end: float,
    num_points: int = 50
):
    """Generate P&L curve for a straddle."""
    try:
        from services.options_analytics.calculators.straddle_chart_calculator import StraddleDataPoint
        straddle = StraddleDataPoint(
            strike=strike,
            call_price=call_price,
            put_price=put_price,
            total_cost=call_price + put_price,
            break_even_upper=strike + call_price + put_price,
            break_even_lower=strike - call_price - put_price,
            max_loss=call_price + put_price,
            iv=0
        )
        
        pnl_curve = straddle_chart_calculator.generate_pnl_curve(
            straddle,
            (spot_price_start, spot_price_end),
            num_points
        )
        
        return {
            "strike": strike,
            "pnl_curve": pnl_curve
        }
    except Exception as e:
        logger.exception(f"Error generating P&L curve: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate P&L curve"
        )


# ============================================================================
# Synthetic Future Endpoints
# ============================================================================

class SyntheticFutureRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=50)
    spot_price: float = Field(..., gt=0)
    expiry_date: date
    option_chain: List[Dict[str, Any]] = Field(..., min_items=1)
    days_to_expiry: int = Field(..., gt=0)
    actual_future_price: Optional[float] = None
    risk_free_rate: Optional[float] = None


@router.post(
    "/synthetic-future/calculate",
    summary="Calculate Synthetic Futures",
    description="Calculate synthetic futures from option prices using put-call parity"
)
async def calculate_synthetic_futures(request: SyntheticFutureRequest):
    """Calculate synthetic futures for a symbol."""
    try:
        result = synthetic_future_calculator.calculate_synthetic_futures(
            symbol=request.symbol,
            spot_price=request.spot_price,
            option_chain=request.option_chain,
            expiry_date=request.expiry_date.isoformat(),
            days_to_expiry=request.days_to_expiry,
            actual_future_price=request.actual_future_price,
            risk_free_rate=request.risk_free_rate
        )
        
        return {
            "symbol": result.symbol,
            "expiry_date": result.expiry_date,
            "spot_price": result.spot_price,
            "risk_free_rate": result.risk_free_rate,
            "days_to_expiry": result.days_to_expiry,
            "synthetic_points": [
                {
                    "strike": p.strike,
                    "call_price": p.call_price,
                    "put_price": p.put_price,
                    "synthetic_future_price": p.synthetic_future_price,
                    "actual_future_price": p.actual_future_price,
                    "arbitrage_opportunity": p.arbitrage_opportunity,
                    "arbitrage_profit": p.arbitrage_profit,
                    "mispricing_pct": p.mispricing_pct
                }
                for p in result.synthetic_points
            ],
            "fair_value": {
                "fair_future_price": result.fair_future_price,
                "cost_of_carry": result.cost_of_carry
            },
            "arbitrage_analysis": {
                "arbitrage_opportunities": [
                    {
                        "strike": p.strike,
                        "arbitrage_profit": p.arbitrage_profit,
                        "mispricing_pct": p.mispricing_pct
                    }
                    for p in result.arbitrage_opportunities
                ],
                "max_arbitrage_profit": result.max_arbitrage_profit,
                "avg_mispricing": result.avg_mispricing
            },
            "market_efficiency": {
                "is_market_efficient": result.is_market_efficient,
                "efficiency_score": result.efficiency_score
            },
            "trading_signals": {
                "recommendation": result.recommendation,
                "confidence": result.confidence
            },
            "calculated_at": result.calculated_at
        }
    except Exception as e:
        logger.exception(f"Error calculating synthetic futures: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to calculate synthetic futures: {str(e)}"
        )


@router.post(
    "/synthetic-future/validate-parity",
    summary="Validate Put-Call Parity",
    description="Validate put-call parity for a specific strike"
)
async def validate_put_call_parity(
    strike: float,
    call_price: float,
    put_price: float,
    spot_price: float,
    risk_free_rate: float = 0.06,
    days_to_expiry: int = 30,
    tolerance: float = 0.02
):
    """Validate put-call parity."""
    try:
        validation = synthetic_future_calculator.validate_put_call_parity(
            strike=strike,
            call_price=call_price,
            put_price=put_price,
            spot_price=spot_price,
            risk_free_rate=risk_free_rate,
            days_to_expiry=days_to_expiry,
            tolerance=tolerance
        )
        return validation
    except Exception as e:
        logger.exception(f"Error validating put-call parity: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to validate put-call parity"
        )


@router.post(
    "/synthetic-future/basis-risk",
    summary="Calculate Basis Risk",
    description="Calculate basis risk between synthetic and actual futures"
)
async def calculate_basis_risk(
    synthetic_future_price: float,
    actual_future_price: float,
    spot_price: float
):
    """Calculate basis risk."""
    try:
        basis_risk = synthetic_future_calculator.calculate_basis_risk(
            synthetic_future_price=synthetic_future_price,
            actual_future_price=actual_future_price,
            spot_price=spot_price
        )
        return basis_risk
    except Exception as e:
        logger.exception(f"Error calculating basis risk: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to calculate basis risk"
        )


# ============================================================================
# Multi-Strike OI Endpoints
# ============================================================================

class MultiStrikeOIRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=50)
    spot_price: float = Field(..., gt=0)
    expiry_date: date
    option_chain: List[Dict[str, Any]] = Field(..., min_items=1)


@router.post(
    "/multi-strike-oi/analyze",
    summary="Analyze Multi-Strike OI",
    description="Analyze open interest across multiple strikes to identify support/resistance and positioning"
)
async def analyze_multi_strike_oi(request: MultiStrikeOIRequest):
    """Analyze multi-strike OI for a symbol."""
    try:
        result = multi_strike_oi_calculator.analyze_multi_strike_oi(
            symbol=request.symbol,
            spot_price=request.spot_price,
            option_chain=request.option_chain,
            expiry_date=request.expiry_date.isoformat()
        )
        
        return {
            "symbol": result.symbol,
            "expiry_date": result.expiry_date,
            "spot_price": result.spot_price,
            "strikes_data": [
                {
                    "strike": s.strike,
                    "call_oi": s.call_oi,
                    "put_oi": s.put_oi,
                    "total_oi": s.total_oi,
                    "put_call_ratio": s.put_call_ratio,
                    "max_pain_contribution": s.max_pain_contribution
                }
                for s in result.strikes_data
            ],
            "support_resistance": {
                "support_levels": result.support_levels,
                "resistance_levels": result.resistance_levels,
                "max_pain_strike": result.max_pain_strike
            },
            "institutional_positioning": {
                "total_call_oi": result.total_call_oi,
                "total_put_oi": result.total_put_oi,
                "overall_pcr": result.overall_pcr,
                "net_oi_bias": result.net_oi_bias
            },
            "concentration": {
                "oi_concentration": result.oi_concentration,
                "max_oi_strike": result.max_oi_strike,
                "max_oi_value": result.max_oi_value
            },
            "market_signals": {
                "is_bullish_positioning": result.is_bullish_positioning,
                "is_bearish_positioning": result.is_bearish_positioning,
                "sentiment_score": result.sentiment_score
            },
            "calculated_at": result.calculated_at
        }
    except Exception as e:
        logger.exception(f"Error analyzing multi-strike OI: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to analyze multi-strike OI: {str(e)}"
        )


@router.get(
    "/pnl-tracker/scenarios/{position_id}",
    summary="Scenario Analysis",
    description="Run scenario analysis on a position"
)
async def scenario_analysis(
    position_id: str,
    price_changes: Optional[List[float]] = None
):
    """Run scenario analysis."""
    try:
        analysis = await pnl_tracker.scenario_analysis(
            position_id=position_id,
            price_changes=price_changes
        )
        return analysis
    except Exception as e:
        logger.exception(f"Error running scenario analysis: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to run scenario analysis"
        )
