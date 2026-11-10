"""No-network tests for session and broker stop-loss validation."""
from dataclasses import replace
import asyncio
import pytest
from app import forex_demo_preflight as p

ACCOUNT_ID = "cmwb1b0fi0kaio9012c9azw6n"
ACCOUNT = {"isDemo": True, "broker": "mt5", "status": "online",
           "account": {"equity": 10000, "freeMargin": 9000}, "positions": []}
ROSTER = [{"id": ACCOUNT_ID, "isDemo": True, "broker": "mt5",
           "status": "CONNECTED", "hot": True}]
SPEC = {"name": "EURUSD", "specSource": "broker", "point": 0.00001,
        "tickSize": 0.00001, "tickValueAccount": 1,
        "volumeMin": 0.01, "volumeMax": 100, "volumeStep": 0.01,
        "stopLevel": 10}
QUOTE = {"symbol": "EURUSD", "bid": 1.10000, "ask": 1.10010}

def test_ready_session_does_not_claim_order_permission():
    result = p.validate_session(ACCOUNT, ROSTER, ACCOUNT_ID)
    assert result["session_ready"] is True
    assert result["trading_permission_verified"] is False

@pytest.mark.parametrize("account,roster", [
    ({**ACCOUNT, "status": "offline"}, ROSTER),
    (ACCOUNT, [{**ROSTER[0], "hot": False}]),
    (ACCOUNT, [{**ROSTER[0], "isDemo": False}]),
    ({**ACCOUNT, "broker": "mt4"}, ROSTER),
    ({**ACCOUNT, "positions": [{"ticket": 1}]}, ROSTER),
    ({**ACCOUNT, "account": {"equity": None, "freeMargin": 9000}}, ROSTER),
])
def test_session_fails_closed(account, roster):
    with pytest.raises(p.PreflightRejected):
        p.validate_session(account, roster, ACCOUNT_ID)

def test_valid_stop_geometry_is_preflight_only():
    result = p.validate_protective_stop(SPEC, QUOTE, side="BUY", stop_loss=1.09980)
    assert result["protective_stop_payload_supported"]
    assert not result["stop_installed_at_broker"]
    assert not result["trade_authorized"]

@pytest.mark.parametrize("spec,quote,side,stop", [
    (SPEC, QUOTE, "BUY", 1.10000),
    (SPEC, QUOTE, "SELL", 1.10010),
    (SPEC, QUOTE, "BUY", 1.09995),
    (SPEC, QUOTE, "BUY", 1.099805),
    ({**SPEC, "stopLevel": None}, QUOTE, "BUY", 1.09980),
    ({**SPEC, "specSource": "cache"}, QUOTE, "BUY", 1.09980),
    ({**SPEC, "tickValueAccount": None}, QUOTE, "BUY", 1.09980),
    (SPEC, {**QUOTE, "ask": None}, "BUY", 1.09980),
])
def test_stop_validation_fails_closed(spec, quote, side, stop):
    with pytest.raises(p.PreflightRejected):
        p.validate_protective_stop(spec, quote, side=side, stop_loss=stop)

def test_read_only_preflight_makes_only_get_requests(monkeypatch):
    seen = []
    async def fake(path):
        seen.append(path)
        if path == "/v1/accounts":
            return ROSTER
        if path.endswith("/spec"):
            return {"spec": SPEC}
        if path.endswith("/quote"):
            return QUOTE
        if path.endswith("/symbols"):
            return {"symbols": ["EURUSD"]}
        return ACCOUNT
    monkeypatch.setattr(p, "_read", fake)
    result = asyncio.run(p.read_only_demo_preflight(ACCOUNT_ID, "EURUSD", "BUY", 1.09980))
    assert result["execution_enabled"] is False
    assert len(seen) == 5
    assert all(path.startswith("/v1/accounts") for path in seen)

def test_protected_order_preview_requires_nonzero_stop():
    payload = p.build_protected_order_preview(symbol="EURUSD", side="BUY",
                                              volume="0.01", stop_loss="1.09980")
    assert payload["stopLoss"] == 1.09980
    assert payload["type"] == "market"
    with pytest.raises(p.PreflightRejected):
        p.build_protected_order_preview(symbol="EURUSD", side="BUY",
                                        volume="0.01", stop_loss=0)
