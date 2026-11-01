# AgentForge launch checklist

**Release posture:** private single-owner workspace. Do not advertise this build as a public multi-tenant SaaS or fully autonomous publishing/trading service.

## Verified in repository / CI

- [x] Backend test suite passes on the current OMONUX integration head (CI run #210).
- [x] Frontend TypeScript/Vite production build passes on the same head.
- [x] Owner authentication and CSRF protections are present in the application.
- [x] SQLite persistence is configured for the Render disk path.
- [x] OMONUX manual live execution is feature-flagged and requires preview plus explicit confirmation.
- [x] Reconciliation worker only queries recorded orders; it does not submit orders.
- [x] FIFO analytics regression test is included.

## Must complete before any public-facing launch

- [ ] Merge the stacked pull requests in dependency order (#2, #3, #4 and #5), resolving any conflicts and requiring green CI on the final `main` commit. PR #5 must not be merged ahead of its base dependency.
- [ ] Inspect the final GitHub diff and confirm no credentials, private keys, personal exchange data or local database files are committed.
- [ ] Create the Render Blueprint service only after the final code is on `main`; verify the paid plan, Frankfurt region, disk and estimated bill before confirming.
- [ ] Set a unique owner password, password salt, session secret, AI provider key and `COOKIE_SECURE=true` using private environment settings.
- [ ] Set `SECRET_ENCRYPTION_KEY` privately and back it up securely before entering Telegram or exchange secrets.
- [ ] Keep `LIVE_TRADING_ENABLED=false` and `BYBIT_LIVE_TRADING_ENABLED=false`. Do not activate real-money trading for launch.
- [ ] Verify health endpoint, owner sign-in/out, session expiry, CSRF writes, AI provider test and app navigation on the deployed HTTPS URL.
- [ ] Verify database persistence after a redeploy and complete a backup/restore drill before storing business-critical data.
- [ ] Verify Telegram test delivery and opt-in event alerts only if the owner configures the bot privately.
- [ ] Review Render logs, resource use, rate limits, error handling and service restart behavior.
- [ ] Keep the service private / access-controlled until an independent production security review is complete.

## Not implemented — do not promise at launch

- Automated trend discovery to select trending topics.
- End-to-end 30-second vertical video production with generated voice/audio and captions.
- YouTube OAuth connection, upload scheduling and automatic publishing.
- YouTube views, subscriber growth and revenue analytics or Telegram reporting for those metrics.
- General-purpose workflow execution across external apps.
- Multi-user / multi-tenant accounts, billing, roles and tenant isolation.
- Full historical exchange reconciliation, non-USDT fee conversion and tax-grade accounting.
- Independent audit of live order execution and operational recovery.

## Trading safety

The trading dashboard contains paper simulation and separately guarded manual Binance/Bybit Spot live-order endpoints. A green CI result is not authorization to trade. Keep live flags OFF, use withdrawal-disabled API keys, and do not connect real-money credentials until an independent reviewer has tested exchange permissions, order sizing, partial fills, unknown submissions, emergency-stop behavior and recovery procedures. Never use the automated paper strategy as a live order-placement path.

## Launch wording

Accurate: "AgentForge is a private AI operations workspace with CRM, content drafting, research and OMONUX trading research/paper tools."

Not accurate: "Fully autonomous AI business, YouTube publishing and revenue system" or "hands-free live trading platform."
