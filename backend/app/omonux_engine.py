"""Omonux market-data and deterministic signal engine.

This module deliberately produces research signals only. It never places orders.
"""
from __future__ import annotations

import math
import re
from typing import Any

import httpx

BINANCE = "https://api.binance.com"
INTERVALS = {"5m", "15m", "30m", "1h", "4h", "1d"}
SYMBOL_RE = re.compile(r"^[A-Z0-9]{2,20}$")


def validate_symbol(symbol: str) -> str:
    value = symbol.upper().replace("/", "").replace("-", "")
    if not SYMBOL_RE.fullmatch(value):
        raise ValueError("Use a valid market symbol such as BTCUSDT or ETHUSDT.")
    return value


async def fetch_candles(symbol: str, interval: str = "30m", limit: int = 120) -> list[dict[str, Any]]:
    symbol = validate_symbol(symbol)
    if interval not in INTERVALS:
        raise ValueError("Unsupported timeframe. Choose 5m, 15m, 30m, 1h, 4h or 1d.")
    limit = max(30, min(int(limit), 500))
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(
            f"{BINANCE}/api/v3/klines",
            params={"symbol": symbol, "interval": interval, "limit": limit},
        )
        response.raise_for_status()
        raw = response.json()
    # Binance includes the currently-forming candle as the final row.
    closed = raw[:-1]
    return [
        {
            "time": int(row[0]),
            "open": float(row[1]),
            "high": float(row[2]),
            "low": float(row[3]),
            "close": float(row[4]),
            "volume": float(row[5]),
            "close_time": int(row[6]),
        }
        for row in closed
    ]


def ema(values: list[float], period: int) -> list[float]:
    if not values or period < 1:
        raise ValueError("EMA requires values and a positive period.")
    alpha = 2 / (period + 1)
    result = [values[0]]
    for value in values[1:]:
        result.append(value * alpha + result[-1] * (1 - alpha))
    return result


def rsi(values: list[float], period: int = 14) -> list[float]:
    if len(values) <= period:
        raise ValueError("Not enough candles to calculate RSI.")
    gains = [max(values[i] - values[i - 1], 0.0) for i in range(1, len(values))]
    losses = [max(values[i - 1] - values[i], 0.0) for i in range(1, len(values))]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    result = [50.0] * period
    result.append(100.0 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss))
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        result.append(100.0 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss))
    return result


def atr(candles: list[dict[str, Any]], period: int = 14) -> list[float]:
    if len(candles) < period + 1:
        raise ValueError("Not enough candles to calculate ATR.")
    true_ranges = []
    for i, candle in enumerate(candles):
        previous = candles[i - 1]["close"] if i else candle["close"]
        true_ranges.append(max(
            candle["high"] - candle["low"],
            abs(candle["high"] - previous),
            abs(candle["low"] - previous),
        ))
    current = sum(true_ranges[:period]) / period
    result = [current] * period
    for value in true_ranges[period:]:
        current = (current * (period - 1) + value) / period
        result.append(current)
    return result


def build_signal(symbol: str, candles: list[dict[str, Any]]) -> dict[str, Any]:
    if len(candles) < 30:
        raise ValueError("At least 30 closed candles are required.")
    closes = [float(item["close"]) for item in candles]
    fast = ema(closes, 9)
    slow = ema(closes, 21)
    momentum = rsi(closes, 14)
    volatility = atr(candles, 14)
    i = len(closes) - 1
    score = 50
    score += 18 if fast[i] > slow[i] else -18
    score += 14 if 55 <= momentum[i] <= 72 else (-12 if momentum[i] < 45 else 0)
    score += 8 if closes[i] > closes[i - 1] else -6
    score = max(0, min(100, round(score)))
    side = "BUY" if score >= 60 else ("SELL" if score <= 40 else "HOLD")
    price = closes[i]
    return {
        "symbol": symbol,
        "timeframe": "closed_candles",
        "side": side,
        "confidence": score,
        "price": price,
        "indicators": {
            "ema_9": round(fast[i], 8),
            "ema_21": round(slow[i], 8),
            "rsi_14": round(momentum[i], 2),
            "atr_14": round(volatility[i], 8),
        },
        "risk_levels": {
            "stop_reference": round(price - 2 * volatility[i], 8) if side == "BUY" else round(price + 2 * volatility[i], 8),
            "target_reference": round(price + 3 * volatility[i], 8) if side == "BUY" else round(price - 3 * volatility[i], 8),
        },
        "candle_time": candles[i]["time"],
        "source": "Binance public market data",
        "execution": "research_only_no_order_placed",
    }
