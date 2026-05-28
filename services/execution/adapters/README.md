# Broker Adapter Layer

OpenAlgo-compatible broker adapter layer for Signalix execution engine.

## Overview

This module provides a unified interface for executing trades across multiple brokers and markets:

- **OpenAlgo Adapter**: Supports 30+ Indian brokers (Angel One, Zerodha, Upstox, Fyers, etc.)
- **Binance Adapter**: Direct integration for cryptocurrency trading
- **OANDA Adapter**: Direct integration for forex trading
- **Alpaca Adapter**: Direct integration for US equities trading

All adapters implement the same `BrokerAdapter` interface, ensuring consistent behavior across different brokers.

## Architecture

```
BrokerAdapter (Abstract Base Class)
├── OpenAlgoAdapter (Indian Brokers via OpenAlgo)
│   ├── Angel One
│   ├── Zerodha
│   ├── Upstox
│   └── 27+ more brokers
├── BinanceAdapter (Crypto - Direct API)
├── OandaAdapter (Forex - Direct API)
└── AlpacaAdapter (US Equities - Direct API)
```

## Installation

Required dependencies are already in `requirements.txt`:

```bash
pip install httpx pydantic
```

For specific brokers, you may need additional packages:
- Angel One: `smartapi-python`
- Upstox: `upstox-python-sdk`

## Usage

### OpenAlgo Adapter (Indian Brokers)

```python
from services.execution.adapters import OpenAlgoAdapter, Order, OrderSide, OrderType, ProductType

# Configure adapter
config = {
    "base_url": "http://localhost:5000",  # OpenAlgo server URL
    "api_key": "your_openalgo_api_key",
    "broker": "angelone"  # or "zerodha", "upstox", etc.
}

# Create adapter instance
adapter = OpenAlgoAdapter(config, paper_trading=False)

# Connect to broker
await adapter.connect()

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

# Get positions
positions = await adapter.get_positions()
for pos in positions:
    print(f"{pos.symbol}: {pos.quantity} @ {pos.average_price}")

# Get account margin
margin = await adapter.get_margin()
print(f"Available cash: {margin.available_cash}")

# Disconnect
await adapter.disconnect()
```

### Binance Adapter (Cryptocurrency)

```python
from services.execution.adapters import BinanceAdapter, Order, OrderSide, OrderType

# Configure adapter
config = {
    "api_key": "your_binance_api_key",
    "api_secret": "your_binance_api_secret",
    "testnet": False,  # Use True for testnet
    "futures": False   # Use True for futures trading
}

# Create adapter instance
adapter = BinanceAdapter(config, paper_trading=False)

# Connect to Binance
await adapter.connect()

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

# Get positions (futures only)
positions = await adapter.get_positions()

# Disconnect
await adapter.disconnect()
```

### OANDA Adapter (Forex)

```python
from services.execution.adapters import OandaAdapter, Order, OrderSide, OrderType

# Configure adapter
config = {
    "api_key": "your_oanda_api_token",
    "account_id": "your_account_id",
    "practice": False  # Use True for practice account
}

# Create adapter instance
adapter = OandaAdapter(config, paper_trading=False)

# Connect to OANDA
await adapter.connect()

# Place a market order
order = Order(
    symbol="EUR_USD",
    exchange="OANDA",
    side=OrderSide.BUY,
    order_type=OrderType.MARKET,
    quantity=10000  # 10,000 units
)

result = await adapter.place_order(order)

# Get positions
positions = await adapter.get_positions()

# Disconnect
await adapter.disconnect()
```

### Alpaca Adapter (US Equities)

```python
from services.execution.adapters import AlpacaAdapter, Order, OrderSide, OrderType

# Configure adapter
config = {
    "api_key": "your_alpaca_key_id",
    "api_secret": "your_alpaca_secret_key",
    "paper": False  # Use True for paper trading
}

# Create adapter instance
adapter = AlpacaAdapter(config, paper_trading=False)

# Connect to Alpaca
await adapter.connect()

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

# Get positions
positions = await adapter.get_positions()

# Disconnect
await adapter.disconnect()
```

## Paper Trading Mode

All adapters support paper trading mode for testing without real money:

```python
# Enable paper trading
adapter = OpenAlgoAdapter(config, paper_trading=True)

# Orders will be simulated
order = Order(...)
result = await adapter.place_order(order)
# Returns immediately with FILLED status
```

## Common Interface

All adapters implement these methods:

### Connection Management
- `connect()`: Establish connection to broker
- `disconnect()`: Close connection
- `is_paper_trading()`: Check if in paper trading mode

