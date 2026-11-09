"""Research-only $68 challenge calculations. Never sends exchange orders."""
from __future__ import annotations

from .omonux_backtest import backtest_closed_candles


def challenge_report(symbol: str, candles: list[dict], *, initial_cash: float = 68.0,
                     target_cash: float = 750.0, fee_bps: float = 10.0,
                     slippage_bps: float = 5.0) -> dict:
    if not (0 < initial_cash <= 100000 and initial_cash < target_cash <= 1000000):
        raise ValueError("Starting cash and target must be positive, with target greater than starting cash.")
    if not (0 <= fee_bps <= 1000 and 0 <= slippage_bps <= 1000):
        raise ValueError("Fees and slippage must be between 0 and 1000 basis points.")
    result = backtest_closed_candles(symbol, candles, fee_bps=fee_bps,
                                     slippage_bps=slippage_bps)
    # The backtest compounds one fully allocated position at a time.
    # This is a research scenario, NOT the live paper engine's allocation policy.
    ending = round(initial_cash * (1 + result["net_return_pct"] / 100), 6)
    return {
        "challenge": "68_to_750", "symbol": symbol, "timeframe": "5m",
        "starting_cash": initial_cash, "target_cash": target_cash,
        "target_return_pct": round((target_cash / initial_cash - 1) * 100, 2),
        "historical_ending_cash": ending, "historical_profit": round(ending - initial_cash, 6),
        "target_reached_in_sample": ending >= target_cash,
        "progress_pct": round(max(0, min(100, (ending - initial_cash) / (target_cash - initial_cash) * 100)), 2),
        "history_start": candles[0]["time"], "history_end": candles[-1]["time"],
        "historical_candles": len(candles), "backtest": result,
        "mode": "historical_paper_research_only",
        "notice": "5-minute historical simulation, not a continuously running trading bot. No real trades, no guaranteed returns. This simplified backtest assumes full allocation and does not model funding, liquidity, partial fills or exchange minimums.",
    }
