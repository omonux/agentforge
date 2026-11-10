"""AgentForge Forex V1: read-only MT5/MetaApi quote adapter and conservative paper plans.

No broker order placement, no credential persistence, no leverage, no guaranteed profits.
The MetaApi URL is explicitly configured by the operator, not user-supplied.
"""
from __future__ import annotations
import math
import os
import time
from datetime import datetime, timezone
from urllib.parse import urlparse
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/trading/forex", tags=["Forex paper research"])
PAIRS = {"EURUSD": 0.0001, "GBPUSD": 0.0001, "USDJPY": 0.01}
MAX_SPREAD_PIPS = 2.0
MAX_QUOTE_AGE_SECONDS = 30
VIRTUAL_BALANCE_USD = 100.0


class Quote(BaseModel):
    symbol: str
    bid: float = Field(gt=0, allow_inf_nan=False)
    ask: float = Field(gt=0, allow_inf_nan=False)
    timestamp: datetime


def validate_quote(quote: Quote, now: datetime | None = None) -> dict:
    symbol = quote.symbol.upper().replace("/", "")
    if symbol not in PAIRS:
        raise ValueError("Unsupported Forex pair")
    if quote.ask <= quote.bid:
        raise ValueError("Invalid bid/ask quote")
    clock = now or datetime.now(timezone.utc)
    ts = quote.timestamp
    if ts.tzinfo is None:
        raise ValueError("Quote must have a timezone-aware timestamp")
    age = (clock - ts.astimezone(timezone.utc)).total_seconds()
    if age < -5 or age > MAX_QUOTE_AGE_SECONDS:
        raise ValueError("Forex quote is stale or has an invalid future timestamp")
    spread = (quote.ask - quote.bid) / PAIRS[symbol]
    if not math.isfinite(spread) or spread > MAX_SPREAD_PIPS:
        raise ValueError("Forex spread exceeds safety limit")
    return {"symbol": symbol, "bid": quote.bid, "ask": quote.ask,
            "spread_pips": round(spread, 3), "quote_age_seconds": round(age, 2),
            "timestamp": ts.isoformat(), "source": "configured MetaApi MT5 read-only feed"}


def paper_plan(quote: Quote, *, side: str, stop_pips: float,
               confidence: float, risk_percent: float = 0.5) -> dict:
    market = validate_quote(quote)
    if side not in ("BUY", "SELL"):
        raise ValueError("A verified directional signal is required")
    if not (0.1 <= risk_percent <= 1.0 and 0 <= confidence <= 100):
        raise ValueError("Risk or confidence out of range")
    if confidence < 85:
        raise ValueError("Forex entry blocked: confidence below 85")
    if not (5 <= stop_pips <= 100):
        raise ValueError("Stop must be between 5 and 100 pips")
    # Only a read-only plan; units are base currency, no broker lot rounding.
    # Approximate quote-currency P&L is converted to USD for JPY pairs.
    pip = PAIRS[market["symbol"]]
    entry = quote.ask if side == "BUY" else quote.bid
    stop = entry + (-1 if side == "BUY" else 1) * stop_pips * pip
    target = entry + (1 if side == "BUY" else -1) * stop_pips * pip * 2
    conversion = 1 / entry if market["symbol"].endswith("JPY") else 1
    # Include spread and modeled slippage in the risk budget.
    total_risk_pips = stop_pips + market["spread_pips"] + 0.5
    units = (VIRTUAL_BALANCE_USD * risk_percent / 100) / (total_risk_pips * pip * conversion)
    # No leverage: at most $10 of notional from a $100 virtual account.
    units = min(units, 10 / entry)
    return {"mode": "paper_preview_only", "execution": "no_order_placed",
            "symbol": market["symbol"], "side": side, "entry": round(entry, 6),
            "stop": round(stop, 6), "target": round(target, 6),
            "units": round(units, 8), "maximum_notional_usd": 10,
            "risk_percent": risk_percent, "spread_pips": market["spread_pips"],
            "slippage_assumption_pips": 0.5,
            "virtual_starting_balance_usd": VIRTUAL_BALANCE_USD,
            "notice": "No trade was opened. Stops cannot guarantee exit prices; Forex profits are not guaranteed."}


