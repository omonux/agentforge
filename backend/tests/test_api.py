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


def test_omonux_auto_paper_engine_controls_and_cycle(tmp_path, monkeypatch):
    import asyncio
    monkeypatch.setattr(main, "DB", tmp_path / "auto.db")

    async def fake_candles(symbol, interval="30m", limit=120):
        return [
            {"time": i, "open": 100 + i, "high": 101 + i,
             "low": 99 + i, "close": 100 + i, "volume": 10}
            for i in range(120)
        ]

    monkeypatch.setattr(main, "fetch_candles", fake_candles)
    with TestClient(main.app) as client:
        login(client, monkeypatch)
        status = client.get("/api/v1/trading/auto/status")
        assert status.status_code == 200
        assert status.json()["running"] is False
        assert status.json()["settings"]["mode"] == "paper"

        rejected = client.post("/api/v1/trading/auto/run-once")
        assert rejected.status_code == 409

        config = client.put("/api/v1/trading/auto/config", json={
            "mode": "paper", "risk_percent": 1,
            "min_confidence": 60, "max_open_positions": 2,
            "max_daily_loss_percent": 5, "cooldown_minutes": 0,
            "max_trades_per_day": 5, "max_notional_percent": 25
        })
        assert config.status_code == 200

        started = client.post("/api/v1/trading/auto/start")
        assert started.status_code == 200 and started.json()["running"] is True

        cycle = client.post("/api/v1/trading/auto/run-once")
        assert cycle.status_code == 200
        assert cycle.json()["mode"] == "paper_only"
        assert all(a["action"] == "OPEN_PAPER" for a in cycle.json()["actions"])
        assert len(cycle.json()["actions"]) <= 2

        events = client.get("/api/v1/trading/auto/events").json()
        assert any(e["event_type"] == "PAPER_ENTRY" for e in events)

        stopped = client.post("/api/v1/trading/auto/stop")
        assert stopped.status_code == 200 and stopped.json()["running"] is False


def test_omonux_auto_engine_rejects_live_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB", tmp_path / "auto-live.db")
    with TestClient(main.app) as client:
        login(client, monkeypatch)
        response = client.put("/api/v1/trading/auto/config", json={"mode": "live"})
        assert response.status_code == 400

