"""Regression tests for demo-only read-only MT5 positions."""
import pytest
import asyncio
from fastapi import HTTPException
from app import omonux_forex as forex


def test_positions_reads_only_verified_demo(monkeypatch):
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
    result = asyncio.run(forex.forex_open_positions())
    assert result["count"] == 1
    assert result["positions"][0]["stop_loss"] == 1.09
    assert result["positions"][0]["magic"] == 0
    assert "password" not in str(result)
    assert calls == ["/v1/accounts", "/v1/accounts/demo12345", "/v1/accounts/demo12345/positions"]
    assert result["execution_enabled"] is False


def test_live_account_never_reads_positions(monkeypatch):
    calls = []
    async def fake_get(path, params=None):
        calls.append(path)
        return [{"id": "demo12345", "isDemo": False, "broker": "mt5"}]
    monkeypatch.setattr(forex, "_tickerall_get", fake_get)
    monkeypatch.setattr(forex, "_account_id", lambda: "demo12345")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(forex.forex_open_positions())
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


@pytest.mark.parametrize("entry_key", ["openPrice", "priceOpen", "price_open", "entryPrice", "price"])
def test_entry_price_aliases(entry_key):
    row = forex._normalize_demo_positions([{"symbol": "EURUSD", entry_key: "1.12345"}])[0]
    assert row["open_price"] == 1.12345


@pytest.mark.parametrize("sl_key,tp_key", [
    ("stopLoss", "takeProfit"), ("sl", "tp"), ("stop_loss", "take_profit"),
    ("stopLossPrice", "takeProfitPrice")
])
def test_broker_stop_aliases(sl_key, tp_key):
    row = forex._normalize_demo_positions([{sl_key: "1.09", tp_key: "1.13"}])[0]
    assert row["stop_loss_status"] == "set"
    assert row["take_profit_status"] == "set"
    assert row["stop_loss"] == 1.09


def test_unknown_stop_is_not_claimed_unprotected():
    row = forex._normalize_demo_positions([{"symbol": "EURUSD"}])[0]
    assert row["stop_loss_status"] == "unknown"
    assert row["stop_loss"] is None


def test_explicit_zero_stop_is_not_set():
    row = forex._normalize_demo_positions([{"sl": 0, "tp": "0"}])[0]
    assert row["stop_loss_status"] == "not_set"
    assert row["take_profit_status"] == "not_set"


def test_malformed_stop_is_unknown():
    row = forex._normalize_demo_positions([{"sl": "invalid", "tp": -1}])[0]
    assert row["stop_loss_status"] == "unknown"
    assert row["take_profit_status"] == "unknown"
