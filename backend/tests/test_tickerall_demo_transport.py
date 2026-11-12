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
    with pytest.raises(ValueError, match="stop loss"):
        asyncio.run(broker.submit_demo_market_order(
            "cmwb1b0fi0kaio9012c9azw6n", symbol="EURUSD", side="BUY",
            volume=0.01, idempotency_key=str(uuid.uuid4())))

@pytest.mark.parametrize("pending", [{"orders": [{"ticket": 44}]}, {}, [], {"orders": None}])
def test_pending_or_unverified_orders_block_entry(monkeypatch, pending):
    requests = install_order_broker(monkeypatch, pending=pending)
    with pytest.raises(broker.BrokerUnavailable, match="Pending orders"):
        submit_protected_order()
    assert not any(method == "POST" for method, path in requests)


def install_order_broker(monkeypatch, *, pending=None, position_volume=0.01):
    monkeypatch.setenv("TICKERALL_DEMO_EXECUTION_TRANSPORT", "enabled")
    requests = []
    position_reads = 0
    async def request(method, path, **kwargs):
        nonlocal position_reads
        requests.append((method, path))
        if path == "/v1/accounts/demo12345":
            return {"isDemo": True, "broker": "mt5", "status": "online", "account": {}}
        if path == "/v1/accounts":
            return [{"id": "demo12345", "isDemo": True, "broker": "mt5", "hot": True, "status": "online"}]
        if path.endswith('/positions'):
            position_reads += 1
            return {"positions": [] if position_reads == 1 else [{
                "ticket": 123, "symbol": "EURUSDm", "side": "BUY",
                "volume": position_volume, "stopLoss": 1.09, "takeProfit": 1.12}]}
        if path.endswith('/orders') and method == 'GET':
            return {"orders": []} if pending is None else pending
        if path.endswith('/orders') and method == 'POST':
            return {"status": "open", "ticket": 123}
        raise AssertionError((method, path))
    monkeypatch.setattr(broker, '_request', request)
    return requests


def submit_protected_order():
    return asyncio.run(broker.submit_demo_market_order(
        'demo12345', symbol='EURUSDm', side='BUY', volume=0.01,
        stop_loss=1.09, take_profit=1.12, idempotency_key=str(uuid.uuid4())))


@pytest.mark.parametrize('volume', [0.02, None, True, float('nan')])
def test_unverified_fill_volume_is_not_acknowledged(monkeypatch, volume):
    install_order_broker(monkeypatch, position_volume=volume)
    with pytest.raises(broker.BrokerUnavailable, match='volume'):
        submit_protected_order()


def test_protected_order_confirms_volume_and_stops(monkeypatch):
    requests = install_order_broker(monkeypatch)
    result = submit_protected_order()
    assert result['confirmed_open'] is True
    assert sum(method == 'POST' for method, path in requests) == 1
