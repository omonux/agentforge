"""Paper stake selection stays within available cash and risk limits."""
import pytest
from app.omonux_stake_sizing import adaptive_paper_quantity


@pytest.mark.parametrize("confidence,expected",[ (76,3.0),(87,5.0),(95,10.0)])
def test_confidence_tiers(confidence,expected):
    quantity,info=adaptive_paper_quantity(price=100,stop=99,equity=100,
        available_cash=100,risk_percent=1,max_notional_percent=20,
        confidence=confidence)
    assert info["stake_usdt"]==expected
    assert quantity*100==pytest.approx(expected)
    assert info["leverage"]==1


def test_cash_and_risk_limits():
    qty,info=adaptive_paper_quantity(price=100,stop=90,equity=100,
        available_cash=4,risk_percent=1,max_notional_percent=20,
        confidence=99)
    assert info["stake_usdt"]==4
    assert qty*100<=4
    qty,info=adaptive_paper_quantity(price=100,stop=50,equity=100,
        available_cash=100,risk_percent=1,max_notional_percent=20,
        confidence=99)
    assert info["stake_usdt"]==2


def test_insufficient_cash_blocks_trade():
    qty,info=adaptive_paper_quantity(price=100,stop=99,equity=100,
        available_cash=.5,risk_percent=1,max_notional_percent=20,
        confidence=99)
    assert qty==0
    assert "reason" in info


def test_bad_inputs_rejected():
    with pytest.raises(ValueError):
        adaptive_paper_quantity(price=0,stop=99,equity=100,
            available_cash=100,risk_percent=1,max_notional_percent=20,confidence=90)
