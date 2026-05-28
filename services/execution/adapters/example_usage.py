"""
Example usage of broker adapters.

This script demonstrates how to use the broker adapter layer for different markets.
"""

import asyncio
from typing import Dict, Any

from base import Order, OrderSide, OrderType, ProductType
from openalgo_adapter import OpenAlgoAdapter
from binance_adapter import BinanceAdapter
from oanda_adapter import OandaAdapter
from alpaca_adapter import AlpacaAdapter


async def example_openalgo_indian_broker():
    """Example: Trading on Indian markets via OpenAlgo (Angel One)."""
    print("\n=== OpenAlgo Example (Angel One) ===")
    
    config = {
        "base_url": "http://localhost:5000",
        "api_key": "your_openalgo_api_key",
        "broker": "angelone"
    }
    
    # Create adapter in paper trading mode
    adapter = OpenAlgoAdapter(config, paper_trading=True)
    
    try:
        # Connect to broker
        connected = await adapter.connect()
        if not connected:
            print("Failed to connect to OpenAlgo")
            return
        
        print(f"Connected to {adapter.get_broker_name()}")
        
        # Place a market order
        order = Order(
            symbol="SBIN",
            exchange="NSE",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=10,
            product_type=ProductType.INTRADAY
        )
        
        result = await adapter.place_order(order)
        print(f"Order placed: {result.broker_order_id}")
        print(f"Status: {result.status}")
        print(f"Filled quantity: {result.filled_quantity}")
        
        # Get positions
        positions = await adapter.get_positions()
        print(f"\nPositions: {len(positions)}")
        for pos in positions:
            print(f"  {pos.symbol}: {pos.quantity} @ {pos.average_price}")
        
        # Get margin
        margin = await adapter.get_margin()
        print(f"\nAvailable cash: ₹{margin.available_cash:,.2f}")
        print(f"Used margin: ₹{margin.used_margin:,.2f}")
        
    finally:
        await adapter.disconnect()


async def example_binance_crypto():
    """Example: Trading cryptocurrency on Binance."""
    print("\n=== Binance Example (Crypto) ===")
    
    config = {
        "api_key": "your_binance_api_key",
        "api_secret": "your_binance_api_secret",
        "testnet": True,  # Use testnet for testing
        "futures": False  # Spot trading
    }
    
    # Create adapter in paper trading mode
    adapter = BinanceAdapter(config, paper_trading=True)
    
    try:
        # Connect to Binance
        connected = await adapter.connect()
        if not connected:
            print("Failed to connect to Binance")
            return
        
        print(f"Connected to {adapter.get_broker_name()} (Testnet)")
        
        # Place a limit order
        order = Order(
            symbol="BTC/USDT",
            exchange="BINANCE",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=0.001,
            price=50000.0
        )
        
        result = await adapter.place_order(order)
        print(f"Order placed: {result.broker_order_id}")
        print(f"Status: {result.status}")
        
        # Get account balance
        margin = await adapter.get_margin()
        print(f"\nAvailable USDT: ${margin.available_cash:,.2f}")
        
    finally:
        await adapter.disconnect()


async def example_oanda_forex():
    """Example: Trading forex on OANDA."""
    print("\n=== OANDA Example (Forex) ===")
    
    config = {
        "api_key": "your_oanda_api_token",
        "account_id": "001-001-1234567-001",
        "practice": True  # Use practice account
    }
    
    # Create adapter in paper trading mode
    adapter = OandaAdapter(config, paper_trading=True)
    
    try:
        # Connect to OANDA
        connected = await adapter.connect()
        if not connected:
            print("Failed to connect to OANDA")
            return
        
        print(f"Connected to {adapter.get_broker_name()} (Practice)")
        
        # Place a market order
        order = Order(
            symbol="EUR_USD",
            exchange="OANDA",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=10000  # 10,000 units
        )
        
        result = await adapter.place_order(order)
        print(f"Order placed: {result.broker_order_id}")
        print(f"Status: {result.status}")
        
        # Get positions
        positions = await adapter.get_positions()
        print(f"\nPositions: {len(positions)}")
        for pos in positions:
            print(f"  {pos.symbol}: {pos.quantity} units @ {pos.average_price}")
            print(f"    P&L: ${pos.pnl:,.2f} ({pos.pnl_percentage:.2f}%)")
        
    finally:
        await adapter.disconnect()


