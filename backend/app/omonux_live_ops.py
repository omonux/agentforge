"""OMONUX live operations: Bybit Spot, reconciliation, analytics, research and alerts.

All order placement remains manual, preview-based and behind server-side feature flags.
Research endpoints never place orders. Telegram alerts are opt-in and best-effort.
"""
from __future__ import annotations

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

from .main import db, stamp
from .omonux_integrations import read_secret
from .omonux_engine import fetch_candles, ema

router = APIRouter(prefix="/api/v1/trading/live-ops", tags=["OMONUX Live Operations"])
BYBIT = "https://api.bybit.com"
RECV = "5000"


def ensure_ops_tables():
    with db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS live_order_previews(
            id TEXT PRIMARY KEY, exchange_name TEXT NOT NULL, symbol TEXT NOT NULL, side TEXT NOT NULL,
            quantity TEXT NOT NULL, quote_price TEXT NOT NULL, limit_price TEXT NOT NULL DEFAULT '0',
            notional_usdt TEXT NOT NULL, created_at TEXT NOT NULL, expires_at INTEGER NOT NULL,
            state TEXT NOT NULL DEFAULT 'pending', response TEXT)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS live_orders(
            id TEXT PRIMARY KEY, preview_id TEXT NOT NULL UNIQUE, exchange_order_id TEXT,
            client_order_id TEXT NOT NULL UNIQUE, symbol TEXT NOT NULL, side TEXT NOT NULL,
            quantity TEXT NOT NULL, executed_quantity TEXT, quote_quantity TEXT,
            status TEXT NOT NULL, response TEXT NOT NULL, created_at TEXT NOT NULL)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS live_trading_state(
            id INTEGER PRIMARY KEY CHECK(id=1), emergency_stopped INTEGER NOT NULL DEFAULT 1,
            reason TEXT, updated TEXT NOT NULL)""")
        conn.execute("INSERT OR IGNORE INTO live_trading_state(id,emergency_stopped,updated) VALUES(1,1,?)", (stamp(),))
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(live_orders)")}
        if "exchange_name" not in columns:
            conn.execute("ALTER TABLE live_orders ADD COLUMN exchange_name TEXT NOT NULL DEFAULT 'binance'")
        conn.execute("""CREATE TABLE IF NOT EXISTS live_alert_preferences(
            id INTEGER PRIMARY KEY CHECK(id=1), enabled INTEGER NOT NULL DEFAULT 0,
            on_fill INTEGER NOT NULL DEFAULT 1, on_partial INTEGER NOT NULL DEFAULT 1,
            on_reject INTEGER NOT NULL DEFAULT 1, on_risk_stop INTEGER NOT NULL DEFAULT 1,
            updated TEXT NOT NULL)""")
        conn.execute("INSERT OR IGNORE INTO live_alert_preferences(id,updated) VALUES(1,?)", (stamp(),))
        conn.execute("""CREATE TABLE IF NOT EXISTS live_alert_outbox(
            id TEXT PRIMARY KEY, event_type TEXT NOT NULL, payload TEXT NOT NULL,
            status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
            error TEXT, created TEXT NOT NULL, sent_at TEXT)""")


def decimal(value, label):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise HTTPException(400, f"Invalid {label}.")
    if not result.is_finite():
        raise HTTPException(400, f"Invalid {label}.")
    return result


def bybit_keys():
    key, secret = read_secret("bybit_live_api_key"), read_secret("bybit_live_api_secret")
    if not key or not secret:
        raise HTTPException(409, "Save separate Bybit LIVE API credentials in the encrypted integration vault first.")
    return key, secret


def bybit_signature(secret: str, timestamp: str, key: str, payload: str) -> str:
    return hmac.new(secret.encode(), (timestamp + key + RECV + payload).encode(), hashlib.sha256).hexdigest()


async def bybit_request(method: str, path: str, key: str, secret: str, params=None, body=None, private=True):
    params = params or {}
    body = body or {}
    timestamp = str(int(time.time() * 1000))
    query = urlencode(sorted((k, str(v)) for k, v in params.items()))
    body_text = json.dumps(body, separators=(",", ":"), ensure_ascii=False)
    headers = {"Content-Type": "application/json"}
    if private:
        payload = query if method == "GET" else body_text
        headers.update({
            "X-BAPI-API-KEY": key,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": RECV,
            "X-BAPI-SIGN": bybit_signature(secret, timestamp, key, payload),
            "X-BAPI-SIGN-TYPE": "2",
        })
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            if method == "GET":
                response = await client.get(BYBIT + path, params=params, headers=headers)
            else:
                response = await client.post(BYBIT + path, content=body_text, headers=headers)
        response.raise_for_status()
        data = response.json()
        if data.get("retCode", 0) != 0:
            raise HTTPException(502, "Bybit rejected the request. Check API key permissions, IP restrictions and account status.")
        return data.get("result", {})
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, "Could not verify the Bybit request. Check the exchange account before retrying any order.")


async def telegram_send(message: str):
    token, chat = read_secret("telegram_bot_token"), read_secret("telegram_chat_id")
    if not token or not chat:
        return False, "Telegram credentials are not configured."
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(f"https://api.telegram.org/bot{token}/sendMessage",
                                         json={"chat_id": chat, "text": message[:3900], "disable_web_page_preview": True})
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            return False, "Telegram did not accept the message."
        return True, None
    except httpx.HTTPError:
        return False, "Telegram delivery failed; event remains recorded locally."


async def queue_alert(event_type: str, payload: dict):
    ensure_ops_tables()
    with db() as conn:
        pref = conn.execute("SELECT * FROM live_alert_preferences WHERE id=1").fetchone()
    flag = {"FILL": "on_fill", "PARTIAL_FILL": "on_partial", "REJECT": "on_reject", "RISK_STOP": "on_risk_stop"}.get(event_type)
    if not pref or not pref["enabled"] or not flag or not pref[flag]:
        return
    alert_id = str(uuid.uuid4())
    with db() as conn:
        conn.execute("INSERT INTO live_alert_outbox(id,event_type,payload,status,created) VALUES(?,?,?,'pending',?)",
                     (alert_id, event_type, json.dumps(payload), stamp()))
    message = "AgentForge / OMONUX LIVE ALERT\n" + event_type.replace("_", " ") + "\n" + "\n".join(f"{k}: {v}" for k, v in payload.items())
    ok, error = await telegram_send(message)
    with db() as conn:
        conn.execute("UPDATE live_alert_outbox SET status=?,attempts=attempts+1,error=?,sent_at=? WHERE id=?",
                     ("sent" if ok else "pending", error, stamp() if ok else None, alert_id))


class BybitPreview(BaseModel):
    symbol: str = Field(min_length=5, max_length=20, pattern=r"^[A-Za-z0-9]+$")
    side: str
    quantity: Decimal = Field(gt=0, max_digits=24, decimal_places=12)


class BybitPlace(BaseModel):
    preview_id: str = Field(min_length=36, max_length=36)
    confirmation: str = Field(min_length=10, max_length=80)


class AlertPreferences(BaseModel):
    enabled: bool = False
    on_fill: bool = True
    on_partial: bool = True
    on_reject: bool = True
    on_risk_stop: bool = True


@router.post("/bybit/preview")
async def preview_bybit(request: BybitPreview):
    ensure_ops_tables()
    if os.getenv("BYBIT_LIVE_TRADING_ENABLED", "").lower() != "true":
        raise HTTPException(423, "Bybit live execution is disabled by the server feature flag.")
    side = request.side.upper()
    symbol = request.symbol.upper()
    if side not in ("BUY", "SELL") or not symbol.endswith("USDT"):
        raise HTTPException(400, "Only BUY/SELL spot pairs quoted in USDT are supported.")
    quantity = decimal(request.quantity, "quantity")
    key, secret = bybit_keys()
    account = await bybit_request("GET", "/v5/account/wallet-balance", key, secret, {"accountType": "UNIFIED"})
    tickers = await bybit_request("GET", "/v5/market/tickers", key, secret, {"category": "spot", "symbol": symbol}, private=False)
    instruments = await bybit_request("GET", "/v5/market/instruments-info", key, secret, {"category": "spot", "symbol": symbol}, private=False)
    ticker = next(iter(tickers.get("list", [])), None)
    instrument = next(iter(instruments.get("list", [])), None)
    if not ticker or not instrument or instrument.get("status") != "Trading":
        raise HTTPException(400, "Bybit spot symbol is unavailable or not trading.")
    price = decimal(ticker["lastPrice"], "market price")
    lot = instrument.get("lotSizeFilter", {})
    qty_step = decimal(lot.get("qtyStep", "0.00000001"), "quantity step")
    min_qty = decimal(lot.get("minOrderQty", "0"), "minimum quantity")
    max_qty = decimal(lot.get("maxOrderQty", "0"), "maximum quantity")
    if quantity % qty_step != 0 or quantity < min_qty or (max_qty > 0 and quantity > max_qty):
        raise HTTPException(400, f"Quantity must satisfy Bybit lot-size rules (step {qty_step}, min {min_qty}).")
    price_filter = instrument.get("priceFilter", {})
    tick = decimal(price_filter.get("tickSize", "0.00000001"), "price tick")
    raw_limit = price * (Decimal("1.005") if side == "BUY" else Decimal("0.995"))
    limit_price = (raw_limit / tick).to_integral_value(rounding=ROUND_UP if side == "BUY" else ROUND_DOWN) * tick
    notional = quantity * limit_price
    max_order = decimal(os.getenv("LIVE_MAX_ORDER_NOTIONAL_USDT", "25"), "per-order cap")
    daily_cap = decimal(os.getenv("LIVE_MAX_DAILY_NOTIONAL_USDT", "100"), "daily cap")
    if max_order <= 0 or daily_cap <= 0 or max_order > daily_cap:
        raise HTTPException(503, "Bybit live order risk limits are invalid.")
    if notional > max_order:
        raise HTTPException(400, f"Order exceeds configured per-order cap ({max_order} USDT).")
    day_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    with db() as conn:
        reserved = conn.execute("SELECT COALESCE(SUM(CAST(notional_usdt AS REAL)),0) AS total FROM live_order_previews WHERE created_at>=? AND state IN ('submitting','submitted','unknown')", (day_start,)).fetchone()["total"]
    if decimal(reserved, "daily reserved notional") + notional > daily_cap:
        raise HTTPException(400, f"Order would exceed daily live notional cap ({daily_cap} USDT).")
    min_order = decimal(lot.get("minOrderAmt", "0"), "minimum order amount")
    if notional < min_order:
        raise HTTPException(400, f"Order is below Bybit minimum order amount ({min_order} USDT).")
    wallets = account.get("list", [])
    coins = wallets[0].get("coin", []) if wallets else []
    if side == "BUY":
        available = next((decimal(c.get("availableToWithdraw", c.get("walletBalance", "0")), "USDT balance") for c in coins if c.get("coin") == "USDT"), Decimal("0"))
        if notional > available:
            raise HTTPException(400, "Insufficient available USDT balance.")
    else:
        base = instrument.get("baseCoin")
        available = next((decimal(c.get("availableToWithdraw", c.get("walletBalance", "0")), "base balance") for c in coins if c.get("coin") == base), Decimal("0"))
        if quantity > available:
            raise HTTPException(400, f"Insufficient available {base} balance.")
    preview_id = str(uuid.uuid4())
    expires = int(time.time()) + 60
    with db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS live_order_previews(
            id TEXT PRIMARY KEY, exchange_name TEXT NOT NULL, symbol TEXT NOT NULL, side TEXT NOT NULL,
            quantity TEXT NOT NULL, quote_price TEXT NOT NULL, limit_price TEXT NOT NULL DEFAULT '0',
            notional_usdt TEXT NOT NULL, created_at TEXT NOT NULL, expires_at INTEGER NOT NULL,
            state TEXT NOT NULL DEFAULT 'pending', response TEXT)""")
        conn.execute("INSERT INTO live_order_previews(id,exchange_name,symbol,side,quantity,quote_price,limit_price,notional_usdt,created_at,expires_at,state) VALUES(?,?,?,?,?,?,?,?,?,?,'pending')",
                     (preview_id, "bybit", symbol, side, str(quantity), str(price), str(limit_price), str(notional), stamp(), expires))
    return {"preview_id": preview_id, "exchange": "Bybit Spot LIVE", "symbol": symbol, "side": side,
            "order_type": "LIMIT IOC (price-protected)", "quantity": str(quantity), "reference_price": str(price),
            "limit_price": str(limit_price), "maximum_notional_usdt": str(notional), "expires_at": expires,
            "confirmation_text": f"PLACE LIVE {side} {symbol}", "execution_enabled": True,
            "warning": "IOC limit order: fills only at this limit or better; any unfilled remainder is cancelled. Partial fills and fees are possible."}


