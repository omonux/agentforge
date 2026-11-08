"""Bounded 50-market Binance/Bybit Spot discovery for OMONUX.

Public market data only. This module never reads credentials or submits orders.
It ranks a curated liquid USDT Spot universe and fails closed when either venue
is missing, candles are stale, or venue prices diverge beyond the configured cap.
"""
from __future__ import annotations

import asyncio
from typing import Any

from .omonux_engine import build_signal
from .omonux_exchange_market_data import fetch_both_market_candles

# Curated, common USDT Spot pairs. Exchange listing/availability is verified at scan time.
UNIVERSE_SYMBOLS = (
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "TRXUSDT", "AVAXUSDT", "LINKUSDT",
    "DOTUSDT", "MATICUSDT", "LTCUSDT", "BCHUSDT", "NEARUSDT",
    "ATOMUSDT", "UNIUSDT", "ETCUSDT", "XLMUSDT", "FILUSDT",
    "APTUSDT", "ARBUSDT", "OPUSDT", "INJUSDT", "SUIUSDT",
    "SEIUSDT", "TIAUSDT", "ICPUSDT", "AAVEUSDT", "RUNEUSDT",
    "FTMUSDT", "ALGOUSDT", "VETUSDT", "HBARUSDT", "EOSUSDT",
    "GRTUSDT", "MKRUSDT", "SNXUSDT", "CRVUSDT", "LDOUSDT",
    "IMXUSDT", "STXUSDT", "THETAUSDT", "EGLDUSDT", "SANDUSDT",
    "MANAUSDT", "AXSUSDT", "CHZUSDT", "APEUSDT", "PEPEUSDT",
)


async def scan_market_universe(
    interval: str = "30m",
    limit: int = 120,
    max_symbols: int = 50,
    max_price_divergence_pct: float = 0.35,
) -> dict[str, Any]:
    """Compare both venues for up to 50 markets and rank deterministic candidates."""
    symbols = UNIVERSE_SYMBOLS[: max(1, min(int(max_symbols), 50))]
    semaphore = asyncio.Semaphore(8)

    async def inspect(symbol: str) -> dict[str, Any]:
        async with semaphore:
            try:
                venues = await fetch_both_market_candles(symbol, interval, limit)
                left, right = venues["binance"], venues["bybit"]
                if len(left) < 40 or len(right) < 40:
                    raise ValueError("Insufficient completed candles on both venues.")
                b, y = left[-1], right[-1]
                if b["time"] != y["time"]:
                    raise ValueError("Latest completed candle timestamps do not align.")
                mid = (float(b["close"]) + float(y["close"])) / 2
                divergence = abs(float(b["close"]) - float(y["close"])) / mid * 100 if mid else 999
                signal = build_signal(symbol, left)
                eligible = divergence <= max_price_divergence_pct
                score = signal["confidence"] if signal["side"] == "BUY" and eligible else 0
                return {
                    "symbol": symbol, "status": "ready" if eligible else "divergent",
                    "signal": signal["side"] if eligible else "HOLD",
                    "confidence": signal["confidence"], "rank_score": score,
                    "binance_price": b["close"], "bybit_price": y["close"],
                    "price_divergence_pct": round(divergence, 4),
                    "candle_time": b["time"], "completed_candles": min(len(left), len(right)),
                    "eligible": eligible, "reason": None if eligible else "Venue price divergence exceeds safety threshold.",
                }
            except Exception as exc:
                return {
                    "symbol": symbol, "status": "unavailable", "signal": "HOLD",
                    "confidence": 0, "rank_score": 0, "eligible": False,
                    "reason": str(exc)[:180],
                }

    markets = await asyncio.gather(*(inspect(symbol) for symbol in symbols))
    ranked = sorted(markets, key=lambda item: (item["rank_score"], item["confidence"]), reverse=True)
    return {
        "universe_size": len(symbols),
        "venues": ["binance_spot", "bybit_spot"],
        "interval": interval,
        "markets_checked": len(markets),
        "markets_ready": sum(item["status"] == "ready" for item in markets),
        "markets_unavailable": sum(item["status"] == "unavailable" for item in markets),
        "top_candidates": [item for item in ranked if item["rank_score"] > 0][:10],
        "markets": ranked,
        "execution": "research_and_paper_candidate_only",
        "notice": "A ranked signal is not a trade instruction. The 12-agent council and deterministic risk gate must approve every paper entry. Public candles do not provide order-book depth, spread, fees, slippage or news verification.",
    }
