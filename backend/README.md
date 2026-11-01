# Backend API

FastAPI service for AgentForge.

## Setup
Create a virtual environment, install requirements.txt, copy .env.example to .env, then configure an OpenAI-compatible chat completion provider using AI_BASE_URL, AI_API_KEY, and AI_MODEL.

Run with:
    uvicorn app.main:app --reload --port 8000

Interactive API documentation is available at /docs while the server is running.

## Current endpoints
- /api/v1/agents, /api/v1/tasks
- /api/v1/crm/leads
- /api/v1/support/tickets
- /api/v1/content
- /api/v1/automations
- /api/v1/trading/watchlist
- /api/v1/trading/paper/trades
- /api/v1/analytics/summary

## Important limitations
This is a development API. It currently has no user authentication, tenant isolation, role permissions, rate limiting, production database migrations, or background job queue. Do not expose it publicly or use it for sensitive customer data until those controls are implemented. Workflow plans and content are not automatically sent or published. Trading endpoints are paper-only.