def _feed_configured() -> bool:
    return bool(os.getenv("METAAPI_TOKEN") and os.getenv("METAAPI_ACCOUNT_ID")
                and os.getenv("METAAPI_PRICE_URL_TEMPLATE"))


async def fetch_metaapi_quote(symbol: str) -> Quote:
    if symbol not in PAIRS:
        raise ValueError("Unsupported Forex pair")
    if not _feed_configured():
        raise ValueError("MetaApi read-only feed is not configured")
    template = os.environ["METAAPI_PRICE_URL_TEMPLATE"]
    # Operator-controlled URL; never accept a URL from a browser request.
    url = template.replace("{account_id}", os.environ["METAAPI_ACCOUNT_ID"]).replace("{symbol}", symbol)
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or not (
        parsed.hostname == "agiliumtrade.ai" or parsed.hostname.endswith(".agiliumtrade.ai")
    ):
        raise ValueError("MetaApi price URL must use HTTPS on agiliumtrade.ai")
    async with httpx.AsyncClient(timeout=8, follow_redirects=False) as client:
        response = await client.get(url, headers={"auth-token": os.environ["METAAPI_TOKEN"]})
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Invalid MetaApi price response")
    # Reject responses without provider timestamps: no fabricated freshness.
    raw_time = payload.get("brokerTime") or payload.get("time")
    if not raw_time:
        raise ValueError("MetaApi quote missing provider timestamp")
    if isinstance(raw_time, str) and raw_time.endswith("Z"):
        raw_time = raw_time[:-1] + "+00:00"
    return Quote(symbol=symbol, bid=payload["bid"], ask=payload["ask"],
                 timestamp=datetime.fromisoformat(raw_time))


@router.get("/status")
def forex_status():
    return {"module": "AgentForge Forex Intelligence V1", "markets": sorted(PAIRS),
            "broker": "MetaTrader 5 via MetaApi", "feed_configured": _feed_configured(),
            "execution_enabled": False, "mode": "paper_research_only",
            "virtual_starting_balance_usd": VIRTUAL_BALANCE_USD,
            "max_paper_notional_usd": 10, "max_spread_pips": MAX_SPREAD_PIPS,
            "quote_max_age_seconds": MAX_QUOTE_AGE_SECONDS,
            "next_step": "Set METAAPI_TOKEN, METAAPI_ACCOUNT_ID and METAAPI_PRICE_URL_TEMPLATE server-side. Do not paste secrets into chat."}


@router.get("/quote/{symbol}")
async def forex_quote(symbol: str):
    market = symbol.upper().replace("/", "")
    try:
        return validate_quote(await fetch_metaapi_quote(market))
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except (httpx.HTTPError, KeyError, TypeError) as exc:
        raise HTTPException(503, "Forex quote provider unavailable or invalid; no trade allowed") from exc


class PreviewRequest(BaseModel):
    symbol: str
    side: str
    stop_pips: float = Field(default=20, ge=5, le=100)
    confidence: float = Field(default=85, ge=0, le=100)
    risk_percent: float = Field(default=0.5, ge=0.1, le=1)


@router.post("/preview")
async def forex_preview(req: PreviewRequest):
    try:
        quote = await fetch_metaapi_quote(req.symbol.upper().replace("/", ""))
        return paper_plan(quote, side=req.side.upper(), stop_pips=req.stop_pips,
                          confidence=req.confidence, risk_percent=req.risk_percent)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except (httpx.HTTPError, KeyError, TypeError) as exc:
        raise HTTPException(503, "Forex provider unavailable; paper preview blocked") from exc
