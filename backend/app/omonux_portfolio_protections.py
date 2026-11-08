"""Deterministic, fail-closed portfolio entry protections (research/testnet only).

Inspired by the layered protection approach documented by Freqtrade.
This module does not connect to an exchange or submit orders.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Iterable


@dataclass(frozen=True)
class ProtectionLimits:
    max_drawdown_fraction: Decimal = Decimal("0.10")
    max_daily_loss_fraction: Decimal = Decimal("0.03")
    max_consecutive_losses: int = 3
    cooldown_seconds: int = 1800


@dataclass(frozen=True)
class ClosedTrade:
    closed_at: datetime
    pnl_usdt: Decimal


def _number(value: object, label: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"Invalid {label}") from exc
    if not result.is_finite():
        raise ValueError(f"Invalid {label}")
    return result


def check_entry_protections(
    *,
    equity_usdt: object,
    peak_equity_usdt: object,
    day_start_equity_usdt: object,
    closed_trades: Iterable[ClosedTrade],
    now: datetime,
    limits: ProtectionLimits = ProtectionLimits(),
) -> dict:
    """Return entry eligibility and deterministic block reasons.

    Inputs must be from verified, reconciled portfolio state. An empty trade
    history is valid; missing/invalid equity is not. No order is authorized.
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone aware")
    if not (Decimal("0") < limits.max_drawdown_fraction < Decimal("1")
            and Decimal("0") < limits.max_daily_loss_fraction < Decimal("1")
            and limits.max_consecutive_losses > 0 and limits.cooldown_seconds >= 0):
        raise ValueError("Invalid protection configuration")
    equity = _number(equity_usdt, "equity")
    peak = _number(peak_equity_usdt, "peak equity")
    start = _number(day_start_equity_usdt, "day start equity")
    if equity < 0 or peak <= 0 or start <= 0 or peak < equity:
        raise ValueError("Unverified or inconsistent portfolio equity")
    trades = list(closed_trades)
    for trade in trades:
        if trade.closed_at.tzinfo is None or trade.closed_at.utcoffset() is None:
            raise ValueError("Trade timestamps must be timezone aware")
        if trade.closed_at > now:
            raise ValueError("Future-dated trade")
        _number(trade.pnl_usdt, "trade P/L")
    trades.sort(key=lambda t: t.closed_at)
    reasons = []
    if (peak - equity) / peak >= limits.max_drawdown_fraction:
        reasons.append("MAX_DRAWDOWN")
    if (start - equity) / start >= limits.max_daily_loss_fraction:
        reasons.append("DAILY_LOSS")
    consecutive_losses = 0
    for trade in reversed(trades):
        if _number(trade.pnl_usdt, "trade P/L") < 0:
            consecutive_losses += 1
        else:
            break
    if consecutive_losses >= limits.max_consecutive_losses:
        reasons.append("CONSECUTIVE_LOSSES")
    if trades and (now - trades[-1].closed_at).total_seconds() < limits.cooldown_seconds:
        reasons.append("COOLDOWN")
    return {"entry_allowed": not reasons, "blockers": reasons,
            "automatic_live_orders_authorized": False}
