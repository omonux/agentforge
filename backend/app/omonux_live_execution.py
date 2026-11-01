"""Guarded Binance Spot LIVE order workflow.

A live order requires: server feature flag, encrypted LIVE credentials, a fresh
server-generated preview, risk checks, exact per-order confirmation and an
idempotent client order ID. No background/AI path calls the placement endpoint.
"""
import hashlib
import hmac
import json
import os
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_UP
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .omonux_integrations import read_secret
from .main import db, stamp

router = APIRouter(prefix="/api/v1/trading/live", tags=["OMONUX Guarded Live Trading"])
BASE_URL = "https://api.binance.com"
RECV_WINDOW = "5000"
PREVIEW_TTL_SECONDS = 60


def ensure_tables():
    with db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS live_order_previews(
            id TEXT PRIMARY KEY, exchange_name TEXT NOT NULL, symbol TEXT NOT NULL,
            side TEXT NOT NULL, quantity TEXT NOT NULL, quote_price TEXT NOT NULL,
            limit_price TEXT NOT NULL DEFAULT '0', notional_usdt TEXT NOT NULL, created_at TEXT NOT NULL, expires_at INTEGER NOT NULL,
            state TEXT NOT NULL DEFAULT 'pending', response TEXT)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS live_orders(
            id TEXT PRIMARY KEY, preview_id TEXT NOT NULL UNIQUE, exchange_order_id TEXT,
            client_order_id TEXT NOT NULL UNIQUE, symbol TEXT NOT NULL, side TEXT NOT NULL,
            quantity TEXT NOT NULL, executed_quantity TEXT, quote_quantity TEXT,
            status TEXT NOT NULL, response TEXT NOT NULL, created_at TEXT NOT NULL)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS live_trading_state(
            id INTEGER PRIMARY KEY CHECK(id=1), emergency_stopped INTEGER NOT NULL DEFAULT 1,
            reason TEXT, updated TEXT NOT NULL)""")
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(live_order_previews)")}
        if "limit_price" not in columns:
            conn.execute("ALTER TABLE live_order_previews ADD COLUMN limit_price TEXT NOT NULL DEFAULT '0'")
        conn.execute("INSERT OR IGNORE INTO live_trading_state(id,emergency_stopped,updated) VALUES(1,1,?)", (stamp(),))


def live_keys():
    key = read_secret("binance_live_api_key")
    secret = read_secret("binance_live_api_secret")
    if not key or not secret:
        raise HTTPException(409, "Save separate Binance LIVE credentials before requesting a live order preview.")
    return key, secret


def signed_params(secret: str, params: dict) -> dict:
    result = dict(params)
    result["signature"] = hmac.new(secret.encode(), urlencode(result).encode(), hashlib.sha256).hexdigest()
    return result


def dec(value, label):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise HTTPException(400, f"Invalid {label}.")
    if not result.is_finite():
        raise HTTPException(400, f"Invalid {label}.")
    return result


async def binance_get(path, key, secret, params=None):
    payload = dict(params or {})
    payload.update({"recvWindow": RECV_WINDOW, "timestamp": str(int(time.time() * 1000))})
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.get(BASE_URL + path, params=signed_params(secret, payload), headers={"X-MBX-APIKEY": key})
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError:
        raise HTTPException(502, "Binance rejected a live-trading validation request. Check key permissions, IP restrictions and account status.")
    except (httpx.RequestError, ValueError):
        raise HTTPException(502, "Could not validate the live order with Binance.")


def risk_limits():
    per_order = dec(os.getenv("LIVE_MAX_ORDER_NOTIONAL_USDT", "25"), "per-order limit")
    daily = dec(os.getenv("LIVE_MAX_DAILY_NOTIONAL_USDT", "100"), "daily limit")
    if per_order <= 0 or daily <= 0 or per_order > daily:
        raise HTTPException(503, "Live trading risk limits are invalid. Configure positive limits with per-order not greater than daily.")
    return per_order, daily


class PreviewRequest(BaseModel):
    symbol: str = Field(min_length=5, max_length=20, pattern=r"^[A-Za-z0-9]+$")
    side: str
    quantity: Decimal = Field(gt=0, max_digits=24, decimal_places=12)


class PlaceRequest(BaseModel):
    preview_id: str = Field(min_length=36, max_length=36)
    confirmation: str = Field(min_length=10, max_length=80)


class HaltRequest(BaseModel):
    reason: str = Field(default="Operator live-trading emergency stop", min_length=3, max_length=240)


class ResetRequest(BaseModel):
    confirmation: str


@router.get("/status")
def live_trading_status():
    ensure_tables()
    with db() as conn:
        state = conn.execute("SELECT emergency_stopped,reason,updated FROM live_trading_state WHERE id=1").fetchone()
    return {
        "exchange": "Binance Spot",
        "feature_enabled": os.getenv("LIVE_TRADING_ENABLED", "").lower() == "true" or os.getenv("BYBIT_LIVE_TRADING_ENABLED", "").lower() == "true",
        "binance_enabled": os.getenv("LIVE_TRADING_ENABLED", "").lower() == "true",
        "bybit_enabled": os.getenv("BYBIT_LIVE_TRADING_ENABLED", "").lower() == "true",
        "emergency_stopped": bool(state["emergency_stopped"]) if state else True,
        "reason": state["reason"] if state else "Safety state not initialized",
        "scope": "Manual, individually confirmed Binance Spot market orders only",
        "automatic_orders": False,
        "default_limits_usdt": {
            "per_order": os.getenv("LIVE_MAX_ORDER_NOTIONAL_USDT", "25"),
            "daily": os.getenv("LIVE_MAX_DAILY_NOTIONAL_USDT", "100"),
        },
    }


@router.post("/emergency-stop")
def live_emergency_stop(request: HaltRequest):
    ensure_tables()
    with db() as conn:
        conn.execute("UPDATE live_trading_state SET emergency_stopped=1,reason=?,updated=? WHERE id=1", (request.reason, stamp()))
        conn.execute("UPDATE live_order_previews SET state='cancelled' WHERE state='pending'")
    return live_trading_status()


@router.post("/reset")
def live_safety_reset(request: ResetRequest):
    ensure_tables()
    if request.confirmation != "RESET LIVE TRADING SAFETY":
        raise HTTPException(400, 'Type exactly "RESET LIVE TRADING SAFETY" to clear the live-trading stop latch.')
    if os.getenv("LIVE_TRADING_ENABLED", "").lower() != "true" and os.getenv("BYBIT_LIVE_TRADING_ENABLED", "").lower() != "true":
        raise HTTPException(423, "Live trading remains disabled by the server feature flags.")
    with db() as conn:
        conn.execute("UPDATE live_trading_state SET emergency_stopped=0,reason=NULL,updated=? WHERE id=1", (stamp(),))
    return live_trading_status()


@router.post("/binance/preview")
async def preview_binance_order(request: PreviewRequest):
    ensure_tables()
    if request.side.upper() not in ("BUY", "SELL"):
        raise HTTPException(400, "Side must be BUY or SELL.")
    symbol = request.symbol.upper()
    if not symbol.endswith("USDT"):
        raise HTTPException(400, "The first live release only supports Binance Spot USDT-quoted pairs.")
    quantity = dec(request.quantity, "quantity")
    if quantity <= 0:
        raise HTTPException(400, "Quantity must be positive.")
    key, secret = live_keys()
    account, exchange_info, ticker = await __import__("asyncio").gather(
        binance_get("/api/v3/account", key, secret),
        public_binance_get("/api/v3/exchangeInfo", {"symbol": symbol}),
        public_binance_get("/api/v3/ticker/price", {"symbol": symbol}),
    )
    if not account.get("canTrade"):
        raise HTTPException(403, "Binance account does not have spot trading enabled.")
    symbol_info = next((item for item in exchange_info.get("symbols", []) if item.get("symbol") == symbol), None)
    if not symbol_info or symbol_info.get("status") != "TRADING" or not symbol_info.get("isSpotTradingAllowed", False):
        raise HTTPException(400, "This symbol is not currently eligible for Binance Spot trading.")
    if symbol_info.get("quoteAsset") != "USDT":
        raise HTTPException(400, "Only USDT quote assets are supported in this first release.")
    filters = {item["filterType"]: item for item in symbol_info.get("filters", [])}
    lot = filters.get("LOT_SIZE", {})
    step = dec(lot.get("stepSize", "0.00000001"), "quantity step")
    minimum_qty = dec(lot.get("minQty", "0"), "minimum quantity")
    maximum_qty = dec(lot.get("maxQty", "0"), "maximum quantity")
    if step <= 0 or quantity % step != 0:
        raise HTTPException(400, f"Quantity must match the exchange step size ({step}). No rounding was applied.")
    if quantity < minimum_qty or (maximum_qty > 0 and quantity > maximum_qty):
        raise HTTPException(400, "Quantity is outside Binance LOT_SIZE limits.")
    price = dec(ticker.get("price"), "market price")
    price_filter = filters.get("PRICE_FILTER", {})
    tick = dec(price_filter.get("tickSize", "0.00000001"), "price tick")
    if tick <= 0:
        raise HTTPException(502, "Binance returned an invalid price tick.")
    raw_limit = price * (Decimal("1.005") if request.side.upper() == "BUY" else Decimal("0.995"))
    rounding = ROUND_UP if request.side.upper() == "BUY" else ROUND_DOWN
    limit_price = (raw_limit / tick).to_integral_value(rounding=rounding) * tick
    notional = quantity * limit_price
    per_order, daily_limit = risk_limits()
    if notional > per_order:
        raise HTTPException(400, f"Order notional {notional:.8f} USDT exceeds the configured per-order cap of {per_order} USDT.")
    notional_filter = filters.get("NOTIONAL") or filters.get("MIN_NOTIONAL")
    min_notional = dec(notional_filter.get("minNotional", "0"), "minimum notional") if notional_filter else Decimal("0")
    if notional < min_notional:
        raise HTTPException(400, f"Order is below Binance minimum notional ({min_notional} USDT).")
    if request.side.upper() == "SELL":
        base_asset = symbol_info["baseAsset"]
        available = next((dec(b["free"], "free balance") for b in account.get("balances", []) if b.get("asset") == base_asset), Decimal("0"))
        if quantity > available:
            raise HTTPException(400, f"Insufficient free {base_asset} balance for this sell order.")
    else:
        quote_available = next((dec(b["free"], "free balance") for b in account.get("balances", []) if b.get("asset") == "USDT"), Decimal("0"))
        if notional > quote_available:
            raise HTTPException(400, "Insufficient free USDT balance for this buy order at the current reference price.")
    with db() as conn:
        used = conn.execute("SELECT COALESCE(SUM(CAST(notional_usdt AS REAL)),0) AS total FROM live_order_previews WHERE state IN ('submitting','submitted','unknown') AND created_at >= ?", (datetime.now(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0).isoformat(),)).fetchone()["total"]
    if dec(used, "daily usage") + notional > daily_limit:
        raise HTTPException(400, f"Order would exceed the configured daily notional cap of {daily_limit} USDT.")
    preview_id = str(uuid.uuid4())
    expiry = int(time.time()) + PREVIEW_TTL_SECONDS
    with db() as conn:
        conn.execute("INSERT INTO live_order_previews(id,exchange_name,symbol,side,quantity,quote_price,limit_price,notional_usdt,created_at,expires_at,state) VALUES(?,?,?,?,?,?,?,?,?,?,'pending')",
            (preview_id, "binance", symbol, request.side.upper(), str(quantity), str(price), str(limit_price), str(notional), stamp(), expiry))
    return {
        "preview_id": preview_id, "exchange": "Binance Spot LIVE", "symbol": symbol,
        "side": request.side.upper(), "order_type": "LIMIT IOC (price-protected)", "quantity": str(quantity),
        "reference_price": str(price), "limit_price": str(limit_price), "maximum_notional_usdt": str(notional),
        "per_order_limit_usdt": str(per_order), "daily_limit_usdt": str(daily_limit),
        "expires_at": expiry, "confirmation_text": f"PLACE LIVE {request.side.upper()} {symbol}",
        "warning": "Price-protected LIMIT IOC: fills only at this limit or better; unfilled remainder is cancelled. Partial fills are possible; fees apply. Preview valid for 60 seconds.",
        "execution_enabled": os.getenv("LIVE_TRADING_ENABLED", "").lower() == "true",
    }


async def public_binance_get(path, params=None):
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.get(BASE_URL + path, params=params or {})
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPStatusError, httpx.RequestError, ValueError):
        raise HTTPException(502, "Could not retrieve current Binance market rules or reference price.")


@router.post("/binance/place")
async def place_binance_order(request: PlaceRequest):
    ensure_tables()
    if os.getenv("LIVE_TRADING_ENABLED", "").lower() != "true":
        raise HTTPException(423, "Real-money order execution is disabled. Set LIVE_TRADING_ENABLED=true privately on the server only after reviewing the safeguards.")
    state = live_trading_status()
    if state["emergency_stopped"]:
        raise HTTPException(423, "Live-trading emergency stop is active.")
    key, secret = live_keys()
    with db() as conn:
        preview = conn.execute("SELECT * FROM live_order_previews WHERE id=?", (request.preview_id,)).fetchone()
    if not preview:
        raise HTTPException(404, "Order preview not found.")
    if preview["state"] != "pending":
        raise HTTPException(409, "This preview has already been used or cancelled.")
    if int(time.time()) > int(preview["expires_at"]):
        with db() as conn:
            conn.execute("UPDATE live_order_previews SET state='expired' WHERE id=? AND state='pending'", (request.preview_id,))
        raise HTTPException(410, "Order preview expired. Request a fresh preview.")
    expected = f"PLACE LIVE {preview['side']} {preview['symbol']}"
    if request.confirmation != expected:
        raise HTTPException(400, f'Type exactly "{expected}" to confirm this individual market order.')
    # Recheck the live account and market price immediately before placement.
    account = await binance_get("/api/v3/account", key, secret)
    if not account.get("canTrade"):
        raise HTTPException(403, "Binance spot trading permission is not active.")
    ticker = await public_binance_get("/api/v3/ticker/price", {"symbol": preview["symbol"]})
    current_price = dec(ticker.get("price"), "current price")
    reference_price = dec(preview["quote_price"], "preview price")
    if abs(current_price - reference_price) / reference_price > Decimal("0.005"):
        with db() as conn:
            conn.execute("UPDATE live_order_previews SET state='price_moved' WHERE id=? AND state='pending'", (request.preview_id,))
        raise HTTPException(409, "Market price moved more than 0.5% since preview. Generate a new preview and review it.")
    quantity = dec(preview["quantity"], "quantity")
    limit_price = dec(preview["limit_price"], "limit price")
    notional = quantity * limit_price
    symbol_info = await public_binance_get("/api/v3/exchangeInfo", {"symbol": preview["symbol"]})
    rules = next((item for item in symbol_info.get("symbols", []) if item.get("symbol") == preview["symbol"]), None)
    if not rules or rules.get("status") != "TRADING" or not rules.get("isSpotTradingAllowed", False):
        raise HTTPException(400, "The symbol is no longer eligible for Binance Spot trading.")
    if preview["side"] == "SELL":
        base_asset = rules["baseAsset"]
        free = next((dec(b["free"], "free balance") for b in account.get("balances", []) if b.get("asset") == base_asset), Decimal("0"))
        if quantity > free:
            raise HTTPException(400, f"Insufficient free {base_asset} balance at final validation.")
    else:
        free_usdt = next((dec(b["free"], "free balance") for b in account.get("balances", []) if b.get("asset") == "USDT"), Decimal("0"))
        if notional > free_usdt:
            raise HTTPException(400, "Insufficient free USDT balance at final validation.")
    per_order, daily_limit = risk_limits()
    if notional > per_order:
        raise HTTPException(400, "Current estimated notional now exceeds the per-order risk cap.")
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        used = conn.execute("SELECT COALESCE(SUM(CAST(notional_usdt AS REAL)),0) AS total FROM live_order_previews WHERE state IN ('submitting','submitted','unknown') AND created_at >= ?", (datetime.now(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0).isoformat(),)).fetchone()["total"]
        if dec(used, "daily usage") + notional > daily_limit:
            raise HTTPException(400, "Current order would exceed the daily notional risk cap.")
        # Atomically claim the preview and reserve its full estimated notional.
        cur = conn.execute("UPDATE live_order_previews SET state='submitting' WHERE id=? AND state='pending'", (request.preview_id,))
        if cur.rowcount != 1:
            raise HTTPException(409, "This preview is already being processed.")
    client_order_id = "AF" + request.preview_id.replace("-", "")[:30]
    params = {
        "symbol": preview["symbol"], "side": preview["side"], "type": "LIMIT",
        "timeInForce": "IOC", "quantity": str(quantity), "price": str(limit_price),
        "newClientOrderId": client_order_id,
        "newOrderRespType": "FULL", "recvWindow": RECV_WINDOW,
        "timestamp": str(int(time.time() * 1000)),
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(BASE_URL + "/api/v3/order", params=signed_params(secret, params), headers={"X-MBX-APIKEY": key})
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPStatusError as exc:
        uncertain = exc.response.status_code >= 500
        with db() as conn:
            conn.execute("UPDATE live_order_previews SET state=? WHERE id=? AND state='submitting'", ("unknown" if uncertain else "exchange_error", request.preview_id))
        raise HTTPException(502, "Binance returned an uncertain server error. Check exchange order history before retrying; the system will not resubmit this preview." if uncertain else "Binance rejected the order. Review the exchange response and create a fresh preview if appropriate.")
    except httpx.RequestError:
        with db() as conn:
            conn.execute("UPDATE live_order_previews SET state='unknown' WHERE id=? AND state='submitting'", (request.preview_id,))
        raise HTTPException(502, "Order result is unknown due to a network error. Check Binance order history before doing anything else; do not retry this preview.")
    executed = str(data.get("executedQty", "0"))
    quote = str(data.get("cummulativeQuoteQty", "0"))
    order_id = str(data.get("orderId", ""))
    with db() as conn:
        conn.execute("INSERT INTO live_orders(id,preview_id,exchange_order_id,client_order_id,symbol,side,quantity,executed_quantity,quote_quantity,status,response,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), request.preview_id, order_id, client_order_id, preview["symbol"], preview["side"], str(quantity), executed, quote, data.get("status", "UNKNOWN"), json.dumps(data), stamp()))
        conn.execute("UPDATE live_order_previews SET state='submitted',response=? WHERE id=?", (json.dumps({"orderId": order_id, "status": data.get("status")}), request.preview_id))
    return {
        "submitted": True, "exchange": "Binance Spot LIVE", "order_id": order_id,
        "client_order_id": client_order_id, "symbol": preview["symbol"], "side": preview["side"],
        "status": data.get("status"), "executed_quantity": executed,
        "cumulative_quote_quantity": quote, "fills": data.get("fills", []),
        "notice": "Binance accepted the order request. Verify final fills and fees in exchange order history.",
    }


@router.get("/orders")
def live_orders(limit: int = 50):
    ensure_tables()
    if limit < 1 or limit > 200:
        raise HTTPException(400, "Limit must be between 1 and 200.")
    with db() as conn:
        rows = conn.execute("SELECT id,exchange_order_id,client_order_id,symbol,side,quantity,executed_quantity,quote_quantity,status,created_at FROM live_orders ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [dict(row) for row in rows]
