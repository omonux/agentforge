# OMONUX 50-market autonomous research pipeline

## What this adds
- A curated, unique 50-pair USDT Spot universe.
- Concurrent public completed-candle reads from Binance Spot and Bybit Spot (bounded concurrency).
- Deterministic ranking from the existing EMA/RSI/ATR signal engine.
- Cross-venue timestamp and price-divergence checks; unavailable or divergent data fails closed.
- A dashboard scan endpoint and top-candidate list.

## Auto-trading behavior
The existing scheduler still controls the paper engine. Its candidate discovery expands from three hard-coded pairs to this 50-pair universe. Each five-minute cycle manages open paper positions first, screens the universe, and sends at most one eligible fresh-candle candidate to the 12-agent council. Only a complete council approval plus deterministic sizing/risk checks can open a simulated position.

## Boundaries
This is not 50 exchanges; it is up to 50 Spot markets checked across two exchanges. The adapters use public candle endpoints. No authenticated orders are sent. The 12 agents are inference-time reviewers, not models retrained on proprietary data. No strategy is guaranteed profitable. Before any real-money use, validate with historical out-of-sample and forward paper results including fees, spread, slippage, partial fills, outage behavior and reconciliation. Live order endpoints remain separate and individually confirmed; automated live trading stays disabled.

## API
- `GET /api/v1/trading/universe` returns the configured universe and supported venues.
- `POST /api/v1/trading/universe/scan` scans up to 50 markets. Body: `{"interval":"30m","max_symbols":50}`.
