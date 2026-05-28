import os
import requests
import logging

logger = logging.getLogger(__name__)

class FinnhubClient:
    def __init__(self):
        self.api_key = os.getenv("FINNHUB_API_KEY")
        self.base_url = "https://finnhub.io/api/v1"
        self.connected = bool(self.api_key)

    def fetch_live_prices(self, symbols):
        """
        Fetches live prices from Finnhub.
        symbols is a list of tickers like ['OANDA:XAU_USD', 'OANDA:WTICO_USD', 'OANDA:USD_INR', 'US500']
        Note: Free tier might not have real-time index data, but has US stocks & forex.
        """
        if not self.connected:
            return {}
            
        results = {}
        for sym in symbols:
            try:
                # Use quote endpoint for live price
                url = f"{self.base_url}/quote?symbol={sym}&token={self.api_key}"
                response = requests.get(url, timeout=5)
                
                if response.status_code == 200:
                    data = response.json()
                    # c = Current price, pc = Previous close price
                    results[sym] = {
                        "price": float(data.get('c', 0.0)),
                        "previous_close": float(data.get('pc', 0.0))
                    }
                else:
                    logger.error(f"Finnhub API Error for {sym}: {response.text}")
                    results[sym] = {"price": 0.0, "previous_close": 0.0}
            except Exception as e:
                logger.error(f"Finnhub API Exception for {sym}: {str(e)}")
                results[sym] = {"price": 0.0, "previous_close": 0.0}
                
        return results