async def example_alpaca_us_equities():
    """Example: Trading US equities on Alpaca."""
    print("\n=== Alpaca Example (US Equities) ===")
    
    config = {
        "api_key": "your_alpaca_key_id",
        "api_secret": "your_alpaca_secret_key",
        "paper": True  # Use paper trading
    }
    
    # Create adapter in paper trading mode
    adapter = AlpacaAdapter(config, paper_trading=True)
    
    try:
        # Connect to Alpaca
        connected = await adapter.connect()
        if not connected:
            print("Failed to connect to Alpaca")
            return
        
        print(f"Connected to {adapter.get_broker_name()} (Paper)")
        
        # Place a limit order
        order = Order(
            symbol="AAPL",
            exchange="ALPACA",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=10,
            price=175.0
        )
        
        result = await adapter.place_order(order)
        print(f"Order placed: {result.broker_order_id}")
        print(f"Status: {result.status}")
        
        # Place a stop loss order
        stop_order = Order(
            symbol="AAPL",
            exchange="ALPACA",
            side=OrderSide.SELL,
            order_type=OrderType.STOP_LOSS,
            quantity=10,
            trigger_price=170.0
        )
        
        stop_result = await adapter.place_order(stop_order)
        print(f"Stop loss placed: {stop_result.broker_order_id}")
        
        # Get positions
        positions = await adapter.get_positions()
        print(f"\nPositions: {len(positions)}")
        for pos in positions:
            print(f"  {pos.symbol}: {pos.quantity} shares @ ${pos.average_price:.2f}")
            print(f"    P&L: ${pos.pnl:,.2f} ({pos.pnl_percentage:.2f}%)")
        
        # Get account info
        margin = await adapter.get_margin()
        print(f"\nCash: ${margin.available_cash:,.2f}")
        print(f"Buying power: ${margin.total_margin:,.2f}")
        
    finally:
        await adapter.disconnect()


async def example_multi_broker_comparison():
    """Example: Compare the same operation across different brokers."""
    print("\n=== Multi-Broker Comparison ===")
    
    # Define the same order for all brokers
    order_configs = [
        {
            "name": "OpenAlgo (Indian)",
            "adapter_class": OpenAlgoAdapter,
            "config": {
                "base_url": "http://localhost:5000",
                "api_key": "test",
                "broker": "angelone"
            },
            "order": Order(
                symbol="SBIN",
                exchange="NSE",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=10,
                product_type=ProductType.INTRADAY
            )
        },
        {
            "name": "Binance (Crypto)",
            "adapter_class": BinanceAdapter,
            "config": {
                "api_key": "test",
                "api_secret": "test",
                "testnet": True
            },
            "order": Order(
                symbol="BTC/USDT",
                exchange="BINANCE",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=0.001
            )
        },
        {
            "name": "OANDA (Forex)",
            "adapter_class": OandaAdapter,
            "config": {
                "api_key": "test",
                "account_id": "test",
                "practice": True
            },
            "order": Order(
                symbol="EUR_USD",
                exchange="OANDA",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=10000
            )
        },
        {
            "name": "Alpaca (US Equities)",
            "adapter_class": AlpacaAdapter,
            "config": {
                "api_key": "test",
                "api_secret": "test",
                "paper": True
            },
            "order": Order(
                symbol="AAPL",
                exchange="ALPACA",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=10
            )
        }
    ]
    
    for config in order_configs:
        print(f"\n{config['name']}:")
        adapter = config["adapter_class"](config["config"], paper_trading=True)
        
        try:
            # All adapters use the same interface
            result = await adapter.place_order(config["order"])
            print(f"  ✓ Order placed: {result.broker_order_id}")
            print(f"  ✓ Status: {result.status}")
            
            margin = await adapter.get_margin()
            print(f"  ✓ Available cash: {margin.available_cash:,.2f}")
            
        except Exception as e:
            print(f"  ✗ Error: {e}")


async def main():
    """Run all examples."""
    print("=" * 60)
    print("Broker Adapter Examples")
    print("=" * 60)
    
    # Note: These examples use paper trading mode and won't make real trades
    # Replace API keys with real credentials for actual trading
    
    try:
        # Run individual examples
        await example_openalgo_indian_broker()
        await example_binance_crypto()
        await example_oanda_forex()
        await example_alpaca_us_equities()
        
        # Run comparison example
        await example_multi_broker_comparison()
        
    except Exception as e:
        print(f"\nError: {e}")
    
    print("\n" + "=" * 60)
    print("Examples completed")
    print("=" * 60)


if __name__ == "__main__":
    # Run the examples
    asyncio.run(main())
