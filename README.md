# AgentForge by Omonux
An AI workforce workspace for small businesses.

## Modules
- Customer support: policy-grounded draft replies and escalation.
- Sales: prospect qualification and outreach drafts.
- Content Studio: original scripts, hooks and captions.
- Automation: reviewable workflow plans.
- Research: source-aware reports.
- Omonux Trading: isolated paper-trading journal; live trading disabled.

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
Active foundation, not production-ready. Authentication, tenant isolation, PostgreSQL, durable queues, file ingestion, connectors, billing, tests, monitoring and deployment hardening are still required before a public paid launch.
