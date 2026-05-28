import asyncio
import os
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv

from orchestration.langgraph_pipeline import AnalysisPipelineV2
from shared.utils.user_context import UserContext
from services.market_data_service.angel_one_client import AngelOneClient

load_dotenv()

async def run_nifty_prediction():
    print("Initializing Angel One Client...")
    client = AngelOneClient()
    
    if not client.login():
        print("Failed to log in to Angel One. Check your .env credentials!")
        return
        
    print("Angel One Login Successful!")
    print("Fetching Nifty 50 Historical Data...")
    
    # Nifty 50 symbol token is "26000" in Angel One
    # Fetch last 30 days of daily data
    from_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d %H:%M")
    to_date = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    data = client.fetch_historical_data(symbol="26000", interval="ONE_DAY", from_date=from_date, to_date=to_date)
    
    if not data:
        print("Failed to fetch data.")
        return
        
    print(f"Fetched {len(data)} days of Nifty 50 data.")
    
    # Format the latest data for the AI Context
    latest = data[-1]
    prev = data[-2] if len(data) > 1 else latest
    
    # Angel One Format: [timestamp, open, high, low, close, volume]
    latest_close = latest[4]
    prev_close = prev[4]
    change = latest_close - prev_close
    change_pct = (change / prev_close) * 100
    
    market_data = {
        "Nifty50": {
            "price": latest_close,
            "previous_close": prev_close,
            "change": change,
            "change_pct": change_pct,
            "trend": "Bullish" if change_pct > 0 else "Bearish",
            "historical_last_5_days": [
                {"date": d[0], "open": d[1], "high": d[2], "low": d[3], "close": d[4], "volume": d[5]} 
                for d in data[-5:]
            ]
        }
    }
    
    # Provide the necessary state for the 21-agent pipeline
    print("Starting the AI Nifty 50 Prediction Pipeline...")
    
    # Build the context
    context = UserContext(
        user_id="demo_user",
        language="en",
        risk_tolerance=5,
        capital_inr=100000.0,
        trading_style="swing",
        tier="pro",
        experience_level="intermediate",
        analysis_depth="shallow",
        notifications_enabled=True,
        market_data=market_data
    )
    
    pipeline = AnalysisPipelineV2(user_context=context)
    
    print("\n⏳ Running all agents... (This might take a few minutes due to API rate limits)")
    
    try:
        result = await pipeline.run(
            instrument="NIFTY50",
            instrument_type="index",
            analysis_type="swing_trade",
            additional_context="Focus on tomorrow's market open based on the recent Angel One data."
        )
        
        print("\n" + "="*50)
        print("🎯 FINAL NIFTY 50 PREDICTION REPORT")
        print("="*50)
        print(json.dumps(result.get("final_decision", {}), indent=2))
            
        print("\n" + "="*50)
        print("📋 AGENTS EXECUTED:")
        for agent in result.get("agents_executed", []):
            print(f"- {agent}")
            
    except Exception as e:
        print(f"\n❌ Pipeline failed during execution: {str(e)}")

if __name__ == "__main__":
    asyncio.run(run_nifty_prediction())
