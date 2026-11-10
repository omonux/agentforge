"""Binance 429 regression tests: coalescing, cooldown and recovery (no network)."""
import asyncio
import httpx
import pytest
from app import omonux_engine as engine


def setup_function():
    engine._CANDLE_CACHE.clear()
    engine._CANDLE_TASKS.clear()
    engine._BINANCE_COOLDOWN_UNTIL = 0.0


def candles():
    return [[i * 1800000, "1", "2", "0.5", "1.5", "100",
             (i + 1) * 1800000 - 1] for i in range(40)]


def test_concurrent_requests_share_single_http_call(monkeypatch):
    calls = []
    async def fake_get(self, url, params):
        calls.append((url, params))
        await asyncio.sleep(0.01)
        return httpx.Response(200, json=candles(), request=httpx.Request("GET", url))
    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    async def run():
        return await asyncio.gather(*(engine.fetch_candles("LINKUSDT") for _ in range(12)))
    result = asyncio.run(run())
    assert len(calls) == 1
    assert all(len(r) == 39 for r in result)
    assert len(asyncio.run(engine.fetch_candles("LINKUSDT"))) == 39
    assert len(calls) == 1


def test_429_stops_new_calls_and_recovers_after_cooldown(monkeypatch):
    calls = []
    async def fake_get(self, url, params):
        calls.append(url)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "60"},
                                  request=httpx.Request("GET", url))
        return httpx.Response(200, json=candles(), request=httpx.Request("GET", url))
    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    with pytest.raises(ValueError, match="rate limit"):
        asyncio.run(engine.fetch_candles("LINKUSDT"))
    with pytest.raises(ValueError, match="cooldown"):
        asyncio.run(engine.fetch_candles("NEARUSDT"))
    assert len(calls) == 1
    engine._BINANCE_COOLDOWN_UNTIL = 0
    assert len(asyncio.run(engine.fetch_candles("LINKUSDT"))) == 39
    assert len(calls) == 2


def test_invalid_interval_never_calls_provider():
    with pytest.raises(ValueError, match="Unsupported timeframe"):
        asyncio.run(engine.fetch_candles("LINKUSDT", "1s"))
