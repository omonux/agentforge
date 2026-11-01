"""Read-only production account connectivity for OMONUX.

These endpoints query real exchange accounts but never submit, cancel, or amend orders.
Use API keys with read-only permissions and withdrawals disabled.
"""
import hashlib
import hmac
import time
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException

from .omonux_integrations import read_secret

router = APIRouter(prefix="/api/v1/trading/live-account", tags=["OMONUX Live Account"])
RECV_WINDOW = "5000"


def binance_live_signature(secret: str, params: dict) -> str:
    return hmac.new(secret.encode(), urlencode(params).encode(), hashlib.sha256).hexdigest()


def bybit_live_signature(secret: str, timestamp: str, api_key: str, query: str) -> str:
    payload = timestamp + api_key + RECV_WINDOW + query
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


@router.post("/binance")
async def binance_live_account():
    api_key = read_secret("binance_live_api_key")
    api_secret = read_secret("binance_live_api_secret")
    if not api_key or not api_secret:
        raise HTTPException(409, "Save separate Binance LIVE account credentials first.")
    params = {"recvWindow": RECV_WINDOW, "timestamp": str(int(time.time() * 1000))}
    params["signature"] = binance_live_signature(api_secret, params)
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.get(
                "https://api.binance.com/api/v3/account",
                params=params,
                headers={"X-MBX-APIKEY": api_key},
            )
        response.raise_for_status()
        data = response.json()
        balances = [
            {"asset": item["asset"], "free": item["free"], "locked": item["locked"]}
            for item in data.get("balances", [])
            if float(item.get("free", 0) or 0) > 0 or float(item.get("locked", 0) or 0) > 0
        ]
        return {
            "connected": True, "environment": "LIVE", "exchange": "Binance Spot",
            "account_type": "spot", "can_trade": bool(data.get("canTrade")),
            "can_withdraw": bool(data.get("canWithdraw")), "balances": balances,
            "notice": "Real account data retrieved. This endpoint is read-only and did not place an order.",
        }
    except httpx.HTTPStatusError:
        raise HTTPException(502, "Binance rejected the live account check. Verify the LIVE key, secret, IP allowlist and read permission.")
    except (httpx.RequestError, ValueError, KeyError, TypeError):
        raise HTTPException(502, "Could not complete the Binance live account check.")


@router.post("/bybit")
async def bybit_live_account():
    api_key = read_secret("bybit_live_api_key")
    api_secret = read_secret("bybit_live_api_secret")
    if not api_key or not api_secret:
        raise HTTPException(409, "Save separate Bybit LIVE account credentials first.")
    timestamp = str(int(time.time() * 1000))
    query = "accountType=UNIFIED"
    signature = bybit_live_signature(api_secret, timestamp, api_key, query)
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.get(
                "https://api.bybit.com/v5/account/wallet-balance",
                params={"accountType": "UNIFIED"},
                headers={
                    "X-BAPI-API-KEY": api_key, "X-BAPI-SIGN": signature,
                    "X-BAPI-SIGN-TYPE": "2", "X-BAPI-TIMESTAMP": timestamp,
                    "X-BAPI-RECV-WINDOW": RECV_WINDOW,
                },
            )
        response.raise_for_status()
        data = response.json()
        if data.get("retCode") != 0:
            raise HTTPException(502, "Bybit rejected the live account check. Verify the LIVE key, secret, IP allowlist and read permission.")
        coins = []
        for account in data.get("result", {}).get("list", []):
            for coin in account.get("coin", []):
                if float(coin.get("walletBalance", 0) or 0) > 0:
                    coins.append({
                        "coin": coin.get("coin"),
                        "wallet_balance": coin.get("walletBalance"),
                        "available_balance": coin.get("availableToWithdraw"),
                    })
        return {
            "connected": True, "environment": "LIVE", "exchange": "Bybit V5",
            "account_type": "UNIFIED", "balances": coins,
            "notice": "Real account data retrieved. This endpoint is read-only and did not place an order.",
        }
    except HTTPException:
        raise
    except httpx.HTTPStatusError:
        raise HTTPException(502, "Bybit rejected the live account check. Verify the LIVE key, secret, IP allowlist and read permission.")
    except (httpx.RequestError, ValueError, KeyError, TypeError):
        raise HTTPException(502, "Could not complete the Bybit live account check.")
