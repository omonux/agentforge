"""Strict MT5 closed-candle normalization and research-only directional signal."""
from __future__ import annotations
import math
from typing import Any

def normalize_forex_candles(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert verified closed MT5 candles to the shared council evidence format.

    Timestamp is a Unix epoch in seconds or milliseconds. Reject invalid,
    duplicated or out-of-order data rather than silently repairing it.
    """
    if not isinstance(rows, list) or len(rows) < 40:
        raise ValueError("At least 40 completed Forex candles are required")
    normalized = []
    previous = -1
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Invalid Forex candle")
        raw = row.get("timestamp")
        if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(raw):
            raise ValueError("Invalid Forex candle timestamp")
        timestamp = float(raw)
        if timestamp > 1e11:
            timestamp /= 1000
        if timestamp < 946684800 or timestamp > 4102444800:
            raise ValueError("Forex candle timestamp outside supported epoch range")
        milliseconds = int(timestamp * 1000)
        if milliseconds <= previous:
            raise ValueError("Forex candles must be strictly time-ordered")
        previous = milliseconds
        values = {}
        for key in ("open", "high", "low", "close"):
            raw_value = row.get(key)
            if isinstance(raw_value, bool):
                raise ValueError("Invalid Forex OHLC")
            try:
                value = float(raw_value)
            except (TypeError, ValueError, OverflowError):
                raise ValueError("Invalid Forex OHLC") from None
            if not math.isfinite(value) or value <= 0:
                raise ValueError("Invalid Forex OHLC")
            values[key] = value
        if values["low"] > min(values["open"], values["close"]) or values["high"] < max(values["open"], values["close"]):
            raise ValueError("Inconsistent Forex OHLC")
        volume = row.get("tickVolume", row.get("volume", 0))
        try:
            volume = float(volume)
        except (TypeError, ValueError, OverflowError):
            raise ValueError("Invalid Forex tick volume") from None
        if not math.isfinite(volume) or volume < 0:
            raise ValueError("Invalid Forex tick volume")
        normalized.append({"time": milliseconds, **values, "volume": volume})
    return normalized

def forex_research_signal(candles: list[dict[str, Any]]) -> dict[str, Any]:
    """Simple transparent directional hypothesis; never an execution approval."""
    if len(candles) < 40:
        raise ValueError("Insufficient candles")
    closes = [c["close"] for c in candles]
    def ema(period: int) -> float:
        value = closes[0]
        alpha = 2 / (period + 1)
        for price in closes[1:]:
            value += alpha * (price - value)
        return value
    fast, slow = ema(9), ema(21)
    side = "BUY" if fast > slow else "SELL" if fast < slow else "HOLD"
    ranges = [max(c["high"] - c["low"], 0) for c in candles[-14:]]
    average_range = sum(ranges) / len(ranges)
    if average_range <= 0:
        side = "HOLD"
    close = closes[-1]
    stop_distance = max(average_range * 1.5, close * 0.0001)
    return {
        "side": side,
        "confidence": 0,
        "signal_type": "EMA_9_21_RESEARCH_HYPOTHESIS",
        "latest_closed_price": close,
        "ema_9": round(fast, 8),
        "ema_21": round(slow, 8),
        "risk_levels": {
            "stop_reference": round(close - stop_distance if side == "BUY" else close + stop_distance, 8),
            "target_reference": round(close + 2 * stop_distance if side == "BUY" else close - 2 * stop_distance, 8),
        } if side != "HOLD" else {},
        "execution": "research_only_no_order_placed",
        "notice": "This is a research hypothesis, not a calibrated probability or an order authorization.",
    }
