"""
Historical Validation Agent
Uses BacktestService to validate signal quality based on historical performance
"""

from typing import Dict, Optional
import httpx
from datetime import datetime, timedelta

class HistoricalValidationAgent:
    """
    Historical Validation - Checks performance of similar signals in the past
    """
    
    def __init__(self, base_url: str = "http://localhost:8008"):
        self.base_url = base_url
    
    async def validate(
        self,
        instrument: str,
        analysis_type: str,
        current_user_id: str
    ) -> Dict:
        """
        Check historical performance for similar signals
        """
        try:
            # Calculate date range (last 90 days)
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=90)
            
            async with httpx.AsyncClient() as client:
                # In production, this would call the actual backtest service
                # For now, we simulate the logic or return mock data if service is not running
                response = await client.get(
                    f"{self.base_url}/api/v1/backtest/strategy-comparison",
                    params={
                        "instrument": instrument,
                        "start_date": start_date.isoformat(),
                        "end_date": end_date.isoformat()
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    strategy_data = data.get("strategy_comparison", {}).get(analysis_type, {})
                    
                    return {
                        "historical_win_rate": strategy_data.get("win_rate", 0.0),
                        "historical_avg_return": strategy_data.get("avg_return_pct", 0.0),
                        "total_historical_signals": strategy_data.get("total_signals", 0),
                        "confidence_boost": 0.1 if strategy_data.get("win_rate", 0) > 0.6 else 0.0
                    }
                else:
                    return {
                        "historical_win_rate": 0.5,
                        "historical_avg_return": 0.0,
                        "total_historical_signals": 0,
                        "confidence_boost": 0.0
                    }
        except Exception as e:
            return {
                "error": str(e),
                "historical_win_rate": 0.5,
                "confidence_boost": 0.0
            }
