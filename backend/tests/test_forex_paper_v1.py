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
    monkeypatch.setenv("METAAPI_TOKEN","sensitive-test-token")
    monkeypatch.setenv("METAAPI_ACCOUNT_ID","secret-account")
    monkeypatch.setenv("METAAPI_PRICE_URL_TEMPLATE","https://mt-client-api-v1.new-york.agiliumtrade.ai/x/{account_id}/{symbol}")
    r=TestClient(app).get("/api/v1/trading/forex/status")
    assert r.status_code==200
    assert r.json()["execution_enabled"] is False
    assert "sensitive-test-token" not in r.text
    assert "secret-account" not in r.text
