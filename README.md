# AgentForge by Omonux

AgentForge is a private, single-owner AI operations workspace. OMONUX is its trading department.

## Product areas

- **AI workforce:** support, sales, content, workflow-planning and research agents backed by a configured OpenAI-compatible provider.
- **Business workspace:** persistent CRM leads, support tickets, content drafts and reviewable workflow plans.
- **OMONUX Trading:** Binance public market candles and indicators, paper trading, automatic paper strategy controls, chart-image analysis, encrypted exchange integrations, read-only account checks, guarded manual Spot execution, order reconciliation, FIFO analytics, EMA research and opt-in Telegram alerts.
- **Billing foundation:** Paystack card checkout and OPay hosted BankCard checkout, signed callbacks, server-side transaction verification and payment/subscription records. Billing is disabled by default.
- **Security:** owner sign-in, HttpOnly session cookie, CSRF protection, login throttling and encrypted integration secrets.

## Current release scope and limitations

This is a **private single-owner release foundation**, not a multi-customer SaaS product. It is not a finished unattended automation platform.

- Workflow records are plans; they do not execute arbitrary external actions.
- Content Studio creates scripts and drafts. Automated trend discovery, video rendering/voice production and YouTube publishing/monetization reporting are not implemented.
- Telegram alerts are limited to configured trading events and explicit tests; they do not report YouTube revenue or subscriber growth.
- Paper trading is simulated. The manual live Binance/Bybit Spot order endpoints are separate, feature-flagged OFF by default, and require preview plus explicit confirmation. Do not enable them for a public launch without an independent security and trading-risk review.
- Trading analytics cover locally recorded fills. They are not a complete exchange-account statement, tax report or independently reconciled portfolio.
- The original OMONUX repository is kept separate and is not modified by this integration.

## Repository structure

- `apps/web`: React, TypeScript and Vite dashboard.
- `backend`: FastAPI API, SQLite persistence and AI provider integration.
- `deploy`: Nginx and Supervisor configuration.
- `Dockerfile` and `render.yaml`: container build and Render Blueprint.

## Run locally

Backend:

```bash
cd backend
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

Frontend:

```bash
cd apps/web
npm install
npm run dev
```

For the full container:

```bash
docker compose up --build
```

The local development setup is not a production security certification.

## Required private configuration

Set secrets only in the hosting provider's encrypted environment-variable settings. Never commit them or paste them into chat.

- `ADMIN_PASSWORD`: unique password, at least 14 characters.
- `ADMIN_PASSWORD_SALT`: random salt.
- `SESSION_SECRET`: unique high-entropy secret.
- `COOKIE_SECURE=true` on HTTPS production.
- `AI_BASE_URL`, `AI_API_KEY`, `AI_MODEL`: provider configuration.
- `SECRET_ENCRYPTION_KEY`: Fernet key required to encrypt stored exchange and Telegram credentials. Back it up securely; losing it makes saved credentials unreadable.
- Telegram bot token and chat ID: enter through the authenticated integration screen, not source code.

Keep `LIVE_TRADING_ENABLED=false` and `BYBIT_LIVE_TRADING_ENABLED=false` for launch. Keep exchange API withdrawal permissions disabled. Do not store live credentials until you have completed a separate security review.

## Render deployment

The Blueprint provisions a paid Starter web service and a 1 GB persistent disk mounted at `/data`. SQLite uses `/data/agentforge.db`; the service is single-instance. Review current pricing and regional availability in Render before provisioning.

The Blueprint currently targets `main`. **Do not deploy until the required pull requests have been merged to main and the main-branch CI is green.** PR #5 is currently based on the OpenAI integration branch, so merge the dependency chain in order and verify the resulting main branch before creating the Render service. Do not deploy a stacked feature branch by guessing its runtime state.

After the code is merged:

1. Connect `omonux/agentforge` to Render as a Blueprint and inspect the planned resources.
2. Confirm the deploy branch is `main`, the persistent disk is mounted at `/data`, and the health check is `/health`.
3. Set the private owner password and AI API key when prompted; confirm generated session secrets are present.
4. Add `SECRET_ENCRYPTION_KEY` as a private environment variable before saving any exchange or Telegram credentials.
5. Keep live trading flags OFF. Do not add live exchange keys for the initial public demonstration.
6. Deploy, then verify sign-in, sign-out, CSRF-protected writes, AI connection test, health check, SQLite persistence across redeploy, logs and backup/restore.
7. Restrict access to the owner until the production security review is complete.

A successful CI build does not mean a Render service has been created or deployed.

## Verification

GitHub Actions runs backend pytest tests and the frontend TypeScript/Vite production build. The OMONUX integration head `0c5dc51e7a04101ecac117d8baf46abe4d5ddb18` passed both jobs in CI run #210. That verifies those automated checks only; it does not replace deployment, integration, security, exchange-testnet or backup/restore testing.

## Payments and paid plans

AgentForge now contains a **disabled-by-default payment integration foundation**:

- Paystack hosted card checkout in NGN. Recurring billing is available only when a matching Paystack monthly plan code is configured in the Paystack dashboard and the amount matches the AgentForge plan price.
- OPay hosted cashier checkout with the BankCard method requested. OPay sends the customer to its hosted checkout; AgentForge does not receive or store card number or CVV data.
- Paystack callbacks are HMAC-SHA512 verified and the transaction is fetched again from Paystack before a payment is marked successful.
- OPay callbacks are validated using OPay's documented HMAC-SHA3-512 canonical signature and independently checked against OPay's cashier status API before a payment is marked successful.
- Payment references are unique and successful callback processing is idempotent.

Configure the following privately in the hosting dashboard:

- `BILLING_BASE_URL`: public HTTPS application URL.
- `BILLING_ENABLED=false`: keep checkout disabled until sandbox testing is ready. Set true only when using sandbox credentials/endpoints.
- `BILLING_LIVE_ENABLED=false`: keep live payment endpoints and live Paystack keys blocked until both providers pass sandbox and production readiness checks.
- `AGENTFORGE_PRO_MONTHLY_NGN` and `AGENTFORGE_BUSINESS_MONTHLY_NGN`: monthly plan prices as whole naira.
- `PAYSTACK_SECRET_KEY`; optionally `PAYSTACK_PRO_MONTHLY_PLAN_CODE` and `PAYSTACK_BUSINESS_MONTHLY_PLAN_CODE` for recurring subscriptions.
- `OPAY_PUBLIC_KEY`, `OPAY_SECRET_KEY`, `OPAY_MERCHANT_ID`, and confirm `OPAY_API_BASE_URL` with OPay for your approved NGN merchant account.

The current app still has single-owner authentication. Billing records are stored by customer email, but **customer entitlements are not enforced** and there is no tenant isolation or public customer registration. Do not sell or grant paid access to customers until the multi-tenant account, entitlement, renewal, cancellation, refund, chargeback and support flows are implemented and reviewed. OPay recurring billing is not assumed; OPay renewals are manual in this foundation.

Never collect card details in AgentForge forms, never paste merchant keys into chat or Git, and never enable live billing before sandbox testing and a security review.
