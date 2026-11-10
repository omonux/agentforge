"""Read-only, normalized OHLCV adapters for Binance Spot and Bybit Spot.

Both adapters return the same candle shape and exclude the currently-forming
candle. This module never reads credentials and never places orders.
"""
from __future__ import annotations

import time
from typing import Any

import httpx

from .omonux_engine import INTERVALS, validate_symbol, fetch_candles

BINANCE = "https://api.binance.com"
BYBIT = "https://api.bybit.com"
_BYBIT_INTERVALS = {
    "5m": "5",
    "15m": "15",
    "30m": "30",
    "1h": "60",
    "4h": "240",
    "1d": "D",
}
_INTERVAL_MS = {
    "5m": 5 * 60_000,
    "15m": 15 * 60_000,
    "30m": 30 * 60_000,
    "1h": 60 * 60_000,
    "4h": 4 * 60 * 60_000,
    "1d": 24 * 60 * 60_000,
}
EXCHANGES = {"binance", "bybit"}


def _normalize_binance(rows: list[list[Any]], now_ms: int) -> list[dict[str, Any]]:
    candles = []
    for row in rows:
        close_time = int(row[6])
        if close_time >= now_ms:
            continue
        candles.append({
            "time": int(row[0]),
            "open": float(row[1]),
            "high": float(row[2]),
            "low": float(row[3]),
            "close": float(row[4]),
            "volume": float(row[5]),
            "close_time": close_time,
        })
    return sorted(candles, key=lambda item: item["time"])


def _normalize_bybit(rows: list[list[Any]], interval: str, now_ms: int) -> list[dict[str, Any]]:
    duration = _INTERVAL_MS[interval]
    candles = []
    for row in rows:
        start = int(row[0])
        close_time = start + duration - 1
        if close_time >= now_ms:
            continue
        candles.append({
            "time": start,
            "open": float(row[1]),
            "high": float(row[2]),
            "low": float(row[3]),
            "close": float(row[4]),
            "volume": float(row[5]),
            "close_time": close_time,
        })
    return sorted(candles, key=lambda item: item["time"])


async def fetch_market_candles(
    exchange: str,
    symbol: str,
    interval: str = "30m",
    limit: int = 120,
) -> list[dict[str, Any]]:
    """Fetch completed Spot candles from one exchange using a shared schema."""
    venue = exchange.strip().lower()
    if venue not in EXCHANGES:
        raise ValueError("Exchange must be 'binance' or 'bybit'.")
    if interval not in INTERVALS:
        raise ValueError("Unsupported timeframe. Choose 5m, 15m, 30m, 1h, 4h or 1d.")
    market = validate_symbol(symbol)
    count = max(30, min(int(limit), 500))
    now_ms = int(time.time() * 1000)

    async with httpx.AsyncClient(timeout=15) as client:
        if venue == "binance":
            # Use the same bounded/coalesced Binance client as signal research.
            # A rate-limit response pauses new paper entries rather than retrying.
            return await fetch_candles(market, interval, count)
        else:
            response = await client.get(
                f"{BYBIT}/v5/market/kline",
                params={
                    "category": "spot",
                    "symbol": market,
                    "interval": _BYBIT_INTERVALS[interval],
                    "limit": count,
                },
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("retCode") != 0:
                raise ValueError("Bybit rejected the market-data request.")
            raw = payload.get("result", {}).get("list", [])
            if not isinstance(raw, list):
                raise ValueError("Bybit returned an unexpected candle response.")
            candles = _normalize_bybit(raw, interval, now_ms)

    return candles


async def fetch_both_market_candles(
    symbol: str,
    interval: str = "30m",
    limit: int = 120,
) -> dict[str, list[dict[str, Any]]]:
    """Fetch both venues concurrently; any missing venue fails the comparison."""
    import asyncio

    binance, bybit = await asyncio.gather(
        fetch_market_candles("binance", symbol, interval, limit),
        fetch_market_candles("bybit", symbol, interval, limit),
    )
    return {"binance": binance, "bybit": bybit}
