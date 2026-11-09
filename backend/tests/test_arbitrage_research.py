import pytest
from app.omonux_arbitrage_research import analyze_discrepancy


def test_equal_prices_never_pass_cost_gate():
    result=analyze_discrepancy(100,100)
    assert result["estimated_net_edge_bps"] < 0
    assert not result["passes_assumed_cost_threshold"]
    assert not result["executable"]


def test_costs_reduce_estimated_edge():
    cheap=analyze_discrepancy(100,101,roundtrip_fee_bps=0,roundtrip_slippage_bps=0,extra_cost_bps=0)
    costly=analyze_discrepancy(100,101,roundtrip_fee_bps=30,roundtrip_slippage_bps=20,extra_cost_bps=10)
    assert costly["estimated_net_edge_bps"] < cheap["estimated_net_edge_bps"]
    assert costly["buy_venue"]=="binance"
    assert analyze_discrepancy(101,100)["buy_venue"]=="bybit"


def test_invalid_market_prices_fail_closed():
    with pytest.raises(ValueError):
        analyze_discrepancy(0,100)
    with pytest.raises(ValueError):
        analyze_discrepancy(100,101,roundtrip_fee_bps=-1)
