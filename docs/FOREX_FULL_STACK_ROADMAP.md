# OMONUX Forex — full-stack connection and launch checklist

This document describes the target system and distinguishes implemented features from required work. No profitability or loss-free guarantee is possible.

## Current verified repository state
- Existing 12-agent crypto research council: implemented in `backend/app/omonux_council.py`.
- Forex TickerAll read-only account/candle API: implemented in `backend/app/omonux_forex.py`.
- Forex MT5 automatic broker order execution: **not implemented**.
- Council-to-Forex orchestration, economic-news ingestion, demo order lifecycle, and independent Forex position supervision: **not implemented**.
- Forex council market-aware evidence foundation: proposed in PR #87; not deployed.
- Existing Forex frontend is read-only and must not claim that an MT5 account is execution-ready.

## Connections needed
1. **AI provider:** `AI_BASE_URL`, `AI_API_KEY`, `AI_MODEL` (or the authenticated encrypted Connect API vault). Check provider quotas, model JSON output compatibility, and twelve-request council costs.
2. **MT5 demo broker account:** verify broker server, demo status, account permissions, allowed instruments, market hours, minimum lot/lot step, contract size, margin and filling modes. A connected account does not prove trading authorization. Keep credentials outside GitHub.
3. **TickerAll market data:** `TICKERALL_API_KEY`; discover the actual account identifier via `GET /v1/accounts`. **Do not assume identifiers start with `acc_`**; the current main-branch validation may reject legitimate IDs. PR #86 proposes an account verification fix; reconcile before merging.
4. **Execution bridge:** choose and verify a provider-documented order API with demo permission, or a Windows MT5 terminal plus a securely authenticated outbound bridge. Render Linux containers cannot run the Windows MT5 terminal directly. Do not invent TickerAll order endpoints.
5. **Economic news and calendar:** select licensed/authorized timestamped feeds, capture source, publication time, event time, currency impact and stale-data rules. Political statements are uncertain signals, not assured price forecasts.
6. **Persistence and alerts:** verify the active database storage is durable across redeploy and single-instance scheduling; configure Telegram bot token/chat ID privately if notifications are wanted.
7. **Secrets and hosting:** Render environment secrets, `SESSION_SECRET`, `ADMIN_PASSWORD`, `ADMIN_PASSWORD_SALT`, `SECRET_ENCRYPTION_KEY`; verify the deployed plan and persistence rather than relying on the README's older Blueprint assumptions.

## Required end-to-end demo acceptance tests
- Fresh complete M15/M30/H1/H4 broker candles; symbol/timezone normalization and missing-data rejection.
- Both BUY and SELL council decisions; invalid or missing votes veto orders; no stale or duplicated candle decisions.
- Broker bid/ask, spread, slippage, margin, contract-size and lot-step checks at order time.
- Demo-only order submission with broker-acknowledged ticket, idempotent client order ID, and reconciliation after timeout.
- Protective broker-side stop-loss and take-profit; emergency stop and position monitoring during API/network outages.
- Daily loss, max positions, trade count, exposure, drawdown and market-hours limits; explicit fail-closed behavior.
- Historical walk-forward tests, out-of-sample evaluation, realistic spread/commission/slippage, forward demo testing.
- Frontend status sourced from the backend; distinguish connected, research-ready, execution-ready, trading, paused and faulted.
- CI tests, TypeScript build, deployment health, persistence and secret-redaction checks before merging.

## Operational principle
The user wants autonomous Forex analysis and execution, but autonomous order placement is not currently present. Never turn on live-money trading simply because a council vote passes; validate demo execution and risk behavior first.
