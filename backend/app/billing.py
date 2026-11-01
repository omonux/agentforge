"""Hosted Paystack and OPay checkout integration for AgentForge.

The application never collects or stores card numbers or CVVs. Card entry occurs
on provider-hosted checkout pages. Billing remains disabled until sandbox checks pass.
"""
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from .omonux_integrations import secret_or_env

router = APIRouter(prefix="/api/v1/billing", tags=["billing"])
DB = Path(os.getenv("DATABASE_PATH", "./agentforge.db"))
PLAN_KEYS = ("pro_monthly", "business_monthly")


def _db():
    DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB, timeout=15)
    conn.row_factory = sqlite3.Row
    return conn


def init_billing_db():
    with _db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS billing_payments(
            reference TEXT PRIMARY KEY, provider TEXT NOT NULL, customer_email TEXT NOT NULL,
            plan TEXT NOT NULL, amount_minor INTEGER NOT NULL, currency TEXT NOT NULL,
            status TEXT NOT NULL, provider_transaction_id TEXT, checkout_url TEXT,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL, verified_at TEXT
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS billing_subscriptions(
            id TEXT PRIMARY KEY, provider TEXT NOT NULL, customer_email TEXT NOT NULL,
            plan TEXT NOT NULL, status TEXT NOT NULL, current_period_end TEXT,
            provider_subscription_id TEXT, last_payment_reference TEXT,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            UNIQUE(provider, customer_email, plan)
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_billing_payments_email ON billing_payments(customer_email,created_at)")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _price(plan: str):
    if plan not in PLAN_KEYS:
        raise HTTPException(400, "Unknown plan.")
    key = "AGENTFORGE_PRO_MONTHLY_NGN" if plan == "pro_monthly" else "AGENTFORGE_BUSINESS_MONTHLY_NGN"
    raw = os.getenv(key, "").strip()
    if not raw:
        return None
    try:
        naira = int(raw)
    except ValueError:
        raise HTTPException(503, "Plan price must be a whole number of naira.")
    if naira < 100 or naira > 10_000_000:
        raise HTTPException(503, "Configured plan price is outside the allowed range.")
    return naira * 100


def _plan_code(plan: str):
    key = "PAYSTACK_PRO_MONTHLY_PLAN_CODE" if plan == "pro_monthly" else "PAYSTACK_BUSINESS_MONTHLY_PLAN_CODE"
    secret_name = "paystack_pro_monthly_plan_code" if plan == "pro_monthly" else "paystack_business_monthly_plan_code"
    return secret_or_env(secret_name, key).strip() or None


def _valid_email(value: str):
    return isinstance(value, str) and len(value) <= 254 and value.count("@") == 1 and "." in value.split("@")[-1] and not any(ch.isspace() for ch in value)


def _safe_checkout_url(value: str, provider: str):
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https":
        return False
    if provider == "paystack":
        return host == "checkout.paystack.com"
    return host in ("cashier.opaycheckout.com", "sandboxcashier.opaycheckout.com")


class CheckoutInput(BaseModel):
    provider: str = Field(pattern="^(paystack|opay)$")
    plan: str = Field(pattern="^(pro_monthly|business_monthly)$")
    email: str = Field(min_length=5, max_length=254)


def _insert_payment(reference, provider, email, plan, amount, currency):
    now = _now()
    with _db() as conn:
        conn.execute("""INSERT INTO billing_payments
            (reference,provider,customer_email,plan,amount_minor,currency,status,created_at,updated_at)
            VALUES(?,?,?,?,?,?, 'initializing',?,?)""",
            (reference, provider, email.lower(), plan, amount, currency, now, now))


def _update_checkout(reference, url, provider_id=None):
    with _db() as conn:
        conn.execute("""UPDATE billing_payments SET checkout_url=?,provider_transaction_id=?,
            status='pending',updated_at=? WHERE reference=? AND status='initializing'""",
            (url, provider_id, _now(), reference))


def _mark_payment(reference, provider, status, provider_id=None):
    if status not in ("success", "failed", "reversed"):
        return
    with _db() as conn:
        row = conn.execute("SELECT * FROM billing_payments WHERE reference=? AND provider=?",
                           (reference, provider)).fetchone()
        if not row or row["status"] == "success":
            return
        now = _now()
        conn.execute("""UPDATE billing_payments SET status=?,provider_transaction_id=COALESCE(?,provider_transaction_id),
            updated_at=?,verified_at=CASE WHEN ?='success' THEN ? ELSE verified_at END WHERE reference=?""",
            (status, provider_id, now, status, now, reference))
        if status == "success":
            sub_id = secrets.token_urlsafe(18)
            existing = conn.execute(
                "SELECT current_period_end,provider_subscription_id FROM billing_subscriptions WHERE provider=? AND customer_email=? AND plan=?",
                (provider, row["customer_email"], row["plan"])).fetchone()
            current = datetime.now(timezone.utc)
            if existing and existing["current_period_end"]:
                try:
                    previous_end = datetime.fromisoformat(existing["current_period_end"].replace("Z", "+00:00"))
                    if previous_end > current:
                        current = previous_end
                except ValueError:
                    pass
            period_end = (current + timedelta(days=30)).isoformat()
            provider_subscription_id = existing["provider_subscription_id"] if existing else None
            if provider == "paystack" and existing and existing["current_period_end"]:
                period_end = existing["current_period_end"]
            conn.execute("""INSERT INTO billing_subscriptions
                (id,provider,customer_email,plan,status,current_period_end,provider_subscription_id,
                 last_payment_reference,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(provider,customer_email,plan) DO UPDATE SET
                 status='active',current_period_end=excluded.current_period_end,
                 provider_subscription_id=COALESCE(excluded.provider_subscription_id,billing_subscriptions.provider_subscription_id),
                 last_payment_reference=excluded.last_payment_reference,updated_at=excluded.updated_at""",
                (sub_id, provider, row["customer_email"], row["plan"], "active", period_end,
                 provider_subscription_id, reference, now, now))


async def _post_json(url, headers, body):
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
            response = await client.post(url, headers=headers, json=body)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(502, f"Payment provider returned HTTP {exc.response.status_code}.")
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, "Payment provider is unavailable or returned an invalid response.")


async def _get_paystack_verification(reference, secret):
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
            response = await client.get(
                "https://api.paystack.co/transaction/verify/" + reference,
                headers={"Authorization": "Bearer " + secret})
            response.raise_for_status()
            return response.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, "Paystack verification is temporarily unavailable.")


