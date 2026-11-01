import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from app import billing, main


def test_provider_webhook_signatures_are_checked():
    raw = b'{"event":"charge.success","data":{"reference":"abc"}}'
    secret = "test-paystack-secret"
    signature = hmac.new(secret.encode(), raw, hashlib.sha512).hexdigest()
    assert billing._paystack_signature_ok(raw, signature, secret)
    assert not billing._paystack_signature_ok(raw, "0" * 128, secret)

    payload = {
        "amount": "150000", "currency": "NGN", "reference": "af_test",
        "refunded": False, "status": "SUCCESS", "timestamp": "2026-11-01T00:00:00Z",
        "token": "token-1", "transactionId": "txn-1",
    }
    signed = (
        '{Amount:"150000",Currency:"NGN",Reference:"af_test",Refunded:f,'
        'Status:"SUCCESS",Timestamp:"2026-11-01T00:00:00Z",Token:"token-1",'
        'TransactionID:"txn-1"}'
    )
    opay_signature = hmac.new(b"test-opay-secret", signed.encode(), hashlib.sha3_512).hexdigest()
    assert billing._opay_signature_ok(payload, opay_signature, "test-opay-secret")
    assert not billing._opay_signature_ok(payload, "0" * 128, "test-opay-secret")


def test_billing_payment_success_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(billing, "DB", tmp_path / "billing.db")
    billing.init_billing_db()
    billing._insert_payment("af_test_1", "paystack", "buyer@example.com",
                            "pro_monthly", 150000, "NGN")
    billing._mark_payment("af_test_1", "paystack", "success", "provider-transaction-1")
    with billing._db() as conn:
        first = conn.execute(
            "SELECT current_period_end FROM billing_subscriptions WHERE customer_email=?",
            ("buyer@example.com",),
        ).fetchone()["current_period_end"]
    billing._mark_payment("af_test_1", "paystack", "success", "provider-transaction-1")
    with billing._db() as conn:
        rows = conn.execute(
            "SELECT current_period_end FROM billing_subscriptions WHERE customer_email=?",
            ("buyer@example.com",),
        ).fetchall()
    assert len(rows) == 1
    assert rows[0]["current_period_end"] == first


def test_checkout_is_disabled_until_explicitly_enabled(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB", tmp_path / "main.db")
    monkeypatch.setattr(billing, "DB", tmp_path / "billing.db")
    monkeypatch.setenv("AGENTFORGE_PRO_MONTHLY_NGN", "1500")
    monkeypatch.setenv("BILLING_ENABLED", "false")
    monkeypatch.setenv("BILLING_LIVE_ENABLED", "false")
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret-that-is-long-enough-123456")
    monkeypatch.setenv("ADMIN_PASSWORD", "strong-test-password-12345")
    monkeypatch.setenv("ADMIN_PASSWORD_SALT", "test-salt-0123456789abcdef")
    monkeypatch.setenv("COOKIE_SECURE", "false")
    with TestClient(main.app) as client:
        signed = client.post("/api/v1/auth/login", json={
            "username": "owner", "password": "strong-test-password-12345"
        })
        assert signed.status_code == 200
        client.headers.update({"X-CSRF-Token": client.cookies["agentforge_csrf"]})
        response = client.post("/api/v1/billing/checkout", json={
            "provider": "paystack", "plan": "pro_monthly", "email": "buyer@example.com"
        })
        assert response.status_code == 503
        assert "disabled" in response.json()["detail"].lower()


def test_webhook_endpoints_are_public_but_reject_unsigned_requests(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB", tmp_path / "main.db")
    monkeypatch.setattr(billing, "DB", tmp_path / "billing.db")
    monkeypatch.delenv("PAYSTACK_SECRET_KEY", raising=False)
    monkeypatch.delenv("OPAY_SECRET_KEY", raising=False)
    with TestClient(main.app) as client:
        paystack = client.post("/api/v1/billing/webhooks/paystack", json={"event": "charge.success"})
        opay = client.post("/api/v1/billing/webhooks/opay", json={"payload": {}, "sha512": "bad"})
        assert paystack.status_code == 401
        assert opay.status_code == 401


def test_checkout_urls_are_restricted_to_provider_domains():
    assert billing._safe_checkout_url("https://checkout.paystack.com/session", "paystack")
    assert not billing._safe_checkout_url("https://checkout.paystack.com.evil.test/x", "paystack")
    assert billing._safe_checkout_url("https://sandboxcashier.opaycheckout.com/session", "opay")
    assert not billing._safe_checkout_url("http://cashier.opaycheckout.com/session", "opay")


def test_paystack_subscription_events_update_existing_entitlement(tmp_path, monkeypatch):
    monkeypatch.setattr(billing, "DB", tmp_path / "subscriptions.db")
    monkeypatch.setenv("PAYSTACK_PRO_MONTHLY_PLAN_CODE", "PLN_test_pro")
    billing.init_billing_db()
    billing._paystack_subscription_event("subscription.create", {
        "subscription": {
            "subscription_code": "SUB_test_123",
            "next_payment_date": "2026-12-01T00:00:00.000Z",
        },
        "customer": {"email": "buyer@example.com"},
        "plan": {"plan_code": "PLN_test_pro"},
    })
    with billing._db() as conn:
        row = conn.execute(
            "SELECT status,provider_subscription_id,current_period_end FROM billing_subscriptions"
        ).fetchone()
    assert row["status"] == "active"
    assert row["provider_subscription_id"] == "SUB_test_123"
    assert row["current_period_end"] == "2026-12-01T00:00:00.000Z"

    billing._paystack_subscription_event("subscription.disable", {
        "subscription": {"subscription_code": "SUB_test_123"}
    })
    with billing._db() as conn:
        row = conn.execute("SELECT status FROM billing_subscriptions").fetchone()
    assert row["status"] == "cancelled"
