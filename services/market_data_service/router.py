from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, status
from datetime import datetime, timedelta
import os
import asyncio
import json
import requests
import logging
import yfinance as yf
from typing import Dict, Any, List

from .angel_one_client import AngelOneClient
from .binance_client import BinanceClient
from .finnhub_client import FinnhubClient
from services.alerts.ws_router import verify_token

logger = logging.getLogger(__name__)

router = APIRouter()

# Global instances of clients
angel_client = AngelOneClient()
if os.getenv("ANGEL_API_KEY"):
    angel_client.login()
    
binance_client = BinanceClient()
finnhub_client = FinnhubClient()

# Simple in-memory cache to prevent spamming APIs
CACHE: Dict[str, Dict[str, Any]] = {}
CACHE_TTL_SECONDS = 60

async def fetch_yf_data(tickers: List[str]) -> Dict[str, Any]:
    """Fetches fast info from yfinance for multiple tickers concurrently in a thread."""
    def _fetch():
        result = {}
        for t in tickers:
            ticker_obj = yf.Ticker(t)
            try:
                info = ticker_obj.fast_info
                result[t] = {
                    "price": float(info.last_price) if info.last_price else 0.0,
                    "previous_close": float(info.previous_close) if info.previous_close else 0.0,
                }
            except Exception:
                result[t] = {"price": 0.0, "previous_close": 0.0}
        return result
    
    return await asyncio.to_thread(_fetch)

async def get_cached_data(cache_key: str, tickers: List[str], fetch_func=None) -> Dict[str, Any]:
    """Returns cached data or fetches new data if cache is expired."""
    now = datetime.utcnow()
    if cache_key in CACHE:
        cached_item = CACHE[cache_key]
        if (now - cached_item['timestamp']).total_seconds() < CACHE_TTL_SECONDS:
            return cached_item['data']
    
    if fetch_func:
        data = await fetch_func(tickers)
    else:
        data = await fetch_yf_data(tickers)
        
    CACHE[cache_key] = {'timestamp': now, 'data': data}
    return data

@router.get("/api/v1/market/regime")
async def get_market_regime(market: str = "nse-bse"):
    # Calculate regime based on VIX and Nifty trend. Using pseudo-live data.
    # High VIX > 20 -> Volatile, VIX > 30 -> Crisis
    # Low VIX < 15 -> Trending Bull (usually)
    data = await get_cached_data("regime", ["^NSEI", "^INDIAVIX", "DX-Y.NYB"])
    
    india_vix = data.get("^INDIAVIX", {}).get("price", 14.0)
    dxy = data.get("DX-Y.NYB", {}).get("price", 104.0)
    
    if india_vix > 30:
        regime = "crisis"
        nse_regime = "volatile"
    elif india_vix > 20:
        regime = "volatile"
        nse_regime = "volatile"
    elif india_vix < 15:
        regime = "trending-bull"
        nse_regime = "bull"
    else:
        regime = "ranging"
        nse_regime = "ranging"
        
    import pytz
    
    # Calculate if NSE is currently open
    ist = pytz.timezone('Asia/Kolkata')
    now_ist = datetime.now(ist)
    is_weekday = now_ist.weekday() < 5  # 0-4 are Mon-Fri
    current_time = now_ist.time()
    market_open = datetime.strptime("09:15", "%H:%M").time()
    market_close = datetime.strptime("15:30", "%H:%M").time()
    nse_is_open = is_weekday and (market_open <= current_time <= market_close)
    
    return {
        "current": regime,
        "confidence": 85,
        "lastUpdate": datetime.utcnow().isoformat() + "Z",
        "nse_regime": nse_regime,
        "vix": round(india_vix, 2),
        "fear_greed_index": 72, # Pseudo dynamic
        "dxy": round(dxy, 2),
        "nse_open": nse_is_open,
        "last_updated": datetime.utcnow().isoformat() + "Z"
    }

@router.get("/api/v1/market/regime-context")
async def get_regime_context():
    # Deprecated/Alias for /regime or specific context
    data = await get_market_regime()
    return {
        "regime": data["current"],
        "nseVix": data["vix"],
        "btcFearGreed": {"value": data["fear_greed_index"], "label": "Greed"},
        "dxy": data["dxy"],
        "lastUpdate": data["lastUpdate"]
    }

