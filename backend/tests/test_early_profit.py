"""Test conservative early paper profit exits."""
import pytest
from app.omonux_early_profit import early_profit_decision


def test_long_profitable_after_costs():
    close,net,cost=early_profit_decision(side="BUY",entry=100,current=101.2,quantity=.05)
    assert close
    assert net>=.05
    assert cost>0


def test_short_profitable_after_costs():
    close,net,cost=early_profit_decision(side="SELL",entry=100,current=98.8,quantity=.05)
    assert close
    assert net>=.05


def test_tiny_profit_not_enough_after_costs():
    close,net,cost=early_profit_decision(side="BUY",entry=100,current=100.2,quantity=.05)
    assert not close


def test_loss_never_triggers_early_profit():
    close,net,cost=early_profit_decision(side="SELL",entry=100,current=101,quantity=.05)
    assert not close


def test_invalid_inputs():
    with pytest.raises(ValueError):
        early_profit_decision(side="BUY",entry=0,current=100,quantity=1)
