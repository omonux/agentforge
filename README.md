# AgentForge by Omonux
An AI workforce workspace for small businesses.

## Modules
- Customer support: policy-grounded draft replies and escalation.
- Sales: prospect qualification and outreach drafts.
- Content Studio: original scripts, hooks and captions.
- Automation: reviewable workflow plans.
- Research: source-aware reports.
- Omonux Trading: paper journal, position accounting, watchlists and an SMA backtester using user-supplied historical closes; live trading disabled.

## Structure
- `apps/web`: React + TypeScript + Vite dashboard.
- `backend`: FastAPI API, SQLite development persistence and configurable chat-completion provider.
- `index.html`: original landing page retained during migration.

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
Set `AI_BASE_URL`, `AI_API_KEY` and `AI_MODEL` in backend/.env for real model-backed tasks. Never commit credentials.

## Safety and truth in product
A task is complete only after a successful provider response. Missing provider configuration is reported as an error, not replaced with fake output. External messaging, publishing, payments and trading require separate integrations and explicit approvals. Omonux Trading is paper-only and does not place live orders or promise returns.

## Status
Active foundation, not production-ready. CRM leads, support tickets, content records, workflow plans, paper portfolio accounting and strategy backtests now have persistent API routes and dashboard screens. CI runs backend tests and the frontend production build. The private single-owner authentication layer now protects application APIs with an HttpOnly signed session cookie, PBKDF2 password verification, CSRF tokens, login throttling and a fail-closed configuration check. Multi-tenant accounts, PostgreSQL, durable queues, file ingestion, real social/CRM connectors, market-data licensing, billing, monitoring and a full production security review remain future work. This is a private single-owner deployment foundation, not a multi-customer SaaS release.

## Run the full stack with Docker

1. Copy backend/.env.example to backend/.env.
2. Add your AI provider key and model to backend/.env (keep this file private).
3. From the repository root run:

    docker compose up --build

4. Open http://localhost:8080.

The API and SQLite data volume are kept behind the web proxy. For local non-Docker development, run the API on port 8000 and Vite on port 5173.

Docker Compose is a development deployment convenience, not a production security certification. The API currently lacks user login and tenant isolation; keep it private until those are implemented and reviewed.

## Private workspace sign-in

AgentForge is configured as a **single-owner private workspace**. All application API routes require a valid owner session, except the health check and sign-in endpoints. Browser writes require a CSRF token. Password verification uses PBKDF2-HMAC-SHA256; the session cookie is HttpOnly, SameSite=Strict and expires after eight hours. Five failed sign-in attempts from one IP are temporarily throttled.

Before starting the app, set these values in `backend/.env` (never commit that file):

- `SESSION_SECRET`: a unique random secret; generate with `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
- `ADMIN_PASSWORD`: a unique password of at least 14 characters.
- `ADMIN_PASSWORD_SALT`: a random salt; generate with `python -c "import secrets; print(secrets.token_hex(24))"`.
- `COOKIE_SECURE=false` only for local HTTP development. Set `COOKIE_SECURE=true` on Render or any HTTPS deployment.

The sign-in username is `owner`. Do not use a password from another service. If any authentication setting is missing or still contains a sample placeholder, private API routes fail closed.

For Render, add the four settings above as private environment variables in the service dashboard before deploying. Do not paste passwords or secret values into GitHub, source files, or public issue trackers. Use a strong, unique owner password and keep it in a password manager.
