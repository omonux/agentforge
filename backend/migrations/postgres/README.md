# Neon trading audit foundation

This migration was applied and checked on the isolated Neon branch
`dev-agentforge-trading-foundation` of project `aged-surf-49272782`.

## Scope
- Council decisions and immutable-at-application-level evidence records
- Proposed/simulated order intents with unique exchange/client order IDs
- Risk events and verified/paper portfolio snapshots
- PostgreSQL constraints and indexes

## Important safety boundary
This migration **does not** enable live trading or connect the running app
to Neon. The current FastAPI application uses `sqlite3` and
`DATABASE_PATH` in `backend/app/main.py`, including other modules that
import `db()`. Setting `DATABASE_URL` alone does **not** migrate these
modules. Do not switch production persistence until every SQLite caller,
transaction, reconciliation worker, vault, and startup migration has been
audited and migrated with tests.

Do not run this migration against production until a code integration plan,
backups, and staging validation are complete. The `order_intents` status
constraint deliberately excludes submitted/executed states. That is not a
general-purpose live order ledger.

## Deployment
Keep `LIVE_TRADING_ENABLED=false` and
`BYBIT_LIVE_TRADING_ENABLED=false`. The Neon connection string belongs
only in the backend secret environment, never in the browser or repository.
Use pooled connections for application requests and direct connections for
schema migrations. Use a distinct development branch for testing.
