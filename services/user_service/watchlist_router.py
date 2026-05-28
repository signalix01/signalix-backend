from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from datetime import datetime, timedelta
import asyncio
from typing import List, Dict
from shared.database.session import get_db
from shared.database.user_models import Watchlist, WatchlistInstrument, User
from shared.database.execution_models import Order
from shared.security.dependencies import get_current_user

# Re-use market data service logic for fetching prices
from services.market_data_service.router import fetch_yf_data

router = APIRouter()

@router.get("/api/v1/user/watchlists")
async def get_watchlists(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Fetch user's watchlists and enrich with live prices."""
    result = await db.execute(select(Watchlist).where(Watchlist.user_id == current_user.id))
    watchlists = result.scalars().all()
    
    if not watchlists:
        return []
    enriched_watchlists = []
    
    for wl in watchlists:
        res_inst = await db.execute(select(WatchlistInstrument).where(WatchlistInstrument.watchlist_id == wl.id))
        instruments = res_inst.scalars().all()
        
        symbols = [i.symbol for i in instruments]
        prices = await fetch_yf_data(symbols) if symbols else {}
        
        enriched_instruments = []
        for i in instruments:
            p_data = prices.get(i.symbol, {})
            current = p_data.get("price", 0.0)
            prev = p_data.get("previous_close", 0.0)
            change_pct = ((current - prev) / prev * 100) if prev > 0 else 0.0
            
            enriched_instruments.append({
                "symbol": i.symbol,
                "name": i.name or i.symbol,
                "currentPrice": round(current, 2),
                "changePercent": round(change_pct, 2),
                "lastUpdate": datetime.utcnow().isoformat() + "Z"
            })
            
        enriched_watchlists.append({
            "id": str(wl.id),
            "name": wl.name,
            "description": wl.description,
            "instruments": enriched_instruments,
            "autoScanEnabled": wl.auto_scan_enabled,
            "scanResultsCount": 0,
            "createdAt": wl.created_at.isoformat() + "Z",
            "updatedAt": wl.updated_at.isoformat() + "Z"
        })
        
    return enriched_watchlists

@router.get("/api/v1/user/profile")
async def get_profile(current_user: User = Depends(get_current_user)):
    return {
        "id": str(current_user.id),
        "subscriptionTier": current_user.subscription_tier or "trial",
        "emailVerified": current_user.is_email_verified,
        "createdAt": current_user.created_at.isoformat() + "Z" if current_user.created_at else None,
        "updatedAt": current_user.updated_at.isoformat() + "Z" if current_user.updated_at else None,
        "tier1": {
            "email": current_user.email,
            "phone": current_user.phone,
            "fullName": current_user.full_name,
            "country": current_user.country_of_residence,
            "declaredCapital": current_user.declared_trading_capital_inr,
            "riskTolerance": current_user.risk_tolerance_score,
            "investmentHorizon": current_user.investment_horizon
        }
    }

@router.get("/api/v1/user/activity")
async def get_recent_activity(
    limit: int = 5,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Fetch recent trades
    result = await db.execute(
        select(Order).where(Order.user_id == current_user.id).order_by(Order.timestamp.desc()).limit(limit)
    )
    orders = result.scalars().all()
    
    activities = []
    for order in orders:
        side_val = order.side.value if hasattr(order.side, 'value') else order.side
        price_val = order.price if order.price else 'MARKET'
        activities.append({
            "id": str(order.id),
            "type": "trade",
            "description": f"{side_val} {order.quantity} {order.instrument} @ {price_val}",
            "timestamp": order.timestamp.isoformat() + "Z" if order.timestamp else None
        })
        
    return activities
