"""Fail-closed demo Forex order risk policy. No broker I/O or order submission.

Inputs must be independently verified by the server against fresh broker state.
This module does not authorize real-money accounts or remove manual approval.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_FLOOR
from typing import Any

RISK_PER_TRADE = Decimal("0.0025")
DEMO_TEST_RISK_CAP = Decimal("4.00")
DEMO_TARGET_R_MULTIPLE = Decimal("2")
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


def build_demo_order_plan(*, side: str, entry_price: Any, stop_reference: Any,
                          tick_size: Any, tick_value_account_per_lot: Any,
                          min_volume: Any, max_volume: Any, volume_step: Any,
                          account_equity: Any, start_of_day_equity: Any,
                          current_equity: Any, account_currency: str) -> dict[str, str]:
    """Size a DEMO plan to the lower of the 0.25% policy and $4 test cap.

    The caller supplies prices and contract values from fresh broker evidence.
    This function is deterministic, does not call a broker, and cannot place an
    order. A too-large broker minimum lot rejects the plan instead of rounding
    risk above the cap.
    """
    if side not in ("BUY", "SELL"):
        raise RiskRejected("Invalid trade direction")
    if not isinstance(account_currency, str) or account_currency.upper() != "USD":
        raise RiskRejected("The $4 demo test cap requires a verified USD account")
    entry = _decimal(entry_price, "Entry price")
    stop_ref = _decimal(stop_reference, "Stop reference")
    tick = _decimal(tick_size, "Tick size")
    tick_value = _decimal(tick_value_account_per_lot, "Account-currency tick value")
    minimum = _decimal(min_volume, "Minimum volume")
    maximum = _decimal(max_volume, "Maximum volume")
    step = _decimal(volume_step, "Volume step")
    equity = _decimal(account_equity, "Account equity")
    start = _decimal(start_of_day_equity, "Start-of-day equity")
    current = _decimal(current_equity, "Current equity")
    if min(entry, stop_ref, tick, tick_value, minimum, maximum, step, equity, start, current) <= 0:
        raise RiskRejected("Broker prices, contract values and equity must be positive")
    if maximum < minimum or (maximum - minimum) % step != 0:
        raise RiskRejected("Invalid broker volume limits")

    if side == "BUY":
        stop = (stop_ref / tick).to_integral_value(rounding=ROUND_FLOOR) * tick
        if stop >= entry:
            raise RiskRejected("BUY stop reference must be below entry")
        distance = entry - stop
        target = ((entry + distance * DEMO_TARGET_R_MULTIPLE) / tick).to_integral_value(rounding=ROUND_CEILING) * tick
    else:
        stop = (stop_ref / tick).to_integral_value(rounding=ROUND_CEILING) * tick
        if stop <= entry:
            raise RiskRejected("SELL stop reference must be above entry")
        distance = stop - entry
        target = ((entry - distance * DEMO_TARGET_R_MULTIPLE) / tick).to_integral_value(rounding=ROUND_FLOOR) * tick

    drawdown = max(Decimal("0"), start - current)
    daily_remaining = start * DAILY_LOSS_LIMIT - drawdown
    cap = min(DEMO_TEST_RISK_CAP, equity * RISK_PER_TRADE, daily_remaining)
    if cap <= 0:
        raise RiskRejected("Daily loss limit reached")
    loss_per_price_unit_per_lot = tick_value / tick
    raw_volume = cap / (distance * loss_per_price_unit_per_lot)
    if raw_volume < minimum:
        raise RiskRejected("Broker minimum volume would exceed the $4 test risk cap")
    steps = ((min(raw_volume, maximum) - minimum) / step).to_integral_value(rounding=ROUND_FLOOR)
    volume = minimum + steps * step
    projected_loss = distance * loss_per_price_unit_per_lot * volume
    while projected_loss > cap and volume - step >= minimum:
        volume -= step
        projected_loss = distance * loss_per_price_unit_per_lot * volume
    if projected_loss <= 0 or projected_loss > cap:
        raise RiskRejected("Could not size within the $4 test risk cap")
    return {
        "mode": "DEMO_ONLY",
        "side": side,
        "entry_reference": str(entry),
        "stop_loss_reference": str(stop),
        "take_profit_reference": str(target),
        "volume_lots": str(volume),
        "risk_amount_usd": str(projected_loss),
        "risk_cap_usd": str(cap),
        "reward_to_risk": str(DEMO_TARGET_R_MULTIPLE),
        "order_submitted": "false",
    }


def build_existing_position_protection(*, side: str, reference_price: Any,
                                       volume: Any, tick_size: Any,
                                       tick_value_account_per_lot: Any,
                                       account_equity: Any, account_currency: str,
                                       bid: Any, ask: Any, point: Any,
                                       stop_level_points: Any) -> dict[str, str]:
    """Calculate broker-aligned SL/TP for one unprotected USD demo position.

    Risk from the current broker close-side price to the stop is capped at the
    lower of $4 or 0.25% of equity. The take-profit reference is 2R. A broker
    minimum distance that violates the cap rejects the plan. No broker I/O or
    position modification happens here.
    """
    if side not in ("BUY", "SELL"):
        raise RiskRejected("Invalid position direction")
    if not isinstance(account_currency, str) or account_currency.upper() != "USD":
        raise RiskRejected("The $4 demo test cap requires a verified USD account")
    reference = _decimal(reference_price, "Current position reference price")
    lots = _decimal(volume, "Position volume")
    tick = _decimal(tick_size, "Tick size")
    tick_value = _decimal(tick_value_account_per_lot, "Account-currency tick value")
    equity = _decimal(account_equity, "Account equity")
    market_bid = _decimal(bid, "Bid")
    market_ask = _decimal(ask, "Ask")
    broker_point = _decimal(point, "Broker point")
    if isinstance(stop_level_points, bool) or stop_level_points is None:
        raise RiskRejected("Broker stop level missing or invalid")
    try:
        min_stop_points = Decimal(str(stop_level_points))
    except (InvalidOperation, ValueError):
        raise RiskRejected("Broker stop level invalid") from None
    if min(market_bid, market_ask, broker_point) <= 0 or market_ask <= market_bid:
        raise RiskRejected("Invalid broker market quote")
    if min(reference, lots, tick, tick_value, equity) <= 0 or min_stop_points < 0:
        raise RiskRejected("Invalid position or broker contract values")

    cap = min(DEMO_TEST_RISK_CAP, equity * RISK_PER_TRADE)
    loss_per_price_unit_per_lot = tick_value / tick
    raw_distance = cap / (lots * loss_per_price_unit_per_lot)
    if raw_distance < tick:
        raise RiskRejected("Position volume is too large for the $4 test risk cap")
    if side == "BUY":
        stop = ((reference - raw_distance) / tick).to_integral_value(rounding=ROUND_CEILING) * tick
        if stop >= reference:
            raise RiskRejected("Could not place a valid BUY stop within the risk cap")
        risk_distance = reference - stop
        target = ((reference + risk_distance * DEMO_TARGET_R_MULTIPLE) / tick).to_integral_value(rounding=ROUND_CEILING) * tick
        if market_bid - stop < min_stop_points * broker_point:
            raise RiskRejected("Calculated BUY stop is inside the broker minimum distance")
        if target - market_ask < min_stop_points * broker_point:
            raise RiskRejected("Calculated BUY target is inside the broker minimum distance")
    else:
        stop = ((reference + raw_distance) / tick).to_integral_value(rounding=ROUND_FLOOR) * tick
        if stop <= reference:
            raise RiskRejected("Could not place a valid SELL stop within the risk cap")
        risk_distance = stop - reference
        target = ((reference - risk_distance * DEMO_TARGET_R_MULTIPLE) / tick).to_integral_value(rounding=ROUND_FLOOR) * tick
        if stop - market_ask < min_stop_points * broker_point:
            raise RiskRejected("Calculated SELL stop is inside the broker minimum distance")
        if market_bid - target < min_stop_points * broker_point:
            raise RiskRejected("Calculated SELL target is inside the broker minimum distance")
    projected_loss = risk_distance * loss_per_price_unit_per_lot * lots
    if projected_loss <= 0 or projected_loss > cap:
        raise RiskRejected("Calculated protection exceeds the $4 demo test risk cap")
    return {"side": side, "stop_loss": str(stop), "take_profit": str(target),
            "risk_amount_usd": str(projected_loss), "risk_cap_usd": str(cap),
            "reward_to_risk": str(DEMO_TARGET_R_MULTIPLE), "mode": "DEMO_ONLY"}

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
    max_risk = min(equity * RISK_PER_TRADE, DEMO_TEST_RISK_CAP)
    if projected_loss <= 0 or projected_loss > max_risk:
        raise RiskRejected("Projected stop loss exceeds the lower of 0.25% equity or $4 demo test cap")
    if start - current + projected_loss > start * DAILY_LOSS_LIMIT:
        raise RiskRejected("Proposed loss would breach daily 1% limit")
    return {
        "decision": "RISK_CHECK_PASSED_MANUAL_APPROVAL_ONLY",
        "risk_amount": str(projected_loss),
        "risk_limit": str(max_risk),
        "daily_loss_limit": str(start * DAILY_LOSS_LIMIT),
        "order_submitted": "false",
    }
