import asyncio

import pytest
from fastapi import HTTPException

from app import omonux_forex


def test_auto_protect_requires_explicit_confirmation(monkeypatch):
    async def fail_if_called(*args, **kwargs):
        raise AssertionError("No broker request should be made before confirmation")

    monkeypatch.setattr(omonux_forex, "_tickerall_get", fail_if_called)
    with pytest.raises(HTTPException) as error:
        asyncio.run(omonux_forex.auto_protect_existing_demo_position(
            omonux_forex.DemoAutoProtectRequest(ticket="123", confirmation=False)))
    assert error.value.status_code == 422


def test_auto_protect_sets_both_levels_and_requires_broker_readback(monkeypatch):
    account_id = "demo_account_12345678"
    position = {"ticket": "123", "symbol": "EURUSDm", "side": "BUY",
                "volume": 0.1, "openPrice": 1.1, "stopLoss": 0, "takeProfit": 0}
    protected = {**position, "stopLoss": 1.0998, "takeProfit": 1.101}
    calls = {"positions": 0, "patch": None}

    async def ticker_get(path):
        if path == "/v1/accounts":
            return [{"id": account_id, "isDemo": True, "broker": "mt5",
                     "hot": True, "status": "online"}]
        if path == f"/v1/accounts/{account_id}/positions":
            calls["positions"] += 1
            return [position if calls["positions"] == 1 else protected]
        if path.endswith("/EURUSDm/quote"):
            return {"symbol": "EURUSDm", "bid": 1.1002, "ask": 1.1003}
        if path.endswith("/EURUSDm/spec"):
            return {"spec": {"name": "EURUSDm", "specSource": "broker",
                              "tickSize": 0.00001, "tickValueAccount": 1,
                              "point": 0.00001, "stopLevel": 0}}
        raise AssertionError(f"Unexpected broker read: {path}")

    async def get_account(_account):
        return {"isDemo": True, "broker": "mt5", "status": "online",
                "account": {"equity": "10000", "currency": "USD"}}

    async def request(method, path, *, payload=None, idempotency_key=None):
        assert method == "PATCH"
        assert path == f"/v1/accounts/{account_id}/positions/123"
        assert idempotency_key
        calls["patch"] = payload
        return {"updated": True}

    monkeypatch.setattr(omonux_forex, "_account_id", lambda: account_id)
    monkeypatch.setattr(omonux_forex, "_tickerall_get", ticker_get)
    monkeypatch.setattr("app.tickerall_demo_transport.get_demo_account", get_account)
    monkeypatch.setattr("app.tickerall_demo_transport._request", request)
    result = asyncio.run(omonux_forex.auto_protect_existing_demo_position(
        omonux_forex.DemoAutoProtectRequest(ticket="123", confirmation=True)))

    assert calls["patch"] == {"stopLoss": 1.0998, "takeProfit": 1.101}
    assert calls["positions"] == 2
    assert result["confirmed"] is True
    assert float(result["risk_amount_usd"]) == 4.0
    assert result["stop_loss"] == 1.0998
    assert result["take_profit"] == 1.101
