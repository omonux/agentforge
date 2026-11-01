# OMONUX Live Operations Runbook

## What runs automatically

The API process starts a background reconciliation loop during application lifespan. It waits 20 seconds after startup, then checks for locally recorded non-terminal live orders. The default interval is 60 seconds and can be changed with `LIVE_RECONCILE_INTERVAL_SECONDS` (minimum 30 seconds).

The worker is strictly read-only against exchange order endpoints. It never creates, edits, or cancels an order. It does not start the live trading engine. It must run on a single application instance when SQLite is used; multiple replicas can duplicate polling and Telegram messages.

## Live execution safeguards

Live order placement is manual, one preview at a time, and requires exact typed confirmation. Binance and Bybit use price-protected Spot LIMIT IOC orders. IOC means any unfilled remainder is cancelled by the exchange. Partial fills remain possible.

Defaults:
- `LIVE_TRADING_ENABLED=false`
- `BYBIT_LIVE_TRADING_ENABLED=false`
- `LIVE_MAX_ORDER_NOTIONAL_USDT=25`
- `LIVE_MAX_DAILY_NOTIONAL_USDT=100`
- `LIVE_RECONCILE_INTERVAL_SECONDS=60`

Keep live flags off until exchange testnet and operational checks are complete. Use dedicated API keys with Spot trading only, IP allowlists and withdrawals disabled. Never paste credentials into source control or chat. Store them in the encrypted Integrations vault and back up `SECRET_ENCRYPTION_KEY securely.

## Reconciliation and uncertain submissions

An order whose create request times out is not automatically retried. Binance uncertain previews remain in the preview ledger; inspect Binance order history before taking action. Bybit uncertain submissions are also stored with their client order ID, allowing the reconciliation process to query Bybit by `orderLinkId`.

An exchange may take time to expose a just-submitted order in its history. A missing match is reported as UNKNOWN and is not a reason to submit another order. Operators should check the exchange's own order history and account balances.

The worker updates status, cumulative executed quantity, quote value and returned fills/commissions. Telegram fill notifications are generated only when cumulative executed quantity increases, preventing repeat notifications on unchanged reconciliations.

## Alerts

Telegram delivery is opt-in. Configure the bot token and chat ID in the encrypted Integrations vault, then explicitly enable desired alert categories in the OMONUX Live Operations dashboard. Failed deliveries remain in the SQLite outbox for manual retry.

The outbox is not a substitute for external monitoring. Alert delivery failures should be checked operationally.

## Research and analytics

The EMA research endpoint uses completed candles and a chronological split. It is a simplified historical simulation, not a forecast or investment advice. It does not place orders. Assumed fee and slippage settings do not model all spreads, market impact, taxes, liquidity or exchange outages.

Analytics covers locally recorded orders only. It is not a complete portfolio ledger, FIFO realized P&L calculation, tax report, or conversion of non-USDT commissions into USDT.

## Deployment and operations checklist

1. Run backend tests and frontend production build.
2. Test Binance and Bybit testnet signing, permissions, symbol rules, quantity increments, tick sizes, minimum notionals and account types.
3. Exercise partial fills, zero fills, rejected orders, expired previews, network timeouts, duplicate requests, price movement and emergency stop.
4. Verify uncertain order recovery by client order ID before enabling live keys.
5. Keep live flags off until an independent review approves the exact exchange account and risk limits.
6. Deploy one API instance with durable persistent storage and encrypted backups.
7. Verify the reconciliation loop, SQLite backup/restore and Telegram outbox behavior after restart.
8. Monitor process health, exchange API failures, database disk use, alert backlog and reconciliation lag.

The emergency stop prevents new orders through this application; it cannot cancel orders already accepted by an exchange. Use the exchange interface/API to cancel any working order when required.

## Current limitations

- Reconciliation runs in the API process, not as a separate queue worker; one instance is required with SQLite.
- Reconciliation is periodic polling, not an exchange websocket.
- FIFO realized P&L, fee conversion and complete balance snapshots are not implemented.
- Bybit account/permission variations still need real testnet integration coverage.
- No automated AI strategy is permitted to place live orders.
- YouTube trend-to-video generation, publishing, revenue analytics and Telegram creator reports remain separate unfinished product work.
