# AgentForge Neon Auth integration — staged rollout

## Existing infrastructure (verified)
- Neon project: `aged-surf-49272782`
- Production branch: `br-delicate-shadow-b5jz7p1n`
- Database: `neondb`
- Managed Better Auth is provisioned.
- Trusted production origin: `https://agentforge-omonux.onrender.com`

## Important current architecture
AgentForge currently uses a private single-owner FastAPI login with signed
`agentforge_session` cookies and a CSRF cookie. Its application records are
stored in SQLite via `DATABASE_PATH`, **not** in Neon Postgres.
Adding a Neon client alone does not migrate those records, secure the API,
or make Neon Auth the active login.

Do not disable the existing login, modify the trading safety gate, or expose
any new user signup to the owner workspace until backend authorization is
implemented. Neon Auth's current branch allows public email/password signup.

## Frontend
Set this public (non-secret) environment variable at build time:
```
VITE_NEON_AUTH_URL=https://ep-autumn-violet-b5j0xtxr.neonauth.c-7.us-east-2.aws.neon.tech/neondb/auth
```
`apps/web/src/neonAuth.ts` initializes a Neon client when configured.
It is deliberately not wired into the existing login screen yet.

## Remaining implementation
1. Design owner-only account mapping and reject unapproved signups at API boundaries.
2. Verify Neon-issued JWTs server-side against the branch JWKS, validating
   issuer, audience, expiry and subject; do not trust browser session claims.
3. Update all FastAPI routes and subrouters to use consistent authentication
   and resource-level authorization, retaining CSRF for cookie flows.
4. Add a deliberate transition for the existing owner login and logout UI.
5. Plan a separately tested SQLite-to-Postgres migration; do not silently
   switch storage or overwrite existing trading records.
6. Test sign-in, sign-out, refresh, wrong credentials, expired tokens,
   cross-user access, protected API calls, and the trading kill switch.
7. Configure production SMTP and email verification, review localhost access,
   then deploy after review.

No credentials should be committed. Render environment variables must be
configured separately. Production deployment is **not** complete in this PR.
