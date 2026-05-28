import asyncio
import logging
import threading
import json
import os
from datetime import datetime
from services.market_data_service.angel_one_client import AngelOneClient
from services.market_data_service.angel_websocket import AngelWebSocket
from services.market_data_service.instrument_master import instrument_master
from shared.config.settings import settings
import redis

logger = logging.getLogger(__name__)

class OptionsStreamWorker:
    def __init__(self):
        self.client = AngelOneClient()
        self.ws = None
        self.redis_client = None
        try:
            if settings.REDIS_URL:
                self.redis_client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
        except Exception:
            pass
        self.is_running = False
        self.tokens_map = {} # token -> instrument info
        self.memory_store = {} # In-memory fallback if Redis is absent

    async def initialize(self):
        if not self.client.login():
            logger.error("Failed to login to Angel One for stream worker")
            return False
            
        await instrument_master.download_master()
        return True
        
    def _on_tick(self, message):
        """Handle incoming tick data from WebSocket"""
        try:
            token = message.get("token")
            if not token:
                return
                
            inst = self.tokens_map.get(token)
            if not inst:
                return
                
            # Mode 3 (SnapQuote) message parsing
            tick_data = {
                "token": token,
                "symbol": inst.get("symbol"),
                "strike": float(inst.get("strike", 0)) / 100.0,
                "option_type": "CE" if "CE" in inst.get("symbol", "") else "PE",
                "ltp": message.get("last_traded_price", 0) / 100.0,
                "volume": message.get("volume_traded_today", 0),
                "oi": message.get("open_interest", 0),
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # Save to redis for ultra-low latency reads by the UI
            key = f"options_tick:{inst.get('name')}:{token}"
            try:
                if self.redis_client:
                    self.redis_client.setex(key, 60, json.dumps(tick_data))
            except Exception:
                pass
                
            # Always save to memory store
            self.memory_store[key] = tick_data
                
        except Exception as e:
            logger.error(f"Error processing tick: {e}")

    def _start_ws(self):
        self.ws = AngelWebSocket(
            self.client.auth_token,
            self.client.api_key,
            self.client.client_id,
            self.client.feed_token
        )
        self.ws.register_callback(self._on_tick)
        
        # Subscribe to NIFTY tokens for current expiry
        opts = instrument_master.get_options_tokens("NIFTY")
        
        # Take a subset of tokens (e.g. 50 calls, 50 puts)
        tokens_to_subscribe = []
        for o in opts[:100]:
            token = o.get("token")
            if token:
                tokens_to_subscribe.append(token)
                self.tokens_map[token] = o
                
        if tokens_to_subscribe:
            # Setup on_open locally to ensure subscription happens AFTER connection opens
            def on_open_subscribe(wsapp):
                logger.info(f"Subscribing to {len(tokens_to_subscribe)} options tokens...")
                self.ws.subscribe("options_stream", 3, [{"exchangeType": 2, "tokens": tokens_to_subscribe}])
                
            self.ws.sws.on_open = on_open_subscribe
            self.ws.connect()
        else:
            logger.error("No tokens to subscribe")

    async def start(self):
        logger.info("Starting Options Stream Worker...")
        if not await self.initialize():
            return
            
        self.is_running = True
        
        # Run websocket in a separate thread since it blocks
        self.ws_thread = threading.Thread(target=self._start_ws, daemon=True)
        self.ws_thread.start()
        
    def stop(self):
        self.is_running = False
        if self.ws:
            self.ws.close()

# Global instance
options_stream_worker = OptionsStreamWorker()
