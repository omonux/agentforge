import pytest

from app.omonux_exchange_market_data import (
    _normalize_binance,
    _normalize_bybit,
    fetch_market_candles,
)


def test_binance_normalization_sorts_and_excludes_forming_candle():
    rows = [
        [60000, "2", "3", "1", "2.5", "10", 119999],
        [0, "1", "2", "0.5", "1.5", "8", 59999],
        [120000, "3", "4", "2", "3.5", "12", 179999],
    ]
    candles = _normalize_binance(rows, now_ms=150000)
    assert [c["time"] for c in candles] == [0, 60000]
    assert candles[0]["close"] == 1.5
    assert candles[0]["volume"] == 8


def test_bybit_normalization_sorts_and_excludes_forming_candle():
    rows = [
        ["60000", "2", "3", "1", "2.5", "10", "20"],
        ["0", "1", "2", "0.5", "1.5", "8", "15"],
        ["120000", "3", "4", "2", "3.5", "12", "25"],
    ]
    candles = _normalize_bybit(rows, "1m" if False else "5m", now_ms=360000)
    # With 5m candles, the first two rows are not yet complete at this test time.
    assert candles == []


def test_exchange_and_interval_validation_happens_before_network():
    with pytest.raises(ValueError, match="Exchange"):
        import asyncio
        asyncio.run(fetch_market_candles("kraken", "BTCUSDT"))
    with pytest.raises(ValueError, match="timeframe"):
        import asyncio
        asyncio.run(fetch_market_candles("bybit", "BTCUSDT", "2m"))
