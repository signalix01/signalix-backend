# TA-Lib Scoring Layer

## Overview

The TA-Lib Scoring Layer is the second layer of the AI Screening Engine pipeline. It computes composite scores for instruments that passed the SQL pre-filter by analyzing technical indicators from the latest 60 bars of OHLCV data.

**Requirements**: 9.2

**Performance Target**: < 10 seconds for 200 instruments

## Architecture

```
SQL Pre-Filter (200 symbols)
         ↓
    TA Scorer
         ↓
Scored Instruments (sorted by composite score)
         ↓
    AI Scorer (top 50)
```

## Composite Score Formula

The composite score is a weighted combination of four component scores:

```
composite_score = (rsi_score × 0.30) + 
                  (volume_score × 0.30) + 
                  (trend_score × 0.25) + 
                  (momentum_score × 0.15)
```

### Component Scores

#### 1. RSI Score (30% weight)

Measures RSI position relative to criteria bounds or standard interpretation:

- **With criteria bounds**: Scores based on how well RSI fits within specified min/max
  - Within bounds: 70-100 (centered = 100)
  - Outside bounds: 40
  
- **Without criteria bounds**: Standard RSI interpretation
  - RSI ≤ 30 (oversold): 70-100 (lower = higher score)
  - RSI ≥ 70 (overbought): 80-100 (higher = higher score)
  - RSI 40-60 (neutral): 60
  - RSI 30-40, 60-70 (transitional): 50-60

#### 2. Volume Score (30% weight)

Measures volume relative to 20-day average:

```
volume_ratio = current_volume / volume_ma_20

Score mapping:
- Ratio ≥ 2.0: 100
- Ratio 1.0-2.0: 50-100 (linear)
- Ratio 0-1.0: 0-50 (linear)
```

#### 3. Trend Score (25% weight)

Measures EMA stack alignment (bullish = descending order):

Perfect bullish stack: `close > ema_5 > ema_9 > ema_21 > ema_50 > ema_200`

```
Score = (aligned_pairs / total_pairs) × 100

Examples:
- 5/5 aligned: 100
- 3/5 aligned: 60
- 0/5 aligned: 0
```

#### 4. Momentum Score (15% weight)

Measures trend strength using ADX:

```
Score = (ADX / 50) × 100

Capped at 0-100:
- ADX 50+: 100
- ADX 25: 50
- ADX 0: 0
```

## Data Requirements

### Input
- List of symbols (from SQL pre-filter)
- ScreeningCriteria object

### Database Query
Fetches latest 60 bars from `ohlcv_1d` table with columns:
- OHLCV: open, high, low, close, volume
- Indicators: rsi_14, ema_5, ema_9, ema_21, ema_50, ema_200, adx_14, atr_14, volume_ma_20
- Metadata: symbol, timestamp, exchange, asset_class

### Minimum Data Requirements
- At least 10 bars of data
- Non-null values for: close, rsi_14

## Output

### ScreenedInstrument Object

Each scored instrument includes:

```python
{
    "symbol": "RELIANCE",
    "asset_class": "equity",
    "exchange": "NSE",
    "current_price": 2450.50,
    "score": 85.5,              # Composite score (0-100)
    "technical_score": 82.0,    # Average of RSI, trend, momentum scores
    "fundamental_score": 0.0,   # Not computed in TA layer
    "momentum_score": 78.0,     # ADX-based score
    "volume_score": 92.0,       # Volume ratio score
    "ai_signal": null,          # Computed in AI layer
    "ai_confidence": null,      # Computed in AI layer
    "reasons": [
        "RSI at 28.5 within target range 20-35",
        "High volume: 2.3x average",
        "Price above 200 EMA - long-term uptrend",
        "Strong trend: ADX 32.5"
    ],
    "quick_stats": {
        "rsi": 28.5,
        "adx": 32.5,
        "atr": 45.2,
        "volume_ratio": 2.3,
        "ema_position": "above_200",
        "close": 2450.50,
        "ema_5": 2455.0,
        "ema_9": 2452.0,
        "ema_21": 2448.0,
        "ema_50": 2440.0,
        "ema_200": 2420.0
    }
}
```

## EMA Position Classification

The scorer classifies price position relative to EMAs:

