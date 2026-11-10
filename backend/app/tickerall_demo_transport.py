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
                   idempotency_key: str | None = None) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
        response = await client.request(method, BASE + path, json=payload,
                                        headers=_headers(idempotency_key))
    if response.status_code >= 400:
        # Never include upstream response bodies: they may contain broker data.
        raise BrokerUnavailable(f"TickerAll returned HTTP {response.status_code}")
    if "application/json" not in response.headers.get("content-type", ""):
        raise BrokerUnavailable("TickerAll returned non-JSON data")
    data = response.json()
    if not isinstance(data, dict):
        raise BrokerUnavailable("TickerAll returned unexpected response")
    return data

async def get_demo_account(account_id: str) -> dict[str, Any]:
    data = await _request("GET", f"/v1/accounts/{_id(account_id)}")
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
                                   idempotency_key: str) -> dict[str, Any]:
    """Fail-closed transport: broker-enforced stop-loss capability unverified."""
    if os.getenv("TICKERALL_DEMO_EXECUTION_TRANSPORT") != "enabled":
        raise BrokerUnavailable("Demo execution transport not authorized")
    if not SYMBOL.fullmatch(symbol):
        raise ValueError("Invalid broker symbol")
    if side not in ("BUY", "SELL"):
        raise ValueError("Invalid side")
    if not isinstance(volume, (float, int)) or isinstance(volume, bool) or not (0 < volume <= 1):
        raise ValueError("Invalid demo lot volume")
    try:
        uuid.UUID(idempotency_key)
    except (ValueError, TypeError, AttributeError):
        raise ValueError("Invalid idempotency key") from None
    _id(account_id)
    # Provider order payload has no verified broker-enforced protective stop.
    # No order POST is reachable until a safe broker contract is implemented.
    raise BrokerUnavailable("Demo market orders blocked until broker-enforced stop loss is verified")
