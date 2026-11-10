"""TickerAll demo-only session and protective-stop preflight (READ ONLY).

Validates provider account, symbol, quote and broker contract specs.
No broker writes; passing preflight is not permission to place orders.
"""
from __future__ import annotations
from decimal import Decimal, InvalidOperation
from typing import Any
from .tickerall_demo_transport import _id, _headers, BASE, BrokerUnavailable
import httpx

class PreflightRejected(ValueError):
    pass

def _positive(value: Any, field: str) -> Decimal:
    if value is None or isinstance(value, bool):
        raise PreflightRejected(f"{field} unavailable")
    try:
        d = Decimal(str(value))
    except (ValueError, InvalidOperation):
        raise PreflightRejected(f"{field} invalid") from None
    if not d.is_finite() or d <= 0:
        raise PreflightRejected(f"{field} invalid")
    return d

def validate_session(account: dict, roster: list, account_id: str) -> dict:
    if not isinstance(account, dict) or not isinstance(roster, list):
        raise PreflightRejected("Missing broker account state")
    row = next((a for a in roster if isinstance(a, dict) and a.get("id") == account_id), None)
    if not row or row.get("isDemo") is not True or account.get("isDemo") is not True:
        raise PreflightRejected("Account is not verified as demo in both broker views")
    if str(row.get("broker", "")).lower() != "mt5" or str(account.get("broker", "")).lower() != "mt5":
        raise PreflightRejected("Only MT5 demo accounts supported")
    if row.get("hot") is not True or str(row.get("status", "")).lower() not in ("connected", "online"):
        raise PreflightRejected("Broker session is not hot and connected")
    if str(account.get("status", "")).lower() != "online":
        raise PreflightRejected("Broker account is not online")
    info = account.get("account")
    if not isinstance(info, dict) or not isinstance(account.get("positions"), list):
        raise PreflightRejected("Live broker financials or positions unavailable")
    _positive(info.get("equity"), "Equity")
    _positive(info.get("freeMargin"), "Free margin")
    if len(account["positions"]) > 0:
        raise PreflightRejected("An open position already exists")
    return {"session_ready": True, "verified_demo": True,
            "open_positions": 0, "equity": str(info["equity"]),
            "free_margin": str(info["freeMargin"]),
            "trading_permission_verified": False}

def validate_protective_stop(spec: dict, quote: dict, *, side: str, stop_loss: Any) -> dict:
    if not isinstance(spec, dict) or not isinstance(quote, dict):
        raise PreflightRejected("Broker specification or quote missing")
    if spec.get("specSource") != "broker":
        raise PreflightRejected("Broker-sourced symbol specification required")
    if spec.get("name") != quote.get("symbol"):
        raise PreflightRejected("Broker symbol mismatch")
    if side not in ("BUY", "SELL"):
        raise PreflightRejected("Invalid direction")
    bid = _positive(quote.get("bid"), "Bid")
    ask = _positive(quote.get("ask"), "Ask")
    if ask <= bid:
        raise PreflightRejected("Invalid spread")
    stop = _positive(stop_loss, "Stop loss")
    point = _positive(spec.get("point"), "Broker point")
    tick_size = _positive(spec.get("tickSize"), "Tick size")
    _positive(spec.get("tickValueAccount"), "Account-currency tick value")
    _positive(spec.get("volumeMin"), "Minimum volume")
    _positive(spec.get("volumeMax"), "Maximum volume")
    _positive(spec.get("volumeStep"), "Volume step")
    level = spec.get("stopLevel")
    if isinstance(level, bool) or level is None:
        raise PreflightRejected("Broker stop level unavailable")
    try:
        stop_level = Decimal(str(level))
    except (InvalidOperation, ValueError):
        raise PreflightRejected("Broker stop level invalid") from None
    if not stop_level.is_finite() or stop_level < 0:
        raise PreflightRejected("Broker stop level invalid")
    if stop % tick_size != 0:
        raise PreflightRejected("Stop loss not aligned to tick size")
    # Check stop against close-side market price, not just entry price.
    distance = bid - stop if side == "BUY" else stop - ask
    if distance <= 0 or distance < stop_level * point:
        raise PreflightRejected("Stop loss violates broker minimum distance")
    return {"protective_stop_payload_supported": True, "stop_loss": float(stop),
            "broker_stop_level_points": str(stop_level),
            "broker_stop_distance": str(distance),
            "stop_installed_at_broker": False,
            "quote_timestamp_verified": False,
            "trade_authorized": False}

async def _read(path: str) -> Any:
    async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
        response = await client.get(BASE + path, headers=_headers())
    if response.status_code >= 400:
        raise BrokerUnavailable(f"TickerAll preflight HTTP {response.status_code}")
    if "application/json" not in response.headers.get("content-type", ""):
        raise BrokerUnavailable("TickerAll returned non-JSON preflight response")
    return response.json()

async def read_only_demo_preflight(account_id: str, symbol: str, side: str, stop_loss: Any) -> dict:
    account_id = _id(account_id)
    if not isinstance(symbol, str) or not symbol.isascii() or not symbol.replace("_", "").isalnum():
        raise PreflightRejected("Invalid broker symbol")
    roster = await _read("/v1/accounts")
    if not isinstance(roster, list):
        raise PreflightRejected("Invalid account roster")
    account = await _read(f"/v1/accounts/{account_id}")
    session = validate_session(account, roster, account_id)
    symbols = await _read(f"/v1/accounts/{account_id}/symbols")
    if not isinstance(symbols.get("symbols"), list) or symbol not in symbols["symbols"]:
        raise PreflightRejected("Symbol not available on broker")
    spec_result = await _read(f"/v1/accounts/{account_id}/symbols/{symbol}/spec")
    quote = await _read(f"/v1/accounts/{account_id}/symbols/{symbol}/quote")
    spec = spec_result.get("spec")
    stop = validate_protective_stop(spec, quote, side=side, stop_loss=stop_loss)
    return {**session, **stop, "symbol": symbol,
            "execution_enabled": False,
            "reason": "Read-only preflight cannot verify order permissions, quote freshness or actual broker stop installation"}

def build_protected_order_preview(*, symbol: str, side: str, volume: Any,
                                  stop_loss: Any, take_profit: Any | None = None) -> dict:
    """Construct the documented broker request shape; never send it."""
    if not isinstance(symbol, str) or not symbol.isascii() or not symbol.replace("_", "").isalnum():
        raise PreflightRejected("Invalid symbol")
    if side not in ("BUY", "SELL"):
        raise PreflightRejected("Invalid direction")
    lots = _positive(volume, "Volume")
    stop = _positive(stop_loss, "Stop loss")
    body = {"type": "market", "symbol": symbol, "side": side,
            "volume": float(lots), "stopLoss": float(stop)}
    if take_profit is not None:
        body["takeProfit"] = float(_positive(take_profit, "Take profit"))
    return body
