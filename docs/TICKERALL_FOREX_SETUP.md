# AgentForge Forex — TickerAll MT5 demo setup

Forex V1 uses TickerAll instead of MetaApi. Crypto paper trading is unchanged.

1. In TickerAll, connect your MT5 **demo** account. Generate a new **read-only** API key. Revoke any key previously exposed in a screenshot or chat.
2. Open Render → your AgentForge web service → **Environment**. Add `TICKERALL_API_KEY` as a secret environment variable. Never commit it to GitHub, send it in chat, or put it in a `VITE_` frontend variable.
3. Redeploy, sign in to AgentForge, open **Omonux Trading → Auto Trading → Forex Intelligence / Connect API**, and click **Check TickerAll connection**. It uses the authenticated read-only `GET /v1/accounts` API. Find your demo account's `acc_...` ID.
4. In Render Environment, set `TICKERALL_ACCOUNT_ID` to that `acc_...` ID. Redeploy.
5. Click **Verify demo account**, then **Test 30-minute candles**. If the session is cold, reconnect through TickerAll's dashboard. Never store your MT5 password in AgentForge.
6. No Forex orders are enabled. All routes are read-only and reject non-demo accounts for account-specific operations. Forex research does not affect the existing Crypto paper trading engine.

### Endpoints

- `GET /api/v1/trading/forex/status` — configuration status only, no secrets.
- `GET /api/v1/trading/forex/accounts` — sanitized connected account metadata.
- `GET /api/v1/trading/forex/account` — demo-only account health.
- `GET /api/v1/trading/forex/candles/EURUSD?timeframe=M30&hours=72` — validated broker candle history (research only).

Provider docs: https://tickerall.com/docs . Base URL `https://api.tickerall.com`, bearer authentication, and the account/candle routes are documented there.

**Security:** Server-side secrets only; never share your key or passwords. No trading API endpoint, no broker order submission, no leverage, no guarantee of profitability. The broker demo balance and AgentForge's $100 reference paper budget are separate.
