"""Regression checks for fail-closed AI council vote validation."""
import json
import asyncio

import pytest

from app.omonux_council import _parse_vote, run_council


def valid_vote():
    return {"stance": "BUY", "confidence": 70, "reason": "Observed trend supports entry",
            "evidence": ["EMA 9 above EMA 21"], "veto": False}


def test_valid_vote_is_accepted():
    vote = _parse_vote(json.dumps(valid_vote()), "trend", "Trend Analyst")
    assert vote["status"] == "completed"
    assert vote["veto"] is False


@pytest.mark.parametrize("change", [
    {"stance": None}, {"stance": "buy"}, {"confidence": 101},
    {"confidence": -1}, {"confidence": "90"}, {"confidence": True},
    {"reason": ""}, {"reason": None}, {"evidence": "not a list"},
    {"evidence": [None]}, {"veto": "false"}, {"veto": 0},
])
def test_invalid_vote_rejected(change):
    vote = valid_vote()
    vote.update(change)
    with pytest.raises(ValueError):
        _parse_vote(json.dumps(vote), "trend", "Trend Analyst")


@pytest.mark.parametrize("missing", ["stance", "confidence", "reason", "evidence", "veto"])
def test_missing_required_vote_field_rejected(missing):
    vote = valid_vote()
    del vote[missing]
    with pytest.raises(ValueError):
        _parse_vote(json.dumps(vote), "trend", "Trend Analyst")


def test_council_accepts_optional_timeframes_without_name_error():
    with pytest.raises(ValueError, match="at least 40"):
        asyncio.run(run_council("BTCUSDT", "30m", [], {}, "https://example.invalid",
                                "placeholder", "test-model", multi_timeframe_candles={}))
