"""Offline tests for TickerAll's documented full-close contract."""
import asyncio
import uuid

import pytest

from app import tickerall_demo_transport as transport


ACCOUNT_ID = "demo_account_12345678"
TICKET = "123456789"


def test_full_close_uses_idempotent_position_delete_and_broker_readback(monkeypatch):
    position = {"ticket": TICKET, "symbol": "EURUSDm", "side": "BUY", "volume": 0.01}
    calls = []
    position_reads = 0

    async def get_account(_account_id):
        return {"isDemo": True, "broker": "mt5", "status": "online"}

    async def request(method, path, *, payload=None, idempotency_key=None):
        nonlocal position_reads
        calls.append((method, path, payload, idempotency_key))
        if method == "GET" and path == "/v1/accounts":
            return [{"id": ACCOUNT_ID, "isDemo": True, "broker": "mt5",
                     "hot": True, "status": "online"}]
        if method == "GET" and path == f"/v1/accounts/{ACCOUNT_ID}/positions":
            position_reads += 1
            return [position] if position_reads == 1 else []
        if method == "DELETE":
            return {"ticket": TICKET, "closed": True,
                    "dealTicket": "998", "profit": 0.12}
        raise AssertionError(f"Unexpected broker request: {method} {path}")

    key = str(uuid.uuid4())
    monkeypatch.setenv("TICKERALL_DEMO_CLOSE_TRANSPORT", "enabled")
    monkeypatch.setattr(transport, "get_demo_account", get_account)
    monkeypatch.setattr(transport, "_request", request)

    result = asyncio.run(transport.close_demo_position_verified(
        ACCOUNT_ID, ticket=TICKET, idempotency_key=key
    ))

    assert result["confirmed_closed"] is True
    assert result["ticket"] == TICKET
    assert result["mode"] == "demo"
    assert [call[:2] for call in calls] == [
        ("GET", "/v1/accounts"),
        ("GET", f"/v1/accounts/{ACCOUNT_ID}/positions"),
        ("DELETE", f"/v1/accounts/{ACCOUNT_ID}/positions/{TICKET}"),
        ("GET", f"/v1/accounts/{ACCOUNT_ID}/positions"),
    ]
    close_call = calls[2]
    assert close_call[2] is None  # No volume means a full close.
    assert close_call[3] == key


def test_full_close_fails_if_ticket_remains_in_broker_readback(monkeypatch):
    position = {"ticket": TICKET, "symbol": "EURUSDm", "side": "BUY", "volume": 0.01}
    calls = []
    position_reads = 0

    async def get_account(_account_id):
        return {"isDemo": True, "broker": "mt5", "status": "online"}

    async def request(method, path, *, payload=None, idempotency_key=None):
        nonlocal position_reads
        calls.append((method, path))
        if method == "GET" and path == "/v1/accounts":
            return [{"id": ACCOUNT_ID, "isDemo": True, "broker": "mt5",
                     "hot": True, "status": "online"}]
        if method == "GET" and path == f"/v1/accounts/{ACCOUNT_ID}/positions":
            position_reads += 1
            return [position]
        if method == "DELETE":
            return {"ticket": TICKET, "closed": True}
        raise AssertionError(f"Unexpected broker request: {method} {path}")

    monkeypatch.setenv("TICKERALL_DEMO_CLOSE_TRANSPORT", "enabled")
    monkeypatch.setattr(transport, "get_demo_account", get_account)
    monkeypatch.setattr(transport, "_request", request)

    with pytest.raises(transport.BrokerUnavailable, match="ticket remains"):
        asyncio.run(transport.close_demo_position_verified(
            ACCOUNT_ID, ticket=TICKET,
            idempotency_key="9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d"
        ))

    assert len([call for call in calls if call[0] == "DELETE"]) == 1
    assert position_reads == 2
