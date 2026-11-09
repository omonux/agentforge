"""Fast radar must rank deterministically and never submit orders."""
import asyncio
from fastapi.testclient import TestClient
from app import main, omonux_fast_radar


def candles():
    return [{"time": i*300000, "open": 100+i*.1, "high": 101+i*.1,
             "low": 99+i*.1, "close": 100+i*.1, "volume": 100} for i in range(60)]


def test_radar_cost_filter(monkeypatch):
    monkeypatch.setattr(omonux_fast_radar, "build_signal", lambda symbol, cs: {
        "side":"BUY", "directional_confidence":90,
        "risk_levels":{"stop_reference":100,"target_reference":107}})
    result=omonux_fast_radar.score_market("BTCUSDT",candles(),fee_bps=10,slippage_bps=5)
    assert result["eligible_for_review"]
    assert result["estimated_round_trip_cost_pct"]==0.3
    expensive=omonux_fast_radar.score_market("BTCUSDT",candles(),fee_bps=500,slippage_bps=500)
    assert not expensive["eligible_for_review"]
    assert any("costs" in w for w in expensive["warnings"])


def test_radar_scan_is_read_only(monkeypatch):
    async def fake_candles(symbol,interval,limit):
        assert interval=="5m"
        return candles()
    monkeypatch.setattr(omonux_fast_radar,"fetch_candles",fake_candles)
    monkeypatch.setattr(omonux_fast_radar,"build_signal",lambda symbol,cs:{
        "side":"HOLD","directional_confidence":0,"risk_levels":{}})
    report=asyncio.run(omonux_fast_radar.scan_fast_radar(["BTCUSDT","ETHUSDT"]))
    assert report["markets_checked"]==2
    assert report["review_candidates"]==0
    assert report["mode"]=="research_only_no_orders"


def test_radar_requires_auth(tmp_path,monkeypatch):
    monkeypatch.setattr(main,"DB",tmp_path/"radar.db")
    with TestClient(main.app) as client:
        response=client.post("/api/v1/trading/radar/5m",json={"symbols":["BTCUSDT"]})
        assert response.status_code in (401,503)