@router.get("/status")
def billing_status():
    return {
        "paystack_configured": bool(secret_or_env("paystack_secret_key","PAYSTACK_SECRET_KEY")),
        "opay_configured": all(secret_or_env(n,e) for n,e in (("opay_public_key","OPAY_PUBLIC_KEY"),("opay_secret_key","OPAY_SECRET_KEY"),("opay_merchant_id","OPAY_MERCHANT_ID"))),
        "opay_country": secret_or_env("opay_country","OPAY_COUNTRY","NG"),
        "opay_currency": secret_or_env("opay_currency","OPAY_CURRENCY","NGN"),
        "prices_configured": all(_price(plan) for plan in PLAN_KEYS),
        "checkout_enabled": os.getenv("BILLING_ENABLED", "false").lower() == "true",
        "live_payments_enabled": os.getenv("BILLING_LIVE_ENABLED", "false").lower() == "true",
        "customer_entitlements_enforced": False,
    }


@router.get("/plans")
def billing_plans():
    return {
        "currency": "NGN",
        "plans": [
            {"id": "pro_monthly", "name": "Pro", "amount_minor": _price("pro_monthly"),
             "recurring_available": bool(_plan_code("pro_monthly"))},
            {"id": "business_monthly", "name": "Business", "amount_minor": _price("business_monthly"),
             "recurring_available": bool(_plan_code("business_monthly"))},
        ],
        "notice": "Prices must be configured privately. OPay renewals are manual.",
    }


@router.get("/payments")
def billing_payments():
    init_billing_db()
    with _db() as conn:
        return [dict(row) for row in conn.execute(
            """SELECT reference,provider,customer_email,plan,amount_minor,currency,status,
            provider_transaction_id,created_at,updated_at,verified_at
            FROM billing_payments ORDER BY created_at DESC LIMIT 200"""
        )]


