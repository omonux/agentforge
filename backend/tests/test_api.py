from fastapi.testclient import TestClient
from app import main

def login(client, monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret-that-is-long-enough-123456")
    monkeypatch.setenv("ADMIN_PASSWORD", "strong-test-password-12345")
    monkeypatch.setenv("ADMIN_PASSWORD_SALT", "test-salt-0123456789abcdef")
    monkeypatch.setenv("COOKIE_SECURE", "false")
    response = client.post("/api/v1/auth/login", json={
        "username": "owner", "password": "strong-test-password-12345"
    })
    assert response.status_code == 200
    client.headers.update({"X-CSRF-Token": client.cookies["agentforge_csrf"]})

def test_health_and_core_records(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB", tmp_path / "test.db")
    with TestClient(main.app) as client:
        login(client, monkeypatch)
        assert client.get("/health").json()["status"] == "ok"
        lead = client.post("/api/v1/crm/leads", json={
            "name": "Test Customer", "email": "test@example.com",
            "company": "Example Co", "stage": "new"
        })
        assert lead.status_code == 200
        assert lead.json()["name"] == "Test Customer"

        ticket = client.post("/api/v1/support/tickets", json={
            "customer": "Test Customer", "subject": "Need help",
            "message": "I need assistance", "priority": "high"
        })
        assert ticket.status_code == 200
        assert ticket.json()["status"] == "open"

        content = client.post("/api/v1/content", json={
            "title": "First short", "channel": "youtube",
            "format": "short_video"
        })
        assert content.status_code == 200
        assert content.json()["status"] == "draft"

        workflow = client.post("/api/v1/automations", json={
            "name": "Review new lead", "trigger_name": "New lead",
            "action_plan": "Draft a follow-up for human review"
        })
        assert workflow.status_code == 200
        assert workflow.json()["status"] == "draft"

        watch = client.post("/api/v1/trading/watchlist", json={"symbol": "BTCUSD"})
        assert watch.status_code == 200
        assert watch.json()["symbol"] == "BTCUSD"

        assert client.get("/api/v1/analytics/summary").json()["leads_total"] == 1

def test_invalid_stage_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB", tmp_path / "invalid.db")
    with TestClient(main.app) as client:
        login(client, monkeypatch)
        response = client.post("/api/v1/crm/leads", json={
            "name": "Bad Stage", "stage": "invented"
        })
        assert response.status_code == 400

def test_paper_portfolio_prevents_short_sales_and_backtests(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB", tmp_path / "trading.db")
    with TestClient(main.app) as client:
        login(client, monkeypatch)
        buy = client.post("/api/v1/trading/paper/trades", json={
            "symbol": "ETHUSD", "side": "buy", "quantity": 1,
            "reference_price": 100
        })
        assert buy.status_code == 200
        rejected = client.post("/api/v1/trading/paper/trades", json={
            "symbol": "ETHUSD", "side": "sell", "quantity": 2,
            "reference_price": 110
        })
        assert rejected.status_code == 400
        sell = client.post("/api/v1/trading/paper/trades", json={
            "symbol": "ETHUSD", "side": "sell", "quantity": 0.5,
            "reference_price": 120
        })
        assert sell.status_code == 200
        portfolio = client.get("/api/v1/trading/paper/portfolio").json()
        assert portfolio["realized_pnl"] == 10
        assert portfolio["positions"][0]["quantity"] == 0.5

        result = client.post("/api/v1/trading/backtests", json={
            "symbol": "ETHUSD", "closes": list(range(100, 140)),
            "fast_window": 2, "slow_window": 5, "initial_cash": 10000
        })
        assert result.status_code == 200
        assert result.json()["report"]["data_points"] == 40
        assert client.get("/api/v1/trading/backtests").status_code == 200


def test_private_routes_require_login(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB", tmp_path / "private.db")
    with TestClient(main.app) as client:
        assert client.get("/api/v1/crm/leads").status_code == 503
        monkeypatch.setenv("SESSION_SECRET", "test-session-secret-that-is-long-enough-123456")
        monkeypatch.setenv("ADMIN_PASSWORD", "strong-test-password-12345")
        monkeypatch.setenv("ADMIN_PASSWORD_SALT", "test-salt-0123456789abcdef")
        monkeypatch.setenv("COOKIE_SECURE", "false")
        assert client.get("/api/v1/crm/leads").status_code == 401
        assert client.post("/api/v1/auth/login", json={"username":"owner","password":"strong-test-password-12345"}).status_code == 200
        assert client.get("/api/v1/crm/leads").status_code == 200
        assert client.post("/api/v1/crm/leads", json={"name":"Blocked"}).status_code == 403
