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
    if not symbols:
        return {}
    unique=list(dict.fromkeys(symbols))
    if len(unique)>20:
        raise ValueError("Too many paper positions to monitor")
    async with httpx.AsyncClient(timeout=5) as client:
        async def one(symbol):
            response=await client.get("https://api.binance.com/api/v3/ticker/price",
                                      params={"symbol":symbol})
            response.raise_for_status()
            payload=response.json()
            price=float(payload["price"])
            if not math.isfinite(price) or price<=0 or payload.get("symbol")!=symbol:
                raise ValueError("Invalid price quote")
            # This endpoint has no exchange-side timestamp. Freshness is bounded
            # by response receipt and request duration, NOT by quote age on venue.
            return symbol,price
        results=await asyncio.gather(*(one(s) for s in unique),return_exceptions=True)
    prices={}
    for result in results:
        if not isinstance(result,BaseException):
            symbol,price=result
            prices[symbol]=price
    return prices


def paper_exit_reason(side: str, price: float, stop: float, target: float) -> str | None:
    if side not in ("BUY","SELL") or any(not math.isfinite(x) or x<=0 for x in (price,stop,target)):
        raise ValueError("Invalid paper exit inputs")
    if side=="BUY":
        return "STOP_LOSS" if price<=stop else "TAKE_PROFIT" if price>=target else None
    return "STOP_LOSS" if price>=stop else "TAKE_PROFIT" if price<=target else None
