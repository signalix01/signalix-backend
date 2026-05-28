import requests
import logging

logger = logging.getLogger(__name__)

class BinanceClient:
    def __init__(self):
        self.base_url = "https://api.binance.com/api/v3"

    def fetch_live_prices(self, symbols):
        """
        Fetches live crypto prices from Binance public API.
        symbols is a list of trading pairs like ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
        """
        results = {}
        try:
            # Binance allows fetching all tickers or specific ones
            # Using ticker/24hr endpoint gives us price and 24h change (previous close equivalent)
            symbols_formatted = '["' + '","'.join(symbols) + '"]'
            url = f"{self.base_url}/ticker/24hr?symbols={symbols_formatted}"
            
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                for item in data:
                    results[item['symbol']] = {
                        "price": float(item['lastPrice']),
                        "previous_close": float(item['prevClosePrice']),
                        "change_percent": float(item['priceChangePercent'])
                    }
            else:
                logger.error(f"Binance API Error: {response.text}")
        except Exception as e:
            logger.error(f"Binance API Exception: {str(e)}")
            
        # Ensure all requested symbols have at least default values
        for sym in symbols:
            if sym not in results:
                results[sym] = {"price": 0.0, "previous_close": 0.0, "change_percent": 0.0}
                
        return results
