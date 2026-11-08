# Binance + Bybit Spot market-data adapters

AgentForge now has a read-only market-data adapter for Binance Spot and Bybit
Spot. Both adapters normalize candles to the same fields:

- `time`, `open`, `high`, `low`, `close`, `volume`, `close_time`
- Candles are returned oldest-first.
- The currently-forming candle is excluded using its close timestamp.
- Supported intervals: 5m, 15m, 30m, 1h, 4h and 1d.
- Public market data requires no API key.

The comparison endpoint is:

`GET /api/v1/trading/market/compare/BTCUSDT?interval=30m&limit=120`

It fetches both exchanges concurrently and returns separate candle arrays and
the latest completed candle from each venue. The endpoint does not infer
arbitrage or promise that a displayed price difference is executable profit.
It does not place orders.

A valid cross-exchange arbitrage engine still needs synchronized executable
bid/ask prices, order-book depth, fees, spread, slippage, latency and inventory
constraints. These adapters are only the first read-only data layer.
