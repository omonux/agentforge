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


# TickerAll credentials are configured only through Render environment secrets.
# No key is accepted from the browser or returned by any API route.
import re

TICKERALL_BASE = "https://api.tickerall.com"
_ACCOUNT_RE = re.compile(r"^[A-Za-z0-9_-]{8,128}$")


def _feed_configured() -> bool:
    return bool(os.getenv("TICKERALL_API_KEY"))


async def _tickerall_get(path: str, params: dict | None = None):
    token = os.getenv("TICKERALL_API_KEY", "")
    if not token:
        raise ValueError("TickerAll API key not configured in Render")
    async with httpx.AsyncClient(timeout=12, follow_redirects=False) as client:
        response = await client.get(TICKERALL_BASE + path,
                                    params=params,
                                    headers={"Authorization": "Bearer " + token})
        if response.status_code in (401, 403):
            raise ValueError("TickerAll authentication or read-only permission failed")
        if response.status_code in (409, 429):
            raise ValueError("TickerAll session is cold or rate-limited; wait or reconnect from TickerAll dashboard")
        response.raise_for_status()
        return response.json()


def _account_id() -> str:
    account_id = os.getenv("TICKERALL_ACCOUNT_ID", "")
    if not _ACCOUNT_RE.fullmatch(account_id):
        raise ValueError("Set TICKERALL_ACCOUNT_ID in Render using the account ID returned by TickerAll")
    return account_id


@router.get("/status")
def forex_status():
    return {"module": "AgentForge Forex Intelligence V1",
            "provider": "TickerAll", "broker": "MetaTrader 5",
            "markets": sorted(PAIRS), "feed_configured": _feed_configured(),
            "account_configured": bool(_ACCOUNT_RE.fullmatch(os.getenv("TICKERALL_ACCOUNT_ID", ""))),
            "execution_enabled": False, "mode": "paper_research_only",
            "virtual_starting_balance_usd": VIRTUAL_BALANCE_USD,
            "max_paper_notional_usd": 10,
            "next_step": "Set TICKERALL_API_KEY in Render; use Check connection to find the account ID, then set TICKERALL_ACCOUNT_ID. No broker orders are enabled."}


@router.get("/accounts")
async def forex_accounts():
    try:
        payload = await _tickerall_get("/v1/accounts")
        if not isinstance(payload, list):
            raise ValueError("TickerAll returned unexpected account list")
        # Only safe metadata, never passwords, tokens, balances or full account numbers.
        return {"accounts": [{"id": str(a.get("id", "")),
                              "broker": a.get("broker"),
                              "server": a.get("server"),
                              "is_demo": a.get("isDemo"),
                              "status": a.get("status"),
                              "hot": a.get("hot")}
                             for a in payload if isinstance(a, dict)]}
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except httpx.HTTPError as exc:
        raise HTTPException(503, "TickerAll connection unavailable; no trading permitted") from exc


@router.get("/account")
async def forex_account(account_id: str | None = None):
    try:
        # Allow verification of an ID discovered from the read-only accounts list.
        # Never accept arbitrary paths or use this for broker order execution.
        if account_id is not None:
            if not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", account_id):
                raise ValueError("Invalid TickerAll account ID")
            listed = await _tickerall_get("/v1/accounts")
            if not isinstance(listed, list) or not any(isinstance(a, dict) and str(a.get("id")) == account_id for a in listed):
                raise ValueError("Account ID not present in connected TickerAll accounts")
            selected_id = account_id
        else:
            selected_id = _account_id()
        payload = await _tickerall_get("/v1/accounts/" + selected_id)
        if not isinstance(payload, dict) or payload.get("isDemo") is not True:
            raise ValueError("Only verified MT5 demo accounts are supported")
        return {"status": payload.get("status"), "is_demo": True,
                "broker": payload.get("broker"), "server": payload.get("server"),
                "account": {"currency": (payload.get("account") or {}).get("currency"),
                            "balance": (payload.get("account") or {}).get("balance"),
                            "equity": (payload.get("account") or {}).get("equity")},
                "execution_enabled": False}
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except httpx.HTTPError as exc:
        raise HTTPException(503, "TickerAll account unavailable") from exc


