"""Independent read-only quote fetch for fast paper position monitoring.

Quotes are public Binance spot ticker prices. No exchange orders are placed.
"""
from __future__ import annotations
from datetime import datetime, timezone
import asyncio
import math
import time
import httpx

QUOTE_MAX_AGE_SECONDS=15


async def fetch_fresh_prices(symbols: list[str]) -> dict[str,float]:
    """Use two independent Binance public hosts; never reuse a stale cached price.

    A failed symbol is omitted so callers can block new entries and leave
    existing positions unchanged. A response timestamp is not provided by
    ticker/price, so venue-side quote freshness cannot be certified.
    """
    if not symbols:
        return {}
    unique=list(dict.fromkeys(symbols))
    if len(unique)>20:
        raise ValueError("Too many paper positions to monitor")
    hosts=("https://api.binance.com", "https://data-api.binance.vision")
    async with httpx.AsyncClient(timeout=httpx.Timeout(3.0)) as client:
        async def one(symbol):
            if not isinstance(symbol,str) or not symbol.isascii() or not symbol.isalnum() or len(symbol)>24:
                return None
            for host in hosts:
                try:
                    started=time.monotonic()
                    response=await client.get(host+"/api/v3/ticker/price",params={"symbol":symbol})
                    response.raise_for_status()
                    payload=response.json()
                    price=float(payload["price"])
                    if (time.monotonic()-started<=QUOTE_MAX_AGE_SECONDS
                            and math.isfinite(price) and price>0
                            and payload.get("symbol")==symbol):
                        return symbol,price
                except (httpx.HTTPError,ValueError,TypeError,KeyError,AttributeError):
                    continue
            return None
        results=await asyncio.gather(*(one(s) for s in unique))
    return {symbol:price for result in results if result is not None
            for symbol,price in (result,)}


def paper_exit_reason(side: str, price: float, stop: float, target: float) -> str | None:
    if side not in ("BUY","SELL") or any(not math.isfinite(x) or x<=0 for x in (price,stop,target)):
        raise ValueError("Invalid paper exit inputs")
    if side=="BUY":
        return "STOP_LOSS" if price<=stop else "TAKE_PROFIT" if price>=target else None
    return "STOP_LOSS" if price>=stop else "TAKE_PROFIT" if price<=target else None
