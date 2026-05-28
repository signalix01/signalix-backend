from fastapi import APIRouter
from datetime import datetime, timedelta
import random

# Unified router for all mock endpoints until they are properly implemented
router = APIRouter()

# --- Market Data Stub ---
@router.get("/api/v1/market/regime")
async def get_market_regime(market: str = "nse-bse"):
    return {
        "current": "bullish",
        "confidence": 78,
        "lastUpdate": datetime.utcnow().isoformat() + "Z",
        "nse_regime": "bull",
        "vix": 14.2,
        "fear_greed_index": 72,
        "dxy": 104.2,
        "nse_open": True,
        "last_updated": datetime.utcnow().isoformat() + "Z"
    }

@router.get("/api/v1/market/regime-context")
async def get_regime_context():
    return {
        "regime": "trending-bull",
        "nseVix": 14.2,
        "btcFearGreed": {"value": 72, "label": "Greed"},
        "dxy": 104.2,
        "lastUpdate": datetime.utcnow().isoformat() + "Z"
    }

@router.get("/api/v1/market/macro-context")
async def get_macro_context(market: str = "nse-bse"):
    return {
        "vix": {"level": 13.42, "percentile": 22, "trend": "falling"},
        "indiaVix": {"level": 13.42, "percentile": 22},
        "fiiDiiFlow": [
            {"date": "2026-04-28", "fiiBuy": 8420, "fiiSell": 6180, "fiiNet": 2240, "diiBuy": 4320, "diiSell": 3890, "diiNet": 430},
        ],
        "currencyPairs": [
            {"pair": "USD/INR", "rate": 83.42, "changePercent": -0.12},
        ],
        "commodities": [
            {"name": "Crude Oil (WTI)", "price": 78.34, "changePercent": 1.24},
        ],
        "interestRates": [
            {"name": "RBI Repo Rate", "rate": 6.50, "lastChange": "2024-02-08"},
        ],
        "economicCalendar": [
            {"event": "RBI MPC Meeting", "date": "2026-05-08", "importance": "high"},
        ]
    }

@router.get("/api/v1/market/indices")
async def get_indices():
    return [
        {"symbol": "NIFTY50", "name": "NIFTY 50", "value": 24356.75, "change": 187.40, "changePercent": 0.78},
        {"symbol": "SENSEX", "name": "SENSEX", "value": 80218.37, "change": 612.21, "changePercent": 0.77},
        {"symbol": "SPX", "name": "S&P 500", "value": 5308.13, "change": -12.45, "changePercent": -0.23},
        {"symbol": "VIX", "name": "India VIX", "value": 13.42, "change": -0.38, "changePercent": -2.75},
    ]

# --- Portfolio Stub ---
@router.get("/api/v1/portfolio/analytics")
async def get_portfolio_analytics():
    return {
        "summary": {
            "totalValue": 1284320,
            "todayPnL": 6322.50,
            "todayPnLPercent": 0.49,
            "weekPnL": 18450.00,
            "monthPnL": 54230.00,
            "activePositions": 4,
            "pendingAnalyses": 2,
            "unreadNotifications": 5
        },
        "performance": {
            "cumulativeReturns": [],
            "winRate": 64.2,
            "averageReturn": 2.87,
            "averageHoldPeriod": 4.3,
            "totalTrades": 47,
            "sharpeRatio": 1.84,
            "maxDrawdown": 8.3,
            "recoveryTime": 12
        },
        "allocation": {
            "bySector": [{"sector": "IT", "percentage": 32, "value": 412984, "positionCount": 2}],
            "byMarket": [{"market": "nse-bse", "percentage": 85, "value": 1091672, "positionCount": 4}],
            "byAnalysisType": [{"analysisType": "swing-trade", "winRate": 68, "averageReturn": 3.2, "tradeCount": 22}]
        },
        "topTrades": {
            "winners": [],
            "losers": []
        }
    }

@router.get("/api/v1/portfolio/positions")
async def get_positions():
    return [
        {
            "id": "pos-001", "instrument": "RELIANCE", "entryPrice": 2845.00, "currentPrice": 2934.50,
            "quantity": 50, "side": "LONG", "pnl": 4475.00, "pnlPercentage": 3.14, "status": "open",
            "entryTime": (datetime.utcnow() - timedelta(days=3)).isoformat() + "Z",
            "stopLoss": 2780.00, "targets": [2950.00, 3020.00], "signalId": "sig-001"
        }
    ]

# --- Watchlist Stub ---
@router.get("/api/v1/user/watchlists")
async def get_watchlists():
    return [
        {
            "id": "wl-001", "name": "Nifty 50 Picks", "description": "Top large-cap swing trade candidates",
            "instruments": [
                {"symbol": "RELIANCE", "name": "Reliance Industries", "currentPrice": 2934.50, "changePercent": 1.24, "lastUpdate": datetime.utcnow().isoformat() + "Z"},
            ],
            "autoScanEnabled": True, "scanResultsCount": 3,
            "createdAt": (datetime.utcnow() - timedelta(days=30)).isoformat() + "Z", "updatedAt": datetime.utcnow().isoformat() + "Z"
        }
    ]

# --- User Profile Stub ---
@router.get("/api/v1/user/profile")
async def get_profile():
    return {
        "id": "user-001",
        "subscriptionTier": "standard",
        "emailVerified": True,
        "createdAt": (datetime.utcnow() - timedelta(days=90)).isoformat() + "Z",
        "updatedAt": datetime.utcnow().isoformat() + "Z",
        "tier1": {
            "email": "trader@signalixaiai.com",
            "phone": "+91 98765 43210",
            "fullName": "Arjun Sharma",
            "country": "India",
            "declaredCapital": 1284320,
            "riskTolerance": "moderate",
            "investmentHorizon": "medium"
        }
    }
