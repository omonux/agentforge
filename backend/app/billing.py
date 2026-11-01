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
    return os.getenv(key, "").strip() or None


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
