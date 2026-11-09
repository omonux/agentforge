"""Authenticated historical backtest API tests: real feed is mocked for repeatability."""
from fastapi.testclient import TestClient
from app import main


def candles(n=120):
    return [{"time":i*900000,"open":100+i*.3,"high":101+i*.3,
             "low":99+i*.3,"close":100+i*.3,"volume":1000} for i in range(n)]


def test_backtest_requires_login(tmp_path,monkeypatch):
    monkeypatch.setattr(main,"DB",tmp_path/"backtest.db")
    with TestClient(main.app) as client:
        response=client.post("/api/v1/trading/backtest",json={"symbol":"BTCUSDT","interval":"15m"})
        assert response.status_code in (401,503)


def test_backtest_endpoint_uses_closed_candles_and_no_orders(tmp_path,monkeypatch):
    monkeypatch.setattr(main,"DB",tmp_path/"backtest.db")
    monkeypatch.setenv("SESSION_SECRET","test-session-secret-that-is-long-enough-123456")
    monkeypatch.setenv("ADMIN_PASSWORD","strong-test-password-12345")
    monkeypatch.setenv("ADMIN_PASSWORD_SALT","test-salt-0123456789abcdef")
    monkeypatch.setenv("COOKIE_SECURE","false")
    seen=[]
    async def fake_fetch(symbol,interval,limit):
        seen.append((symbol,interval,limit))
        return candles()
    monkeypatch.setattr(main,"fetch_candles",fake_fetch)
    with TestClient(main.app) as client:
        login=client.post("/api/v1/auth/login",json={"username":"owner","password":"strong-test-password-12345"})
        assert login.status_code==200
        client.headers.update({"X-CSRF-Token":client.cookies["agentforge_csrf"]})
        response=client.post("/api/v1/trading/backtest",json={"symbol":"BTCUSDT","interval":"15m","fee_bps":10,"slippage_bps":5})
        assert response.status_code==200,response.text
        body=response.json()
        assert body["mode"]=="historical_research_only"
        assert body["interval"]=="15m"
        assert body["candles"]==120
        assert body["fee_bps"]==10
        assert seen==[("BTCUSDT","15m",500)]
        assert client.post("/api/v1/trading/backtest",json={"symbol":"ETHUSDT"}).status_code==422
