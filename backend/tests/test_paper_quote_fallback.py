"""Fallback and fail-closed tests for $5 paper position monitoring."""
import pytest
import httpx
from app import omonux_fast_monitor as monitor


@pytest.mark.asyncio
async def test_fallback_host_recovers_public_quote(monkeypatch):
    calls=[]
    class Response:
        def __init__(self, price): self.price=price
        def raise_for_status(self): pass
        def json(self): return {"symbol":"UNIUSDT","price":self.price}
    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def get(self, url, params):
            calls.append(url)
            if "api.binance.com" in url:
                raise httpx.ConnectError("primary unavailable")
            return Response("6.95")
    monkeypatch.setattr(monitor.httpx,"AsyncClient",Client)
    assert await monitor.fetch_fresh_prices(["UNIUSDT"])=={"UNIUSDT":6.95}
    assert len(calls)==2


@pytest.mark.asyncio
async def test_both_hosts_fail_closed(monkeypatch):
    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def get(self, url, params): raise httpx.ConnectError("unavailable")
    monkeypatch.setattr(monitor.httpx,"AsyncClient",Client)
    assert await monitor.fetch_fresh_prices(["UNIUSDT"])=={}


@pytest.mark.asyncio
async def test_rejects_invalid_quote_and_symbol(monkeypatch):
    class Response:
        def raise_for_status(self): pass
        def json(self): return {"symbol":"OTHER","price":"nan"}
    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def get(self, url, params): return Response()
    monkeypatch.setattr(monitor.httpx,"AsyncClient",Client)
    assert await monitor.fetch_fresh_prices(["UNIUSDT","../../etc"])=={}
