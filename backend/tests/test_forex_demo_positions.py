"""Regression tests for demo-only read-only MT5 positions."""
import pytest
from fastapi import HTTPException
from app import omonux_forex as forex


@pytest.mark.asyncio
async def test_positions_reads_only_verified_demo(monkeypatch):
    calls = []
    async def fake_get(path, params=None):
        calls.append(path)
        if path == "/v1/accounts":
            return [{"id": "demo12345", "isDemo": True, "broker": "mt5"}]
        if path == "/v1/accounts/demo12345":
            return {"isDemo": True, "broker": "mt5"}
        if path == "/v1/accounts/demo12345/positions":
            return [{"ticket": 123, "symbol": "EURUSD", "side": "BUY", "volume": 0.01,
                     "stopLoss": 1.09, "takeProfit": 1.12, "magic": 0,
                     "password": "must-never-leak"}]
        raise AssertionError(path)
    monkeypatch.setattr(forex, "_tickerall_get", fake_get)
    monkeypatch.setattr(forex, "_account_id", lambda: "demo12345")
    result = await forex.forex_open_positions()
    assert result["count"] == 1
    assert result["positions"][0]["stop_loss"] == 1.09
    assert result["positions"][0]["magic"] == 0
    assert "password" not in str(result)
    assert calls == ["/v1/accounts", "/v1/accounts/demo12345", "/v1/accounts/demo12345/positions"]
    assert result["execution_enabled"] is False


@pytest.mark.asyncio
async def test_live_account_never_reads_positions(monkeypatch):
    calls = []
    async def fake_get(path, params=None):
        calls.append(path)
        return [{"id": "demo12345", "isDemo": False, "broker": "mt5"}]
    monkeypatch.setattr(forex, "_tickerall_get", fake_get)
    monkeypatch.setattr(forex, "_account_id", lambda: "demo12345")
    with pytest.raises(HTTPException) as exc:
        await forex.forex_open_positions()
    assert exc.value.status_code == 422
    assert calls == ["/v1/accounts"]


@pytest.mark.parametrize("payload", [{}, {"positions": None}, {"positions": [{}], "bad": True}, "invalid"])
def test_invalid_positions_fail_closed(payload):
    if isinstance(payload, dict) and isinstance(payload.get("positions"), list):
        assert forex._normalize_demo_positions(payload)[0]["symbol"] is None
    else:
        with pytest.raises(ValueError):
            forex._normalize_demo_positions(payload)


def test_position_response_whitelist_and_numeric_safety():
    rows = forex._normalize_demo_positions({"positions": [{"symbol": "GBPUSD",
        "volume": float("nan"), "profit": float("inf"), "magic": 42,
        "secret": "hidden"}]})
    assert rows[0]["volume"] is None
    assert rows[0]["profit"] is None
    assert rows[0]["magic"] == 42
    assert "secret" not in str(rows)