def _safe_position_number(value):
    """Return finite broker numeric values, including numeric strings."""
    if isinstance(value, bool):
        return None
    if not isinstance(value, (int, float, str)):
        return None
    try:
        result = float(value)
    except (ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _first_present(position, *keys):
    """Choose the first present non-null field, preserving zero as meaningful."""
    for key in keys:
        if key in position and position[key] is not None:
            return position[key]
    return None


def _broker_price(position, *keys):
    value = _first_present(position, *keys)
    return _safe_position_number(value)


def _stop_status(position, keys):
    """Unknown is not the same as absent. A zero broker stop means unset."""
    raw = _first_present(position, *keys)
    if raw is None:
        return "unknown"
    number = _safe_position_number(raw)
    if number is None or number < 0:
        return "unknown"
    return "set" if number > 0 else "not_set"


def _normalize_demo_positions(payload):
    """Allowlist broker fields; never claim stop protection without evidence."""
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict) and isinstance(payload.get("positions"), list):
        rows = payload["positions"]
    else:
        raise ValueError("TickerAll positions response has an unexpected shape")
    if len(rows) > 1000 or any(not isinstance(p, dict) for p in rows):
        raise ValueError("TickerAll positions response invalid")
    positions = []
    sl_keys = ("stopLoss", "stop_loss", "sl", "stopLossPrice", "stop_loss_price")
    tp_keys = ("takeProfit", "take_profit", "tp", "takeProfitPrice", "take_profit_price")
    for p in rows:
        side = _first_present(p, "side", "type", "direction")
        if isinstance(side, (int, float)) and not isinstance(side, bool):
            side = {0: "BUY", 1: "SELL"}.get(side, "UNKNOWN")
        positions.append({
            "ticket": str(_first_present(p, "ticket", "positionId", "position_id", "id"))[:80] if _first_present(p, "ticket", "positionId", "position_id", "id") is not None else None,
            "symbol": str(p["symbol"])[:80] if p.get("symbol") is not None else None,
            "side": str(side or "UNKNOWN")[:32],
            "volume": _broker_price(p, "volume", "lots", "lot"),
            "open_price": _broker_price(p, "openPrice", "priceOpen", "price_open", "open_price", "entryPrice", "entry_price", "price"),
            "stop_loss": _broker_price(p, *sl_keys),
            "take_profit": _broker_price(p, *tp_keys),
            "stop_loss_status": _stop_status(p, sl_keys),
            "take_profit_status": _stop_status(p, tp_keys),
            "profit": _broker_price(p, "profit", "floatingProfit", "floating_profit"),
            "magic": int(p["magic"]) if type(p.get("magic")) is int else None,
        })
    return positions


@router.get("/positions")
async def forex_open_positions():
    """Read-only positions for the configured account, verified as demo in both views."""
    try:
        account_id = _account_id()
        roster = await _tickerall_get("/v1/accounts")
        if not isinstance(roster, list) or not any(
            isinstance(row, dict) and row.get("id") == account_id
            and row.get("isDemo") is True and str(row.get("broker", "")).lower() == "mt5"
            for row in roster
        ):
            raise ValueError("Configured account is not a verified MT5 demo account in roster")
        account = await _tickerall_get("/v1/accounts/" + account_id)
        if not isinstance(account, dict) or account.get("isDemo") is not True or str(account.get("broker", "")).lower() != "mt5":
            raise ValueError("Configured account is not a verified MT5 demo account")
        raw = await _tickerall_get("/v1/accounts/" + account_id + "/positions")
        positions = _normalize_demo_positions(raw)
        return {"positions": positions, "count": len(positions),
                "account_id": account_id, "execution_enabled": False,
                "source": "TickerAll MT5 demo read-only positions",
                "stop_verification": "broker_snapshot_only_not_execution_authorization",
                "stop_status_counts": {status: sum(p["stop_loss_status"] == status for p in positions)
                                       for status in ("set", "not_set", "unknown")}}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except (httpx.HTTPError, TypeError, AttributeError) as exc:
        raise HTTPException(503, "MT5 positions unavailable; cannot establish flat account") from exc


