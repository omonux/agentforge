# MT5 demo order coordinator — safe integration stage

This connects the **existing** `forex_demo_risk.evaluate_demo_order` to a PostgreSQL-backed durable idempotency journal. It deliberately does not submit broker orders. The account starts **halted** until an independently authorized operator unhalts it. Missing DATABASE_URL fails closed.

Database setup (after verifying the Neon connection): configure `DATABASE_URL` as a secret in Render with TLS, then run `NeonDemoJournal().initialize()` in a controlled migration. Do not print the URL or put it in GitHub.

The review coordinator takes **server-verified** risk evidence only, then atomically reserves an approved signal. The code does not expose an HTTP route or auto scheduler. It cannot be enabled by sending arbitrary JSON approval booleans.

Remaining before demo execution: authenticated approval and kill-switch APIs; broker-sourced fresh account/spec/quote evidence; stop-loss and take-profit broker read-back; reconciliation for uncertain submissions; a broker-verified trade journal; durable daily equity baseline; demo close verification; scheduler with safe single-worker coordination; integration tests. Never allow live-money accounts.

Run tests: `PYTHONPATH=backend pytest -q backend/tests/test_forex_demo_coordinator.py`.
