"""Forex MT5/MetaApi read-only safety tests; no network or broker credentials."""
from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient
from app.omonux_forex import Quote, validate_quote, paper_plan
from app.main import app


def quote(symbol="EURUSD", bid=1.10000, ask=1.10010, age=0):
    return Quote(symbol=symbol,bid=bid,ask=ask,
                 timestamp=datetime.now(timezone.utc)-timedelta(seconds=age))


def test_valid_quote_and_spread():
    assert validate_quote(quote())["spread_pips"] == pytest.approx(1)


def test_reject_stale_crossed_and_wide_quotes():
    with pytest.raises(ValueError,match="stale"):
        validate_quote(quote(age=45))
    with pytest.raises(ValueError,match="bid/ask"):
        validate_quote(quote(ask=1.0999))
    with pytest.raises(ValueError,match="spread"):
        validate_quote(quote(ask=1.1005))


def test_forex_paper_plan_no_leverage_or_orders():
    p=paper_plan(quote(),side="BUY",stop_pips=20,confidence=90)
    assert p["execution"]=="no_order_placed"
    assert p["mode"]=="paper_preview_only"
    assert p["units"]*p["entry"]<=10.000001
    assert p["stop"]<p["entry"]<p["target"]
    with pytest.raises(ValueError,match="confidence"):
        paper_plan(quote(),side="BUY",stop_pips=20,confidence=60)


def test_jpy_and_short():
    p=paper_plan(quote("USDJPY",bid=150.00,ask=150.01),side="SELL",
                 stop_pips=20,confidence=90)
    assert p["target"]<p["entry"]<p["stop"]
    assert p["units"]*p["entry"]<=10.000001


def test_status_no_secrets(monkeypatch):
    monkeypatch.setenv("TICKERALL_API_KEY","sensitive-test-token")
    monkeypatch.setenv("TICKERALL_ACCOUNT_ID","acc_example123")
    from app.omonux_forex import forex_status
    status = forex_status()
    assert status["feed_configured"] is True
    assert status["account_configured"] is True
    assert status["execution_enabled"] is False
    assert "sensitive-test-token" not in str(status)


def test_real_tickerall_account_id(monkeypatch):
    from app.omonux_forex import _account_id, forex_status
    monkeypatch.setenv("TICKERALL_ACCOUNT_ID", "cmwb1b0fi0kaio9012c9azw6n")
    assert _account_id() == "cmwb1b0fi0kaio9012c9azw6n"
    assert forex_status()["account_configured"] is True


def test_account_id_validation(monkeypatch):
    from app.omonux_forex import _account_id
    monkeypatch.setenv("TICKERALL_ACCOUNT_ID","https://evil.example")
    with pytest.raises(ValueError,match="TICKERALL_ACCOUNT_ID"):
        _account_id()


def test_tickerall_auth_header_and_read_only(monkeypatch):
    import asyncio
    import httpx
    from app.omonux_forex import _tickerall_get
    seen=[]
    async def fake_get(self,url,params=None,headers=None):
        seen.append((url,params,headers))
        return httpx.Response(200,json=[],request=httpx.Request("GET",url))
    monkeypatch.setenv("TICKERALL_API_KEY","secret-test-token")
    monkeypatch.setattr(httpx.AsyncClient,"get",fake_get)
    assert asyncio.run(_tickerall_get("/v1/accounts"))==[]
    assert seen[0][0]=="https://api.tickerall.com/v1/accounts"
    assert seen[0][2]["Authorization"]=="Bearer secret-test-token"
    assert len(seen)==1


def test_tickerall_rejects_cold_session(monkeypatch):
    import asyncio
    import httpx
    from app.omonux_forex import _tickerall_get
    async def fake_get(self,url,params=None,headers=None):
        return httpx.Response(409,request=httpx.Request("GET",url))
    monkeypatch.setenv("TICKERALL_API_KEY","test-token")
    monkeypatch.setattr(httpx.AsyncClient,"get",fake_get)
    with pytest.raises(ValueError,match="cold"):
        asyncio.run(_tickerall_get("/v1/accounts"))