@router.get("/subscriptions")
def billing_subscriptions():
    init_billing_db()
    with _db() as conn:
        return [dict(row) for row in conn.execute(
            """SELECT id,provider,customer_email,plan,status,current_period_end,
            provider_subscription_id,last_payment_reference,created_at,updated_at
            FROM billing_subscriptions ORDER BY created_at DESC LIMIT 200"""
        )]


@router.post("/checkout")
async def create_checkout(data: CheckoutInput):
    init_billing_db()
    if not _valid_email(data.email):
        raise HTTPException(400, "Enter a valid customer email address.")
    if os.getenv("BILLING_ENABLED", "false").lower() != "true":
        raise HTTPException(503, "Billing checkout is disabled until sandbox testing is enabled.")
    amount = _price(data.plan)
    if not amount:
        raise HTTPException(503, "This plan has no configured NGN price.")
    base_url = os.getenv("BILLING_BASE_URL", "").rstrip("/")
    if not base_url.startswith("https://"):
        raise HTTPException(503, "Set BILLING_BASE_URL to the public HTTPS application URL.")
    reference = "af_" + secrets.token_urlsafe(22).replace("-", "").replace("_", "")[:28]
    email = data.email.lower()
    _insert_payment(reference, data.provider, email, data.plan, amount, "NGN")
    try:
        if data.provider == "paystack":
            secret = secret_or_env("paystack_secret_key","PAYSTACK_SECRET_KEY")
            if not secret:
                raise HTTPException(503, "Paystack secret key is not configured.")
            if secret.startswith("sk_live_") and os.getenv("BILLING_LIVE_ENABLED", "false").lower() != "true":
                raise HTTPException(503, "Live Paystack keys are blocked until live billing is explicitly enabled.")
            body = {
                "email": email, "amount": str(amount), "currency": "NGN",
                "reference": reference, "callback_url": base_url + "/billing/return",
                "channels": ["card"],
                "metadata": {"plan": data.plan, "product": "AgentForge"},
            }
            plan_code = _plan_code(data.plan)
            if plan_code:
                body["plan"] = plan_code
                body.pop("amount", None)
            result = await _post_json(
                "https://api.paystack.co/transaction/initialize",
                {"Authorization": "Bearer " + secret, "Content-Type": "application/json"}, body)
            if not result.get("status") or not isinstance(result.get("data"), dict):
                raise HTTPException(502, "Paystack did not create a checkout session.")
            checkout_url = result["data"].get("authorization_url", "")
            if not _safe_checkout_url(checkout_url, "paystack"):
                raise HTTPException(502, "Paystack returned an unexpected checkout destination.")
            _update_checkout(reference, checkout_url, str(result["data"].get("reference") or reference))
        else:
            public_key = secret_or_env("opay_public_key","OPAY_PUBLIC_KEY")
            merchant_id = secret_or_env("opay_merchant_id","OPAY_MERCHANT_ID")
            if not public_key or not merchant_id:
                raise HTTPException(503, "OPay merchant public key and merchant ID are not configured.")
            country = secret_or_env("opay_country","OPAY_COUNTRY","NG").upper()
            currency = secret_or_env("opay_currency","OPAY_CURRENCY","NGN").upper()
            if country != "NG" or currency != "NGN":
                raise HTTPException(503, "OPay checkout is configured for Nigeria NGN only.")
            api_base = secret_or_env("opay_api_base_url","OPAY_API_BASE_URL","https://sandboxapi.opaycheckout.com").rstrip("/")
            if urlparse(api_base).hostname in ("api.opaycheckout.com", "liveapi.opaycheckout.com") and os.getenv("BILLING_LIVE_ENABLED", "false").lower() != "true":
                raise HTTPException(503, "Live OPay endpoint is blocked until live billing is explicitly enabled.")
            body = {
                "country": country, "reference": reference,
                "amount": {"total": amount, "currency": currency},
                "returnUrl": base_url + "/billing/return",
                "callbackUrl": base_url + "/api/v1/billing/webhooks/opay",
                "cancelUrl": base_url + "/billing/cancel",
                "expireAt": 30, "userInfo": {"userEmail": email},
                "productList": [{
                    "productId": data.plan, "name": "AgentForge " + data.plan,
                    "description": "AgentForge monthly plan", "price": amount, "quantity": 1,
                }],
                "payMethod": "BankCard",
            }
            result = await _post_json(
                api_base + "/api/v1/international/cashier/create",
                {"Authorization": "Bearer " + public_key, "MerchantId": merchant_id,
                 "Content-Type": "application/json"}, body)
            if result.get("code") != "00000" or not isinstance(result.get("data"), dict):
                raise HTTPException(502, "OPay did not create a hosted checkout.")
            checkout_url = result["data"].get("cashierUrl", "")
            if not _safe_checkout_url(checkout_url, "opay"):
                raise HTTPException(502, "OPay returned an unexpected cashier destination.")
            _update_checkout(reference, checkout_url, str(result["data"].get("orderNo") or ""))
    except Exception:
        with _db() as conn:
            conn.execute("""UPDATE billing_payments SET status='failed',updated_at=?
                WHERE reference=? AND status='initializing'""", (_now(), reference))
        raise
    return {"reference": reference, "provider": data.provider, "checkout_url": checkout_url,
            "status": "pending", "message": "Complete payment on the provider's hosted checkout."}