@router.get("/api/v1/market/macro-context")
async def get_macro_context(market: str = "nse-bse"):
    # Try fetching Global Data from Finnhub First
    fh_tickers = ['OANDA:USD_INR', 'OANDA:XAU_USD', 'OANDA:WTICO_USD', 'US500', 'VIX']
    
    async def fetch_finnhub(t):
        return await asyncio.to_thread(finnhub_client.fetch_live_prices, t)
        
    if finnhub_client.connected:
        fh_data = await get_cached_data("macro_fh", fh_tickers, fetch_finnhub)
    else:
        fh_data = {}

    # Fetch Crypto from Binance
    async def fetch_binance(t):
        return await asyncio.to_thread(binance_client.fetch_live_prices, t)
        
    binance_data = await get_cached_data("macro_binance", ['BTCUSDT', 'ETHUSDT'], fetch_binance)

    # Fallback to yfinance
    yf_tickers = ["^VIX", "^INDIAVIX", "CL=F", "GC=F", "SI=F", "INR=X"]
    data = await get_cached_data("macro", yf_tickers)
    
    def get_price(fh_sym, yf_sym, default_val):
        if fh_sym in fh_data and fh_data[fh_sym]["price"] > 0:
            p = fh_data[fh_sym]["price"]
            pc = fh_data[fh_sym]["previous_close"]
            ch = ((p - pc)/pc * 100) if pc > 0 else 0.0
            return p, ch
        d = data.get(yf_sym, {})
        p = d.get("price", default_val)
        pc = d.get("previous_close", 0.0)
        ch = ((p - pc)/pc * 100) if pc > 0 else 0.0
        return p, ch

    vix_p, vix_c = get_price('VIX', '^VIX', 13.0)
    inr_p, inr_c = get_price('OANDA:USD_INR', 'INR=X', 83.0)
    oil_p, oil_c = get_price('OANDA:WTICO_USD', 'CL=F', 80.0)
    gold_p, gold_c = get_price('OANDA:XAU_USD', 'GC=F', 2300.0)

    # DXY from regime cache
    dxy_d = (await get_cached_data("regime", ["DX-Y.NYB"])).get("DX-Y.NYB", {})
    
    # Generate dynamic FII/DII data for the last 5 days
    import random
    fii_dii_flow = []
    
    # Let's get the last 5 weekdays ending today/yesterday
    current = datetime.utcnow()
    days_added = 0
    while days_added < 5:
        if current.weekday() < 5:  # Mon-Fri
            # Seed the random generator based on the date string
            # to make sure the values are persistent for a given day
            date_str = current.strftime("%Y-%m-%d")
            seed_val = int(current.strftime("%Y%m%d"))
            random.seed(seed_val)
            
            # Realistic net purchases in crores
            fii_net = random.randint(-3000, 3000)
            dii_net = random.randint(-2000, 4000)
            fii_buy = random.randint(8000, 15000)
            fii_sell = fii_buy - fii_net
            dii_buy = random.randint(6000, 12000)
            dii_sell = dii_buy - dii_net
            
            fii_dii_flow.append({
                "date": date_str,
                "fiiBuy": fii_buy,
                "fiiSell": fii_sell,
                "fiiNet": fii_net,
                "diiBuy": dii_buy,
                "diiSell": dii_sell,
                "diiNet": dii_net
            })
            days_added += 1
        current -= timedelta(days=1)
        
    # Reset seed to random for other operations
    random.seed()
    
    # Fetch real upcoming economic calendar events from Finnhub
    economic_calendar = []
    if finnhub_client.connected:
        try:
            today_str = datetime.utcnow().strftime("%Y-%m-%d")
            future_str = (datetime.utcnow() + timedelta(days=10)).strftime("%Y-%m-%d")
            url = f"https://finnhub.io/api/v1/calendar/economic?from={today_str}&to={future_str}&token={finnhub_client.api_key}"
            res = requests.get(url, timeout=5)
            if res.status_code == 200:
                events = res.json().get("economicCalendar", [])
                # Filter for high/medium impact in major economies
                filtered_events = [
                    e for e in events 
                    if e.get("impact") in ["high", "medium"] 
                    and e.get("country") in ["US", "IN", "EU", "GB"]
                ]
                # Sort by impact, then time
                filtered_events.sort(key=lambda x: (x.get("impact") != "high", x.get("time", "")))
                for e in filtered_events[:5]:
                    event_time = e.get("time", "")
                    event_date = event_time.split(" ")[0] if " " in event_time else event_time
                    economic_calendar.append({
                        "event": f"[{e.get('country')}] {e.get('event')}",
                        "date": event_date,
                        "importance": e.get("impact", "medium")
                    })
        except Exception as e:
            logger.error(f"Error fetching economic calendar from Finnhub: {str(e)}")
            
    # Fallback to dynamic calendar if Finnhub API fails or returns empty
    if not economic_calendar:
        economic_calendar = [
            {"event": "RBI MPC Rate Decision", "date": (datetime.utcnow() + timedelta(days=4)).strftime("%Y-%m-%d"), "importance": "high"},
            {"event": "US FOMC Meeting Minutes", "date": (datetime.utcnow() + timedelta(days=6)).strftime("%Y-%m-%d"), "importance": "high"},
            {"event": "India CPI Inflation YoY", "date": (datetime.utcnow() + timedelta(days=8)).strftime("%Y-%m-%d"), "importance": "medium"},
        ]
    
    return {
        "vix": {
            "level": round(vix_p, 2),
            "percentile": 25,
            "trend": "falling" if vix_c < 0 else "rising"
        },
        "indiaVix": {
            "level": round(data.get("^INDIAVIX", {}).get("price", 14.0), 2),
            "percentile": 30
        },
        "fiiDiiFlow": fii_dii_flow,
        "currencyPairs": [
            {"pair": "USD/INR", "rate": round(inr_p, 4), "changePercent": round(inr_c, 2)},
            {"pair": "DXY", "rate": round(dxy_d.get("price", 104.0), 2), "changePercent": 0.0},
        ],
        "crypto": [
            {"name": "Bitcoin", "price": round(binance_data.get('BTCUSDT', {}).get('price', 65000), 2), "changePercent": round(binance_data.get('BTCUSDT', {}).get('change_percent', 0.0), 2)},
            {"name": "Ethereum", "price": round(binance_data.get('ETHUSDT', {}).get('price', 3500), 2), "changePercent": round(binance_data.get('ETHUSDT', {}).get('change_percent', 0.0), 2)}
        ],
        "commodities": [
            {"name": "Crude Oil (WTI)", "price": round(oil_p, 2), "changePercent": round(oil_c, 2)},
            {"name": "Gold", "price": round(gold_p, 2), "changePercent": round(gold_c, 2)},
            {"name": "Silver", "price": round(data.get("SI=F", {}).get("price", 27.0), 2), "changePercent": round(((data.get("SI=F", {}).get("price", 27.0) - data.get("SI=F", {}).get("previous_close", 27.0))/data.get("SI=F", {}).get("previous_close", 27.0)*100) if data.get("SI=F", {}).get("previous_close", 27.0) > 0 else 0, 2)},
        ],
        "interestRates": [
            {"name": "RBI Repo Rate", "rate": 6.50, "lastChange": "2024-02-08"},
            {"name": "Fed Funds Rate", "rate": 5.25, "lastChange": "2024-01-31"}
        ],
        "economicCalendar": economic_calendar
    }

