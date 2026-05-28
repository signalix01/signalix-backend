"""
Seed Analysis Types
Populates the analysis_types table with 10 predefined analysis configurations
"""

import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.config.settings import settings
from shared.database.models import AnalysisType


# Analysis type configurations
ANALYSIS_TYPES = [
    {
        "type_code": "swing_trade",
        "display_name": "Swing Trade",
        "description": "3-7 day swing trading opportunities with technical breakouts and momentum",
        "primary_agents": ["fundamentals", "technical", "macro", "sentiment", "risk_manager", "final_trader"],
        "output_format": "standard",
        "typical_holding_period": "3-7 days",
        "risk_profile": "medium",
        "recommended_for": ["swing", "positional"]
    },
    {
        "type_code": "intraday_scalp",
        "display_name": "Intraday Scalp",
        "description": "Intraday momentum and scalping opportunities with tight stops",
        "primary_agents": ["technical", "sentiment", "liquidity", "volatility", "risk_manager", "final_trader"],
        "output_format": "concise",
        "typical_holding_period": "intraday",
        "risk_profile": "high",
        "recommended_for": ["intraday"]
    },
    {
        "type_code": "options_strategy",
        "display_name": "Options Strategy",
        "description": "Options-based strategies with Greeks analysis and volatility assessment",
        "primary_agents": ["fundamentals", "technical", "volatility", "options", "risk_manager", "final_trader"],
        "output_format": "detailed",
        "typical_holding_period": "1-4 weeks",
        "risk_profile": "high",
        "recommended_for": ["swing", "positional"]
    },
    {
        "type_code": "earnings_play",
        "display_name": "Earnings Play",
        "description": "Pre/post earnings trading opportunities with earnings analysis",
        "primary_agents": ["fundamentals", "earnings", "technical", "sentiment", "volatility", "risk_manager", "final_trader"],
        "output_format": "detailed",
        "typical_holding_period": "1-5 days",
        "risk_profile": "high",
        "recommended_for": ["swing"]
    },
    {
        "type_code": "macro_position",
        "display_name": "Macro Position",
        "description": "Macro-driven positional trades based on economic themes",
        "primary_agents": ["fundamentals", "macro", "sector_rotation", "technical", "risk_manager", "final_trader"],
        "output_format": "detailed",
        "typical_holding_period": "2-8 weeks",
        "risk_profile": "medium",
        "recommended_for": ["positional", "long_term"]
    },
    {
        "type_code": "portfolio_hedge",
        "display_name": "Portfolio Hedge",
        "description": "Hedging strategies to protect portfolio from downside risk",
        "primary_agents": ["macro", "volatility", "correlation", "options", "risk_manager", "final_trader"],
        "output_format": "detailed",
        "typical_holding_period": "1-3 months",
        "risk_profile": "low",
        "recommended_for": ["positional", "long_term"]
    },
    {
        "type_code": "technical_breakout",
        "display_name": "Technical Breakout",
        "description": "Pure technical breakout trades with chart patterns and momentum",
        "primary_agents": ["technical", "sentiment", "liquidity", "risk_manager", "final_trader"],
        "output_format": "concise",
        "typical_holding_period": "3-10 days",
        "risk_profile": "medium",
        "recommended_for": ["swing"]
    },
    {
        "type_code": "mean_reversion",
        "display_name": "Mean Reversion",
        "description": "Mean reversion trades on oversold/overbought conditions",
        "primary_agents": ["technical", "fundamentals", "sentiment", "volatility", "risk_manager", "final_trader"],
        "output_format": "standard",
        "typical_holding_period": "5-15 days",
        "risk_profile": "medium",
        "recommended_for": ["swing", "positional"]
    },
    {
        "type_code": "crypto_directional",
        "display_name": "Crypto Directional",
        "description": "Directional crypto trades with technical and sentiment analysis",
        "primary_agents": ["technical", "sentiment", "macro", "volatility", "risk_manager", "final_trader"],
        "output_format": "standard",
        "typical_holding_period": "1-7 days",
        "risk_profile": "very_high",
        "recommended_for": ["intraday", "swing"]
    },
    {
        "type_code": "forex_carry",
        "display_name": "Forex Carry",
        "description": "Forex carry trades based on interest rate differentials",
        "primary_agents": ["macro", "technical", "sentiment", "risk_manager", "final_trader"],
        "output_format": "detailed",
        "typical_holding_period": "1-3 months",
        "risk_profile": "medium",
        "recommended_for": ["positional", "long_term"]
    }
]


async def seed_analysis_types():
    """Seed analysis types into database"""
    # Create async engine
    engine = create_async_engine(settings.DATABASE_URL, echo=True)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        try:
            print("🌱 Seeding analysis types...")
            
            for config in ANALYSIS_TYPES:
                # Check if already exists
                from sqlalchemy import select
                result = await session.execute(
                    select(AnalysisType).where(AnalysisType.type_code == config["type_code"])
                )
                existing = result.scalar_one_or_none()
                
                if existing:
                    print(f"  ⏭️  Skipping {config['type_code']} (already exists)")
                    continue
                
                # Create new analysis type
                analysis_type = AnalysisType(
                    type_code=config["type_code"],
                    display_name=config["display_name"],
                    description=config["description"],
                    primary_agents=config["primary_agents"],
                    secondary_agents=config.get("secondary_agents"),
                    skipped_agents=config.get("skipped_agents"),
                    output_format=config["output_format"],
                    extra_context={
                        "typical_holding_period": config.get("typical_holding_period"),
                        "risk_profile": config.get("risk_profile"),
                        "recommended_for": config.get("recommended_for")
                    }
                )
                
                session.add(analysis_type)
                print(f"  ✅ Created {config['type_code']}")
            
            await session.commit()
            print("\n✅ Analysis types seeded successfully!")
            
        except Exception as e:
            print(f"\n❌ Error seeding analysis types: {e}")
            await session.rollback()
            raise
        finally:
            await engine.dispose()


if __name__ == "__main__":
    print("=" * 60)
    print("SignalixAI AI - Seed Analysis Types")
    print("=" * 60)
    print()
    
    asyncio.run(seed_analysis_types())
