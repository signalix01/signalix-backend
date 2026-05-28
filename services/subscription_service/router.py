from fastapi import APIRouter
from typing import Dict, Any, List

router = APIRouter(prefix="/api/v1/subscription", tags=["subscription"])

@router.get("/current", response_model=Dict[str, Any])
async def get_current_subscription():
    return {
        "id": "sub-123",
        "userId": "user-456",
        "tier": "pro",
        "status": "active",
        "analysesLimit": 100,
        "analysesUsed": 45,
        "resetDate": "2026-06-01T00:00:00Z",
        "billingCycle": "monthly",
        "nextBillingDate": "2026-06-01T00:00:00Z",
        "amount": 29.99,
        "currency": "USD",
        "features": ["Advanced Analytics", "Options Strategies", "Real-time Alerts"],
        "createdAt": "2026-01-01T00:00:00Z",
        "updatedAt": "2026-05-01T00:00:00Z"
    }

@router.get("/usage", response_model=Dict[str, Any])
async def get_usage_statistics():
    return {
        "currentPeriod": {
            "startDate": "2026-05-01T00:00:00Z",
            "endDate": "2026-06-01T00:00:00Z",
            "analysesUsed": 45,
            "analysesLimit": 100,
            "percentageUsed": 45
        },
        "dailyUsage": [
            {"date": "2026-05-20", "count": 5},
            {"date": "2026-05-21", "count": 8},
            {"date": "2026-05-22", "count": 2}
        ],
        "byAnalysisType": [
            {"type": "Technical Analysis", "count": 20},
            {"type": "Fundamental Analysis", "count": 10},
            {"type": "Options Analysis", "count": 15}
        ]
    }

@router.post("/upgrade", response_model=Dict[str, Any])
async def upgrade_subscription(req: Dict[str, Any]):
    return {
        "success": True,
        "message": "Subscription upgraded successfully",
        "subscription": {
            "id": "sub-123",
            "tier": req.get("targetTier", "elite"),
            "status": "active"
        }
    }

@router.get("/invoices", response_model=List[Dict[str, Any]])
async def get_invoice_history():
    return [
        {
            "id": "inv-1",
            "date": "2026-05-01T00:00:00Z",
            "amount": 29.99,
            "currency": "USD",
            "status": "paid",
            "invoiceNumber": "INV-2026-05-01",
            "description": "Pro Tier Monthly Subscription"
        }
    ]

@router.post("/cancel", response_model=Dict[str, Any])
async def cancel_subscription(req: Dict[str, Any]):
    return {
        "success": True,
        "message": "Subscription cancelled successfully",
        "effectiveDate": "2026-06-01T00:00:00Z"
    }
