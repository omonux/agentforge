"""Fast read-only five-minute market radar; never places orders."""
from __future__ import annotations

import asyncio
import math
from .omonux_engine import fetch_candles, build_signal, validate_symbol
from .omonux_universe import UNIVERSE_SYMBOLS


def score_market(symbol: str, candles: list[dict], *, fee_bps: float = 10,
                 slippage_bps: float = 5) -> dict:
    if len(candles) < 50:
        raise ValueError("At least 50 closed candles are required")
    signal = build_signal(symbol, candles)
    last = candles[-1]
    closes = [float(c["close"]) for c in candles]
    volumes = [float(c["volume"]) for c in candles]
    if any(not math.isfinite(x) or x <= 0 for x in closes) or any(not math.isfinite(x) or x < 0 for x in volumes):
        raise ValueError("Invalid prices or volumes")
    change_pct = (closes[-1] / closes[-6] - 1) * 100
    avg_volume = sum(volumes[-21:-1]) / 20
    volume_ratio = volumes[-1] / avg_volume if avg_volume > 0 else 0
    stop = signal.get("risk_levels", {}).get("stop_reference")
    target = signal.get("risk_levels", {}).get("target_reference")
    price = closes[-1]
    direction = signal.get("side")
    valid_geometry = bool(stop and target and (
        (float(stop) < price < float(target)) if direction == "BUY" else
        (float(target) < price < float(stop)) if direction == "SELL" else False
    ))
    gross_reward_pct = abs(float(target) / price - 1) * 100 if valid_geometry else 0
    round_trip_cost_pct = 2 * (fee_bps + slippage_bps) / 100
    net_reward_pct = gross_reward_pct - round_trip_cost_pct
    confidence = float(signal.get("directional_confidence") or 0)
    # This is a transparent ranking heuristic, not a calibrated probability.
    ranking = max(0, min(100, confidence * .65 + min(volume_ratio, 3) * 8 +
                         min(abs(change_pct), 3) * 4 - round_trip_cost_pct * 10))
    reasons = []
    if direction not in ("BUY", "SELL"):
        reasons.append("No directional technical signal")
    if volume_ratio < .75:
        reasons.append("Below-average recent trading volume")
    if not valid_geometry:
        reasons.append("Invalid stop/target geometry")
    if net_reward_pct <= 0:
        reasons.append("Target distance does not cover estimated round-trip costs")
    return {
        "symbol": symbol, "side": direction, "signal_confidence": confidence,
        "rank_score": round(ranking, 2), "volume_ratio": round(volume_ratio, 3),
        "five_candle_change_pct": round(change_pct, 3),
        "estimated_round_trip_cost_pct": round(round_trip_cost_pct, 4),
        "estimated_net_target_distance_pct": round(net_reward_pct, 4),
        "candle_time": last["time"], "eligible_for_review": not reasons,
        "warnings": reasons, "mode": "research_only",
    }


async def scan_fast_radar(symbols: list[str] | None = None, *,
                          fee_bps: float = 10, slippage_bps: float = 5) -> dict:
    if fee_bps < 0 or slippage_bps < 0:
        raise ValueError("Cost assumptions cannot be negative")
    selected = list(dict.fromkeys(validate_symbol(s) for s in (symbols or list(UNIVERSE_SYMBOLS)[:20])))
    if not selected or len(selected) > 50 or any(s not in UNIVERSE_SYMBOLS for s in selected):
        raise ValueError("Select 1-50 supported universe markets")
    semaphore = asyncio.Semaphore(6)
    async def evaluate(symbol):
        async with semaphore:
            try:
                candles = await fetch_candles(symbol, "5m", 100)
                return score_market(symbol, candles, fee_bps=fee_bps, slippage_bps=slippage_bps)
            except Exception as exc:
                return {"symbol": symbol, "eligible_for_review": False,
                        "error": type(exc).__name__, "mode": "research_only"}
    results = await asyncio.gather(*(evaluate(s) for s in selected))
    ranked = sorted(results, key=lambda r: (not r.get("eligible_for_review", False),
                                            -r.get("rank_score", 0)))
    return {"timeframe": "5m", "markets_checked": len(selected),
            "review_candidates": sum(bool(r.get("eligible_for_review")) for r in results),
            "markets": ranked, "mode": "research_only_no_orders",
            "notice": "Fast screening only; ranking is not a win probability, AI council approval, or authorization to trade."}
