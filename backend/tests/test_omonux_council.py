import json

import pytest

from app.omonux_council import SPECIALISTS, _parse_vote, _market_evidence


def test_council_has_twelve_distinct_specialists():
    assert len(SPECIALISTS) == 12
    assert len({item[0] for item in SPECIALISTS}) == 12


def test_parse_vote_accepts_only_known_stances():
    vote = _parse_vote('{"stance":"BUY","confidence":77,"reason":"Trend and momentum align.","evidence":["EMA9 above EMA21"],"veto":false}', "trend", "Trend Analyst")
    assert vote["stance"] == "BUY"
    assert vote["confidence"] == 77
    assert vote["status"] == "completed"


def test_parse_vote_rejects_invalid_stance():
    with pytest.raises(ValueError):
        _parse_vote('{"stance":"YOLO","confidence":99,"reason":"Trust me"}', "trend", "Trend Analyst")


def test_parse_vote_rejects_missing_reason():
    with pytest.raises(ValueError):
        _parse_vote('{"stance":"BUY","confidence":99}', "trend", "Trend Analyst")


def test_council_evidence_contains_explicit_data_limits():
    candles = [{"time": i, "open": 10, "high": 11, "low": 9, "close": 10, "volume": 100} for i in range(50)]
    signal = {"side": "HOLD", "confidence": 50}
    evidence = _market_evidence("BTCUSDT", "30m", candles, signal)
    assert evidence["closed_candle_count"] == 50
    assert any("No order-book" in item for item in evidence["limitations"])