@router.get("/preflight/session")
async def forex_session_preflight():
    """Read-only broker session verification. Never authorizes execution."""
    from .forex_demo_preflight import _read, validate_session, PreflightRejected
    from .tickerall_demo_transport import BrokerUnavailable
    try:
        account_id = _account_id()
        roster = await _read("/v1/accounts")
        account = await _read("/v1/accounts/" + account_id)
        result = validate_session(account, roster, account_id)
        return {"account_id": account_id, "session_ready": result["session_ready"],
                "verified_demo": result["verified_demo"],
                "open_positions": result["open_positions"],
                "trading_permission_verified": False,
                "protective_stop_verified": False,
                "execution_enabled": False,
                "next_step": "Verify broker symbol specification, fresh quote, stop loss, trading permission and durable reconciliation before any order."}
    except (ValueError, PreflightRejected, BrokerUnavailable) as exc:
        raise HTTPException(422, "MT5 session preflight blocked: " + str(exc)) from exc
    except (httpx.HTTPError, TypeError, AttributeError) as exc:
        raise HTTPException(503, "TickerAll session preflight unavailable; broker execution remains disabled") from exc


@router.get("/candles/{symbol}")
async def forex_candles(symbol: str, timeframe: str = "M30", hours: int = 72):
    market = symbol.upper()
    if market not in PAIRS or timeframe not in {"M15", "M30", "H1", "H4", "D1"} or not (24 <= hours <= 720):
        raise HTTPException(422, "Unsupported Forex market, timeframe or lookback")
    try:
        # Verify account is demo before accessing broker-specific candles.
        account = await _tickerall_get("/v1/accounts/" + _account_id())
        if not isinstance(account, dict) or account.get("isDemo") is not True:
            raise ValueError("Demo-only Forex connection required")
        payload = await _tickerall_get("/v1/accounts/" + _account_id() + "/candles",
                                       {"symbol": market, "timeframe": timeframe, "hours": hours})
        if not isinstance(payload, dict) or not isinstance(payload.get("candles"), list):
            raise ValueError("TickerAll candle response invalid")
        if payload.get("truncated") or payload.get("coverage") != "complete":
            raise ValueError("TickerAll candle history incomplete; research blocked")
        bars = payload["candles"]
        if len(bars) < 30:
            raise ValueError("Insufficient Forex candles for analysis")
        # Last bar is forming: never use it as closed evidence.
        seconds = {"M15": 900, "M30": 1800, "H1": 3600, "H4": 14400, "D1": 86400}[timeframe]
        now = time.time()
        closed = [b for b in bars if isinstance(b, dict) and
                  isinstance(b.get("timestamp"), (int, float)) and
                  b["timestamp"] + seconds <= now]
        if len(closed) < 30 or now - (closed[-1]["timestamp"] + seconds) > 2 * seconds:
            raise ValueError("Forex closed candles stale or insufficient")
        return {"symbol": market, "timeframe": timeframe,
                "candles": closed[-120:], "count": len(closed[-120:]),
                "source": "TickerAll MT5 demo account",
                "execution": "research_only_no_order_placed"}
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except httpx.HTTPError as exc:
        raise HTTPException(503, "TickerAll candles unavailable; research blocked") from exc


@router.get("/research/{symbol}")
async def forex_research(symbol: str, timeframe: str = "M30", hours: int = 168):
    """Read-only Forex analysis using verified demo candles and existing council."""
    from .omonux_forex_intelligence import normalize_forex_candles, forex_research_signal, forex_risk_warning
    from .omonux_council import run_council
    from .main import current_ai_config

    candles_response = await forex_candles(symbol, timeframe, hours)
    try:
        normalized = normalize_forex_candles(candles_response["candles"])
        signal = forex_research_signal(normalized)
        risk_warning = forex_risk_warning(normalized, signal)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if signal["side"] == "HOLD":
        return {"symbol": symbol.upper(), "timeframe": timeframe, "signal": signal,
                "decision": "NO_TRADE", "risk_warning": risk_warning, "reason": "Insufficient directional evidence",
                "execution": "research_only_no_order_placed"}
    base, key, model = current_ai_config()
    if not (base and key and model):
        raise HTTPException(503, "AI provider not configured; no council decision")
    try:
        council = await run_council(symbol.upper(), timeframe, normalized, signal,
                                    base, key, model, market_type="forex")
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"symbol": symbol.upper(), "timeframe": timeframe, "signal": signal,
            "council": council, "risk_warning": risk_warning, "execution": "research_only_no_order_placed"}
