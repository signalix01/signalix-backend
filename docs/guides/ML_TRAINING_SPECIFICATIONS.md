# SignalixAI Machine Learning Pipeline Specifications
**Document Version:** 1.0  
**Core Framework:** Unsupervised Isolation Forest (scikit-learn)  
**Target Application:** Multi-Dimensional Market Anomaly Detection  

---

## 1. Architectural Overview & Feature Engineering

The SignalixAI anomaly detection engine utilizes an **Isolation Forest** ensemble to detect complex, multi-dimensional structural breaks in global financial assets. Instead of analyzing single metrics in isolation, it evaluates cross-asset relationships using scale-agnostic feature engineering.

### Scaling to 25 Engineered Features
To capture advanced market microstructure, liquidity exhaustion, and momentum divergences, the input vector expands from basic price/volume tracking to a robust **25-dimensional feature space**. All features are normalized as percentages, distance ratios, or oscillators to ensure cross-asset compatibility.

#### Feature Matrix Categories
1. **Price Momentum & Structure:** Intraday bar ranges, multi-timeframe price changes, distance from moving averages (e.g., Close to 20-EMA / 50-EMA distance ratios).
2. **Volume & Liquidity Imbalances:** Relative Volume (RVOL) surges, volume moving average ratios, up-volume vs. down-volume pressure metrics.
3. **Volatility Contours:** Multi-timeframe Average True Range (ATR) expansions/compressions, Bollinger Band width indicators, historical rolling volatility.
4. **Oscillators & Momentum Divergences:** Scaled RSI, MACD histogram slopes, stochastic crossovers.
5. **Statistical Distribution Metrics:** Rolling skewness and kurtosis of bar returns to detect tail-risk behavior.

---

## 2. Historical Data Horizon: Current vs. Optimal

### Current Implementation
* **Data Depth:** **90-Day Rolling Window (~0.25 Years)**.
* **Characteristics:** Captures immediate baseline conditions. Suitable for ultra-short-term shifts but lacks visibility into broader macroeconomic regimes.

### Optimal Horizon for Best Results
* **Recommended Depth:** **1 to 2 Years of Historical Data**.
* **Statistical Rationale:** Financial markets rotate through distinct behavioral regimes (bull cycles, bear trends, low-volatility sideways consolidations, and macroeconomic shocks). Training on **1 to 2 years** ensures the Isolation Forest learns these diverse structural baselines. Consequently, a standard macro shift is correctly recognized as a normal regime change rather than falsely triggering critical anomaly alerts.
* **Avoiding Concept Drift:** Feeding data older than 2 to 3 years can degrade performance due to **concept drift**—fundamental changes in market composition, algorithmic trading prevalence, and structural liquidity rules over time. Therefore, **1 to 2 years represents the optimal statistical sweet spot**.

---

## 3. Data Sizing & System Memory Footprint

With a **25-feature matrix**, each input row requires exactly **200 bytes** of raw floating-point storage (25 columns × 8-byte floats). Below is the memory footprint and network retrieval load mapped across different timeframes for an optimal **1-Year Training Window**:

| Timeframe | Duration | Approx. Rows (Global 24x7 Feeds) | RAM Footprint per Instrument | Database Fetch Payload Size |
| :--- | :--- | :--- | :--- | :--- |
| **Daily (1D)** | 1 Year | ~252 rows (Equities) / 365 rows (Crypto) | **~50 KB – 75 KB** | **~90 KB – 110 KB** |
| **Hourly (1H)** | 1 Year | ~8,760 rows | **~1.75 MB** | **~2.2 MB** |
| **5-Minute (5M)** | 1 Year | ~105,120 rows | **~21.0 MB** | **~26.5 MB** |
| **1-Minute (1m)**| 1 Year | ~525,600 rows | **~105.0 MB** | **~132.0 MB** |

> **Engineering Note:** For intraday detection, using an **Hourly (1H)** or **5-Minute (5M)** timeframe over a 1-to-2-year horizon provides exceptional precision while keeping memory requirements strictly under **25 MB per instrument**. This allows background Celery tasks to process hundreds of models concurrently without risk of out-of-memory errors.

---

## 4. Global Market Ingestion & Platform Infrastructure

The SignalixAI platform leverages a highly redundant hybrid data architecture designed to seamlessly ingest real-time and historical pricing across all global jurisdictions.

### Integration Sources
1. **Free Global Historical Backfill Engine (`yfinance`):**
   * Configured via `scripts/load_market_data.py` to seamlessly backfill decades of historical OHLCV data into the PostgreSQL `market_data` table at **$0 operational cost**. Covers international equities, forex pairs, commodities, and global market indices.
2. **Institutional Global Feeds (Configured via `settings.py`):**
   * **Polygon.io:** Low-latency pricing feeds for US Equities (NYSE/NASDAQ), Global Options, Indices, Forex, and Crypto.
   * **Binance API:** High-throughput Spot and Perpetual Futures connectivity for 24/7 digital assets.
   * **OANDA API:** Deep institutional liquidity pricing for Forex and CFDs.
   * **Glassnode API:** Specialized on-chain fundamental metrics.
3. **Native Direct-Broker Adapters:**
   * Production-ready regional adapter patterns supporting continuous synchronization with **Angel One, Dhan, Upstox, Zerodha, and ICICI Direct**.

### Universal Global Readiness
Because the machine learning pipeline translates raw pricing into **scale-agnostic feature ratios**, global users can input any international ticker symbol. The framework automatically adapts to local trading hours, normalizes events to **UTC**, builds tailored statistical distributions, and dynamically caches custom-trained anomaly models in Redis.
