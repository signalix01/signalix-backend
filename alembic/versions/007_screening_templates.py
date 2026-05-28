"""Seed screening templates

Revision ID: 007
Revises: 006
Create Date: 2025-01-15 14:00:00.000000

Requirements: 10.1, 10.2, 10.3, 10.4
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid
import json
from datetime import datetime

# revision identifiers, used by Alembic.
revision = '007'
down_revision = '006'
branch_labels = None
depends_on = None


# Screening template data
SCREENING_TEMPLATES = [
    {
        "id": "a1111111-1111-1111-1111-111111111111",
        "name": "Turtle Breakout Scanner",
        "description": "Find instruments breaking out to new 20-day highs with strong volume. Based on Richard Dennis' Turtle Trading methodology.",
        "methodology": "Richard Dennis - Turtle Trading System",
        "use_cases": "All markets, trending instruments. Best in strong directional moves.",
        "criteria_spec": {
            "name": "Turtle Breakout Scanner",
            "description": "Find instruments breaking out to new 20-day highs with strong volume",
            "asset_class": ["equity", "fo", "crypto", "forex", "commodity"],
            "price_breakout_days": 20,
            "min_volume_ratio": 1.5,
            "min_adx": 25.0,
            "require_above_ema": 200
        }
    },
    {
        "id": "a2222222-2222-2222-2222-222222222222",
        "name": "Oversold Reversal Scanner",
        "description": "Find oversold instruments (RSI < 30) above 200 EMA showing reversal signals. Mean reversion strategy for quality instruments.",
        "methodology": "Mean Reversion + Trend Filter",
        "use_cases": "Equity markets, quality stocks. Best in bull markets with corrections.",
        "criteria_spec": {
            "name": "Oversold Reversal Scanner",
            "description": "Find oversold instruments above 200 EMA showing reversal signals",
            "asset_class": ["equity"],
            "min_rsi": 20.0,
            "max_rsi": 35.0,
            "require_above_ema": 200,
            "min_volume_ratio": 1.3,
            "min_market_cap_cr": 1000.0,
            "min_roe_pct": 12.0
        }
    },
    {
        "id": "a3333333-3333-3333-3333-333333333333",
        "name": "F&O High IV Seller",
        "description": "Find F&O instruments with elevated IV Rank (> 70) suitable for option selling. Edward Thorp's volatility premium capture approach.",
        "methodology": "Edward Thorp - Volatility Premium Capture",
        "use_cases": "F&O markets, option selling strategies. Best when IV is elevated.",
        "criteria_spec": {
            "name": "F&O High IV Seller",
            "description": "Find F&O instruments with elevated IV Rank suitable for option selling",
            "asset_class": ["fo"],
            "min_iv_rank": 70.0,
            "min_pcr": 0.8,
            "max_pcr": 1.5,
            "min_rsi": 40.0,
            "max_rsi": 70.0
        }
    },
    {
        "id": "a4444444-4444-4444-4444-444444444444",
        "name": "Strong Trend Momentum Scanner",
        "description": "Find instruments in strong uptrends (ADX > 30, price > 200 EMA) with momentum confirmation. Paul Tudor Jones' macro trend approach.",
        "methodology": "Paul Tudor Jones - Macro Trend Following",
        "use_cases": "All markets, trending instruments. Best in strong bull markets.",
        "criteria_spec": {
            "name": "Strong Trend Momentum Scanner",
            "description": "Find instruments in strong uptrends with momentum confirmation",
            "asset_class": ["equity", "fo", "crypto", "forex"],
            "require_above_ema": 200,
            "min_adx": 30.0,
            "min_rsi": 55.0,
            "max_rsi": 80.0,
            "min_volume_ratio": 1.2
        }
    },
    {
        "id": "a5555555-5555-5555-5555-555555555555",
        "name": "Crypto Accumulation Scanner",
        "description": "Find crypto assets in accumulation zones (RSI < 40, price > 200 EMA). Long-term wealth building strategy.",
        "methodology": "Dollar Cost Averaging + Momentum Confirmation",
        "use_cases": "Crypto markets (BTC, ETH, altcoins). Best in bull markets with corrections.",
        "criteria_spec": {
            "name": "Crypto Accumulation Scanner",
            "description": "Find crypto assets in accumulation zones",
            "asset_class": ["crypto"],
            "min_rsi": 25.0,
            "max_rsi": 40.0,
            "require_above_ema": 200,
            "min_fear_greed": 20
        }
    },
    {
        "id": "a6666666-6666-6666-6666-666666666666",
        "name": "Forex Carry Opportunity Scanner",
        "description": "Find forex pairs with favorable carry trade conditions. Interest rate differential opportunities.",
        "methodology": "Carry Trade Strategy",
        "use_cases": "Forex markets, major and minor pairs. Best in stable trending markets.",
        "criteria_spec": {
            "name": "Forex Carry Opportunity Scanner",
            "description": "Find forex pairs with favorable carry trade conditions",
            "asset_class": ["forex"],
            "require_above_ema": 200,
            "min_adx": 20.0,
            "min_rsi": 45.0,
            "max_rsi": 65.0
        }
    },
    {
        "id": "a7777777-7777-7777-7777-777777777777",
        "name": "Earnings Momentum Scanner",
        "description": "Find NSE equities with strong fundamentals and technical momentum. Rakesh Jhunjhunwala's value + momentum approach.",
        "methodology": "Rakesh Jhunjhunwala - Value + Momentum",
        "use_cases": "NSE equities, quality stocks. Best for swing and positional trading.",
        "criteria_spec": {
            "name": "Earnings Momentum Scanner",
            "description": "Find NSE equities with strong fundamentals and technical momentum",
            "asset_class": ["equity"],
            "min_market_cap_cr": 5000.0,
            "max_pe_ratio": 35.0,
            "min_roe_pct": 15.0,
            "min_revenue_growth_pct": 10.0,
            "min_promoter_holding_pct": 50.0,
            "require_above_ema": 50,
            "min_rsi": 55.0,
            "min_volume_ratio": 1.2
        }
    },
    {
        "id": "a8888888-8888-8888-8888-888888888888",
        "name": "Fundamental Value Scanner",
        "description": "Find undervalued quality stocks with strong fundamentals. Classic value investing approach.",
        "methodology": "Benjamin Graham - Value Investing",
        "use_cases": "Equity markets, long-term investing. Best for patient investors.",
        "criteria_spec": {
            "name": "Fundamental Value Scanner",
            "description": "Find undervalued quality stocks with strong fundamentals",
            "asset_class": ["equity"],
            "min_market_cap_cr": 2000.0,
            "max_pe_ratio": 20.0,
            "min_roe_pct": 18.0,
            "min_revenue_growth_pct": 12.0,
            "min_promoter_holding_pct": 55.0,
            "require_above_ema": 200
        }
    }
]


def upgrade() -> None:
    """Seed screening templates into the screening_criteria table"""
    
    # Create connection
    connection = op.get_bind()
    
    # Insert each template
    for template in SCREENING_TEMPLATES:
        criteria_json = json.dumps(template["criteria_spec"])
        connection.execute(
            sa.text("""
                INSERT INTO screening_criteria (id, user_id, template_id, name, description, criteria_spec, 
                                                schedule_enabled, schedule_cron, is_active, created_at, updated_at)
                VALUES (:id, :user_id, NULL, :name, :description, :criteria_spec::jsonb, 
                        false, NULL, true, NOW(), NOW())
            """),
            {
                "id": template["id"],
                "user_id": "00000000-0000-0000-0000-000000000000",  # System user
                "name": template["name"],
                "description": f"{template['description']}\n\nMethodology: {template['methodology']}\n\nUse Cases: {template['use_cases']}",
                "criteria_spec": criteria_json
            }
        )
    
    print(f"✓ Seeded {len(SCREENING_TEMPLATES)} screening templates")
    print("  - Turtle Breakout Scanner")
    print("  - Oversold Reversal Scanner")
    print("  - F&O High IV Seller")
    print("  - Strong Trend Momentum Scanner")
    print("  - Crypto Accumulation Scanner")
    print("  - Forex Carry Opportunity Scanner")
    print("  - Earnings Momentum Scanner")
    print("  - Fundamental Value Scanner")


def downgrade() -> None:
    """Remove screening templates"""
    
    connection = op.get_bind()
    
    # Delete all templates by their IDs
    template_ids = [t["id"] for t in SCREENING_TEMPLATES]
    connection.execute(
        sa.text("""
            DELETE FROM screening_criteria WHERE id = ANY(:ids)
        """),
        {"ids": template_ids}
    )
    
    print(f"✓ Removed {len(SCREENING_TEMPLATES)} screening templates")
