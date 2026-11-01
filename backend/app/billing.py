"""Payment-provider integration scaffold. Card data is always collected by hosted providers."""
import os
from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/billing", tags=["billing"])

@router.get("/status")
def billing_status():
    return {
        "paystack_configured": bool(os.getenv("PAYSTACK_SECRET_KEY")),
        "opay_configured": all(os.getenv(k) for k in ("OPAY_PUBLIC_KEY", "OPAY_SECRET_KEY", "OPAY_MERCHANT_ID")),
        "live_payments_enabled": os.getenv("BILLING_LIVE_ENABLED", "false").lower() == "true",
        "customer_entitlements_enforced": False,
    }

import hashlib
import hmac
import json
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

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
    return os.getenv(key, "").strip() or None


def _safe_checkout_url(value: str, provider: str):
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https":
        return False
    if provider == "paystack":
        return host == "checkout.paystack.com"
    return host in ("cashier.opaycheckout.com", "sandboxcashier.opaycheckout.com")


class CheckoutInput(BaseModel):
    provider: str = Field(pattern=r"^(paystack|opay)$")
    plan: str = Field(pattern=r"^(pro_monthly|business_monthly)$")
    email: str = Field(min_length=5, max_length=254, pattern=r'^[^@\\s]+@[^@\\s]+\\.[^@\\s]+


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
        if not row or (row["status"] == "success" and status != "success"):
            return
        now = _now()
        conn.execute("""UPDATE billing_payments SET status=?,provider_transaction_id=COALESCE(?,provider_transaction_id),
            updated_at=?,verified_at=CASE WHEN ?='success' THEN ? ELSE verified_at END WHERE reference=?""",
            (status, provider_id, now, status, now, reference))
        if status == "success":
            sub_id = secrets.token_urlsafe(18)
            period_end = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
            conn.execute("""INSERT INTO billing_subscriptions
                (id,provider,customer_email,plan,status,current_period_end,provider_subscription_id,
                 last_payment_reference,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(provider,customer_email,plan) DO UPDATE SET
                 status='active',current_period_end=excluded.current_period_end,
                 last_payment_reference=excluded.last_payment_reference,updated_at=excluded.updated_at""",
                (sub_id, provider, row["customer_email"], row["plan"], "active", period_end,
                 None, reference, now, now))


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
)


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
        if not row or (row["status"] == "success" and status != "success"):
            return
        now = _now()
        conn.execute("""UPDATE billing_payments SET status=?,provider_transaction_id=COALESCE(?,provider_transaction_id),
            updated_at=?,verified_at=CASE WHEN ?='success' THEN ? ELSE verified_at END WHERE reference=?""",
            (status, provider_id, now, status, now, reference))
        if status == "success":
            sub_id = secrets.token_urlsafe(18)
            period_end = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
            conn.execute("""INSERT INTO billing_subscriptions
                (id,provider,customer_email,plan,status,current_period_end,provider_subscription_id,
                 last_payment_reference,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(provider,customer_email,plan) DO UPDATE SET
                 status='active',current_period_end=excluded.current_period_end,
                 last_payment_reference=excluded.last_payment_reference,updated_at=excluded.updated_at""",
                (sub_id, provider, row["customer_email"], row["plan"], "active", period_end,
                 None, reference, now, now))


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
        "notice": "Configure prices privately before checkout. OPay renewals are manual.",
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
    if os.getenv("BILLING_LIVE_ENABLED", "false").lower() != "true":
        raise HTTPException(503, "Billing is disabled until merchant setup and sandbox testing are complete.")
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
            secret = os.getenv("PAYSTACK_SECRET_KEY", "")
            if not secret:
                raise HTTPException(503, "Paystack secret key is not configured.")
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
            public_key = os.getenv("OPAY_PUBLIC_KEY", "")
            merchant_id = os.getenv("OPAY_MERCHANT_ID", "")
            if not public_key or not merchant_id:
                raise HTTPException(503, "OPay merchant public key and merchant ID are not configured.")
            country = os.getenv("OPAY_COUNTRY", "NG").upper()
            currency = os.getenv("OPAY_CURRENCY", "NGN").upper()
            if country != "NG" or currency != "NGN":
                raise HTTPException(503, "OPay checkout is configured for Nigeria NGN only.")
            api_base = os.getenv("OPAY_API_BASE_URL", "https://sandboxapi.opaycheckout.com").rstrip("/")
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
