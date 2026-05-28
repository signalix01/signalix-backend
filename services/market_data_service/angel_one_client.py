import os
import pyotp
import logging
from datetime import datetime
from dotenv import load_dotenv
from SmartApi import SmartConnect

load_dotenv()
logger = logging.getLogger(__name__)

class AngelOneClient:
    def __init__(self):
        self.api_key = os.getenv("ANGEL_API_KEY")
        self.client_id = os.getenv("ANGEL_CLIENT_ID")
        self.pin = os.getenv("ANGEL_PIN")
        self.totp_secret = os.getenv("ANGEL_TOTP_SECRET")
        
        if not all([self.api_key, self.client_id, self.pin, self.totp_secret]):
            logger.warning("Missing Angel One credentials in .env file. Client will not be able to connect.")
            self.connected = False
            return
            
        self.smartApi = SmartConnect(api_key=self.api_key)
        self.connected = False
        self.auth_token = None
        self.refresh_token = None
        self.feed_token = None

    def login(self):
        """Authenticates with Angel One using credentials and TOTP."""
        if not all([self.api_key, self.client_id, self.pin, self.totp_secret]):
            return False
            
        try:
            totp = pyotp.TOTP(self.totp_secret).now()
            
            data = self.smartApi.generateSession(self.client_id, self.pin, totp)
            
            if data['status'] == True:
                logger.info("Angel One Login Successful")
                self.auth_token = data['data']['jwtToken']
                self.refresh_token = data['data']['refreshToken']
                self.feed_token = self.smartApi.getfeedToken()
                self.connected = True
                return True
            else:
                logger.error(f"Angel One Login Failed: {data['message']}")
                return False
                
        except Exception as e:
            logger.error(f"Angel One Login Exception: {str(e)}")
            return False

    def fetch_historical_data(self, symbol="26000", exchange="NSE", interval="ONE_DAY", from_date=None, to_date=None):
        """Fetches historical candlestick data for a symbol (Default: Nifty 50)"""
        if not self.connected:
            if not self.login():
                return None
                
        if to_date is None:
            to_date = datetime.now().strftime("%Y-%m-%d %H:%M")
        if from_date is None:
            # Default to last 30 days
            from datetime import timedelta
            from_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d %H:%M")

        try:
            historicParam = {
                "exchange": exchange,
                "symboltoken": symbol,
                "interval": interval,
                "fromdate": from_date, 
                "todate": to_date
            }
            response = self.smartApi.getCandleData(historicParam)
            if response and response.get('status') == True:
                return response['data']
            else:
                logger.error(f"Error fetching historical data: {response}")
                return None
        except Exception as e:
            logger.error(f"Exception in fetch_historical_data: {str(e)}")
            return None

    def fetch_live_prices(self, symbols_info):
        """
        Fetches live LTP (Last Traded Price) for given symbols.
        symbols_info should be a list of dicts: [{'exchange': 'NSE', 'tradingsymbol': 'Nifty 50', 'symboltoken': '26000'}, ...]
        """
        if not self.connected:
            if not self.login():
                return {}
                
        results = {}
        for sym in symbols_info:
            try:
                # ltpData takes exchange, tradingsymbol, symboltoken
                resp = self.smartApi.ltpData(sym['exchange'], sym['tradingsymbol'], sym['symboltoken'])
                if resp and resp.get('status') == True:
                    data = resp['data']
                    results[sym['symboltoken']] = {
                        "price": data['ltp'],
                        # SmartAPI doesn't always provide prev_close in ltpData, but we can return price
                        "previous_close": data.get('close', data['ltp']) 
                    }
                else:
                    logger.error(f"Failed to fetch LTP for {sym['tradingsymbol']}")
                    results[sym['symboltoken']] = {"price": 0.0, "previous_close": 0.0}
            except Exception as e:
                logger.error(f"Exception fetching LTP: {str(e)}")
                results[sym['symboltoken']] = {"price": 0.0, "previous_close": 0.0}
        
        return results