def _paystack_signature_ok(raw: bytes, signature: str | None, secret: str):
    if not signature:
        return False
    expected = hmac.new(secret.encode(), raw, hashlib.sha512).hexdigest()
    return hmac.compare_digest(expected, signature)


def _opay_signature_ok(payload: dict, signature: str | None, secret: str):
    if not signature:
        return False
    try:
        refunded = "t" if payload.get("refunded") is True else "f"
        keys = ("amount", "currency", "reference", "status", "timestamp", "transactionId")
        if any(payload.get(key) is None for key in keys):
            return False
        signed = (
            f'{{Amount:"{payload["amount"]}",Currency:"{payload["currency"]}",'
            f'Reference:"{payload["reference"]}",Refunded:{refunded},'
            f'Status:"{payload["status"]}",Timestamp:"{payload["timestamp"]}",'
            f'Token:"{payload.get("token") or ""}",TransactionID:"{payload["transactionId"]}"}}'
        )
        expected = hmac.new(secret.encode(), signed.encode(), hashlib.sha3_512).hexdigest()
        return hmac.compare_digest(expected.lower(), signature.lower())
    except (KeyError, TypeError, ValueError):
        return False


def _paystack_plan_for_code(plan_code: str):
    for plan in PLAN_KEYS:
        if _plan_code(plan) == plan_code and plan_code:
            return plan
    return None


def _paystack_subscription_event(event_name: str, data: dict):
    subscription = data.get("subscription") or data
    code = str(subscription.get("subscription_code") or data.get("subscription_code") or "")
    if not code:
        return
    if event_name == "subscription.disable":
        state = "cancelled"
    elif event_name == "invoice.payment_failed":
        state = "past_due"
    elif event_name in ("subscription.create", "invoice.payment_success"):
        state = "active"
    else:
        return
    customer = data.get("customer") or subscription.get("customer") or {}
    email = str(customer.get("email") or "").lower()
    plan_info = data.get("plan") or subscription.get("plan") or {}
    plan_code = str(plan_info.get("plan_code") or "")
    plan = _paystack_plan_for_code(plan_code)
    if not email or not plan:
        with _db() as conn:
            row = conn.execute(
                "SELECT customer_email,plan FROM billing_subscriptions WHERE provider='paystack' AND provider_subscription_id=?",
                (code,)).fetchone()
        if row:
            email, plan = row["customer_email"], row["plan"]
    if not email or not plan:
        return
    next_date = subscription.get("next_payment_date") or data.get("next_payment_date")
    now = _now()
    with _db() as conn:
        existing = conn.execute(
            "SELECT id,current_period_end FROM billing_subscriptions WHERE provider='paystack' AND customer_email=? AND plan=?",
            (email, plan)).fetchone()
        ident = existing["id"] if existing else secrets.token_urlsafe(18)
        period_end = next_date or (existing["current_period_end"] if existing else None)
        conn.execute("""INSERT INTO billing_subscriptions
            (id,provider,customer_email,plan,status,current_period_end,provider_subscription_id,
             last_payment_reference,created_at,updated_at)
            VALUES(?,'paystack',?,?,?,?,?,?,?,?)
            ON CONFLICT(provider,customer_email,plan) DO UPDATE SET
            status=excluded.status,current_period_end=COALESCE(excluded.current_period_end,billing_subscriptions.current_period_end),
            provider_subscription_id=excluded.provider_subscription_id,updated_at=excluded.updated_at""",
            (ident, email, plan, state, period_end, code, None, now, now))


