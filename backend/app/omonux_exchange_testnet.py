"""Read-only exchange connectivity checks against exchange testnets. No order endpoints exist here."""
import hashlib
import hmac
import time
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException

from .omonux_integrations import read_secret

router = APIRouter(prefix="/api/v1/trading/exchanges", tags=["OMONUX Exchange Testnet"])
RECV_WINDOW = "5000"


def binance_signature(secret: str, params: dict) -> str:
    return hmac.new(secret.encode(), urlencode(params).encode(), hashlib.sha256).hexdigest()


def bybit_signature(secret: str, timestamp: str, api_key: str, query: str) -> str:
    payload = timestamp + api_key + RECV_WINDOW + query
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


@router.post("/binance/test")
async def test_binance_testnet():
    api_key = read_secret("binance_api_key")
    api_secret = read_secret("binance_api_secret")
    if not api_key or not api_secret:
        raise HTTPException(409, "Save both Binance API credentials first.")
    params = {"recvWindow": RECV_WINDOW, "timestamp": str(int(time.time() * 1000))}
    params["signature"] = binance_signature(api_secret, params)
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.get(
                "https://testnet.binance.vision/api/v3/account",
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
        return {"connected": True, "exchange": "Binance Spot Testnet", "account_type": "spot", "can_trade": bool(data.get("canTrade")), "can_withdraw": False, "balances": balances, "notice": "Read-only account check. No order was placed."}
    except httpx.HTTPStatusError:
        raise HTTPException(502, "Binance testnet rejected the connection. Check the testnet key, secret and API permissions.")
    except (httpx.RequestError, ValueError, KeyError):
        raise HTTPException(502, "Could not complete the Binance testnet check. Try again later.")


@router.post("/bybit/test")
async def test_bybit_testnet():
    api_key = read_secret("bybit_api_key")
    api_secret = read_secret("bybit_api_secret")
    if not api_key or not api_secret:
        raise HTTPException(409, "Save both Bybit API credentials first.")
    timestamp = str(int(time.time() * 1000))
    query = "accountType=UNIFIED"
    signature = bybit_signature(api_secret, timestamp, api_key, query)
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.get(
                "https://api-testnet.bybit.com/v5/account/wallet-balance",
                params={"accountType": "UNIFIED"},
                headers={
                    "X-BAPI-API-KEY": api_key,
                    "X-BAPI-SIGN": signature,
                    "X-BAPI-SIGN-TYPE": "2",
                    "X-BAPI-TIMESTAMP": timestamp,
                    "X-BAPI-RECV-WINDOW": RECV_WINDOW,
                },
            )
        response.raise_for_status()
        data = response.json()
        if data.get("retCode") != 0:
            raise HTTPException(502, "Bybit testnet rejected the connection. Check the testnet key, secret and API permissions.")
        accounts = data.get("result", {}).get("list", [])
        coins = []
        for account in accounts:
            for coin in account.get("coin", []):
                if float(coin.get("walletBalance", 0) or 0) > 0:
                    coins.append({"coin": coin.get("coin"), "wallet_balance": coin.get("walletBalance"), "available_balance": coin.get("availableToWithdraw")})
        return {"connected": True, "exchange": "Bybit V5 Testnet", "account_type": "UNIFIED", "balances": coins, "notice": "Read-only account check. No order was placed."}
    except HTTPException:
        raise
    except httpx.HTTPStatusError:
        raise HTTPException(502, "Bybit testnet rejected the connection. Check the testnet key, secret and API permissions.")
    except (httpx.RequestError, ValueError, KeyError, TypeError):
        raise HTTPException(502, "Could not complete the Bybit testnet check. Try again later.")
