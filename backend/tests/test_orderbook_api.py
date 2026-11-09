"""Authenticated read-only order-book research API regression tests."""
from fastapi.testclient import TestClient
from app import main


def test_orderbook_research_requires_auth(tmp_path,monkeypatch):
    monkeypatch.setattr(main,"DB",tmp_path/"books.db")
    with TestClient(main.app) as client:
        response=client.post("/api/v1/trading/orderbook/research",json={"symbols":["BTCUSDT"]})
        assert response.status_code in (401,503)


def test_orderbook_research_is_authenticated_and_bounded(tmp_path,monkeypatch):
    monkeypatch.setattr(main,"DB",tmp_path/"books.db")
    monkeypatch.setenv("SESSION_SECRET","test-session-secret-that-is-long-enough-123456")
    monkeypatch.setenv("ADMIN_PASSWORD","strong-test-password-12345")
    monkeypatch.setenv("ADMIN_PASSWORD_SALT","test-salt-0123456789abcdef")
    monkeypatch.setenv("COOKIE_SECURE","false")
    calls=[]
    async def fake_scan(symbols,**kwargs):
        calls.append((symbols,kwargs))
        return {"markets":[{"symbol":"BTCUSDT","executable":False}],"market_count":1,
                "execution":"research_only_no_orders","checked_at_unix_ms":123,"notice":"Research only"}
    monkeypatch.setattr(main,"scan_live_books",fake_scan)
    with TestClient(main.app) as client:
        login=client.post("/api/v1/auth/login",json={"username":"owner","password":"strong-test-password-12345"})
        assert login.status_code==200
        client.headers.update({"X-CSRF-Token":client.cookies["agentforge_csrf"]})
        response=client.post("/api/v1/trading/orderbook/research",json={"symbols":["BTCUSDT"],"fee_bps":25})
        assert response.status_code==200,response.text
        assert response.json()["execution"]=="research_only_no_orders"
        assert calls==[(["BTCUSDT"],{"fee_bps":25.0,"slippage_bps":10.0,"extra_cost_bps":5.0})]
        assert client.post("/api/v1/trading/orderbook/research",json={"symbols":[]}).status_code==422
        assert client.post("/api/v1/trading/orderbook/research",json={"fee_bps":-1}).status_code==422
