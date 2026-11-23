# Neon persistence and trading audit foundation

This migration was applied and checked on the isolated Neon branch
`dev-agentforge-trading-foundation` of project `aged-surf-49272782`.

## Scope
- Council decisions and immutable-at-application-level evidence records
- Proposed/simulated order intents with unique exchange/client order IDs
- Risk events and verified/paper portfolio snapshots
- PostgreSQL constraints and indexes

## App storage

`DATABASE_URL` is the backend's production database connection. With it set,
the shared `backend/app/database.py` adapter routes the workspace tables,
integration-secret vault, billing, image metadata and YouTube metadata to
PostgreSQL. The app initializes feature tables additively at startup or when a
feature is first opened. It supports the existing SQLite behavior for local
development when `DATABASE_URL` is absent. On Render, the backend fails closed
when the database URL is missing; it will not quietly create a new ephemeral
SQLite database.

Existing rows in a local SQLite file are not automatically copied to Neon.
Before production cutover, export any records that must be retained and load
them into the corresponding PostgreSQL tables. Generated image and video files
remain file storage; the database stores their metadata and paths.

The owner login remains the existing private workspace login. Neon Auth is
provisioned but is not the app's login provider yet. Public Neon Auth sign-up
has been disabled so an unrelated Neon account cannot be mistaken for the
workspace owner.

## Important trading boundary
The database migration **does not** enable live trading. `LIVE_TRADING_ENABLED`
and `BYBIT_LIVE_TRADING_ENABLED` must stay false unless separately reviewed.
Connecting the app to Neon makes storage durable; it does not verify broker
order acceptance, protected stops, account permissions, or automated execution.

The `order_intents` status constraint deliberately excludes submitted/executed
states. That is not a general-purpose live order ledger.

## Deployment
Keep `LIVE_TRADING_ENABLED=false` and
`BYBIT_LIVE_TRADING_ENABLED=false`. The Neon connection string belongs
only in the backend secret environment, never in the browser or repository.
Use pooled connections for application requests and direct connections for
schema migrations. Use a distinct development branch for testing.