- **above_all**: Price above all EMAs (strongest bullish)
- **above_short_term**: Price above short-term EMAs (5, 9, 21)
- **above_medium_term**: Price above medium-term EMAs (21, 50)
- **above_200**: Price above 200 EMA only
- **above_50**: Price above 50 EMA only
- **below_all**: Price below all EMAs (strongest bearish)
- **below_long_term**: Price below long-term EMAs
- **mixed**: Price between EMAs

## Reason Generation

The scorer generates human-readable reasons explaining why each instrument passed:

### RSI Reasons
- "RSI at X within target range Y-Z"
- "RSI oversold at X - potential reversal"
- "RSI overbought at X - strong momentum"
- "RSI neutral at X"

### Volume Reasons
- "Exceptional volume: Xx average" (ratio ≥ 2.0)
- "High volume: Xx average" (ratio ≥ 1.5)
- "Above-average volume: Xx" (ratio ≥ 1.2)

### Trend Reasons
- "Price above all EMAs - strong uptrend"
- "Price above 200 EMA - long-term uptrend"
- "Price above 50 EMA - medium-term uptrend"
- "Price below all EMAs - strong downtrend"

### Momentum Reasons
- "Very strong trend: ADX X" (ADX ≥ 40)
- "Strong trend: ADX X" (ADX ≥ 25)
- "Weak trend: ADX X - ranging market" (ADX < 20)

## Usage Example

```python
from sqlalchemy.ext.asyncio import AsyncSession
from services.screening.ta_scorer import TAScorer
from services.screening.models import ScreeningCriteria

# Initialize scorer with database session
scorer = TAScorer(session)

# Define screening criteria
criteria = ScreeningCriteria(
    name="Momentum Scanner",
    description="Find strong momentum stocks",
    asset_class=["equity"],
    min_rsi=30.0,
    max_rsi=70.0,
    min_adx=25.0,
    min_volume_ratio=1.5
)

# Score symbols (from SQL pre-filter)
symbols = ["RELIANCE", "TCS", "INFY", "HDFC"]
scored_instruments = await scorer.score(symbols, criteria)

# Results are sorted by composite score (descending)
for inst in scored_instruments:
    print(f"{inst.symbol}: {inst.score:.1f} - {inst.reasons[0]}")
```

## Error Handling

The scorer handles errors gracefully:

1. **Insufficient data**: Returns empty result if < 10 bars available
2. **Missing critical data**: Skips symbol if close or RSI is null
3. **Database errors**: Logs error and continues with other symbols
4. **Missing optional data**: Uses neutral scores (50.0) for missing indicators

## Performance Characteristics

- **Parallel processing**: Scores all symbols concurrently using asyncio.gather
- **Database efficiency**: Single query per symbol (60 bars)
- **Memory efficient**: Processes one symbol at a time
- **Target performance**: < 10 seconds for 200 instruments

## Testing

Comprehensive test suite in `test_ta_scorer.py`:

```bash
# Run all tests
pytest services/screening/test_ta_scorer.py -v

# Run specific test
pytest services/screening/test_ta_scorer.py::TestTAScorer::test_score_single_symbol_success -v
```

Test coverage includes:
- Empty input handling
- Single and multiple symbol scoring
- Insufficient data handling
- Missing critical data handling
- Composite score calculation
- Quick stats population
- Reason generation
- Component score calculations (RSI, volume, trend, momentum)
- EMA position determination
- Database error handling

## Integration with Screening Pipeline

The TA Scorer integrates with the full screening pipeline:

1. **SQL Pre-Filter** → filters 10,000 instruments to ~200
2. **TA Scorer** → scores 200 instruments, returns sorted list
3. **AI Scorer** → analyzes top 50 with LLM for final recommendations

## Future Enhancements

Potential improvements for future iterations:

1. **Caching**: Cache indicator calculations for frequently screened symbols
2. **Batch queries**: Fetch data for multiple symbols in single query
3. **Custom weights**: Allow users to customize component score weights
4. **Additional indicators**: Support for more TA-Lib indicators (MACD, Stochastic, etc.)
5. **Sector-relative scoring**: Score relative to sector averages
6. **Historical score tracking**: Track how scores change over time

## References

- Requirements: Section 9.2 (AI Screening Engine)
- Design: `design_algo_backend.md` - Service 3: AI Screening Engine
- Related: `sql_filter.py` (Layer 1), `ai_scorer.py` (Layer 3)
