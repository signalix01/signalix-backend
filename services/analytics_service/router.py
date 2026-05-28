from fastapi import APIRouter
from typing import Dict, Any

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])

@router.get("/performance", response_model=Dict[str, Any])
async def get_performance_metrics():
    return {
        "cumulativeReturns": [
            {"date": "2026-04-20", "value": 1000000},
            {"date": "2026-05-20", "value": 1054230}
        ],
        "winRate": 64.2,
        "averageReturn": 2.87,
        "averageHoldPeriod": 4.3,
        "totalTrades": 47,
        "sharpeRatio": 1.84,
        "maxDrawdown": 8.3,
        "recoveryTime": 12,
        "monthlyReturns": [
            {"month": "Jan", "return": 2.1},
            {"month": "Feb", "return": 3.4},
            {"month": "Mar", "return": -1.2},
            {"month": "Apr", "return": 4.5},
            {"month": "May", "return": 5.4}
        ],
        "dailyReturns": [
            {"date": "2026-05-20", "return": 0.5},
            {"date": "2026-05-21", "return": -0.2},
            {"date": "2026-05-22", "return": 1.1},
            {"date": "2026-05-23", "return": 0.3},
            {"date": "2026-05-24", "return": 0.8}
        ]
    }

@router.get("/behavioral-insights", response_model=Dict[str, Any])
async def get_behavioral_insights():
    return {
        "score": 78,
        "strengths": ["Patience in winning trades", "Consistent position sizing"],
        "weaknesses": ["Revenge trading after losses", "Closing winners too early"],
        "recommendations": ["Use trailing stop losses", "Take a break after 3 consecutive losses"],
        "insights": [
            {"observation": "You tend to hold losing positions 40% longer than winning positions.", "category": "negative", "recommendation": "Set strict time-based stop losses."},
            {"observation": "Your win rate is highest on Tuesdays and Wednesdays.", "category": "positive"}
        ],
        "lastUpdated": "2026-05-24T10:00:00Z"
    }