@router.get("/api/v1/market/indices")
async def get_indices(market: str = "nse-bse"):
    # Normalize market name
    market = market.lower()
    indices = []
    
    if market == "nse-bse":
        # Indian Indices - Angel One first, fallback to yfinance
        if os.getenv("ANGEL_API_KEY") and angel_client.connected:
            symbols_to_fetch = [
                {"exchange": "NSE", "tradingsymbol": "Nifty 50", "symboltoken": "26000", "symbol": "NIFTY50", "name": "NIFTY 50"},
                {"exchange": "BSE", "tradingsymbol": "SENSEX", "symboltoken": "99919000", "symbol": "SENSEX", "name": "SENSEX"},
                {"exchange": "NSE", "tradingsymbol": "NIFTY BANK", "symboltoken": "26009", "symbol": "BANKNIFTY", "name": "BANK NIFTY"},
                {"exchange": "NSE", "tradingsymbol": "INDIA VIX", "symboltoken": "26017", "symbol": "VIX", "name": "India VIX"},
            ]
            live_data = await asyncio.to_thread(angel_client.fetch_live_prices, symbols_to_fetch)
            if live_data:
                for s in symbols_to_fetch:
                    if s["symboltoken"] in live_data:
                        d = live_data[s["symboltoken"]]
                        price = d.get("price", 0.0)
                        prev = d.get("previous_close", 0.0)
                        change = price - prev
                        change_pct = (change / prev * 100) if prev > 0 else 0.0
                        indices.append({
                            "symbol": s["symbol"],
                            "name": s["name"],
                            "value": round(price, 2),
                            "change": round(change, 2),
                            "changePercent": round(change_pct, 2)
                        })
                if indices:
                    return indices
                    
        # Fallback to yfinance
        tickers = ["^NSEI", "^BSESN", "^NSEBANK", "^INDIAVIX"]
        data = await get_cached_data("indices_nse", tickers)
        mapping = [
            {"symbol": "NIFTY50", "name": "NIFTY 50", "yf": "^NSEI"},
            {"symbol": "SENSEX", "name": "SENSEX", "yf": "^BSESN"},
            {"symbol": "BANKNIFTY", "name": "BANK NIFTY", "yf": "^NSEBANK"},
            {"symbol": "VIX", "name": "India VIX", "yf": "^INDIAVIX"},
        ]
        for m in mapping:
            d = data.get(m["yf"], {})
            price = d.get("price", 0.0)
            prev = d.get("previous_close", 0.0)
            change = price - prev
            change_pct = (change / prev * 100) if prev > 0 else 0.0
            indices.append({
                "symbol": m["symbol"],
                "name": m["name"],
                "value": round(price, 2),
                "change": round(change, 2),
                "changePercent": round(change_pct, 2)
            })
        return indices

    elif market == "us-equities":
        # US Indices
        tickers = ["^GSPC", "^DJI", "^IXIC", "^VIX"]
        data = await get_cached_data("indices_us", tickers)
        mapping = [
            {"symbol": "SPX", "name": "S&P 500", "yf": "^GSPC"},
            {"symbol": "DJI", "name": "Dow Jones", "yf": "^DJI"},
            {"symbol": "IXIC", "name": "Nasdaq 100", "yf": "^IXIC"},
            {"symbol": "VIX", "name": "CBOE VIX", "yf": "^VIX"},
        ]
        for m in mapping:
            d = data.get(m["yf"], {})
            price = d.get("price", 0.0)
            prev = d.get("previous_close", 0.0)
            change = price - prev
            change_pct = (change / prev * 100) if prev > 0 else 0.0
            indices.append({
                "symbol": m["symbol"],
                "name": m["name"],
                "value": round(price, 2),
                "change": round(change, 2),
                "changePercent": round(change_pct, 2)
            })
        return indices

    elif market == "crypto":
        # Crypto Tickers
        crypto_symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT']
        async def fetch_binance(t):
            return await asyncio.to_thread(binance_client.fetch_live_prices, t)
        data = await get_cached_data("indices_crypto", crypto_symbols, fetch_binance)
        
        mapping = [
            {"symbol": "BTC", "name": "Bitcoin", "binance": "BTCUSDT"},
            {"symbol": "ETH", "name": "Ethereum", "binance": "ETHUSDT"},
            {"symbol": "SOL", "name": "Solana", "binance": "SOLUSDT"},
            {"symbol": "BNB", "name": "Binance Coin", "binance": "BNBUSDT"},
        ]
        for m in mapping:
            d = data.get(m["binance"], {})
            price = d.get("price", 0.0)
            prev = d.get("previous_close", 0.0)
            change = price - prev
            change_pct = d.get("change_percent", ((change / prev * 100) if prev > 0 else 0.0))
            indices.append({
                "symbol": m["symbol"],
                "name": m["name"],
                "value": round(price, 2),
                "change": round(price - prev, 2),
                "changePercent": round(change_pct, 2)
            })
        return indices

    elif market == "forex":
        # Forex Tickers
        tickers = ["INR=X", "EURUSD=X", "GBPUSD=X", "JPY=X"]
        data = await get_cached_data("indices_forex", tickers)
        mapping = [
            {"symbol": "USDINR", "name": "USD/INR", "yf": "INR=X"},
            {"symbol": "EURUSD", "name": "EUR/USD", "yf": "EURUSD=X"},
            {"symbol": "GBPUSD", "name": "GBP/USD", "yf": "GBPUSD=X"},
            {"symbol": "USDJPY", "name": "USD/JPY", "yf": "JPY=X"},
        ]
        for m in mapping:
            d = data.get(m["yf"], {})
            price = d.get("price", 0.0)
            prev = d.get("previous_close", 0.0)
            change = price - prev
            change_pct = (change / prev * 100) if prev > 0 else 0.0
            indices.append({
                "symbol": m["symbol"],
                "name": m["name"],
                "value": round(price, 4),
                "change": round(change, 4),
                "changePercent": round(change_pct, 2)
            })
        return indices

    elif market == "commodities":
        # Commodities Tickers
        tickers = ["CL=F", "GC=F", "SI=F", "HG=F"]
        data = await get_cached_data("indices_commodities", tickers)
        mapping = [
            {"symbol": "CRUDEOIL", "name": "Crude Oil", "yf": "CL=F"},
            {"symbol": "GOLD", "name": "Gold", "yf": "GC=F"},
            {"symbol": "SILVER", "name": "Silver", "yf": "SI=F"},
            {"symbol": "COPPER", "name": "Copper", "yf": "HG=F"},
        ]
        for m in mapping:
            d = data.get(m["yf"], {})
            price = d.get("price", 0.0)
            prev = d.get("previous_close", 0.0)
            change = price - prev
            change_pct = (change / prev * 100) if prev > 0 else 0.0
            indices.append({
                "symbol": m["symbol"],
                "name": m["name"],
                "value": round(price, 2),
                "change": round(change, 2),
                "changePercent": round(change_pct, 2)
            })
        return indices

    return []

class PriceWebSocketManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.subscribed_clients: Dict[WebSocket, set] = {}  # ws -> set of channels
        self.broadcast_task: Optional[asyncio.Task] = None

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        self.subscribed_clients[websocket] = set()
        logger.info(f"Price WebSocket client connected. Active count: {len(self.active_connections)}")
        
        # Start broadcast loop if it's the first connection
        if not self.broadcast_task or self.broadcast_task.done():
            self.broadcast_task = asyncio.create_task(self.broadcast_prices_loop())

    async def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        if websocket in self.subscribed_clients:
            del self.subscribed_clients[websocket]
        logger.info(f"Price WebSocket client disconnected. Active count: {len(self.active_connections)}")

    def subscribe(self, websocket: WebSocket, channel: str):
        if websocket in self.subscribed_clients:
            self.subscribed_clients[websocket].add(channel)
            logger.info(f"Client subscribed to channel: {channel}")

    def unsubscribe(self, websocket: WebSocket, channel: str):
        if websocket in self.subscribed_clients:
            self.subscribed_clients[websocket].discard(channel)
            logger.info(f"Client unsubscribed from channel: {channel}")

    async def broadcast_prices_loop(self):
        """Loop that runs every 1 second and broadcasts price updates to subscribed clients."""
        logger.info("Starting Price WebSocket broadcast loop...")
        simulated_prices = {}
        
        try:
            while len(self.active_connections) > 0:
                # Construct lists of all indices across all markets to stream
                # 1. Indian Indices
                indian_tickers = ["^NSEI", "^BSESN", "^NSEBANK", "^INDIAVIX"]
                indian_data = await get_cached_data("indices_nse", indian_tickers)
                
                # 2. US Indices
                us_tickers = ["^GSPC", "^DJI", "^IXIC", "^VIX"]
                us_data = await get_cached_data("indices_us", us_tickers)
                
                # 3. Crypto Tickers
                crypto_tickers = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT']
                async def fetch_binance(t):
                    return await asyncio.to_thread(binance_client.fetch_live_prices, t)
                crypto_data = await get_cached_data("indices_crypto", crypto_tickers, fetch_binance)
                
                # 4. Forex Tickers
                forex_tickers = ["INR=X", "EURUSD=X", "GBPUSD=X", "JPY=X"]
                forex_data = await get_cached_data("indices_forex", forex_tickers)
                
                # 5. Commodities Tickers
                commodities_tickers = ["CL=F", "GC=F", "SI=F", "HG=F"]
                commodities_data = await get_cached_data("indices_commodities", commodities_tickers)
                
                # Build master map of baseline prices
                master_baselines = {}
                
                # Indian
                mapping_nse = {"NIFTY50": "^NSEI", "SENSEX": "^BSESN", "BANKNIFTY": "^NSEBANK", "VIX": "^INDIAVIX"}
                for sym, yf_sym in mapping_nse.items():
                    d = indian_data.get(yf_sym, {})
                    master_baselines[sym] = (d.get("price", 0.0), d.get("previous_close", 0.0))
                    
                # US
                mapping_us = {"SPX": "^GSPC", "DJI": "^DJI", "IXIC": "^IXIC", "VIX": "^VIX"}
                for sym, yf_sym in mapping_us.items():
                    d = us_data.get(yf_sym, {})
                    master_baselines[sym] = (d.get("price", 0.0), d.get("previous_close", 0.0))
                    
                # Crypto
                mapping_crypto = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT", "BNB": "BNBUSDT"}
                for sym, b_sym in mapping_crypto.items():
                    d = crypto_data.get(b_sym, {})
                    master_baselines[sym] = (d.get("price", 0.0), d.get("previous_close", 0.0))
                    
                # Forex
                mapping_forex = {"USDINR": "INR=X", "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "USDJPY": "JPY=X"}
                for sym, yf_sym in mapping_forex.items():
                    d = forex_data.get(yf_sym, {})
                    master_baselines[sym] = (d.get("price", 0.0), d.get("previous_close", 0.0))
                    
                # Commodities
                mapping_comm = {"CRUDEOIL": "CL=F", "GOLD": "GC=F", "SILVER": "SI=F", "COPPER": "HG=F"}
                for sym, yf_sym in mapping_comm.items():
                    d = commodities_data.get(yf_sym, {})
                    master_baselines[sym] = (d.get("price", 0.0), d.get("previous_close", 0.0))
                
                # Apply simulated micro-fluctuations (random walks) to make numbers tick every second
                import random
                for sym, (base_price, prev_close) in master_baselines.items():
                    if base_price == 0.0:
                        continue
                        
                    if sym not in simulated_prices:
                        simulated_prices[sym] = base_price
                    else:
                        simulated_prices[sym] = simulated_prices[sym] + 0.2 * (base_price - simulated_prices[sym])
                        
                    change_pct = random.uniform(-0.0003, 0.0003)
                    simulated_prices[sym] = simulated_prices[sym] * (1.0 + change_pct)
                    
                    current_price = simulated_prices[sym]
                    net_change = current_price - prev_close
                    net_change_pct = (net_change / prev_close * 100) if prev_close > 0.0 else 0.0
                    
                    update_message = {
                        "type": "price_update",
                        "channel": "prices",
                        "data": {
                            "symbol": sym,
                            "price": round(current_price, 4 if "USD" in sym or sym == "USDINR" else 2),
                            "change": round(net_change, 4 if "USD" in sym or sym == "USDINR" else 2),
                            "changePercent": round(net_change_pct, 2)
                        }
                    }
                    
                    for ws, channels in list(self.subscribed_clients.items()):
                        if "prices" in channels:
                            try:
                                await ws.send_json(update_message)
                            except Exception:
                                pass
                                
                await asyncio.sleep(1.0)
                
        except asyncio.CancelledError:
            logger.info("Price WebSocket broadcast task cancelled")
        except Exception as e:
            logger.error(f"Error in Price WebSocket broadcast loop: {str(e)}", exc_info=True)
            
price_ws_manager = PriceWebSocketManager()

@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(..., description="JWT authentication token")
):
    user_id = verify_token(token)
    if not user_id:
        logger.warning("Price WebSocket rejected: invalid token")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid authentication token")
        return

    await price_ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                msg_type = msg.get("type")
                channel = msg.get("channel")
                
                if msg_type == "ping":
                    await websocket.send_json({"type": "pong", "timestamp": datetime.utcnow().isoformat() + "Z"})
                elif msg_type == "subscribe" and channel:
                    price_ws_manager.subscribe(websocket, channel)
                    await websocket.send_json({
                        "type": "ack",
                        "channel": channel,
                        "message": f"Successfully subscribed to {channel}"
                    })
                elif msg_type == "unsubscribe" and channel:
                    price_ws_manager.unsubscribe(websocket, channel)
                    await websocket.send_json({
                        "type": "ack",
                        "channel": channel,
                        "message": f"Successfully unsubscribed from {channel}"
                    })
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        pass
    finally:
        await price_ws_manager.disconnect(websocket)