def test_omonux_chart_scan_validates_upload_and_ai_configuration(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB", tmp_path / "chart.db")
    monkeypatch.delenv("AI_BASE_URL", raising=False)
    monkeypatch.delenv("AI_API_KEY", raising=False)
    monkeypatch.delenv("AI_MODEL", raising=False)
    with TestClient(main.app) as client:
        login(client, monkeypatch)
        bad_type = client.post(
            "/api/v1/trading/chart-scan",
            files={"chart": ("chart.txt", b"not an image", "text/plain")},
        )
        assert bad_type.status_code == 415

        no_provider = client.post(
            "/api/v1/trading/chart-scan",
            files={"chart": ("chart.png", b"fake-png-bytes", "image/png")},
        )
        assert no_provider.status_code == 503


def test_omonux_chart_scan_requires_authentication(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB", tmp_path / "chart-auth.db")
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret-that-is-long-enough-123456")
    monkeypatch.setenv("ADMIN_PASSWORD", "strong-test-password-12345")
    monkeypatch.setenv("ADMIN_PASSWORD_SALT", "test-salt-0123456789abcdef")
    monkeypatch.setenv("COOKIE_SECURE", "false")
    with TestClient(main.app) as client:
        response = client.post(
            "/api/v1/trading/chart-scan",
            files={"chart": ("chart.png", b"fake-png-bytes", "image/png")},
        )
        assert response.status_code == 401

def test_omonux_integration_secrets_are_encrypted_and_never_returned(tmp_path, monkeypatch):
    import sqlite3

    monkeypatch.setattr(main, "DB", tmp_path / "integration-secrets.db")
    monkeypatch.setenv("SECRET_ENCRYPTION_KEY", "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=")
    with TestClient(main.app) as client:
        login(client, monkeypatch)
        saved = client.put("/api/v1/trading/integrations/secrets", json={
            "name": "telegram_bot_token", "value": "123456:private-test-token"
        })
        assert saved.status_code == 200
        assert saved.json() == {
            "saved": True, "name": "telegram_bot_token", "value_returned": False
        }
        status = client.get("/api/v1/trading/integrations/status").json()
        assert status["secrets"]["telegram_bot_token"] is True
        assert status["telegram_ready"] is False
        with sqlite3.connect(main.DB) as conn:
            ciphertext = conn.execute(
                "SELECT ciphertext FROM integration_secrets WHERE name='telegram_bot_token'"
            ).fetchone()[0]
        assert b"123456:private-test-token" not in ciphertext

        deleted = client.delete("/api/v1/trading/integrations/secrets/telegram_bot_token")
        assert deleted.status_code == 200
        assert client.get("/api/v1/trading/integrations/status").json()["secrets"]["telegram_bot_token"] is False


def test_omonux_integration_secrets_fail_closed_without_encryption_key(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB", tmp_path / "integration-no-key.db")
    monkeypatch.delenv("SECRET_ENCRYPTION_KEY", raising=False)
    with TestClient(main.app) as client:
        login(client, monkeypatch)
        response = client.put("/api/v1/trading/integrations/secrets", json={
            "name": "binance_api_key", "value": "never-store-this-in-plaintext"
        })
        assert response.status_code == 503
        assert client.get("/api/v1/trading/integrations/status").json()["encryption_configured"] is False


def test_omonux_telegram_test_requires_saved_credentials(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB", tmp_path / "telegram-test.db")
    monkeypatch.setenv("SECRET_ENCRYPTION_KEY", "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=")
    with TestClient(main.app) as client:
        login(client, monkeypatch)
        response = client.post("/api/v1/trading/integrations/telegram/test")
        assert response.status_code == 409



def test_omonux_exchange_testnet_requires_saved_credentials(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB", tmp_path / "exchange-testnet.db")
    monkeypatch.setenv("SECRET_ENCRYPTION_KEY", "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=")
    with TestClient(main.app) as client:
        login(client, monkeypatch)
        binance = client.post("/api/v1/trading/exchanges/binance/test")
        bybit = client.post("/api/v1/trading/exchanges/bybit/test")
        assert binance.status_code == 409
        assert bybit.status_code == 409
        assert "Save both Binance" in binance.json()["detail"]
        assert "Save both Bybit" in bybit.json()["detail"]


def test_omonux_exchange_testnet_signatures_are_deterministic():
    from app.omonux_exchange_testnet import binance_signature, bybit_signature

    params = {"recvWindow": "5000", "timestamp": "1700000000000"}
    first = binance_signature("test-secret", params)
    assert first == binance_signature("test-secret", params)
    assert len(first) == 64
    signature = bybit_signature("test-secret", "1700000000000", "test-key", "accountType=UNIFIED")
    assert signature == bybit_signature("test-secret", "1700000000000", "test-key", "accountType=UNIFIED")
    assert len(signature) == 64

def test_omonux_daily_loss_gate_includes_unrealized_open_position_loss(tmp_path, monkeypatch):
    from datetime import datetime, timezone

    monkeypatch.setattr(main, "DB", tmp_path / "mark-to-market.db")

    async def losing_market(symbol, interval="30m", limit=120):
        return [
            {"time": i, "open": 100, "high": 101, "low": 99, "close": 100, "volume": 10}
            for i in range(60)
        ]

    monkeypatch.setattr(main, "fetch_candles", losing_market)
    with TestClient(main.app) as client:
        login(client, monkeypatch)
        started = client.post("/api/v1/trading/auto/start")
        assert started.status_code == 200
        with main.db() as conn:
            conn.execute(
                "INSERT INTO auto_trade_positions VALUES(?,?,?,?,?,?,?,?)",
                ("losing-position", "BTCUSDT", "BUY", 100, 200, 150, 300,
                 datetime.now(timezone.utc).isoformat()),
            )

        cycle = client.post("/api/v1/trading/auto/run-once")
        assert cycle.status_code == 409
        assert "including open-position losses" in cycle.json()["detail"]
        assert client.get("/api/v1/trading/auto/status").json()["running"] is False
        events = client.get("/api/v1/trading/auto/events").json()
        assert any(
            event["event_type"] == "RISK_BLOCK"
            and "unrealized P&L" in (event["details"] or "")
            for event in events
        )

def test_omonux_paper_portfolio_reports_mark_to_market_pnl(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB", tmp_path / "paper-mark.db")

    async def market(symbol, interval="30m", limit=120):
        return [
            {"time": i, "open": 120, "high": 121, "low": 119, "close": 120, "volume": 10}
            for i in range(60)
        ]

    monkeypatch.setattr(main, "fetch_candles", market)
    with TestClient(main.app) as client:
        login(client, monkeypatch)
        with main.db() as conn:
            conn.execute(
                "INSERT INTO paper_trades VALUES(?,?,?,?,?,?)",
                ("paper-buy-1", "BTCUSDT", "buy", 2, 100, main.stamp()),
            )
        response = client.get("/api/v1/trading/paper/portfolio")
        assert response.status_code == 200
        data = response.json()
        assert data["mark_to_market_complete"] is True
        assert data["realized_pnl"] == 0
        assert data["unrealized_pnl"] == 40
        assert data["total_pnl"] == 40
        assert data["positions"][0]["mark_price"] == 120



def test_live_exchange_account_routes_require_separate_live_credentials(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB", tmp_path / "live-account.db")
    with TestClient(main.app) as client:
        login(client, monkeypatch)
        binance = client.post("/api/v1/trading/live-account/binance")
        bybit = client.post("/api/v1/trading/live-account/bybit")
        assert binance.status_code == 409
        assert bybit.status_code == 409
        assert "LIVE" in binance.json()["detail"]
        assert "LIVE" in bybit.json()["detail"]


def test_live_exchange_signatures_are_sha256_hex():
    from app.omonux_live_account import binance_live_signature, bybit_live_signature
    assert len(binance_live_signature("secret", {"timestamp": "123", "recvWindow": "5000"})) == 64
    assert len(bybit_live_signature("secret", "123", "key", "accountType=UNIFIED")) == 64


def test_trading_emergency_stop_is_latched_until_explicit_reset(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB", tmp_path / "safety.db")
    with TestClient(main.app) as client:
        login(client, monkeypatch)
        stopped = client.post("/api/v1/trading/safety/emergency-stop", json={
            "reason": "Operator detected unexpected behaviour"
        })
        assert stopped.status_code == 200
        assert stopped.json()["emergency_stopped"] is True
        assert stopped.json()["scope"] == "paper automatic trading engine only"
        assert client.post("/api/v1/trading/auto/start").status_code == 423
        assert client.post("/api/v1/trading/auto/run-once").status_code == 423
        assert client.post("/api/v1/trading/safety/reset", json={
            "confirmation": "wrong phrase"
        }).status_code == 400
        reset = client.post("/api/v1/trading/safety/reset", json={
            "confirmation": "RESET TRADING SAFETY"
        })
        assert reset.status_code == 200
        assert reset.json()["emergency_stopped"] is False
        assert client.get("/api/v1/trading/auto/status").json()["running"] is False


def test_live_execution_is_disabled_and_emergency_stopped_by_default(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB", tmp_path / "live-execution.db")
    monkeypatch.delenv("LIVE_TRADING_ENABLED", raising=False)
    with TestClient(main.app) as client:
        login(client, monkeypatch)
        status = client.get("/api/v1/trading/live/status")
        assert status.status_code == 200
        assert status.json()["feature_enabled"] is False
        assert status.json()["emergency_stopped"] is True
        blocked = client.post("/api/v1/trading/live/binance/place", json={
            "preview_id": "00000000-0000-0000-0000-000000000000",
            "confirmation": "PLACE LIVE BUY BTCUSDT",
        })
        assert blocked.status_code == 423
        reset = client.post("/api/v1/trading/live/reset", json={
            "confirmation": "RESET LIVE TRADING SAFETY"
        })
        assert reset.status_code == 423


def test_live_execution_preview_requires_separate_live_credentials(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB", tmp_path / "live-preview.db")
    with TestClient(main.app) as client:
        login(client, monkeypatch)
        response = client.post("/api/v1/trading/live/binance/preview", json={
            "symbol": "BTCUSDT", "side": "BUY", "quantity": "0.0001"
        })
        assert response.status_code == 409


def test_live_ops_analytics_and_alerts_are_safe_by_default(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB", tmp_path / "live-ops.db")
    with TestClient(main.app) as client:
        login(client, monkeypatch)
        analytics = client.get("/api/v1/trading/live-ops/analytics")
        assert analytics.status_code == 200
        assert analytics.json()["orders_included"] == 0
        prefs = client.get("/api/v1/trading/live-ops/alerts/preferences")
        assert prefs.status_code == 200
        assert prefs.json()["enabled"] is False
        disabled = client.post("/api/v1/trading/live-ops/bybit/preview", json={
            "symbol": "BTCUSDT", "side": "BUY", "quantity": "0.001"
        })
        assert disabled.status_code == 423


def test_live_ops_alerts_require_explicit_opt_in(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB", tmp_path / "live-alerts.db")
    with TestClient(main.app) as client:
        login(client, monkeypatch)
        response = client.put("/api/v1/trading/live-ops/alerts/preferences", json={
            "enabled": False, "on_fill": True, "on_partial": True,
            "on_reject": True, "on_risk_stop": True
        })
        assert response.status_code == 200
        assert response.json()["enabled"] is False