@router.post("/bybit/place")
async def place_bybit(request: BybitPlace):
    ensure_ops_tables()
    if os.getenv("BYBIT_LIVE_TRADING_ENABLED", "").lower() != "true":
        raise HTTPException(423, "Bybit live execution is disabled by the server feature flag.")
    with db() as conn:
        state = conn.execute("SELECT emergency_stopped FROM live_trading_state WHERE id=1").fetchone()
        preview = conn.execute("SELECT * FROM live_order_previews WHERE id=? AND exchange_name='bybit'", (request.preview_id,)).fetchone()
    if not state or state["emergency_stopped"]:
        raise HTTPException(423, "Global live-trading emergency stop is active.")
    if not preview or preview["state"] != "pending":
        raise HTTPException(404, "Pending Bybit order preview not found.")
    if int(time.time()) > int(preview["expires_at"]):
        with db() as conn:
            conn.execute("UPDATE live_order_previews SET state='expired' WHERE id=?", (request.preview_id,))
        raise HTTPException(410, "Preview expired. Request a fresh preview.")
    expected = f"PLACE LIVE {preview['side']} {preview['symbol']}"
    if request.confirmation != expected:
        raise HTTPException(400, f'Type exactly "{expected}" to confirm this order.')
    key, secret = bybit_keys()
    # Recheck market price and account funds immediately before submitting.
    ticker = await bybit_request("GET", "/v5/market/tickers", key, secret, {"category": "spot", "symbol": preview["symbol"]}, private=False)
    latest = next(iter(ticker.get("list", [])), None)
    if not latest:
        raise HTTPException(502, "Could not refresh Bybit price; no order was sent.")
    current_price = decimal(latest["lastPrice"], "current price")
    reference = decimal(preview["quote_price"], "preview price")
    if abs(current_price-reference)/reference > Decimal("0.005"):
        with db() as conn:
            conn.execute("UPDATE live_order_previews SET state='price_moved' WHERE id=? AND state='pending'", (request.preview_id,))
        raise HTTPException(409, "Bybit price moved more than 0.5%; create and review a new preview.")
    wallet = await bybit_request("GET", "/v5/account/wallet-balance", key, secret, {"accountType": "UNIFIED"})
    balances = wallet.get("list", [])
    coins = balances[0].get("coin", []) if balances else []
    instrument = await bybit_request("GET", "/v5/market/instruments-info", key, secret, {"category": "spot", "symbol": preview["symbol"]}, private=False)
    item = next(iter(instrument.get("list", [])), None)
    if not item or item.get("status") != "Trading":
        raise HTTPException(400, "Bybit symbol is no longer eligible for spot trading.")
    qty = decimal(preview["quantity"], "quantity")
    limit_price = decimal(preview["limit_price"], "limit price")
    estimated = qty * limit_price
    if preview["side"] == "BUY":
        available = next((decimal(c.get("availableToWithdraw", c.get("walletBalance", "0")), "USDT balance") for c in coins if c.get("coin") == "USDT"), Decimal("0"))
        if estimated > available:
            raise HTTPException(400, "Insufficient available USDT at final validation.")
    else:
        base = item.get("baseCoin")
        available = next((decimal(c.get("availableToWithdraw", c.get("walletBalance", "0")), "base balance") for c in coins if c.get("coin") == base), Decimal("0"))
        if qty > available:
            raise HTTPException(400, f"Insufficient available {base} at final validation.")
    per_order = decimal(os.getenv("LIVE_MAX_ORDER_NOTIONAL_USDT", "25"), "per-order cap")
    daily_cap = decimal(os.getenv("LIVE_MAX_DAILY_NOTIONAL_USDT", "100"), "daily cap")
    if estimated > per_order:
        raise HTTPException(400, "Order exceeds per-order cap at final validation.")
    # Claim preview and reserve the daily cap atomically; uncertain outcomes are never retried.
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        day_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        reserved = conn.execute("SELECT COALESCE(SUM(CAST(notional_usdt AS REAL)),0) AS total FROM live_order_previews WHERE created_at>=? AND state IN ('submitting','submitted','unknown')", (day_start,)).fetchone()["total"]
        if decimal(reserved, "daily reserved notional") + estimated > daily_cap:
            raise HTTPException(400, "Order would exceed daily notional cap.")
        cur = conn.execute("UPDATE live_order_previews SET state='submitting' WHERE id=? AND state='pending'", (request.preview_id,))
        if cur.rowcount != 1:
            raise HTTPException(409, "This preview has already been submitted or claimed.")
    client_id = "AF" + request.preview_id.replace("-", "")[:30]
    body = {"category": "spot", "symbol": preview["symbol"], "side": preview["side"].title(),
            "orderType": "Limit", "qty": preview["quantity"], "price": preview["limit_price"],
            "timeInForce": "IOC", "orderLinkId": client_id}
    try:
        result = await bybit_request("POST", "/v5/order/create", key, secret, body=body)
    except HTTPException:
        # Persist the client order link even when the HTTP response is ambiguous.
        # Reconciliation can then query Bybit by orderLinkId without ever resubmitting.
        with db() as conn:
            conn.execute("UPDATE live_order_previews SET state='unknown' WHERE id=? AND state='submitting'", (request.preview_id,))
            conn.execute("""INSERT OR IGNORE INTO live_orders(id,preview_id,exchange_order_id,client_order_id,
                symbol,side,quantity,executed_quantity,quote_quantity,status,response,created_at,exchange_name)
                VALUES(?,?,NULL,?,?,?,?,?,?,?,'{}',?,'bybit')""",
                (str(uuid.uuid4()), request.preview_id, client_id, preview["symbol"], preview["side"],
                 preview["quantity"], "0", "0", "UNKNOWN", stamp()))
        raise HTTPException(502, "Bybit order result may be uncertain. Its client order ID has been saved for reconciliation. Check Bybit order history; this preview cannot be retried.")
    order_id = result.get("orderId", "")
    with db() as conn:
        conn.execute("""INSERT INTO live_orders(id,preview_id,exchange_order_id,client_order_id,symbol,side,quantity,
            executed_quantity,quote_quantity,status,response,created_at,exchange_name)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (str(uuid.uuid4()), request.preview_id, order_id, client_id, preview["symbol"], preview["side"],
             preview["quantity"], "0", "0", "New", json.dumps(result), stamp(), "bybit"))
        conn.execute("UPDATE live_order_previews SET state='submitted',response=? WHERE id=?", (json.dumps(result), request.preview_id))
    return {"submitted": True, "exchange": "Bybit Spot LIVE", "order_id": order_id, "client_order_id": client_id,
            "status": "New", "notice": "Bybit accepted the order request; reconcile it to obtain fills and fees."}


@router.post("/orders/reconcile")
async def reconcile_orders():
    ensure_ops_tables()
    results = []
    with db() as conn:
        orders = conn.execute("SELECT * FROM live_orders WHERE status NOT IN ('FILLED','CANCELED','REJECTED','PARTIALLY_FILLED_FINAL','Filled','Cancelled','Rejected') ORDER BY created_at DESC LIMIT 100").fetchall()
    for order in orders:
        exchange = order["exchange_name"] if "exchange_name" in order.keys() else "binance"
        try:
            if exchange == "bybit":
                key, secret = bybit_keys()
                lookup = {"category": "spot", "symbol": order["symbol"]}
                if order["exchange_order_id"]:
                    lookup["orderId"] = order["exchange_order_id"]
                else:
                    lookup["orderLinkId"] = order["client_order_id"]
                data = await bybit_request("GET", "/v5/order/realtime", key, secret, lookup)
                item = next(iter(data.get("list", [])), None)
                if not item:
                    history = await bybit_request("GET", "/v5/order/history", key, secret, lookup)
                    item = next(iter(history.get("list", [])), None)
                if not item:
                    results.append({"id": order["id"], "exchange": exchange,
                                    "status": "UNKNOWN", "notice": "No matching exchange order found yet; do not resubmit."})
                    continue
                status = item.get("orderStatus", order["status"])
                executed = item.get("cumExecQty", order["executed_quantity"] or "0")
                quote = item.get("cumExecValue", order["quote_quantity"] or "0")
                resolved_order_id = item.get("orderId") or order["exchange_order_id"]
                executions = await bybit_request("GET", "/v5/execution/list", key, secret,
                                                  {"category": "spot", "symbol": order["symbol"], "orderId": resolved_order_id})
                detail = {"order": item, "fills": executions.get("list", [])}
            else:
                key, secret = read_secret("binance_live_api_key"), read_secret("binance_live_api_secret")
                if not key or not secret:
                    raise HTTPException(409, "Binance LIVE credentials missing.")
                params = {"symbol": order["symbol"], "recvWindow": RECV,
                          "timestamp": str(int(time.time() * 1000))}
                if order["exchange_order_id"]:
                    params["orderId"] = order["exchange_order_id"]
                else:
                    params["origClientOrderId"] = order["client_order_id"]
                params["signature"] = hmac.new(secret.encode(), urlencode(params).encode(), hashlib.sha256).hexdigest()
                async with httpx.AsyncClient(timeout=12) as client:
                    response = await client.get("https://api.binance.com/api/v3/order", params=params, headers={"X-MBX-APIKEY": key})
                response.raise_for_status()
                item = response.json()
                status = item.get("status", order["status"])
                executed = item.get("executedQty", order["executed_quantity"] or "0")
                quote = item.get("cummulativeQuoteQty", order["quote_quantity"] or "0")
                trade_params = {"symbol": order["symbol"], "orderId": item.get("orderId") or order["exchange_order_id"],
                                "recvWindow": RECV, "timestamp": str(int(time.time() * 1000))}
                trade_params["signature"] = hmac.new(secret.encode(), urlencode(trade_params).encode(), hashlib.sha256).hexdigest()
                async with httpx.AsyncClient(timeout=12) as client:
                    trades_response = await client.get("https://api.binance.com/api/v3/myTrades", params=trade_params, headers={"X-MBX-APIKEY": key})
                trades_response.raise_for_status()
                detail = {"order": item, "fills": trades_response.json()}
            previous_executed = Decimal(str(order["executed_quantity"] or "0"))
            current_executed = Decimal(str(executed or "0"))
            with db() as conn:
                # Compare-and-set the cumulative fill value. Manual and background
                # reconciliation can overlap; only the caller that advances the
                # stored quantity is allowed to emit the corresponding alert.
                updated = conn.execute(
                    """UPDATE live_orders SET exchange_order_id=COALESCE(exchange_order_id,?),
                       status=?,executed_quantity=?,quote_quantity=?,response=?
                       WHERE id=? AND COALESCE(executed_quantity,'0')=?""",
                    (item.get("orderId"), status, str(current_executed), quote, json.dumps(detail),
                     order["id"], str(previous_executed)),
                )
                fill_advanced = updated.rowcount == 1 and current_executed > previous_executed
            # Notify only after this reconciliation atomically advances the fill.
            if fill_advanced:
                await queue_alert("FILL" if status in ("FILLED", "Filled") else "PARTIAL_FILL",
                                  {"exchange": exchange, "symbol": order["symbol"], "side": order["side"],
                                   "newly_executed_quantity": str(current_executed-previous_executed),
                                   "cumulative_executed_quantity": str(current_executed),
                                   "quote_value": quote, "status": status})
            results.append({"id": order["id"], "exchange": exchange, "status": status, "executed_quantity": executed, "quote_quantity": quote})
        except Exception as exc:
            results.append({"id": order["id"], "exchange": exchange, "error": str(exc)[:240]})
    return {"checked": len(orders), "results": results}


@router.get("/analytics")
def live_analytics():
    ensure_ops_tables()
    with db() as conn:
        orders = conn.execute("SELECT exchange_name,symbol,side,quantity,executed_quantity,quote_quantity,status,created_at,response FROM live_orders ORDER BY created_at DESC LIMIT 500").fetchall()
    volume = Decimal("0")
    fees = {}
    by_status = {}
    by_exchange = {}
    for row in orders:
        value = decimal(row["quote_quantity"] or "0", "executed quote value")
        volume += value
        by_status[row["status"]] = by_status.get(row["status"], 0) + 1
        ex = row["exchange_name"] if "exchange_name" in row.keys() else "binance"
        by_exchange[ex] = by_exchange.get(ex, 0) + 1
        try:
            raw = json.loads(row["response"] or "{}")
            fills = raw.get("fills", []) if isinstance(raw, dict) else []
            for fill in fills:
                asset = fill.get("commissionAsset") or fill.get("feeCurrency") or "unknown"
                amount = fill.get("commission", fill.get("execFee", "0"))
                fees[asset] = str(Decimal(fees.get(asset, "0")) + Decimal(str(amount)))
        except (ValueError, InvalidOperation, TypeError):
            pass
    return {"orders_included": len(orders), "executed_quote_volume_usdt": str(volume),
            "fees_by_asset": fees, "orders_by_status": by_status, "orders_by_exchange": by_exchange,
            "warning": "This is order/fill analytics, not net profit. Fees in non-USDT assets are not converted. Only locally recorded orders are included."}


@router.post("/research/ema")
async def research_ema(symbol: str = "BTCUSDT", interval: str = "1h", fast: int = 9, slow: int = 21,
                       fee_bps: float = 10, slippage_bps: float = 5, limit: int = 500):
    if fast < 2 or slow <= fast or slow > 100 or not 0 <= fee_bps <= 100 or not 0 <= slippage_bps <= 100:
        raise HTTPException(400, "Use 2 <= fast < slow <= 100 and fee/slippage assumptions between 0 and 100 basis points.")
    try:
        candles = await fetch_candles(symbol, interval, limit)
    except (ValueError, httpx.HTTPError) as exc:
        raise HTTPException(502, f"Market research data unavailable: {str(exc)[:160]}")
    closes = [float(c["close"]) for c in candles]
    if len(closes) < slow + 30:
        raise HTTPException(400, "Not enough completed candles for this research run.")
    fast_line, slow_line = ema(closes, fast), ema(closes, slow)
    # Signals use candle i; returns begin at candle i+1 to avoid same-close lookahead.
    split = max(slow + 5, int(len(closes) * 0.7))
    cost = (fee_bps + slippage_bps) / 10000
    equity, peak, max_dd = 1.0, 1.0, 0.0
    in_position = False
    trades, returns = [], []
    for i in range(slow, len(closes) - 1):
        if i == split:
            # Out-of-sample section starts flat; no open training trade carries across.
            in_position = False
        if fast_line[i] > slow_line[i] and not in_position:
            entry = closes[i + 1] * (1 + cost)
            in_position = True
            entry_i = i + 1
            entry_price = entry
        elif fast_line[i] <= slow_line[i] and in_position:
            exit_price = closes[i + 1] * (1 - cost)
            trade_return = exit_price / entry_price - 1
            equity *= (1 + trade_return)
            peak = max(peak, equity)
            max_dd = min(max_dd, equity / peak - 1)
            trades.append({"entry_index": entry_i, "exit_index": i + 1, "return_pct": round(trade_return * 100, 4)})
            returns.append(trade_return)
            in_position = False
    out_start = split
    out_trades = [t for t in trades if t["entry_index"] >= out_start]
    out_returns = [t["return_pct"] for t in out_trades]
    wins = sum(1 for r in out_returns if r > 0)
    return {"symbol": symbol.upper(), "interval": interval, "candles": len(candles),
            "strategy": f"EMA {fast}/{slow} long-only crossover", "training_test_split": "70/30 chronological; report out-of-sample segment",
            "out_of_sample_trades": len(out_trades), "out_of_sample_win_rate_pct": round(wins / len(out_returns) * 100, 2) if out_returns else None,
            "out_of_sample_compounded_return_pct": round(((__import__("math").prod(1 + r / 100 for r in out_returns)) - 1) * 100, 3) if out_returns else None,
            "assumed_fee_bps_per_side": fee_bps, "assumed_slippage_bps_per_side": slippage_bps,
            "max_drawdown_full_sample_pct": round(max_dd * 100, 3),
            "sample_trades": out_trades[-20:], "execution": "research_only_no_orders",
            "warning": "Historical, simplified research only. No guarantee of future returns. Fees/slippage are assumptions; no spread, funding, taxes or market impact model."}


@router.get("/alerts/preferences")
def get_alert_preferences():
    ensure_ops_tables()
    with db() as conn:
        row = conn.execute("SELECT enabled,on_fill,on_partial,on_reject,on_risk_stop,updated FROM live_alert_preferences WHERE id=1").fetchone()
    result = dict(row)
    for key in ("enabled", "on_fill", "on_partial", "on_reject", "on_risk_stop"):
        result[key] = bool(result[key])
    return result


@router.put("/alerts/preferences")
def put_alert_preferences(request: AlertPreferences):
    ensure_ops_tables()
    with db() as conn:
        conn.execute("""UPDATE live_alert_preferences SET enabled=?,on_fill=?,on_partial=?,on_reject=?,on_risk_stop=?,updated=? WHERE id=1""",
                     (int(request.enabled), int(request.on_fill), int(request.on_partial), int(request.on_reject), int(request.on_risk_stop), stamp()))
    return get_alert_preferences()


@router.post("/alerts/test")
async def test_alert():
    ok, error = await telegram_send("AgentForge / OMONUX: Telegram alert connection test successful.")
    if not ok:
        raise HTTPException(409, error)
    return {"sent": True}


@router.post("/alerts/retry")
async def retry_alerts():
    ensure_ops_tables()
    with db() as conn:
        pending = conn.execute("SELECT * FROM live_alert_outbox WHERE status='pending' ORDER BY created LIMIT 50").fetchall()
    sent = 0
    for row in pending:
        payload = json.loads(row["payload"])
        message = "AgentForge / OMONUX LIVE ALERT\n" + row["event_type"].replace("_", " ") + "\n" + "\n".join(f"{k}: {v}" for k, v in payload.items())
        ok, error = await telegram_send(message)
        with db() as conn:
            conn.execute("UPDATE live_alert_outbox SET status=?,attempts=attempts+1,error=?,sent_at=? WHERE id=?",
                         ("sent" if ok else "pending", error, stamp() if ok else None, row["id"]))
        sent += int(ok)
    return {"pending_checked": len(pending), "sent": sent}
