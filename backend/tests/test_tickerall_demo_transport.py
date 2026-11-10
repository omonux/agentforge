"""No real broker requests; transport stays disconnected from API routes."""
import asyncio
import uuid
import pytest
from app import tickerall_demo_transport as broker

def test_demo_transport_requires_explicit_permission(monkeypatch):
    monkeypatch.delenv("TICKERALL_DEMO_EXECUTION_TRANSPORT", raising=False)
    with pytest.raises(broker.BrokerUnavailable, match="not authorized"):
        asyncio.run(broker.submit_demo_market_order("cmwb1b0fi0kaio9012c9azw6n",
                    symbol="EURUSD", side="BUY", volume=.01,
                    idempotency_key=str(uuid.uuid4())))

def test_no_live_account_accepted(monkeypatch):
    async def live(_):
        return {"account": {"isDemo": False, "is_demo": False}}
    monkeypatch.setattr(broker, "_request", lambda *args, **kwargs: live(args))
    with pytest.raises(broker.BrokerUnavailable, match="demo"):
        asyncio.run(broker.get_demo_account("cmwb1b0fi0kaio9012c9azw6n"))

def test_invalid_account_identifier():
    with pytest.raises(ValueError, match="account ID"):
        broker._id("../sessions")

def test_invalid_order_arguments_fail_before_broker_call(monkeypatch):
    monkeypatch.setenv("TICKERALL_DEMO_EXECUTION_TRANSPORT", "enabled")
    for kwargs in ({"symbol": "../evil", "side": "BUY", "volume": .01},
                   {"symbol": "EURUSD", "side": "HOLD", "volume": .01},
                   {"symbol": "EURUSD", "side": "BUY", "volume": 0}):
        with pytest.raises(ValueError):
            asyncio.run(broker.submit_demo_market_order(
                "cmwb1b0fi0kaio9012c9azw6n",
                idempotency_key=str(uuid.uuid4()), **kwargs))

def test_root_demo_flag_is_accepted(monkeypatch):
    async def demo(*args, **kwargs):
        return {"isDemo": True, "account": {"currency": "USD"}}
    monkeypatch.setattr(broker, "_request", demo)
    data = asyncio.run(broker.get_demo_account("cmwb1b0fi0kaio9012c9azw6n"))
    assert data["isDemo"] is True

def test_unverified_demo_flag_fails_closed(monkeypatch):
    async def unknown(*args, **kwargs):
        return {"account": {"currency": "USD"}}
    monkeypatch.setattr(broker, "_request", unknown)
    with pytest.raises(broker.BrokerUnavailable, match="demo"):
        asyncio.run(broker.get_demo_account("cmwb1b0fi0kaio9012c9azw6n"))

def test_even_enabled_transport_never_submits_unprotected_order(monkeypatch):
    monkeypatch.setenv("TICKERALL_DEMO_EXECUTION_TRANSPORT", "enabled")
    async def forbidden(*args, **kwargs):
        raise AssertionError("Broker network request must not happen")
    monkeypatch.setattr(broker, "_request", forbidden)
    with pytest.raises(broker.BrokerUnavailable, match="stop loss"):
        asyncio.run(broker.submit_demo_market_order(
            "cmwb1b0fi0kaio9012c9azw6n", symbol="EURUSD", side="BUY",
            volume=0.01, idempotency_key=str(uuid.uuid4())))
