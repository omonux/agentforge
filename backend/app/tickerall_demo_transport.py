"""TickerAll MT5 demo execution transport.

No HTTP route invokes submit_demo_market_order yet. Broker execution is wired only
after session, symbols, lot size, margin, and reconciliation are verified.
"""
from __future__ import annotations
import os
import re
import uuid
from typing import Any
import httpx

BASE = "https://api.tickerall.com"
ACCOUNT_ID = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
SYMBOL = re.compile(r"^[A-Za-z0-9_.-]{3,40}$")

class BrokerUnavailable(RuntimeError):
    pass

def _headers(idempotency_key: str | None = None) -> dict[str, str]:
    key = os.getenv("TICKERALL_API_KEY")
    if not key:
        raise BrokerUnavailable("TickerAll API key not configured")
    headers = {"Authorization": "Bearer " + key, "Accept": "application/json"}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    return headers

def _id(account_id: str) -> str:
    if not ACCOUNT_ID.fullmatch(account_id):
        raise ValueError("Invalid account ID")
    return account_id

async def _request(method: str, path: str, *, payload: dict | None = None,
                   idempotency_key: str | None = None) -> dict[str, Any] | list[Any]:
    async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
        response = await client.request(method, BASE + path, json=payload,
                                        headers=_headers(idempotency_key))
    if response.status_code >= 400:
        # Never include upstream response bodies: they may contain broker data.
        raise BrokerUnavailable(f"TickerAll returned HTTP {response.status_code}")
    if "application/json" not in response.headers.get("content-type", ""):
        raise BrokerUnavailable("TickerAll returned non-JSON data")
    data = response.json()
    if not isinstance(data, (dict, list)):
        raise BrokerUnavailable("TickerAll returned unexpected response")
    return data

async def get_demo_account(account_id: str) -> dict[str, Any]:
    data = await _request("GET", f"/v1/accounts/{_id(account_id)}")
    if not isinstance(data, dict):
        raise BrokerUnavailable("Broker account response must be an object")
    account = data.get("account")
    if not isinstance(account, dict):
        raise BrokerUnavailable("Missing broker account details")
    # The provider must affirmatively mark the account as demo.
    if (data.get("isDemo") is not True and data.get("is_demo") is not True
            and account.get("isDemo") is not True and account.get("is_demo") is not True):
        raise BrokerUnavailable("Broker account not affirmatively verified as demo")
    return data

async def list_broker_symbols(account_id: str) -> dict[str, Any]:
    await get_demo_account(account_id)
    return await _request("GET", f"/v1/accounts/{_id(account_id)}/symbols")

async def submit_demo_market_order(account_id: str, *, symbol: str,
                                   side: str, volume: float,
                                   idempotency_key: str,
                                   stop_loss: float | None = None,
                                   take_profit: float | None = None) -> dict[str, Any]:
    """Submit a protected MT5 DEMO market order and verify broker position.

    This primitive is not exposed as an HTTP endpoint or scheduled worker.
    No caller may omit both broker-native protective levels.
    """
    import math
    if os.getenv("TICKERALL_DEMO_EXECUTION_TRANSPORT") != "enabled":
        raise BrokerUnavailable("Demo execution transport not authorized")
    _id(account_id)
    if not SYMBOL.fullmatch(symbol):
        raise ValueError("Invalid broker symbol")
    if side not in ("BUY", "SELL"):
        raise ValueError("Invalid side")
    if not isinstance(volume, (float, int)) or isinstance(volume, bool) or not math.isfinite(volume) or not (0 < volume <= 1):
        raise ValueError("Invalid demo lot volume")
    for name, price in (("stop loss", stop_loss), ("take profit", take_profit)):
        if isinstance(price, bool) or not isinstance(price, (float, int)) or not math.isfinite(price) or price <= 0:
            raise ValueError(f"Valid broker-enforced {name} required")
    try:
        uuid.UUID(idempotency_key)
    except (ValueError, TypeError, AttributeError):
        raise ValueError("Invalid idempotency key") from None
    account = await get_demo_account(account_id)
    roster = await _request("GET", "/v1/accounts")
    if not isinstance(roster, list):
        raise BrokerUnavailable("Broker roster unavailable")
    row = next((x for x in roster if isinstance(x, dict) and x.get("id") == account_id), None)
    if (not row or row.get("isDemo") is not True or
            str(row.get("broker", "")).lower() != "mt5" or
            str(account.get("broker", "")).lower() != "mt5" or
            row.get("hot") is not True or
            str(row.get("status", "")).lower() not in ("online", "connected") or
            str(account.get("status", "")).lower() != "online"):
        raise BrokerUnavailable("MT5 demo account and hot session unverified")
    before = await _request("GET", f"/v1/accounts/{account_id}/positions")
    positions = before if isinstance(before, list) else before.get("positions")
    if not isinstance(positions, list) or len(positions) != 0:
        raise BrokerUnavailable("Account must be flat and position roster verified before entry")
    payload = {"type": "market", "symbol": symbol, "side": side,
               "volume": volume, "stopLoss": stop_loss,
               "takeProfit": take_profit, "comment": "AgentForge-demo"}
    result = await _request("POST", f"/v1/accounts/{account_id}/orders",
                            payload=payload, idempotency_key=idempotency_key)
    if not isinstance(result, dict) or result.get("status") != "open":
        raise BrokerUnavailable("Order response uncertain; reconcile broker before retry")
    ticket = str(result.get("ticket", ""))
    if not re.fullmatch(r"[0-9]{1,20}", ticket):
        raise BrokerUnavailable("Order ticket missing; reconcile broker before retry")
    after = await _request("GET", f"/v1/accounts/{account_id}/positions")
    current = after if isinstance(after, list) else after.get("positions")
    if not isinstance(current, list):
        raise BrokerUnavailable("Order placed; position read-back unavailable")
    matching = [p for p in current if isinstance(p, dict) and str(p.get("ticket")) == ticket]
    if len(matching) != 1:
        raise BrokerUnavailable("Order response received but position unconfirmed; reconcile broker")
    p = matching[0]
    if (p.get("symbol") != symbol or p.get("side") != side or
            not isinstance(p.get("stopLoss"), (int, float)) or
            not isinstance(p.get("takeProfit"), (int, float)) or
            abs(p["stopLoss"] - stop_loss) > 1e-7 or
            abs(p["takeProfit"] - take_profit) > 1e-7):
        raise BrokerUnavailable("Position exists but protective levels not confirmed; inspect MT5 immediately")
    return {"ticket": ticket, "confirmed_open": True, "mode": "demo",
            "stop_loss": p["stopLoss"], "take_profit": p["takeProfit"]}


