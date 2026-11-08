# OMONUX real-money Spot trading readiness

OMONUX has separate, owner-confirmed live order paths for Binance Spot and Bybit Spot. This is real-money execution when the server-side feature flags are explicitly enabled and the encrypted exchange credentials are configured. The strategy research engine and 12-agent council do not directly submit orders.

## Supported execution

- Binance Spot and Bybit Spot, USDT-quoted pairs only.
- Price-protected LIMIT IOC orders. The exchange fills only at the limit price or better; any unfilled remainder is cancelled. Partial fills and fees are possible.
- Each order requires a fresh server-side preview, a matching exact confirmation phrase, a second browser confirmation, and a unique client order ID.
- Per-order and daily notional caps are enforced server-side.
- A shared live emergency-stop latch blocks new orders and cancels pending previews.
- Reconciliation checks uncertain or pending submissions rather than blindly resubmitting them.
- No margin, futures, leverage, withdrawals, or AI-triggered live order placement.

## Private server configuration

Set these environment variables in the hosting provider's private environment settings; never commit values or paste exchange secrets into chat:

- LIVE_TRADING_ENABLED=false — Binance Spot live order flag.
- BYBIT_LIVE_TRADING_ENABLED=false — Bybit Spot live order flag.
- LIVE_MAX_ORDER_NOTIONAL_USDT=25 — maximum notional for one order.
- LIVE_MAX_DAILY_NOTIONAL_USDT=100 — maximum aggregate daily notional.

The flags deliberately default to false. Before enabling either exchange, store its API key and secret in the encrypted Integrations vault. Create a dedicated API key with Spot trading permission only, disable withdrawals and margin/futures permissions, apply IP allowlisting where the exchange supports it, and verify the account and symbol permissions. Do not reuse a withdrawal-capable key.

The current code defaults allow up to 25 USDT per order and 100 USDT aggregate daily notional. These are turnover caps, not a recommended amount to risk. For a planned 100 USDT starting balance, review and lower them before the first order if you want smaller exposure.

## First live-order procedure

1. Deploy the reviewed main build and confirm /health is healthy.
2. Configure the AI provider privately if using the 12-agent analysis council. AI analysis may be unavailable without a valid provider/model.
3. Add exchange credentials privately and test account/balance reads first.
4. Keep the live emergency stop active until the correct exchange, symbol, available balance, price, quantity, and notional are visible in a preview.
5. Enable only the exchange flag you intend to use.
6. Submit one small manually confirmed LIMIT IOC order and verify the exchange order ID, actual fills, fee asset, and reconciliation record.
7. Re-check limits, alerts, and emergency-stop operation before any further order.

A live-order acceptance response is not proof of a full fill. Always verify fills and fees against the exchange account. Research and backtest results are historical measurements, not guarantees of future performance.
