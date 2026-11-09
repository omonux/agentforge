"""Deterministic, research-only closed-candle backtest. Never submits orders.

A signal is computed at candle t close; entry occurs at t+1 open to avoid
lookahead. Stops/targets use the subsequent candle range. When both hit,
assume the adverse stop filled first. Results are not live performance.
"""
from __future__ import annotations

from .omonux_engine import build_signal


def backtest_closed_candles(symbol: str, candles: list[dict], *,
                            fee_bps: float = 10.0, slippage_bps: float = 5.0,
                            min_history: int = 50) -> dict:
    if fee_bps < 0 or slippage_bps < 0 or min_history < 30:
        raise ValueError("Fees/slippage must be nonnegative and history >=30")
    if len(candles) < min_history + 2:
        raise ValueError("Insufficient closed candles for backtest")
    if any(int(b["time"]) <= int(a["time"]) for a, b in zip(candles, candles[1:])):
        raise ValueError("Candles must be strictly chronological")
    trades = []
    i = min_history
    while i < len(candles) - 1:
        signal = build_signal(symbol, candles[:i + 1])
        side = signal["side"]
        if side == "HOLD":
            i += 1
            continue
        entry_index = i + 1
        raw_entry = float(candles[entry_index]["open"])
        if raw_entry <= 0:
            i += 1
            continue
        direction = 1 if side == "BUY" else -1
        slip = slippage_bps / 10000
        fee = fee_bps / 10000
        entry = raw_entry * (1 + direction * slip)
        stop = float(signal["risk_levels"]["stop_reference"])
        target = float(signal["risk_levels"]["target_reference"])
        if not ((stop < entry < target) if direction == 1 else (target < entry < stop)):
            i += 1
            continue
        j = entry_index
        exit_price = None
        reason = "end_of_data"
        while j < len(candles):
            candle = candles[j]
            low, high = float(candle["low"]), float(candle["high"])
            stop_hit = low <= stop if direction == 1 else high >= stop
            target_hit = high >= target if direction == 1 else low <= target
            if stop_hit:
                exit_price, reason = stop, "stop"  # conservative if both touched
                break
            if target_hit:
                exit_price, reason = target, "target"
                break
            j += 1
        if exit_price is None:
            j = len(candles) - 1
            exit_price = float(candles[j]["close"])
        executed_exit = exit_price * (1 - direction * slip)
        net_return = direction * (executed_exit - entry) / entry - fee * (1 + executed_exit / entry)
        trades.append({"side": side, "entry_time": candles[entry_index]["time"],
                       "exit_time": candles[j]["time"], "entry": entry,
                       "exit": executed_exit, "reason": reason,
                       "net_return_pct": round(net_return * 100, 6)})
        i = j + 1  # one position at a time
    equity, peak, drawdown = 1.0, 1.0, 0.0
    for trade in trades:
        equity *= max(0.0, 1 + trade["net_return_pct"] / 100)
        peak = max(peak, equity)
        drawdown = max(drawdown, (peak - equity) / peak)
    gains = sum(max(0.0, t["net_return_pct"]) for t in trades)
    losses = sum(max(0.0, -t["net_return_pct"]) for t in trades)
    return {"symbol": symbol, "trades": trades, "trade_count": len(trades),
            "win_rate_pct": round(100 * sum(t["net_return_pct"] > 0 for t in trades) / len(trades), 2) if trades else 0,
            "profit_factor": round(gains / losses, 3) if losses else None,
            "net_return_pct": round((equity - 1) * 100, 4),
            "max_drawdown_pct": round(drawdown * 100, 4),
            "fee_bps": fee_bps, "slippage_bps": slippage_bps,
            "mode": "historical_research_only", "limitations": "No funding, borrowing, liquidity constraints, partial fills or out-of-sample validation."}
