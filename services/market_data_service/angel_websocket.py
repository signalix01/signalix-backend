import logging
from typing import List, Dict, Callable
from SmartApi.smartWebSocketV2 import SmartWebSocketV2

logger = logging.getLogger(__name__)

class AngelWebSocket:
    def __init__(self, auth_token, api_key, client_code, feed_token):
        self.auth_token = auth_token
        self.api_key = api_key
        self.client_code = client_code
        self.feed_token = feed_token
        self.sws = SmartWebSocketV2(self.auth_token, self.api_key, self.client_code, self.feed_token)
        self.on_tick_callbacks = []
        
        self.sws.on_data = self._on_data
        self.sws.on_error = self._on_error
        self.sws.on_close = self._on_close
        self.sws.on_open = self._on_open

    def _on_data(self, wsapp, message):
        for callback in self.on_tick_callbacks:
            try:
                callback(message)
            except Exception as e:
                logger.error(f"Error in tick callback: {e}")

    def _on_error(self, wsapp, error):
        logger.error(f"Angel WebSocket Error: {error}")

    def _on_close(self, wsapp, close_status_code, close_msg):
        logger.info(f"Angel WebSocket Closed: {close_status_code} - {close_msg}")

    def _on_open(self, wsapp):
        logger.info("Angel WebSocket Opened Successfully")

    def register_callback(self, callback: Callable):
        self.on_tick_callbacks.append(callback)

    def subscribe(self, correlation_id: str, mode: int, token_list: List[Dict]):
        """
        token_list format: [{"exchangeType": 2, "tokens": ["12345", "12346"]}]
        exchangeType: 1 for NSE, 2 for NFO
        mode: 1 (LTP), 2 (Quote), 3 (SnapQuote)
        """
        self.sws.subscribe(correlation_id, mode, token_list)

    def connect(self):
        # Runs synchronously and blocks
        logger.info("Connecting to Angel One WebSocket V2...")
        self.sws.connect()
        
    def close(self):
        if self.sws:
            self.sws.close_connection()
