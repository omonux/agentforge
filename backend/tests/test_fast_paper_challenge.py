"""Challenge must remain historical-only and account for simulated costs."""
import pytest
from fastapi.testclient import TestClient
from app import main
from app import omonux_challenge


def test_challenge_math_and_costs(monkeypatch):
    def fake_backtest(symbol,candles,**kwargs):
        assert kwargs["fee_bps"] == 10
        assert kwargs["slippage_bps"] == 5
        return {"net_return_pct":10.0,"trade_count":2}
    monkeypatch.setattr(omonux_challenge,"backtest_closed_candles",fake_backtest)
    report=omonux_challenge.challenge_report("BTCUSDT",[{"time":1},{"time":2}])
    assert report["historical_ending_cash"] == 74.8
    assert report["target_reached_in_sample"] is False
    assert report["mode"] == "historical_paper_research_only"
    with pytest.raises(ValueError):
        omonux_challenge.challenge_report("BTCUSDT",[{"time":1},{"time":2}],target_cash=60)


def test_challenge_requires_auth(tmp_path,monkeypatch):
    monkeypatch.setattr(main,"DB",tmp_path/"challenge.db")
    with TestClient(main.app) as client:
        response=client.post("/api/v1/trading/challenge/5m/backtest",json={"symbol":"BTCUSDT"})
        assert response.status_code in (401,503)
