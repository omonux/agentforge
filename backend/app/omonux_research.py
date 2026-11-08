"""Walk-forward strategy research for OMONUX. Research only; never places orders."""
from __future__ import annotations

from itertools import product
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .omonux_engine import fetch_candles, validate_symbol

router = APIRouter()


class ResearchRequest(BaseModel):
    symbol: str = Field(default="BTCUSDT", min_length=2, max_length=20, pattern=r"^[A-Za-z0-9._-]+$")
    timeframe: str = Field(default="30m", pattern=r"^(5m|15m|30m|1h|4h|1d)$")
    candle_limit: int = Field(default=500, ge=300, le=500)


def _ema(values: list[float], period: int) -> list[float]:
    alpha = 2 / (period + 1)
    out = [values[0]]
    for value in values[1:]:
        out.append(alpha * value + (1 - alpha) * out[-1])
    return out


def _rsi(values: list[float], period: int = 14) -> list[float]:
    gains, losses = [0.0], [0.0]
    for a, b in zip(values, values[1:]):
        gains.append(max(0.0, b - a))
        losses.append(max(0.0, a - b))
    avg_gain, avg_loss = _ema(gains, period), _ema(losses, period)
    result = []
    for gain, loss in zip(avg_gain, avg_loss):
        rs = gain / loss if loss > 1e-12 else (100.0 if gain > 0 else 0.0)
        result.append(100 - 100 / (1 + rs) if gain > 0 or loss > 0 else 50.0)
    return result


def _max_drawdown(equity: list[float]) -> float:
    peak = equity[0]
    worst = 0.0
    for value in equity:
        peak = max(peak, value)
        if peak > 0:
            worst = min(worst, (value / peak - 1) * 100)
    return round(worst, 3)


def simulate_strategy(
    candles: list[dict[str, Any]],
    fast: int,
    slow: int,
    fee_bps: float = 10.0,
    slippage_bps: float = 5.0,
    initial_cash: float = 10000.0,
) -> dict[str, Any]:
    """Long-only EMA trend strategy with RSI confirmation and next-candle execution."""
    closes = [float(c["close"]) for c in candles]
    if len(closes) < max(slow + 5, 40) or any(x <= 0 for x in closes):
        raise ValueError("Not enough valid positive close prices for this strategy.")
    fast_ema, slow_ema, rsi = _ema(closes, fast), _ema(closes, slow), _rsi(closes)
    cash, quantity, entry_equity = initial_cash, 0.0, 0.0
    equity_curve, trade_returns = [], []
    fees = (fee_bps + slippage_bps) / 10000
    entries = 0
    for i in range(1, len(closes) - 1):
        mark = cash + quantity * closes[i]
        equity_curve.append(mark)
        bullish = fast_ema[i] > slow_ema[i] and rsi[i] >= 50 and rsi[i] <= 72
        bearish = fast_ema[i] <= slow_ema[i] or rsi[i] > 78
        execution_price = closes[i + 1]
        if quantity == 0 and bullish:
            spend = cash
            quantity = (spend * (1 - fees)) / execution_price
            cash = 0.0
            entry_equity = spend
            entries += 1
        elif quantity > 0 and bearish:
            proceeds = quantity * execution_price * (1 - fees)
            trade_returns.append((proceeds / max(entry_equity, 1e-12) - 1) * 100)
            cash, quantity = proceeds, 0.0
    final_equity = cash + quantity * closes[-1] * (1 - fees if quantity else 1)
    equity_curve.append(final_equity)
    net_return = (final_equity / initial_cash - 1) * 100
    wins = [x for x in trade_returns if x > 0]
    losses = [x for x in trade_returns if x <= 0]
    gross_win, gross_loss = sum(wins), abs(sum(losses))
    return {
        "fast": fast, "slow": slow, "return_pct": round(net_return, 3),
        "max_drawdown_pct": _max_drawdown([initial_cash] + equity_curve),
        "trades": len(trade_returns) + (1 if quantity > 0 else 0),
        "closed_trades": len(trade_returns),
        "win_rate_pct": round(len(wins) / max(1, len(trade_returns)) * 100, 2),
        "profit_factor": round(gross_win / gross_loss, 3) if gross_loss else (99.0 if gross_win else 0.0),
        "average_trade_pct": round(sum(trade_returns) / max(1, len(trade_returns)), 3),
        "final_equity": round(final_equity, 2),
        "fees_and_slippage_bps_per_side": round(fee_bps + slippage_bps, 2),
    }


def run_walk_forward(candles: list[dict[str, Any]], initial_cash: float = 10000.0) -> dict[str, Any]:
    """Select a candidate on the first 70%, then evaluate once on untouched final 30%."""
    if len(candles) < 300:
        raise ValueError("At least 300 completed candles are required for walk-forward research.")
    split = int(len(candles) * 0.70)
    train, test = candles[:split], candles[split:]
    candidates = []
    for fast, slow in product((5, 8, 12,  hacerlo), (21, 30, 40, 55)):
        if fast >= slow:
            continue
        try:
            report = simulate_strategy(train, fast, slow, initial_cash=initial_cash)
            candidates.append(report)
        except ValueError:
            continue
    if not candidates:
        raise ValueError("No valid strategy candidates could be evaluated.")
    # Rank on training return penalized by drawdown; no AI confidence score is used.
    best = max(candidates, key=lambda x: x["return_pct"] - abs(x["max_drawdown_pct"]) * 0.6)
    out_of_sample = simulate_strategy(test, best["fast"], best["slow"], initial_cash=initial_cash)
    baseline = (float(test[-1]["close"]) / float(test[0]["close"]) - 1) * 100
    return {
        "selected_parameters": {"fast_ema": best["fast"], "slow_ema": best["slow"], "rsi_filter": "50–72"},
        "training": {k: best[k] for k in ("return_pct", "max_drawdown_pct", "trades", "win_rate_pct", "profit_factor")},
        "out_of_sample": out_of_sample,
        "buy_and_hold_test_return_pct": round(baseline, 3),
        "data": {"total_completed_candles": len(candles), "training_candles": len(train), "untouched_test_candles": len(test), "split": "70% train / 30% out-of-sample"},
        "assessment": "POSITIVE_OUT_OF_SAMPLE" if out_of_sample["return_pct"] > 0 and out_of_sample["profit_factor"] > 1 else "NOT_VALIDATED",
        "limitations": [
            "Historical simulation is not a forecast and does not establish future profitability.",
            "The final 30% is held out from parameter selection; repeat across multiple symbols and periods before drawing conclusions.",
            "Fees and slippage are approximated at 15 basis points per side; real execution may be worse.",
            "No funding, liquidation, market impact, taxes, or exchange outages are modeled.",
            "This report cannot enable live execution and never places orders.",
        ],
    }


@router.post("/api/v1/trading/research/run")
async def research_run(request: ResearchRequest):
    try:
        symbol = validate_symbol(request.symbol.upper())
        candles = await fetch_candles(symbol, interval=request.timeframe, limit=request.candle_limit)
        report = run_walk_forward(candles)
        return {"symbol": symbol, "timeframe": request.timeframe, **report, "mode": "research_only"}
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(502, "Market data or strategy research failed. No trade was placed.")
