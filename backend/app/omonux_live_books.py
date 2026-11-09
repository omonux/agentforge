"""Bounded read-only cross-exchange top-of-book research.

Spot quote comparisons are indicative, not a guarantee of executable profit.
Never reads API credentials, transfers funds, or submits orders.
"""
from __future__ import annotations
import asyncio
import time
import httpx
from .omonux_universe import UNIVERSE_SYMBOLS

BINANCE_BOOK="https://api.binance.com/api/v3/ticker/bookTicker"
BYBIT_BOOK="https://api.bybit.com/v5/market/tickers"


def evaluate_quotes(symbol: str, binance: dict, bybit: dict, *, fee_bps: float = 20,
                    slippage_bps: float = 10, extra_cost_bps: float = 5,
                    min_edge_bps: float = 10) -> dict:
    quotes={"binance":binance,"bybit":bybit}
    for venue,quote in quotes.items():
        bid,ask=float(quote["bid"]),float(quote["ask"])
        bid_size,ask_size=float(quote["bid_size"]),float(quote["ask_size"])
        if not (0 < bid <= ask and bid_size > 0 and ask_size > 0):
            raise ValueError(f"Invalid {venue} order-book quote")
    routes=[]
    for buy,sell in (("binance","bybit"),("bybit","binance")):
        ask=float(quotes[buy]["ask"]);bid=float(quotes[sell]["bid"])
        gross=(bid-ask)/ask*10000
        costs=fee_bps+slippage_bps+extra_cost_bps
        base_qty=min(float(quotes[buy]["ask_size"]),float(quotes[sell]["bid_size"]))
        routes.append({"buy_venue":buy,"sell_venue":sell,"gross_edge_bps":round(gross,3),
                       "estimated_net_edge_bps":round(gross-costs,3),
                       "top_of_book_base_qty":base_qty,
                       "indicative_notional_usdt":round(base_qty*ask,2),
                       "passes_assumed_cost_threshold":gross-costs>=min_edge_bps})
    best=max(routes,key=lambda x:x["estimated_net_edge_bps"])
    return {"symbol":symbol,"best_route":best,"routes":routes,
            "assumed_total_cost_bps":fee_bps+slippage_bps+extra_cost_bps,
            "executable":False,"execution":"read_only_no_order_placed",
            "notice":"Public best bid/ask snapshots are not atomic across venues. Sizes can disappear before execution. No inventory, latency, fee tier, full depth or settlement checks; no orders placed."}


async def scan_live_books(symbols: list[str], *, fee_bps: float=20,
                          slippage_bps: float=10, extra_cost_bps: float=5) -> dict:
    if not symbols or len(symbols)>10 or len(set(symbols))!=len(symbols):
        raise ValueError("Choose 1-10 unique markets")
    if any(s not in UNIVERSE_SYMBOLS for s in symbols):
        raise ValueError("Market outside curated universe")
    if any(not 0<=v<=100 for v in (fee_bps,slippage_bps,extra_cost_bps)):
        raise ValueError("Cost assumptions must be between 0 and 100 bps")
    async with httpx.AsyncClient(timeout=10) as client:
        async def inspect(symbol):
            try:
                started=time.monotonic()
                a,b=await asyncio.gather(
                    client.get(BINANCE_BOOK,params={"symbol":symbol}),
                    client.get(BYBIT_BOOK,params={"category":"spot","symbol":symbol}))
                a.raise_for_status();b.raise_for_status()
                left=a.json();right=b.json()
                if right.get("retCode")!=0:
                    raise ValueError("Bybit quote request failed")
                records=right.get("result",{}).get("list",[])
                if len(records)!=1 or records[0].get("symbol")!=symbol:
                    raise ValueError("Unexpected Bybit quote")
                r=records[0]
                quote_a={"bid":left["bidPrice"],"ask":left["askPrice"],
                         "bid_size":left["bidQty"],"ask_size":left["askQty"]}
                quote_b={"bid":r["bid1Price"],"ask":r["ask1Price"],
                         "bid_size":r["bid1Size"],"ask_size":r["ask1Size"]}
                output=evaluate_quotes(symbol,quote_a,quote_b,fee_bps=fee_bps,
                                       slippage_bps=slippage_bps,extra_cost_bps=extra_cost_bps)
                output["fetch_duration_ms"]=round((time.monotonic()-started)*1000)
                return output
            except (httpx.HTTPError,ValueError,KeyError,TypeError,IndexError,OverflowError) as exc:
                return {"symbol":symbol,"status":"unavailable","reason":str(exc)[:160],
                        "executable":False}
        results=await asyncio.gather(*(inspect(s) for s in symbols))
    return {"markets":results,"checked_at_unix_ms":int(time.time()*1000),
            "market_count":len(results),"execution":"research_only_no_orders",
            "notice":"Indicative asynchronous public quotes only. Not a live-trading recommendation."}
