"""Fail-closed demo Forex order risk policy. No broker I/O or order submission.

Inputs must be independently verified by the server against fresh broker state.
This module does not authorize real-money accounts or remove manual approval.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

RISK_PER_TRADE = Decimal("0.0025")
DAILY_LOSS_LIMIT = Decimal("0.01")
MAX_OPEN_POSITIONS = 1

class RiskRejected(ValueError):
    pass

def _decimal(value: Any, name: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise RiskRejected(f"{name} missing or invalid")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise RiskRejected(f"{name} invalid") from None
    if not number.is_finite():
        raise RiskRejected(f"{name} invalid")
    return number

@dataclass(frozen=True)
class DemoRiskEvidence:
    verified_demo: bool
    session_ready: bool
    trading_permitted: bool
    broker_state_fresh: bool
    prices_fresh: bool
    symbol_tradeable: bool
    spread_acceptable: bool
    stop_supported: bool
    durable_journal_ready: bool
    reconciliation_ready: bool
    manual_approval_verified: bool
    kill_switch_off: bool
    account_equity: Any
    start_of_day_equity: Any
    current_equity: Any
    open_positions: int
    requested_volume: Any
    min_volume: Any
    max_volume: Any
    volume_step: Any
    entry_price: Any
    stop_price: Any
    loss_per_price_unit_per_lot: Any
    available_margin: Any
    required_margin: Any
    symbol: str
    side: str

def evaluate_demo_order(e: DemoRiskEvidence) -> dict[str, str]:
    """Risk gate only. Passing does NOT submit or authorize an order.

    start_of_day_equity must be a durable broker-verified snapshot.
    loss_per_price_unit_per_lot must be broker-verified for the instrument
    and account currency (not a hard-coded pip value).
    """
    checks = (
        (e.verified_demo, "Account is not positively verified as demo"),
        (e.session_ready, "Broker session not ready"),
        (e.trading_permitted, "Trading permission not verified"),
        (e.broker_state_fresh, "Broker state stale"),
        (e.prices_fresh, "Prices stale"),
        (e.symbol_tradeable, "Symbol not verified tradeable"),
        (e.spread_acceptable, "Spread check failed"),
        (e.stop_supported, "Protective stop not confirmed supported"),
        (e.durable_journal_ready, "Durable idempotency journal unavailable"),
        (e.reconciliation_ready, "Order reconciliation unavailable"),
        (e.manual_approval_verified, "Manual approval missing"),
        (e.kill_switch_off, "Emergency stop engaged"),
    )
    for passed, reason in checks:
        if passed is not True:
            raise RiskRejected(reason)
    if e.side not in ("BUY", "SELL") or not e.symbol or not e.symbol.isascii():
        raise RiskRejected("Invalid symbol or direction")
    if isinstance(e.open_positions, bool) or not isinstance(e.open_positions, int) or e.open_positions < 0:
        raise RiskRejected("Open position count unverified")
    if e.open_positions >= MAX_OPEN_POSITIONS:
        raise RiskRejected("Maximum one simultaneous position")
    equity = _decimal(e.account_equity, "Account equity")
    start = _decimal(e.start_of_day_equity, "Start-of-day equity")
    current = _decimal(e.current_equity, "Current equity")
    volume = _decimal(e.requested_volume, "Volume")
    minimum = _decimal(e.min_volume, "Minimum volume")
    maximum = _decimal(e.max_volume, "Maximum volume")
    step = _decimal(e.volume_step, "Volume step")
    entry = _decimal(e.entry_price, "Entry price")
    stop = _decimal(e.stop_price, "Stop price")
    loss_unit = _decimal(e.loss_per_price_unit_per_lot, "Contract loss conversion")
    margin = _decimal(e.available_margin, "Available margin")
    required = _decimal(e.required_margin, "Required margin")
    if min(equity, start, current, volume, minimum, maximum, step, entry, stop, loss_unit) <= 0:
        raise RiskRejected("Required monetary or broker values must be positive")
    if margin < 0 or required <= 0 or margin < required:
        raise RiskRejected("Insufficient verified margin")
    if maximum < minimum or volume < minimum or volume > maximum:
        raise RiskRejected("Volume outside broker limits")
    if (volume - minimum) % step != 0:
        raise RiskRejected("Volume violates broker step")
    if e.side == "BUY" and stop >= entry:
        raise RiskRejected("BUY stop must be below entry")
    if e.side == "SELL" and stop <= entry:
        raise RiskRejected("SELL stop must be above entry")
    if start - current >= start * DAILY_LOSS_LIMIT:
        raise RiskRejected("Daily loss limit reached")
    projected_loss = abs(entry - stop) * loss_unit * volume
    if projected_loss <= 0 or projected_loss > equity * RISK_PER_TRADE:
        raise RiskRejected("Projected stop loss exceeds 0.25% equity")
    if start - current + projected_loss > start * DAILY_LOSS_LIMIT:
        raise RiskRejected("Proposed loss would breach daily 1% limit")
    return {
        "decision": "RISK_CHECK_PASSED_MANUAL_APPROVAL_ONLY",
        "risk_amount": str(projected_loss),
        "risk_limit": str(equity * RISK_PER_TRADE),
        "daily_loss_limit": str(start * DAILY_LOSS_LIMIT),
        "order_submitted": "false",
    }
