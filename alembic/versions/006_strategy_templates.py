"""Seed strategy templates

Revision ID: 006
Revises: 005
Create Date: 2025-01-15 12:00:00.000000

Requirements: 2.1, 2.2, 2.3
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid
import json
from datetime import datetime

# revision identifiers, used by Alembic.
revision = '006'
down_revision = '005'
branch_labels = None
depends_on = None


# Strategy template data
STRATEGY_TEMPLATES = [
    {
        "id": "11111111-1111-1111-1111-111111111111",
        "name": "Turtle Breakout (Richard Dennis)",
        "description": "20-day channel breakout with ATR-based position sizing and 10-day channel stop. The original Turtle Trading system that turned novices into millionaire traders.",
        "methodology_attribution": "Richard Dennis - The Turtle Trading System (1983)",
        "use_cases": "Trending markets, commodities, forex, crypto. Best in strong directional moves. Avoid in ranging/choppy markets.",
        "spec": {
            "strategy_id": "turtle_breakout_template",
            "user_id": "system",
            "name": "Turtle Breakout (Richard Dennis)",
            "description": "20-day channel breakout with ATR-based position sizing and 10-day channel stop",
            "asset_class": "equity",
            "instruments": ["NIFTY", "BANKNIFTY"],
            "entry_rules": [
                {
                    "direction": "LONG",
                    "condition_groups": [
                        {
                            "conditions": [
                                {
                                    "left_operand": "close",
                                    "operator": "crosses_above",
                                    "right_operand": "highest_high_20",
                                    "time_frame": "1D"
                                }
                            ],
                            "gate": "AND"
                        }
                    ],
                    "confirmation_candles": 1
                }
            ],
            "exit_rules": [
                {
                    "exit_type": "indicator",
                    "indicator_condition": {
                        "left_operand": "close",
                        "operator": "crosses_below",
                        "right_operand": "lowest_low_10",
                        "time_frame": "1D"
                    }
                }
            ],
            "position_sizing": {
                "method": "atr_based",
                "value": 1.0,
                "max_position_pct": 10.0,
                "max_concurrent_positions": 5
            },
            "market_filter": {
                "require_above_200ema": False,
                "min_adx": None,
                "max_vix": None,
                "require_positive_breadth": False
            },
            "indicators_config": {
                "highest_high_20": {"period": 20},
                "lowest_low_10": {"period": 10},
                "atr_14": {"period": 14}
            },
            "risk_per_trade_pct": 1.0,
            "max_daily_loss_pct": 2.0,
            "regime_awareness": True,
            "status": "draft",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
    },
    {
        "id": "22222222-2222-2222-2222-222222222222",
        "name": "Volatility Mean Reversion (Edward Thorp)",
        "description": "Sells options when IV Rank > 70 and buys back at 50% profit. Mathematical edge from IV premium decay. Thorp's quantitative approach to options trading.",
        "methodology_attribution": "Edward Thorp - Beat the Market (1967)",
        "use_cases": "Options trading, high IV environments, F&O markets. Best when IV is elevated. Requires options data and IV calculations.",
        "spec": {
            "strategy_id": "thorp_volatility_template",
            "user_id": "system",
            "name": "Volatility Mean Reversion (Edward Thorp)",
            "description": "Sells options when IV Rank > 70 and buys back at 50% profit",
            "asset_class": "fo",
            "instruments": ["NIFTY", "BANKNIFTY"],
            "entry_rules": [
                {
                    "direction": "SHORT",
                    "condition_groups": [
                        {
                            "conditions": [
                                {
                                    "left_operand": "iv_rank",
                                    "operator": ">",
                                    "right_operand": 70.0,
                                    "time_frame": "1D"
                                },
                                {
                                    "left_operand": "rsi_14",
                                    "operator": "between",
                                    "right_operand": "40,70",
                                    "time_frame": "1D"
                                }
                            ],
                            "gate": "AND"
                        }
                    ],
                    "confirmation_candles": 1
                }
            ],
            "exit_rules": [
                {
                    "exit_type": "target",
                    "target_pct": 50.0
                },
                {
                    "exit_type": "time",
                    "max_hold_candles": 21
                }
            ],
            "position_sizing": {
                "method": "kelly",
                "value": 0.5,
                "max_position_pct": 10.0,
                "max_concurrent_positions": 3
            },
            "market_filter": {
                "require_above_200ema": False,
                "min_adx": None,
                "max_vix": None,
                "require_positive_breadth": False
            },
            "indicators_config": {
                "rsi_14": {"period": 14},
                "iv_rank": {}
            },
            "risk_per_trade_pct": 2.0,
            "max_daily_loss_pct": 3.0,
            "regime_awareness": True,
            "status": "draft",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
    },
    {
        "id": "33333333-3333-3333-3333-333333333333",
        "name": "Macro Momentum (Paul Tudor Jones)",
        "description": "200 EMA trend filter + RSI momentum. Only trades in the direction of the macro trend. Jones' principle: macro regime awareness gates every entry.",
        "methodology_attribution": "Paul Tudor Jones - Macro Trend Following",
        "use_cases": "All markets, especially indices and large caps. Best in trending markets. Filters out counter-trend noise.",
        "spec": {
            "strategy_id": "jones_momentum_template",
            "user_id": "system",
            "name": "Macro Momentum (Paul Tudor Jones)",
            "description": "200 EMA trend filter + RSI momentum",
            "asset_class": "equity",
            "instruments": ["NIFTY", "BANKNIFTY", "RELIANCE", "TCS"],
            "entry_rules": [
                {
                    "direction": "LONG",
                    "condition_groups": [
                        {
                            "conditions": [
                                {
                                    "left_operand": "close",
                                    "operator": ">",
                                    "right_operand": "ema_200",
                                    "time_frame": "1D"
                                },
                                {
                                    "left_operand": "rsi_14",
                                    "operator": "crosses_above",
                                    "right_operand": 50.0,
                                    "time_frame": "1D"
                                }
                            ],
                            "gate": "AND"
                        }
                    ],
                    "confirmation_candles": 1
                }
            ],
            "exit_rules": [
                {
                    "exit_type": "indicator",
                    "indicator_condition": {
                        "left_operand": "rsi_14",
                        "operator": "<",
                        "right_operand": 40.0,
                        "time_frame": "1D"
                    }
                },
                {
                    "exit_type": "indicator",
                    "indicator_condition": {
                        "left_operand": "close",
                        "operator": "<",
                        "right_operand": "ema_200",
                        "time_frame": "1D"
                    }
                }
            ],
            "position_sizing": {
                "method": "pct_capital",
                "value": 5.0,
                "max_position_pct": 10.0,
                "max_concurrent_positions": 4
            },
            "market_filter": {
                "require_above_200ema": True,
                "min_adx": None,
                "max_vix": None,
                "require_positive_breadth": False
            },
            "indicators_config": {
                "ema_200": {"period": 200},
                "rsi_14": {"period": 14}
            },
            "risk_per_trade_pct": 1.0,
            "max_daily_loss_pct": 2.0,
            "regime_awareness": True,
            "status": "draft",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
    },
    {
        "id": "44444444-4444-4444-4444-444444444444",
        "name": "SuperTrend + EMA Cross",
        "description": "SuperTrend direction confirmation with 9/21 EMA crossover. Vivek Gadodia's systematic approach combining trend and momentum.",
        "methodology_attribution": "Vivek Gadodia (RBT Algo) - Systematic Trading",
        "use_cases": "Intraday and swing trading, all liquid instruments. Works well in trending intraday moves. Popular in Indian markets.",
        "spec": {
            "strategy_id": "supertrend_ema_template",
            "user_id": "system",
            "name": "SuperTrend + EMA Cross",
            "description": "SuperTrend direction confirmation with 9/21 EMA crossover",
            "asset_class": "equity",
            "instruments": ["NIFTY", "BANKNIFTY"],
            "entry_rules": [
                {
                    "direction": "LONG",
                    "condition_groups": [
                        {
                            "conditions": [
                                {
                                    "left_operand": "supertrend_direction",
                                    "operator": "==",
                                    "right_operand": 1.0,
                                    "time_frame": "15m"
                                },
                                {
                                    "left_operand": "ema_9",
                                    "operator": "crosses_above",
                                    "right_operand": "ema_21",
                                    "time_frame": "15m"
                                }
                            ],
                            "gate": "AND"
                        }
                    ],
                    "confirmation_candles": 1
                }
            ],
            "exit_rules": [
                {
                    "exit_type": "indicator",
                    "indicator_condition": {
                        "left_operand": "supertrend_direction",
                        "operator": "==",
                        "right_operand": -1.0,
                        "time_frame": "15m"
                    }
                },
                {
                    "exit_type": "indicator",
                    "indicator_condition": {
                        "left_operand": "ema_9",
                        "operator": "crosses_below",
                        "right_operand": "ema_21",
                        "time_frame": "15m"
                    }
                }
            ],
            "position_sizing": {
                "method": "pct_capital",
                "value": 3.0,
                "max_position_pct": 10.0,
                "max_concurrent_positions": 2
            },
            "market_filter": {
                "require_above_200ema": False,
                "min_adx": 20.0,
                "max_vix": None,
                "require_positive_breadth": False
            },
            "indicators_config": {
                "supertrend": {"period": 10, "multiplier": 3.0},
                "ema_9": {"period": 9},
                "ema_21": {"period": 21},
                "adx_14": {"period": 14}
            },
            "risk_per_trade_pct": 1.0,
            "max_daily_loss_pct": 2.0,
            "regime_awareness": True,
            "status": "draft",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
    },
    {
        "id": "55555555-5555-5555-5555-555555555555",
        "name": "BankNifty Iron Condor (PR Sundar)",
        "description": "Sell OTM CE and PE when IVR > 65 and time to expiry > 10 days. Classic option selling strategy for premium collection.",
        "methodology_attribution": "PR Sundar - Options Selling Strategies",
        "use_cases": "BankNifty weekly options, high IV environments. Best when market is range-bound. Requires active management.",
        "spec": {
            "strategy_id": "banknifty_iron_condor_template",
            "user_id": "system",
            "name": "BankNifty Iron Condor (PR Sundar)",
            "description": "Sell OTM CE and PE when IVR > 65 and time to expiry > 10 days",
            "asset_class": "fo",
            "instruments": ["BANKNIFTY"],
            "entry_rules": [
                {
                    "direction": "SHORT",
                    "condition_groups": [
                        {
                            "conditions": [
                                {
                                    "left_operand": "iv_rank",
                                    "operator": ">",
                                    "right_operand": 65.0,
                                    "time_frame": "1D"
                                },
                                {
                                    "left_operand": "days_to_expiry",
                                    "operator": ">",
                                    "right_operand": 10.0,
                                    "time_frame": "1D"
                                },
                                {
                                    "left_operand": "pcr",
                                    "operator": "between",
                                    "right_operand": "0.8,1.4",
                                    "time_frame": "1D"
                                }
                            ],
                            "gate": "AND"
                        }
                    ],
                    "confirmation_candles": 1
                }
            ],
            "exit_rules": [
                {
                    "exit_type": "target",
                    "target_pct": 50.0
                },
                {
                    "exit_type": "stop_loss",
                    "stop_loss_pct": 100.0
                },
                {
                    "exit_type": "indicator",
                    "indicator_condition": {
                        "left_operand": "days_to_expiry",
                        "operator": "<",
                        "right_operand": 3.0,
                        "time_frame": "1D"
                    }
                }
            ],
            "position_sizing": {
                "method": "fixed_capital",
                "value": 50000.0,
                "max_position_pct": 10.0,
                "max_concurrent_positions": 2
            },
            "market_filter": {
                "require_above_200ema": False,
                "min_adx": None,
                "max_vix": 25.0,
                "require_positive_breadth": False
            },
            "indicators_config": {
                "iv_rank": {},
                "pcr": {},
                "days_to_expiry": {}
            },
            "risk_per_trade_pct": 2.0,
            "max_daily_loss_pct": 3.0,
            "regime_awareness": True,
            "status": "draft",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
    },
    {
        "id": "66666666-6666-6666-6666-666666666666",
        "name": "Concentrated Trend (Stanley Druckenmiller)",
        "description": "Single concentrated bet in strongest trending market. ADX > 30, high conviction only. Druckenmiller's approach: big bets when you're right.",
        "methodology_attribution": "Stanley Druckenmiller - Concentrated Position Sizing",
        "use_cases": "Strong trending markets, breakouts, high conviction setups. Not for beginners. Requires strong risk management.",
        "spec": {
            "strategy_id": "druckenmiller_trend_template",
            "user_id": "system",
            "name": "Concentrated Trend (Stanley Druckenmiller)",
            "description": "Single concentrated bet in strongest trending market",
            "asset_class": "equity",
            "instruments": ["NIFTY", "BANKNIFTY"],
            "entry_rules": [
                {
                    "direction": "LONG",
                    "condition_groups": [
                        {
                            "conditions": [
                                {
                                    "left_operand": "adx_14",
                                    "operator": ">",
                                    "right_operand": 30.0,
                                    "time_frame": "1D"
                                },
                                {
                                    "left_operand": "close",
                                    "operator": "crosses_above",
                                    "right_operand": "highest_high_52",
                                    "time_frame": "1D"
                                },
                                {
                                    "left_operand": "volume",
                                    "operator": ">",
                                    "right_operand": "volume_ma_20_x_1.5",
                                    "time_frame": "1D"
                                }
                            ],
                            "gate": "AND"
                        }
                    ],
                    "confirmation_candles": 2
                }
            ],
            "exit_rules": [
                {
                    "exit_type": "trailing_sl",
                    "trailing_sl_pct": 8.0
                },
                {
                    "exit_type": "indicator",
                    "indicator_condition": {
                        "left_operand": "adx_14",
                        "operator": "<",
                        "right_operand": 25.0,
                        "time_frame": "1D"
                    }
                }
            ],
            "position_sizing": {
                "method": "pct_capital",
                "value": 15.0,
                "max_position_pct": 10.0,
                "max_concurrent_positions": 1
            },
            "market_filter": {
                "require_above_200ema": True,
                "min_adx": 30.0,
                "max_vix": None,
                "require_positive_breadth": False
            },
            "indicators_config": {
                "adx_14": {"period": 14},
                "highest_high_52": {"period": 252},
                "volume_ma_20": {"period": 20}
            },
            "risk_per_trade_pct": 2.0,
            "max_daily_loss_pct": 3.0,
            "regime_awareness": True,
            "status": "draft",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
    },
    {
        "id": "77777777-7777-7777-7777-777777777777",
        "name": "Value Momentum (Rakesh Jhunjhunwala)",
        "description": "Combines fundamental value screening with technical momentum. Buy quality stocks showing strong momentum. Jhunjhunwala's approach to long-term wealth creation.",
        "methodology_attribution": "Rakesh Jhunjhunwala - Value + Momentum Investing",
        "use_cases": "Long-term equity investing, quality stocks, swing trading. Best for stocks with strong fundamentals breaking out.",
        "spec": {
            "strategy_id": "value_momentum_template",
            "user_id": "system",
            "name": "Value Momentum (Rakesh Jhunjhunwala)",
            "description": "Combines fundamental value screening with technical momentum",
            "asset_class": "equity",
            "instruments": ["RELIANCE", "TCS", "HDFCBANK", "INFY"],
            "entry_rules": [
                {
                    "direction": "LONG",
                    "condition_groups": [
                        {
                            "conditions": [
                                {
                                    "left_operand": "close",
                                    "operator": ">",
                                    "right_operand": "ema_50",
                                    "time_frame": "1D"
                                },
                                {
                                    "left_operand": "rsi_14",
                                    "operator": ">",
                                    "right_operand": 55.0,
                                    "time_frame": "1D"
                                },
                                {
                                    "left_operand": "volume",
                                    "operator": ">",
                                    "right_operand": "volume_ma_20",
                                    "time_frame": "1D"
                                }
                            ],
                            "gate": "AND"
                        }
                    ],
                    "confirmation_candles": 2
                }
            ],
            "exit_rules": [
                {
                    "exit_type": "trailing_sl",
                    "trailing_sl_pct": 10.0
                },
                {
                    "exit_type": "indicator",
                    "indicator_condition": {
                        "left_operand": "close",
                        "operator": "<",
                        "right_operand": "ema_50",
                        "time_frame": "1D"
                    }
                }
            ],
            "position_sizing": {
                "method": "pct_capital",
                "value": 8.0,
                "max_position_pct": 10.0,
                "max_concurrent_positions": 3
            },
            "market_filter": {
                "require_above_200ema": True,
                "min_adx": None,
                "max_vix": None,
                "require_positive_breadth": True
            },
            "indicators_config": {
                "ema_50": {"period": 50},
                "ema_200": {"period": 200},
                "rsi_14": {"period": 14},
                "volume_ma_20": {"period": 20}
            },
            "risk_per_trade_pct": 1.5,
            "max_daily_loss_pct": 2.5,
            "regime_awareness": True,
            "status": "draft",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
    },
    {
        "id": "88888888-8888-8888-8888-888888888888",
        "name": "Crypto Accumulation",
        "description": "DCA strategy with momentum confirmation for crypto assets. Accumulate on dips when RSI < 40 and price > 200 EMA. Long-term crypto wealth building.",
        "methodology_attribution": "Dollar Cost Averaging + Momentum Confirmation",
        "use_cases": "Crypto markets (BTC, ETH), long-term accumulation. Best in bull markets with corrections. Requires patience.",
        "spec": {
            "strategy_id": "crypto_accumulation_template",
            "user_id": "system",
            "name": "Crypto Accumulation",
            "description": "DCA strategy with momentum confirmation for crypto assets",
            "asset_class": "crypto",
            "instruments": ["BTCUSDT", "ETHUSDT"],
            "entry_rules": [
                {
                    "direction": "LONG",
                    "condition_groups": [
                        {
                            "conditions": [
                                {
                                    "left_operand": "rsi_14",
                                    "operator": "<",
                                    "right_operand": 40.0,
                                    "time_frame": "1D"
                                },
                                {
                                    "left_operand": "close",
                                    "operator": ">",
                                    "right_operand": "ema_200",
                                    "time_frame": "1D"
                                }
                            ],
                            "gate": "AND"
                        }
                    ],
                    "confirmation_candles": 1
                }
            ],
            "exit_rules": [
                {
                    "exit_type": "target",
                    "target_pct": 100.0
                },
                {
                    "exit_type": "indicator",
                    "indicator_condition": {
                        "left_operand": "rsi_14",
                        "operator": ">",
                        "right_operand": 80.0,
                        "time_frame": "1D"
                    }
                }
            ],
            "position_sizing": {
                "method": "fixed_capital",
                "value": 10000.0,
                "max_position_pct": 10.0,
                "max_concurrent_positions": 2
            },
            "market_filter": {
                "require_above_200ema": True,
                "min_adx": None,
                "max_vix": None,
                "require_positive_breadth": False
            },
            "indicators_config": {
                "rsi_14": {"period": 14},
                "ema_200": {"period": 200}
            },
            "risk_per_trade_pct": 2.0,
            "max_daily_loss_pct": 3.0,
            "regime_awareness": True,
            "status": "draft",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
    }
]


def upgrade() -> None:
    """Seed strategy templates into the strategies table"""
    
    # Create connection
    connection = op.get_bind()
    
    # Insert each template
    for template in STRATEGY_TEMPLATES:
        spec_json = json.dumps(template["spec"])
        connection.execute(
            sa.text("""
                INSERT INTO strategies (id, user_id, template_id, name, description, spec, status, created_at, updated_at)
                VALUES (:id, :user_id, NULL, :name, :description, :spec::jsonb, 'draft', NOW(), NOW())
            """),
            {
                "id": template["id"],
                "user_id": "00000000-0000-0000-0000-000000000000",  # System user
                "name": template["name"],
                "description": f"{template['description']}\n\nMethodology: {template['methodology_attribution']}\n\nUse Cases: {template['use_cases']}",
                "spec": spec_json
            }
        )
    
    print(f"✓ Seeded {len(STRATEGY_TEMPLATES)} strategy templates")
    print("  - Turtle Breakout (Richard Dennis)")
    print("  - Volatility Mean Reversion (Edward Thorp)")
    print("  - Macro Momentum (Paul Tudor Jones)")
    print("  - SuperTrend + EMA Cross")
    print("  - BankNifty Iron Condor (PR Sundar)")
    print("  - Concentrated Trend (Stanley Druckenmiller)")
    print("  - Value Momentum (Rakesh Jhunjhunwala)")
    print("  - Crypto Accumulation")


def downgrade() -> None:
    """Remove strategy templates"""
    
    connection = op.get_bind()
    
    # Delete all templates by their IDs
    template_ids = [t["id"] for t in STRATEGY_TEMPLATES]
    connection.execute(
        sa.text("""
            DELETE FROM strategies WHERE id = ANY(:ids)
        """),
        {"ids": template_ids}
    )
    
    print(f"✓ Removed {len(STRATEGY_TEMPLATES)} strategy templates")
