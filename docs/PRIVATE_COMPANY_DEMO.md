# Private company presentation guide

This guide prepares AgentForge for a controlled, owner-led company presentation. It does not turn AgentForge into a public product or a multi-tenant SaaS.

## Recommended presentation setup

Use a separate AgentForge deployment and a separate database for demonstrations. Do not copy the live/owner database into the demo environment.

For the demo deployment:

- Use a separate hosting service/project and a separate persistent disk.
- Set `DATABASE_PATH` to a new demo-only path, for example `/data/agentforge-demo.db`.
- Generate a new, unique `SESSION_SECRET` and `ADMIN_PASSWORD_SALT`; choose a separate strong `ADMIN_PASSWORD`.
- Set `COOKIE_SECURE=true` and serve only over HTTPS.
- Keep `BILLING_ENABLED=false` and `BILLING_LIVE_ENABLED=false`.
- Keep `LIVE_TRADING_ENABLED=false` and `BYBIT_LIVE_TRADING_ENABLED=false`.
- Do not configure live exchange credentials, payment merchant keys, or real customer integrations in the demo.
- If AI is needed, configure a separate restricted AI key in the hosting provider's secret manager. Never put it in frontend configuration, source code, screenshots, or chat.
- Do not add company accounts or share the owner password with the company being presented to.

A separate database path is essential: changing the database path on an existing service does not create a safe demo if the demo service is still pointed at the owner's production database or reuses its disk.

## Demo data rules

Use only invented sample people, companies, emails, tickets, trading positions and workflow records. Clearly label them as sample data in the presentation. Never import:

- customer or employee records;
- real support tickets, emails, phone numbers or addresses;
- API keys, exchange credentials, bot tokens or session cookies;
- real payment records or card information;
- private business documents or confidential company metrics.

If a feature has no safe sample-data mode, show the empty state or explain the feature instead of connecting a real account.

## Presentation access

Keep the demo deployment private. Share the screen from your own device while you control the owner login. Do not publish the URL, create guest accounts, or give the company a login as part of this presentation setup.

If a company later needs its own login, create a separate security project first: organization membership and roles, tenant-scoped authorization on every read/write/query/background job, tenant-scoped secrets and billing, database migration strategy, audit trails, and automated cross-tenant denial tests. Hiding records in the frontend is not isolation. Do not onboard multiple companies until that work has been implemented and independently reviewed.

## Pre-presentation checklist

- [ ] Confirm the demo service uses its own database and persistent disk.
- [ ] Confirm the demo account has a unique password and session secret.
- [ ] Confirm all records are synthetic and visibly marked as examples.
- [ ] Confirm no real exchange, payment, Telegram or customer integrations are connected.
- [ ] Confirm billing and live-trading feature flags are OFF.
- [ ] Confirm unauthenticated requests to private API routes return 401 and the health endpoint reveals no sensitive data.
- [ ] Confirm logout invalidates the session.
- [ ] Confirm no secrets appear in browser developer tools, page source, logs or screenshots.
- [ ] Keep the demo service owner-only before, during and after the meeting.

## Important product status

AgentForge currently uses a single-owner authentication model. It does not provide organization accounts, guest roles, tenant isolation, or customer entitlement enforcement. A separate demo database protects the demonstration from the owner's other database; it does not prove multi-tenant isolation inside one shared installation.

This guide is a deployment and operating procedure, not a security certification. Complete a security review and backup/restore test before using sensitive business information.
