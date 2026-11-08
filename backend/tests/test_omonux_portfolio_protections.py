"""Regression tests for portfolio entry protections."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.omonux_portfolio_protections import (
    ClosedTrade, ProtectionLimits, check_entry_protections,
)

NOW = datetime(2026, 11, 8, 12, tzinfo=timezone.utc)


def evaluate(**changes):
    kwargs = dict(equity_usdt="100", peak_equity_usdt="100",
                  day_start_equity_usdt="100", closed_trades=[], now=NOW)
    kwargs.update(changes)
    return check_entry_protections(**kwargs)


def test_healthy_portfolio_allows_research_candidate():
    result = evaluate()
    assert result["entry_allowed"]
    assert result["automatic_live_orders_authorized"] is False


@pytest.mark.parametrize("equity,peak,start,expected", [
    ("89", "100", "100", "MAX_DRAWDOWN"),
    ("96", "100", "100", "DAILY_LOSS"),
    ("97", "100", "100", "DAILY_LOSS"),
])
def test_loss_guards(equity, peak, start, expected):
    assert expected in evaluate(equity_usdt=equity, peak_equity_usdt=peak,
                                day_start_equity_usdt=start)["blockers"]


def test_consecutive_losses_and_cooldown():
    trades = [ClosedTrade(NOW - timedelta(minutes=i), Decimal("-1"))
              for i in (10, 8, 2)]
    result = evaluate(closed_trades=trades)
    assert "CONSECUTIVE_LOSSES" in result["blockers"]
    assert "COOLDOWN" in result["blockers"]


def test_profit_resets_loss_streak():
    trades = [ClosedTrade(NOW - timedelta(hours=3), Decimal("-1")),
              ClosedTrade(NOW - timedelta(hours=2), Decimal("1"))]
    assert evaluate(closed_trades=trades)["entry_allowed"]


@pytest.mark.parametrize("bad", ["nan", "Infinity", None, "-1"])
def test_bad_equity_rejected(bad):
    with pytest.raises(ValueError):
        evaluate(equity_usdt=bad)


def test_inconsistent_peak_rejected():
    with pytest.raises(ValueError):
        evaluate(peak_equity_usdt="50")


def test_future_trade_rejected():
    with pytest.raises(ValueError):
        evaluate(closed_trades=[ClosedTrade(NOW + timedelta(minutes=1), Decimal("-1"))])


def test_naive_timestamp_rejected():
    with pytest.raises(ValueError):
        evaluate(now=NOW.replace(tzinfo=None))


def test_invalid_limits_rejected():
    with pytest.raises(ValueError):
        evaluate(limits=ProtectionLimits(max_drawdown_fraction=Decimal("0")))
