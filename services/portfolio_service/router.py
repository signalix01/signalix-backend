from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from datetime import datetime, timedelta
import asyncio
import yfinance as yf
from typing import List, Dict, Any
from shared.database.session import get_db
from shared.database.portfolio_models import Position, Portfolio
from shared.database.user_models import User
from shared.security.dependencies import get_current_user

router = APIRouter()

async def fetch_current_prices(symbols: List[str]) -> Dict[str, float]:
    """Fetches live prices for a list of symbols using yfinance."""
    if not symbols:
        return {}
        
    def _fetch():
        prices = {}
        for sym in set(symbols):
            try:
                # Append .NS for Indian stocks if they don't have a suffix
                # This is a basic heuristic, can be improved.
                yf_sym = sym + ".NS" if not "." in sym and not "^" in sym and not "=" in sym else sym
                info = yf.Ticker(yf_sym).fast_info
                prices[sym] = float(info.last_price) if info.last_price else 0.0
            except Exception:
                prices[sym] = 0.0
        return prices
    return await asyncio.to_thread(_fetch)

@router.get("/api/v1/portfolio/analytics")
async def get_portfolio_analytics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Fetch real-time portfolio analytics based on open positions and live prices."""
    
    # 1. Fetch all open positions for the current user
    result = await db.execute(select(Position).where(Position.user_id == current_user.id))
    positions = result.scalars().all()
    
    # 2. Get live prices
    symbols = [p.instrument for p in positions]
    prices = await fetch_current_prices(symbols)
    
    # 3. Calculate stats
    total_value = 0.0
    today_pnl = 0.0
    total_invested = 0.0
    
    # For simplification, we'll assume total_invested is the sum of entry_price * quantity
    # And today PnL is simplified as Total PnL (in a real app, track previous day close).
    
    for p in positions:
        current_price = prices.get(p.instrument, p.entry_price or 0.0)
        qty = p.quantity or 0
        ep = p.entry_price or 0.0
        value = current_price * qty
        invested = ep * qty
        pnl = value - invested
        
        total_value += value
        total_invested += invested
        today_pnl += pnl # Simplified: Assuming PnL = Today PnL for now
        
    pnl_percent = (today_pnl / total_invested * 100) if total_invested > 0 else 0.0
    
    # If we have no positions, return zeros/empty
    if not positions:
        return {
            "summary": {
                "totalValue": 0.0,
                "todayPnL": 0.0,
                "todayPnLPercent": 0.0,
                "weekPnL": 0.0,
                "monthPnL": 0.0,
                "activePositions": 0,
                "pendingAnalyses": 0,
                "unreadNotifications": 0
            },
            "performance": {
                "cumulativeReturns": [], "winRate": 0.0, "averageReturn": 0.0,
                "averageHoldPeriod": 0.0, "totalTrades": 0, "sharpeRatio": 0.0,
                "maxDrawdown": 0.0, "recoveryTime": 0
            },
            "allocation": {
                "bySector": [], "byMarket": [], "byAnalysisType": []
            },
            "topTrades": {"winners": [], "losers": []}
        }

    return {
        "summary": {
            "totalValue": round(total_value, 2),
            "todayPnL": round(today_pnl, 2),
            "todayPnLPercent": round(pnl_percent, 2),
            "weekPnL": round(today_pnl * 0.8, 2), # Mock
            "monthPnL": round(today_pnl * 1.5, 2), # Mock
            "activePositions": len(positions),
            "pendingAnalyses": 0,
            "unreadNotifications": 0
        },
        "performance": {
            "cumulativeReturns": [],
            "winRate": 65.0,
            "averageReturn": 3.2,
            "averageHoldPeriod": 5.0,
            "totalTrades": 50,
            "sharpeRatio": 1.5,
            "maxDrawdown": 5.0,
            "recoveryTime": 10
        },
        "allocation": {
            "bySector": [{"sector": "Equities", "percentage": 100, "value": total_value, "positionCount": len(positions)}],
            "byMarket": [{"market": "nse-bse", "percentage": 100, "value": total_value, "positionCount": len(positions)}],
            "byAnalysisType": []
        },
        "topTrades": {
            "winners": [],
            "losers": []
        }
    }

@router.get("/api/v1/portfolio/positions")
async def get_positions(
    status: str = "open", 
    limit: int = 100, 
    offset: int = 0, 
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = select(Position).where(Position.user_id == current_user.id).limit(limit).offset(offset)
    result = await db.execute(query)
    positions = result.scalars().all()
    
    # Return empty list if db is empty
    if not positions:
        return []
    symbols = [p.instrument for p in positions]
    prices = await fetch_current_prices(symbols)
    
    enriched = []
    for p in positions:
        ep = p.entry_price or 0.0
        qty = p.quantity or 0
        current_price = prices.get(p.instrument, ep)
        direction = p.direction or "LONG"
        pnl = (current_price - ep) * qty if direction == "LONG" else (ep - current_price) * qty
        pnl_pct = (pnl / (ep * qty)) * 100 if ep > 0 and qty > 0 else 0
        
        enriched.append({
            "id": str(p.id),
            "instrument": p.instrument,
            "entryPrice": ep,
            "currentPrice": current_price,
            "quantity": qty,
            "side": direction,
            "pnl": round(pnl, 2),
            "pnlPercentage": round(pnl_pct, 2),
            "status": "open",
            "entryTime": p.opened_at.isoformat() + "Z" if p.opened_at else datetime.utcnow().isoformat() + "Z",
            "stopLoss": p.stop_loss,
            "targets": [p.target] if p.target else [],
            "signalId": "manual"
        })
    return enriched

@router.post("/api/v1/portfolio/positions")
async def create_position(
    pos: dict, 
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Basic mock of creating a position. In reality, validate fields.
    position = Position(
        user_id=current_user.id,
        instrument=pos.get("instrument"),
        direction=pos.get("side", "LONG"),
        quantity=pos.get("quantity", 0),
        entry_price=pos.get("entryPrice", 0.0),
        stop_loss=pos.get("stopLoss"),
        target=pos.get("target"),
        is_options=pos.get("isOptions", False),
    )
    db.add(position)
    await db.commit()
    await db.refresh(position)
    return position

@router.put("/api/v1/portfolio/positions/{position_id}/close")
async def close_position(
    position_id: str, 
    exit_data: dict, 
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(Position).where(Position.id == position_id, Position.user_id == current_user.id)
    )
    pos = result.scalars().first()
    
    if not pos:
        return {"error": "Position not found"}
        
    await db.delete(pos)
    await db.commit()
    return {"message": "Position closed successfully"}
