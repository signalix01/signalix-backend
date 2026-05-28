import os
import json
import logging
import asyncio
import aiohttp
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class InstrumentMaster:
    URL = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
    
    def __init__(self):
        # Resolve path robustly
        self.CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
        self.CACHE_FILE = os.path.join(self.CACHE_DIR, "OpenAPIScripMaster.json")
        self.instruments = []
        os.makedirs(self.CACHE_DIR, exist_ok=True)
        
    async def download_master(self, force=False):
        """Download the Scrip Master JSON if missing or older than 1 day"""
        needs_download = force
        if not os.path.exists(self.CACHE_FILE):
            needs_download = True
        else:
            # Check file age
            mtime = os.path.getmtime(self.CACHE_FILE)
            if datetime.now().timestamp() - mtime > 86400:  # 1 day
                needs_download = True
                
        if needs_download:
            logger.info("Downloading Angel One Scrip Master JSON... (This takes a few seconds)")
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(self.URL) as response:
                        if response.status == 200:
                            data = await response.json()
                            with open(self.CACHE_FILE, 'w') as f:
                                json.dump(data, f)
                            logger.info(f"Scrip Master downloaded successfully to {self.CACHE_FILE}")
                        else:
                            logger.error(f"Failed to download Scrip Master: HTTP {response.status}")
                            return False
            except Exception as e:
                logger.error(f"Error downloading Scrip Master: {e}")
                return False
                
        # Load from cache
        if not self.instruments:
            try:
                with open(self.CACHE_FILE, 'r') as f:
                    self.instruments = json.load(f)
                logger.info(f"Loaded {len(self.instruments)} instruments from cache")
            except Exception as e:
                logger.error(f"Error loading Scrip Master from cache: {e}")
                return False
                
        return True
        
    def get_options_tokens(self, underlying_name, expiry_date_str=None):
        """
        Get all options tokens for a given underlying.
        Example: underlying_name="NIFTY", expiry_date_str="30MAY2024"
        """
        if not self.instruments:
            logger.warning("Instruments not loaded. Call download_master() first.")
            return []
            
        options = []
        for inst in self.instruments:
            if inst.get("name") == underlying_name and inst.get("exch_seg") == "NFO" and inst.get("instrumenttype") in ["OPTIDX", "OPTSTK"]:
                if expiry_date_str:
                    if expiry_date_str.upper() in inst.get("expiry", "").upper():
                        options.append(inst)
                else:
                    options.append(inst)
        return options
        
    def get_underlying_token(self, name, exchange="NSE"):
        """Get the token for the underlying equity/index"""
        if not self.instruments:
            return None
        for inst in self.instruments:
            if inst.get("name") == name and inst.get("exch_seg") == exchange:
                # E.g. Nifty 50 has name "Nifty 50" but token is "26000" and symbol is "Nifty 50"
                # Some APIs use "NIFTY"
                return inst
        return None

# Singleton instance
instrument_master = InstrumentMaster()

if __name__ == "__main__":
    # Test
    logging.basicConfig(level=logging.INFO)
    async def test():
        im = InstrumentMaster()
        await im.download_master()
        opts = im.get_options_tokens("NIFTY")
        if opts:
            print(f"Found {len(opts)} total NIFTY options.")
            # Print a few
            for o in opts[:3]:
                print(o)
    asyncio.run(test())
