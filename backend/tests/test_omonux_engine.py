import pytest

from app.omonux_engine import build_signal, ema, fetch_candles, rsi, validate_symbol


def sample_candles(count=50):
    rows = []
    for i in range(count):
        close = 100 + i * 1.5
        rows.append({
            "time": i * 1800000,
            "open": close - 0.5,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": 1000 + i,
        })
    return rows


def test_ema_and_rsi_return_expected_lengths():
    values = [float(i) for i in range(1, 41)]
    assert len(ema(values, 9)) == len(values)
    assert len(rsi(values, 14)) == len(values)
    assert rsi(values, 14)[-1] == 100


def test_signal_uses_closed_candle_data_and_has_risk_references():
    result = build_signal("BTCUSDT", sample_candles())
    assert result["side"] == "BUY"
    assert result["confidence"] >= 60
    assert result["risk_levels"]["stop_reference"] < result["price"]
    assert result["risk_levels"]["target_reference"] > result["price"]
    assert result["execution"] == "research_only_no_order_placed"


def test_market_symbol_validation_rejects_bad_input():
    assert validate_symbol("btc/usdt") == "BTCUSDT"
    with pytest.raises(ValueError):
        validate_symbol("../../secret")


def test_signal_requires_sufficient_candles():
    with pytest.raises(ValueError):
        build_signal("BTCUSDT", sample_candles(20))
