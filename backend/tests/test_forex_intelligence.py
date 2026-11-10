"""Forex research adapter tests: no network or broker orders."""
from datetime import datetime, timezone
import pytest
from app.omonux_forex_intelligence import normalize_forex_candles, forex_research_signal

def bars():
    start = 1730000000
    return [{"timestamp": start + i * 1800,
             "open": 1.1000 + i * .0001, "high": 1.1005 + i * .0001,
             "low": 1.0995 + i * .0001, "close": 1.1002 + i * .0001,
             "tickVolume": 30} for i in range(45)]

def test_valid_closed_forex_candles_and_research_only_signal():
    candles = normalize_forex_candles(bars())
    assert len(candles) == 45
    assert candles[0]["time"] == 1730000000000
    assert candles[0]["volume"] == 30
    signal = forex_research_signal(candles)
    assert signal["side"] == "BUY"
    assert signal["confidence"] == 0
    assert signal["execution"] == "research_only_no_order_placed"

def test_millisecond_timestamps_supported():
    rows = bars()
    for row in rows:
        row["timestamp"] *= 1000
    assert len(normalize_forex_candles(rows)) == 45

def test_duplicate_and_out_of_order_candles_rejected():
    rows = bars()
    rows[10]["timestamp"] = rows[9]["timestamp"]
    with pytest.raises(ValueError, match="time-ordered"):
        normalize_forex_candles(rows)

def test_invalid_prices_and_volume_rejected():
    rows = bars()
    rows[0]["high"] = rows[0]["low"] - 0.01
    with pytest.raises(ValueError, match="OHLC"):
        normalize_forex_candles(rows)
    rows = bars()
    rows[0]["tickVolume"] = -1
    with pytest.raises(ValueError, match="volume"):
        normalize_forex_candles(rows)

def test_too_few_candles_rejected():
    with pytest.raises(ValueError, match="40"):
        normalize_forex_candles(bars()[:30])
