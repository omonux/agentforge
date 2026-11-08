"""Twelve-specialist market research council for OMONUX.

The council is an analysis and paper-trading gate only. It cannot place exchange orders.
Each specialist receives the same completed-candle evidence and returns a constrained JSON vote.
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import httpx

SPECIALISTS = [
    ("market_regime", "Market Regime Analyst", "Classify the market regime (trend, range, high-volatility, transition). Avoid trades that conflict with the regime."),
    ("trend", "Trend Analyst", "Assess directional trend using EMA structure and recent closes. Identify whether the proposed direction has trend support."),
    ("momentum", "Momentum Analyst", "Assess RSI and price momentum. Flag overbought, oversold, weakening or divergent momentum."),
    ("volume", "Volume Analyst", "Assess volume expansion/contraction and whether it confirms the move. If volume evidence is insufficient, vote HOLD."),
    ("volatility", "Volatility Analyst", "Assess ATR and candle ranges. Reject setups where volatility makes the stop distance or reward/risk unattractive."),
    ("support_resistance", "Support & Resistance Analyst", "Assess nearby swing highs/lows and whether price is entering resistance/support. Do not invent levels."),
    ("multi_timeframe", "Multi-Timeframe Analyst", "Use the supplied timeframe only. Explicitly state that other timeframes are unavailable; do not pretend to have checked them."),
    ("breakout", "Breakout Analyst", "Assess whether price has a confirmed close beyond a recent range. Avoid predicting unconfirmed breakouts."),
    ("mean_reversion", "Mean-Reversion Analyst", "Check whether price is stretched from its recent mean and whether chasing the move is risky."),
    ("liquidity", "Liquidity & Execution Analyst", "Use only candle volume/range as rough proxies. State that order-book depth, spread and slippage are unavailable."),
    ("strategy", "Strategy Analyst", "Evaluate the setup against the deterministic EMA/RSI/ATR signal and the proposed stop/target. Prefer no trade when evidence conflicts."),
    ("red_team", "Skeptic / Red-Team Analyst", "Try to disprove the trade. Identify missing evidence, look-ahead risk, fragile assumptions and reasons to stay out."),
]

_ALLOWED = {"BUY", "SELL", "HOLD"}


def _market_evidence(symbol: str, timeframe: str, candles: list[dict[str, Any]], signal: dict[str, Any]) -> dict[str, Any]:
    closes = [float(c["close"]) for c in candles]
    volumes = [float(c.get("volume", 0)) for c in candles]
    recent = candles[-20:]
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "data_source": "Binance public OHLCV",
        "closed_candle_count": len(candles),
        "latest_closed_candle_time_ms": candles[-1]["time"],
        "latest_price": closes[-1],
        "recent_closes": [round(v, 8) for v in closes[-20:]],
        "recent_highs": [round(float(c["high"]), 8) for c in recent],
        "recent_lows": [round(float(c["low"]), 8) for c in recent],
        "recent_volumes": [round(v, 4) for v in volumes[-20:]],
        "average_volume_20": round(sum(volumes[-20:]) / max(1, len(volumes[-20:])), 4),
        "deterministic_signal": signal,
        "limitations": [
            "Only completed candles are supplied.",
            "No order-book depth, spread, funding, open interest or verified news feed is available.",
            "No other timeframe is fetched unless explicitly supplied.",
            "This is not a prediction or guarantee of future returns.",
        ],
    }


def _parse_vote(content: str, specialist_id: str, name: str) -> dict[str, Any]:
    text = content.strip()
    text = re.sub(r"^\x60{3}(?:json)?\s*|\s*\x60{3}$", "", text, flags=re.IGNORECASE)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("Agent did not return a JSON object.")
    obj = json.loads(text[start:end + 1])
    stance = str(obj.get("stance", "HOLD")).upper()
    if stance not in _ALLOWED:
        raise ValueError("Agent returned an invalid stance.")
    confidence = max(0, min(100, int(obj.get("confidence", 0))))
    reason = str(obj.get("reason", "")).strip()[:700]
    if not reason:
        raise ValueError("Agent did not explain its vote.")
    return {
        "id": specialist_id,
        "name": name,
        "stance": stance,
        "confidence": confidence,
        "reason": reason,
        "veto": bool(obj.get("veto", False)),
        "evidence": [str(x)[:180] for x in obj.get("evidence", [])[:4]] if isinstance(obj.get("evidence", []), list) else [],
        "status": "completed",
    }


async def _run_specialist(
    client: httpx.AsyncClient,
    base_url: str,
    api_key: str,
    model: str,
    specialist_id: str,
    name: str,
    task: str,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    system = (
        f"You are the {name}, one independent specialist in a twelve-agent crypto market research council. "
        f"{task} You are an analyst, not an execution system. Never invent market/news/order-book data. "
        "Use only the supplied evidence. A BUY vote means evidence supports a cautious long paper-trade candidate; "
        "SELL means evidence is materially adverse to that candidate; HOLD means uncertain or insufficient. "
        "Return ONLY valid JSON with keys: stance (BUY|SELL|HOLD), confidence (integer 0-100), "
        "reason (one concise paragraph), evidence (array of short observed facts), veto (boolean). "
        "Set veto=true only for a critical risk that should block even a majority vote."
    )
    response = await client.post(
        base_url.rstrip("/") + "/chat/completions",
        headers={"Authorization": "Bearer " + api_key},
        json={
            "model": model,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(evidence, separators=(",", ":"))},
            ],
        },
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    vote = _parse_vote(content, specialist_id, name)
    return vote


async def run_council(
    symbol: str,
    timeframe: str,
    candles: list[dict[str, Any]],
    signal: dict[str, Any],
    base_url: str,
    api_key: str,
    model: str,
) -> dict[str, Any]:
    """Run all twelve specialists; fail closed if any specialist fails."""
    if not (base_url and api_key and model):
        raise RuntimeError("AI provider is not configured; the twelve-agent council cannot run.")
    if len(candles) < 40:
        raise ValueError("The council requires at least 40 completed candles.")
    evidence = _market_evidence(symbol, timeframe, candles, signal)
    timeout = httpx.Timeout(75.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        results = await asyncio.gather(
            *[
                _run_specialist(client, base_url, api_key, model, sid, name, task, evidence)
                for sid, name, task in SPECIALISTS
            ],
            return_exceptions=True,
        )

    votes: list[dict[str, Any]] = []
    errors: list[str] = []
    for (sid, name, _), result in zip(SPECIALISTS, results):
        if isinstance(result, BaseException):
            errors.append(f"{sid}: {type(result).__name__}")
            votes.append({
                "id": sid, "name": name, "stance": "HOLD", "confidence": 0,
                "reason": "Agent unavailable; no vote was counted.", "evidence": [],
                "veto": True, "status": "failed",
            })
        else:
            votes.append(result)

    summary = summarize_votes(votes)
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        **summary,
        "errors": errors,
        "agents": votes,
        "evidence_timestamp_ms": candles[-1]["time"],
        "execution": "paper_only_no_live_orders",
        "notice": "AI votes are advisory. Deterministic risk checks remain mandatory; no live order can be placed by this council.",
    }


def summarize_votes(votes: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {stance: sum(1 for vote in votes if vote["stance"] == stance and vote["status"] == "completed") for stance in _ALLOWED}
    vetoes = [vote["id"] for vote in votes if vote["veto"]]
    completed = sum(vote["status"] == "completed" for vote in votes)
    buy_votes = counts["BUY"]
    sell_votes = counts["SELL"]
    # Strict fail-closed policy: all specialists must answer, at least 8/12 support,
    # no more than 1 specialist opposes, and no critical veto is raised.
    approved = completed == 12 and buy_votes >= 8 and sell_votes <= 1 and not vetoes
    average_buy_confidence = round(
        sum(v["confidence"] for v in votes if v["stance"] == "BUY" and v["status"] == "completed") / max(1, buy_votes)
    )
    return {
        "approved": approved,
        "decision": "PAPER_CANDIDATE" if approved else "NO_TRADE",
        "vote_counts": counts,
        "buy_consensus_percent": round(buy_votes / 12 * 100),
        "average_buy_confidence": average_buy_confidence,
        "completed_agents": completed,
        "required_buy_votes": 8,
        "vetoes": vetoes,
    }