### Order Management
- `place_order(order)`: Place a new order
- `cancel_order(order_id)`: Cancel an existing order
- `modify_order(order_id, ...)`: Modify an existing order
- `get_order_status(order_id)`: Get status of a specific order
- `get_orders(symbol=None)`: Get all orders (optionally filtered by symbol)

### Position Management
- `get_positions()`: Get all open positions
- `get_position(symbol, exchange)`: Get position for a specific symbol
- `get_holdings()`: Get long-term holdings

### Account Management
- `get_margin()`: Get account balance and margin information

## Order Types

Supported order types:
- `MARKET`: Execute at current market price
- `LIMIT`: Execute at specified price or better
- `STOP_LOSS`: Trigger market order when price reaches stop price
- `STOP_LOSS_LIMIT`: Trigger limit order when price reaches stop price

## Product Types (Indian Markets)

- `DELIVERY`: Cash & Carry (CNC)
- `INTRADAY`: Margin Intraday Square-off (MIS)
- `MARGIN`: Normal margin (NRML) for F&O
- `BO`: Bracket Order
- `CO`: Cover Order

## Error Handling

All adapters raise exceptions on errors:

```python
try:
    result = await adapter.place_order(order)
except RuntimeError as e:
    print(f"Connection error: {e}")
except Exception as e:
    print(f"Order failed: {e}")
```

## Testing

Run integration tests:

```bash
# Run all adapter tests
pytest tests/integration/test_broker_adapters.py -v

# Run specific adapter tests
pytest tests/integration/test_broker_adapters.py::TestOpenAlgoAdapter -v
pytest tests/integration/test_broker_adapters.py::TestBinanceAdapter -v
pytest tests/integration/test_broker_adapters.py::TestOandaAdapter -v
pytest tests/integration/test_broker_adapters.py::TestAlpacaAdapter -v
```

## Configuration Examples

### OpenAlgo (Angel One)
```python
config = {
    "base_url": "http://localhost:5000",
    "api_key": "openalgo_api_key",
    "broker": "angelone",
    "client_id": "A12345"  # Optional
}
```

### OpenAlgo (Zerodha)
```python
config = {
    "base_url": "http://localhost:5000",
    "api_key": "openalgo_api_key",
    "broker": "zerodha"
}
```

### Binance (Spot)
```python
config = {
    "api_key": "binance_api_key",
    "api_secret": "binance_api_secret",
    "testnet": False,
    "futures": False
}
```

### Binance (Futures)
```python
config = {
    "api_key": "binance_api_key",
    "api_secret": "binance_api_secret",
    "testnet": False,
    "futures": True
}
```

### OANDA (Live)
```python
config = {
    "api_key": "oanda_api_token",
    "account_id": "001-001-1234567-001",
    "practice": False
}
```

### Alpaca (Paper)
```python
config = {
    "api_key": "alpaca_key_id",
    "api_secret": "alpaca_secret_key",
    "paper": True
}
```

## Security Best Practices

1. **Never hardcode API keys**: Use environment variables or secure vaults
2. **Use paper trading for testing**: Always test with paper trading first
3. **Validate orders before placement**: Check quantity, price, and limits
4. **Implement rate limiting**: Respect broker API rate limits
5. **Log all operations**: Maintain audit trail of all orders
6. **Handle errors gracefully**: Implement retry logic with exponential backoff

## Supported Brokers

### Via OpenAlgo
- Angel One (Angel Broking)
- Zerodha
- Upstox
- Fyers
- Shoonya (Finvasia)
- AliceBlue
- 5Paisa
- IIFL
- Kotak Securities
- Motilal Oswal
- ICICI Direct
- And 20+ more Indian brokers

### Direct Integration
- Binance (Crypto - Spot & Futures)
- OANDA (Forex)
- Alpaca (US Equities)

## Extending the Adapter

To add a new broker adapter:

1. Create a new file in `services/execution/adapters/`
2. Inherit from `BrokerAdapter`
3. Implement all abstract methods
4. Add to `__init__.py`
5. Write integration tests

Example:

```python
from .base import BrokerAdapter, Order, Position, MarginInfo

class MyBrokerAdapter(BrokerAdapter):
    def _validate_config(self) -> None:
        # Validate configuration
        pass
    
    async def connect(self) -> bool:
        # Implement connection logic
        pass
    
    async def place_order(self, order: Order) -> Order:
        # Implement order placement
        pass
    
    # ... implement other methods
```

## License

This adapter layer is part of the Signalix platform.

## Support

For issues or questions:
- Check the integration tests for usage examples
- Review the base adapter interface documentation
- Consult broker-specific API documentation
