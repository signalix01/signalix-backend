# Migration 006: Strategy Templates Seed Data

**Revision ID**: 006  
**Revises**: 005  
**Requirements**: 2.1, 2.2, 2.3

## Overview

This migration seeds the database with 8 pre-built strategy templates inspired by legendary traders. Each template is a complete, production-ready `StrategySpec` JSON that users can clone and customize.

## Strategy Templates

### 1. Turtle Breakout (Richard Dennis)
- **Methodology**: 20-day channel breakout with ATR-based position sizing
- **Asset Class**: Equity
- **Entry**: Price crosses above 20-day high
- **Exit**: Price crosses below 10-day low
- **Position Sizing**: ATR-based (1% risk per trade)
- **Use Cases**: Trending markets, commodities, forex, crypto

### 2. Volatility Mean Reversion (Edward Thorp)
- **Methodology**: Options selling when IV Rank > 70
- **Asset Class**: F&O (Futures & Options)
- **Entry**: IV Rank > 70 AND RSI between 40-70
- **Exit**: 50% profit target OR 21 days held
- **Position Sizing**: Kelly Criterion
- **Use Cases**: High IV environments, options trading

### 3. Macro Momentum (Paul Tudor Jones)
- **Methodology**: 200 EMA trend filter + RSI momentum
- **Asset Class**: Equity
- **Entry**: Price > 200 EMA AND RSI crosses above 50
- **Exit**: RSI < 40 OR price < 200 EMA
- **Position Sizing**: 5% of capital per trade
- **Use Cases**: All markets, especially indices and large caps

### 4. SuperTrend + EMA Cross
- **Methodology**: SuperTrend direction + 9/21 EMA crossover
- **Asset Class**: Equity
- **Entry**: SuperTrend bullish AND EMA 9 crosses above EMA 21
- **Exit**: SuperTrend bearish OR EMA 9 crosses below EMA 21
- **Position Sizing**: 3% of capital per trade
- **Use Cases**: Intraday and swing trading, liquid instruments

### 5. BankNifty Iron Condor (PR Sundar)
- **Methodology**: Sell OTM options when IV elevated
- **Asset Class**: F&O
- **Entry**: IV Rank > 65, DTE > 10 days, PCR between 0.8-1.4
- **Exit**: 50% profit, 100% loss, or DTE < 3 days
- **Position Sizing**: Fixed capital (Rs 50,000)
- **Use Cases**: BankNifty weekly options, range-bound markets

### 6. Concentrated Trend (Stanley Druckenmiller)
- **Methodology**: Single concentrated bet in strong trends
- **Asset Class**: Equity
- **Entry**: ADX > 30, 52-week high break, volume > 1.5x average
- **Exit**: 8% trailing stop OR ADX < 25
- **Position Sizing**: 15% of capital (concentrated)
- **Use Cases**: Strong trending markets, high conviction setups

### 7. Value Momentum (Rakesh Jhunjhunwala)
- **Methodology**: Fundamental value + technical momentum
- **Asset Class**: Equity
- **Entry**: Price > 50 EMA, RSI > 55, volume > average
- **Exit**: 10% trailing stop OR price < 50 EMA
- **Position Sizing**: 8% of capital per trade
- **Use Cases**: Long-term equity investing, quality stocks

### 8. Crypto Accumulation
- **Methodology**: DCA with momentum confirmation
- **Asset Class**: Crypto
- **Entry**: RSI < 40 AND price > 200 EMA
- **Exit**: 100% profit target OR RSI > 80
- **Position Sizing**: Fixed capital (Rs 10,000)
- **Use Cases**: BTC/ETH accumulation, bull market corrections

## Database Schema

Templates are inserted into the `strategies` table with:
- **id**: UUID (predefined for each template)
- **user_id**: `00000000-0000-0000-0000-000000000000` (system user)
- **template_id**: NULL (these ARE the templates)
- **name**: Template name with attribution
- **description**: Full description including methodology and use cases
- **spec**: Complete StrategySpec JSON (JSONB column)
- **status**: `draft` (users clone and customize)

## Validation

All templates pass StrategySpec Pydantic validation:
- ✓ At least 1 entry rule
- ✓ At least 1 exit rule
- ✓ Valid position sizing configuration
- ✓ Max position cap ≤ 10%
- ✓ Market filter configuration
- ✓ Indicators configuration

Run validation test:
```bash
python test_strategy_templates_validation.py
```

## Usage

Users can clone templates via API:
```bash
POST /api/v1/algo/templates/{template_id}/clone
```

This creates a new strategy in the user's account with `status=draft` that they can customize.

## Requirements Validated

- **2.1**: System provides 8 pre-built strategy templates
- **2.2**: Each template includes name, description, methodology attribution, use cases, and default StrategySpec
- **2.3**: Templates include all 8 specified methodologies (Turtle, Thorp, Jones, SuperTrend, Iron Condor, Druckenmiller, Value Momentum, Crypto)

## Migration Commands

```bash
# Apply migration
alembic upgrade head

# Rollback migration
alembic downgrade -1
```

## Notes

- Templates are immutable (users clone, not modify originals)
- Each template has a fixed UUID for consistent referencing
- All templates use realistic parameters based on historical performance
- Templates cover all major asset classes: equity, F&O, crypto
- Position sizing methods vary: ATR-based, Kelly, percentage, fixed capital
