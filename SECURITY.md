# Security policy and deployment checklist

AgentForge is currently a **private, single-owner workspace**, not a multi-tenant SaaS. Do not expose it to customers or the public until the account and tenant model has been redesigned and independently reviewed.

## Current safeguards

- All application API routes require a valid signed session, except the health check and sign-in/bootstrap identity endpoints.
- The session cookie is HttpOnly, SameSite=Strict and Secure when `COOKIE_SECURE=true`.
- State-changing API requests require the CSRF token returned at sign-in and sent in `X-CSRF-Token`.
- Password verification uses PBKDF2-HMAC-SHA256; configure a long, unique administrator password.
- The reverse proxy adds a restrictive Content Security Policy, clickjacking protection, MIME-sniffing protection, referrer policy and permissions policy.
- The sign-in route has an additional shared request throttle. This is deliberately global for the current single-owner deployment; it is not a substitute for distributed abuse controls in a multi-user service.
- Integration credentials are encrypted at rest with Fernet. The encryption key is not stored in the database.
- Trading live-execution flags default OFF. Keep them OFF until a separate review and controlled test are completed.

## Required private environment configuration

Set these only in the hosting provider's secret/environment-variable interface:

- `SESSION_SECRET`: at least 32 characters of cryptographically random data.
- `ADMIN_PASSWORD`: unique, long password (at least 14 characters; prefer a password manager-generated value).
- `ADMIN_PASSWORD_SALT`: at least 16 characters of random data.
- `SECRET_ENCRYPTION_KEY`: a valid Fernet key. Back it up securely outside the application; losing it makes saved integration secrets unrecoverable.
- `AI_API_KEY`: only if AI features are required.

Never paste credentials into chat, commit them to Git, put them in frontend variables, or include them in screenshots/logs. If a key has ever been exposed, revoke it and create a replacement.

## Before public or paid launch

1. Replace the single-owner auth model with verified multi-user authentication, secure password reset, MFA/passkeys, account recovery and session revocation.
2. Add tenant-scoped authorization to every data query and object lookup; test cross-tenant access denial.
3. Move login throttling and abuse controls to a shared store with verified client identity, progressive delays and alerting.
4. Add database migrations, encrypted backups, restore drills, retention/deletion controls and audit-log protection.
5. Add signed, idempotent payment webhooks and server-side subscription entitlements before enabling paid plans.
6. Run dependency, container, API, CSRF, authorization and penetration testing; fix findings before public exposure.
7. Keep trading live execution disabled until exchange-key scope, withdrawal restrictions, order limits, emergency-stop behaviour and reconciliation have been independently reviewed.

## Known limitations

- In-memory login attempt tracking is process-local and resets when the process restarts. The proxy throttle is global for the current single-owner deployment, not a scalable multi-user rate-limiting design.
- There is no multi-tenant isolation, billing, payment processing, MFA, password-reset flow or production-grade distributed job queue yet.
- A green CI build is not a security audit and does not prove production readiness.


## Payment integration safeguards

- Card data is collected only on Paystack or OPay hosted checkout pages. AgentForge must never receive or store PAN, expiry or CVV.
- Paystack webhook signatures are checked against the raw request body with HMAC-SHA512; successful events are verified again through the Paystack transaction API and compared against the stored amount, currency and reference.
- OPay callbacks are checked using the provider's documented canonical HMAC-SHA3-512 signature, then cross-checked with OPay's cashier status API before marking a payment successful.
- Provider checkout URLs are restricted to known HTTPS provider hostnames to prevent redirect substitution.
- Billing is disabled by default. Keep `BILLING_LIVE_ENABLED=false` until sandbox tests, merchant approval and production review are complete.
- Payment references are unique and success processing is idempotent.
- Do not expose payment routes as a customer SaaS until multi-tenant accounts and tenant-scoped authorization are implemented. Current payment/subscription rows are associated with customer email only; entitlements are not enforced.
- Paystack recurring billing requires a configured provider plan code. OPay is treated as manual-renewal only in this release; do not assume OPay recurring support.
