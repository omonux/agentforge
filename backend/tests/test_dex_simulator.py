from decimal import Decimal
import pytest
from app.dex_simulator import Quote, evaluate_routes

D = Decimal

def test_estimated_profit_deducts_all_costs():
    quote = Quote("A-B-A", D("1012"), D("2.5"), D("3"), D("2"), 5)
    result = evaluate_routes(D("1000"), [quote])[0]
    assert result.net_profit_usd == D("4.5")
    assert result.eligible

def test_stale_quote_is_rejected():
    quote = Quote("A-B-A", D("1050"), D("1"), D("1"), D("1"), 90)
    assert evaluate_routes(D("1000"), [quote])[0].reason == "stale quote"

def test_excessive_impact_is_rejected():
    quote = Quote("A-B-A", D("1100"), D("1"), D("1"), D("20"), 5)
    assert not evaluate_routes(D("1000"), [quote])[0].eligible

def test_negative_or_nonfinite_quote_rejected():
    quote = Quote("A-B-A", D("NaN"), D("1"), D("1"), D("1"), 5)
    with pytest.raises(ValueError):
        evaluate_routes(D("1000"), [quote])
