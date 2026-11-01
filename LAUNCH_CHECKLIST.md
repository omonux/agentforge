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
- [x] Central Connect API vault stores provider credentials encrypted at rest; secret values are never returned to the browser.
- [x] Persistent workflow queue requires explicit approval and only runs allowlisted agent-task, content-draft and Telegram-message actions.
- [x] YouTube script, voice narration, estimated SRT captions, async render polling, channel analytics and Telegram event/report endpoints are implemented; external provider credentials and model compatibility still require live verification.
- [x] YouTube upload uses an atomic approval state transition and blocks automatic retries when the upload outcome is uncertain.

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

## Remaining integration work — do not promise as complete

- [ ] Finish end-to-end YouTube video rendering with model-specific input mapping, asynchronous polling, voice/audio and captions; validate actual MP4 output.
- [ ] Add a manual recovery/reconciliation workflow for YouTube uploads marked upload_unknown; automatic retries are blocked to prevent duplicate videos.
- [ ] Validate YouTube Analytics against a real connected channel; revenue requires eligible monetization and the monetary analytics OAuth scope.
- [x] Add opt-in scheduled daily Telegram analytics delivery, in addition to event notifications and manual reports.
- [ ] Validate scheduled analytics delivery against a real connected YouTube channel and Telegram bot.
- [ ] Expand the workflow runner with additional vetted connectors, retry policies and per-connector permission scopes; current queue supports only agent tasks, content drafts and Telegram messages.
- [ ] Move all departments to a shared production database and validate migrations/backups before public launch.

## Not implemented — do not promise at launch

- Automated trend scoring/selection beyond YouTube popular-video discovery signals.
- Fully validated vertical video generation with model-specific dimensions/duration; voice and estimated SRT caption generation are available, but provider model compatibility and final media quality need end-to-end testing.
- Fully validated YouTube OAuth, provider-specific render success across chosen models, scheduled publishing and upload_unknown recovery.
- Scheduled YouTube views, subscriber growth and revenue analytics delivery to Telegram; manual reporting is available.
- General-purpose workflow execution across external apps; only the explicit allowlisted workflow actions are enabled.
- Multi-user / multi-tenant accounts, billing, roles and tenant isolation.
- Full historical exchange reconciliation, non-USDT fee conversion and tax-grade accounting.
- Independent audit of live order execution and operational recovery.

## Trading safety

The trading dashboard contains paper simulation and separately guarded manual Binance/Bybit Spot live-order endpoints. A green CI result is not authorization to trade. Keep live flags OFF, use withdrawal-disabled API keys, and do not connect real-money credentials until an independent reviewer has tested exchange permissions, order sizing, partial fills, unknown submissions, emergency-stop behavior and recovery procedures. Never use the automated paper strategy as a live order-placement path.

## Launch wording

Accurate: "AgentForge is a private AI operations workspace with CRM, content drafting, research and OMONUX trading research/paper tools."

Not accurate: "Fully autonomous AI business, YouTube publishing and revenue system" or "hands-free live trading platform."
