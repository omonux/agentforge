"""Paper-only profit target and trailing stop invariants."""
import pytest
from app.omonux_profit_protection import trailing_stop


def test_buy_trail_waits_for_one_r():
    assert trailing_stop("BUY",100,98,101)==98
    assert trailing_stop("BUY",100,98,102)==100.5
    assert trailing_stop("BUY",100,98,105)==103.5


def test_sell_trail_waits_for_one_r():
    assert trailing_stop("SELL",100,102,99)==102
    assert trailing_stop("SELL",100,102,98)==99.5
    assert trailing_stop("SELL",100,102,95)==96.5


def test_invalid_position_rejected():
    with pytest.raises(ValueError):
        trailing_stop("BUY",100,102,105)
    with pytest.raises(ValueError):
        trailing_stop("SELL",100,98,95)
