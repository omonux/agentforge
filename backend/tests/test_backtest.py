from app.omonux_backtest import backtest_closed_candles


def sample(n=110):
    return [{"time": i * 1800000, "open": 100 + i * .4,
             "high": 101 + i * .4, "low": 99 + i * .4,
             "close": 100 + i * .4, "volume": 1000} for i in range(n)]


def test_backtest_is_research_only_and_fee_aware():
    candles = sample()
    low = backtest_closed_candles("BTCUSDT", candles, fee_bps=0, slippage_bps=0)
    high = backtest_closed_candles("BTCUSDT", candles, fee_bps=50, slippage_bps=30)
    assert low["mode"] == "historical_research_only"
    assert low["trade_count"] > 0
    assert high["net_return_pct"] <= low["net_return_pct"]
    assert all(t["exit_time"] >= t["entry_time"] for t in high["trades"])


def test_rejects_unsorted_candles():
    candles = sample()
    candles[51]["time"] = candles[50]["time"]
    try:
        backtest_closed_candles("BTCUSDT", candles)
        assert False, "Expected chronological validation"
    except ValueError:
        pass