async def close_demo_position_verified(account_id: str, *, ticket: str, idempotency_key: str) -> dict[str, Any]:
    """Full-close ONE MT5 demo position, verify absence in a fresh broker snapshot.

    This is a transport primitive, not an autonomous trading scheduler. An uncertain
    response is never blindly retried with a different idempotency key.
    """
    if os.getenv("TICKERALL_DEMO_CLOSE_TRANSPORT") != "enabled":
        raise BrokerUnavailable("Demo close transport not authorized")
    _id(account_id)
    if not re.fullmatch(r"[0-9]{1,20}", str(ticket)):
        raise ValueError("Invalid position ticket")
    try:
        uuid.UUID(idempotency_key)
    except (ValueError, TypeError, AttributeError):
        raise ValueError("Invalid idempotency key") from None
    account = await get_demo_account(account_id)
    roster = await _request("GET", "/v1/accounts")
    # The account endpoint can contain nested financial data. Verify the
    # demo/broker/session identity against BOTH top-level account and roster.
    if not isinstance(roster, list):
        raise BrokerUnavailable("Broker account roster unavailable")
    row = next((x for x in roster if isinstance(x, dict) and x.get("id") == account_id), None)
    if (not row or row.get("isDemo") is not True
            or str(row.get("broker", "")).lower() != "mt5"
            or str(account.get("broker", "")).lower() != "mt5"
            or str(row.get("status", "")).lower() not in ("online", "connected")
            or row.get("hot") is not True
            or str(account.get("status", "")).lower() != "online"):
        raise BrokerUnavailable("MT5 demo identity or hot session unverified")
    before = await _request("GET", f"/v1/accounts/{account_id}/positions")
    rows = before if isinstance(before, list) else before.get("positions")
    if not isinstance(rows,list):
        raise BrokerUnavailable("Position roster unavailable")
    matching = [p for p in rows if isinstance(p,dict) and str(p.get("ticket")) == str(ticket)]
    if len(matching) != 1:
        raise BrokerUnavailable("Ticket is not uniquely open; inspect broker before retrying")
    result = await _request("DELETE", f"/v1/accounts/{account_id}/positions/{ticket}",
                            idempotency_key=idempotency_key)
    if not isinstance(result, dict) or result.get("closed") is not True or str(result.get("ticket")) != str(ticket):
        raise BrokerUnavailable("Broker close response unconfirmed; inspect MT5")
    after = await _request("GET", f"/v1/accounts/{account_id}/positions")
    current = after if isinstance(after, list) else after.get("positions")
    if not isinstance(current,list) or any(isinstance(p,dict) and str(p.get("ticket")) == str(ticket) for p in current):
        raise BrokerUnavailable("Close submitted but ticket remains or broker snapshot invalid; inspect MT5")
    return {"ticket":str(ticket),"confirmed_closed":True,"mode":"demo",
            "deal_ticket":result.get("dealTicket"),"broker_profit":result.get("profit")}
