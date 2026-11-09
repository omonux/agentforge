"""Paper decision explanations must reflect recorded audit events."""
from fastapi.testclient import TestClient
from app import main


def test_diagnostics_requires_login(tmp_path,monkeypatch):
    monkeypatch.setattr(main,"DB",tmp_path/"diag.db")
    with TestClient(main.app) as client:
        response=client.get("/api/v1/trading/auto/diagnostics")
        assert response.status_code in (401,503)


def test_diagnostics_returns_real_audit_events(tmp_path,monkeypatch):
    monkeypatch.setattr(main,"DB",tmp_path/"diag.db")
    monkeypatch.setenv("SESSION_SECRET","test-session-secret-that-is-long-enough-123456")
    monkeypatch.setenv("ADMIN_PASSWORD","strong-test-password-12345")
    monkeypatch.setenv("ADMIN_PASSWORD_SALT","test-salt-0123456789abcdef")
    monkeypatch.setenv("COOKIE_SECURE","false")
    with TestClient(main.app) as client:
        login=client.post("/api/v1/auth/login",json={"username":"owner","password":"strong-test-password-12345"})
        assert login.status_code==200
        main.auto_event("RISK_BLOCK","BTCUSDT","Technical signal is HOLD; no BUY or SELL setup")
        response=client.get("/api/v1/trading/auto/diagnostics")
        assert response.status_code==200,response.text
        result=response.json()
        assert result["latest_outcome"]["type"]=="RISK_BLOCK"
        assert "HOLD" in result["latest_outcome"]["reason"]
        assert result["paper_positions"]==0
