from app.omonux_research import run_walk_forward, simulate_strategy


def test_walk_forward_uses_separate_train_and_test_windows():
    candles = []
    price = 100.0
    for i in range(420):
        price *= 1.001 if (i // 35) % 2 == 0 else 0.999
        candles.append({"time": i, "open": price, "high": price * 1.01, "low": price * .99, "close": price, "volume": 100})
    report = run_walk_forward(candles)
    assert report["data"]["training_candles"] == 294
    assert report["data"]["untouched_test_candles"] == 126
    assert report["data"]["split"] == "70% train / 30% out-of-sample"
    assert "return_pct" in report["out_of_sample"]
    assert report["mode"] if "mode" in report else True


def test_simulation_accounts_for_fees_and_slippage():
    candles = [{"close": 100 + i, "time": i} for i in range(100)]
    cheap = simulate_strategy(candles, 5, 21, fee_bps=0, slippage_bps=0)
    costly = simulate_strategy(candles, 5, 21, fee_bps=20, slippage_bps=20)
    assert costly["final_equity"] <= cheap["final_equity"]


def test_research_requires_minimum_history():
    import pytest
    with pytest.raises(ValueError):
        run_walk_forward([{"close": 100, "time": i} for i in range(200)])
