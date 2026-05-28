from fastapi import APIRouter
from typing import List, Dict, Any

router = APIRouter(prefix="/api/v1/risk", tags=["risk"])

@router.get("/assessment", response_model=Dict[str, Any])
async def get_risk_assessment():
    return {
        "riskScore": 65,
        "sectorConcentration": [
            {"sector": "Technology", "percentage": 45, "warning": True},
            {"sector": "Finance", "percentage": 25, "warning": False},
            {"sector": "Energy", "percentage": 30, "warning": False}
        ],
        "positionSizes": [
            {"instrument": "RELIANCE", "percentage": 15, "warning": False},
            {"instrument": "TCS", "percentage": 22, "warning": True}
        ],
        "correlationMatrix": [
            {"instrument1": "RELIANCE", "instrument2": "TCS", "correlation": 0.3},
            {"instrument1": "HDFCBANK", "instrument2": "ICICIBANK", "correlation": 0.8}
        ],
        "stopLossExposure": 4.5,
        "upcomingEarnings": [
            {"instrument": "RELIANCE", "date": "2026-06-15", "daysUntil": 21}
        ],
        "circuitBreakerStatus": {
            "active": False,
            "dailyLossLimit": 10000,
            "currentLoss": 2500,
            "percentageUsed": 25
        }
    }

@router.get("/recommendations", response_model=List[Dict[str, Any]])
async def get_risk_recommendations():
    return [
        {
            "id": "rec-1",
            "type": "reduce-position",
            "severity": "high",
            "title": "Reduce TCS Exposure",
            "description": "TCS represents 22% of your portfolio, exceeding the recommended 15% limit for a single asset.",
            "actionItems": ["Sell 7% of TCS position to rebalance"],
            "affectedInstruments": ["TCS"]
        },
        {
            "id": "rec-2",
            "type": "diversify",
            "severity": "medium",
            "title": "High Sector Concentration",
            "description": "Technology sector accounts for 45% of your portfolio. Consider diversifying into Defensive sectors.",
            "actionItems": ["Explore FMCG or Healthcare stocks", "Reduce IT holdings by 10%"],
            "affectedInstruments": ["TCS", "INFY"]
        }
    ]

@router.get("/market-metrics", response_model=Dict[str, Any])
async def get_market_risk_metrics(market: str = "nse-bse"):
    return {
        "marketCorrelation": 0.75,
        "beta": 1.12,
        "volatility": {
            "daily": 1.2,
            "weekly": 3.5,
            "monthly": 8.1
        },
        "sharpeRatio": 1.4,
        "maxDrawdown": 12.5,
        "valueAtRisk": 2.5
    }