@router.post("/webhooks/paystack")
async def paystack_webhook(request: Request):
    init_billing_db()
    secret = secret_or_env("paystack_secret_key","PAYSTACK_SECRET_KEY")
    raw = await request.body()
    if not secret or not _paystack_signature_ok(raw, request.headers.get("x-paystack-signature"), secret):
        raise HTTPException(401, "Invalid Paystack webhook signature.")
    try:
        event = json.loads(raw)
    except ValueError:
        raise HTTPException(400, "Invalid webhook JSON.")
    event_name = event.get("event")
    data = event.get("data") or {}
    if event_name in ("subscription.create", "subscription.disable", "invoice.payment_failed", "invoice.payment_success"):
        _paystack_subscription_event(event_name, data)
        return {"received": True}
    if event_name != "charge.success":
        return {"received": True}
    reference = str(data.get("reference") or "")
    if not reference or len(reference) > 80:
        return {"received": True}
    with _db() as conn:
        row = conn.execute("SELECT * FROM billing_payments WHERE reference=? AND provider='paystack'",
                           (reference,)).fetchone()
    if not row:
        return {"received": True}
    verified_result = await _get_paystack_verification(reference, secret)
    verified = verified_result.get("data") or {}
    if (verified_result.get("status") and verified.get("status") == "success"
        and str(verified.get("reference")) == reference
        and int(verified.get("amount", -1)) == int(row["amount_minor"])
        and str(verified.get("currency", "")).upper() == row["currency"]):
        _mark_payment(reference, "paystack", "success", str(verified.get("id") or ""))
    elif verified.get("status") in ("failed", "reversed"):
        _mark_payment(reference, "paystack", "failed")
    return {"received": True}


@router.post("/webhooks/opay")
async def opay_webhook(request: Request):
    init_billing_db()
    secret = secret_or_env("opay_secret_key","OPAY_SECRET_KEY")
    try:
        event = await request.json()
    except ValueError:
        raise HTTPException(400, "Invalid OPay callback JSON.")
    payload = event.get("payload") or {}
    if not secret or not _opay_signature_ok(payload, event.get("sha512"), secret):
        raise HTTPException(401, "Invalid OPay callback signature.")
    reference = str(payload.get("reference") or "")
    with _db() as conn:
        row = conn.execute("SELECT * FROM billing_payments WHERE reference=? AND provider='opay'",
                           (reference,)).fetchone()
    if not row:
        return {"received": True}
    # Confirm the callback independently using OPay's transaction-status API.
    merchant_id = secret_or_env("opay_merchant_id","OPAY_MERCHANT_ID")
    api_base = secret_or_env("opay_api_base_url","OPAY_API_BASE_URL","https://sandboxapi.opaycheckout.com").rstrip("/")
    country = os.getenv("OPAY_COUNTRY", "NG").upper()
    currency = os.getenv("OPAY_CURRENCY", "NGN").upper()
    query = {"reference": reference, "country": country}
    query_body = json.dumps(query, separators=(",", ":"))
    signature = hmac.new(secret.encode(), query_body.encode(), hashlib.sha512).hexdigest()
    result = await _post_json(
        api_base + "/api/v1/international/cashier/status",
        {"Authorization": "Bearer " + signature, "MerchantId": merchant_id,
         "Content-Type": "application/json"}, query)
    verified = result.get("data") or {}
    try:
        amount_ok = int(verified.get("amount", {}).get("total", -1)) == int(row["amount_minor"])
    except (TypeError, ValueError):
        amount_ok = False
    if (result.get("code") == "00000" and verified.get("status") == "SUCCESS"
        and str(verified.get("reference")) == reference and amount_ok
        and str(verified.get("amount", {}).get("currency", "")).upper() == row["currency"]
        and country == "NG" and currency == row["currency"]):
        _mark_payment(reference, "opay", "success", str(verified.get("orderNo") or ""))
    elif verified.get("status") in ("FAIL", "CLOSE"):
        _mark_payment(reference, "opay", "failed", str(verified.get("orderNo") or ""))
    return {"received": True}
