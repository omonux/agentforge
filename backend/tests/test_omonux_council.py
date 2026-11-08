import pytest

from app.omonux_council import (
    SPECIALISTS,
    _market_evidence,
    _parse_vote,
    build_execution_gate,
    summarize_votes,
)


def test_council_has_twelve_distinct_specialists():
    assert len(SPECIALISTS) == 12
    assert len({item[0] for item in SPECIALISTS}) == 12


def test_parse_vote_accepts_only_known_stances():
    vote = _parse_vote(
        '{"stance":"BUY","confidence":77,"reason":"Trend and momentum align.","evidence":["EMA9 above EMA21"],"veto":false}',
        "trend",
        "Trend Analyst",
    )
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
    evidence = _market_evidence("BTCUSDT", "30m", candles, {"side": "HOLD", "confidence": 50})
    assert evidence["closed_candle_count"] == 50
    assert any("No order-book" in item for item in evidence["limitations"])


def test_council_evidence_summarizes_real_completed_timeframes():
    candles = [{"time": i, "open": 10 + i, "high": 12 + i, "low": 9 + i, "close": 10 + i, "volume": 100} for i in range(50)]
    evidence = _market_evidence("BTCUSDT", "30m", candles, {"side": "BUY"}, {"30m": candles, "1h": candles})
    assert set(evidence["multi_timeframe_summaries"]) == {"30m", "1h"}
    assert evidence["multi_timeframe_summaries"]["1h"]["closed_candles"] == 50
    assert "ema_9" in evidence["multi_timeframe_summaries"]["1h"]


def _votes(buy=8, sell=0, veto=False):
    values = []
    for index in range(12):
        stance = "BUY" if index < buy else ("SELL" if index < buy + sell else "HOLD")
        values.append({
            "id": f"agent_{index}", "stance": stance, "confidence": 80,
            "veto": veto and index == 0, "status": "completed",
        })
    return values


def test_consensus_requires_eight_buy_votes_and_all_twelve_agents():
    result = summarize_votes(_votes())
    assert result["approved"] is True
    assert result["decision"] == "MANUAL_REVIEW_CANDIDATE"


def test_consensus_rejects_critical_veto_even_with_majority():
    result = summarize_votes(_votes(veto=True))
    assert result["approved"] is False
    assert result["vetoes"] == ["agent_0"]


def test_consensus_rejects_missing_agent_or_excess_opposition():
    incomplete = _votes()
    incomplete[-1]["status"] = "failed"
    assert summarize_votes(incomplete)["approved"] is False
    assert summarize_votes(_votes(buy=8, sell=2))["approved"] is False


def test_execution_gate_only_qualifies_candidate_for_manual_review():
    summary = summarize_votes(_votes())
    gate = build_execution_gate({"side": "BUY"}, summary)
    assert gate["candidate_status"] == "READY_FOR_MANUAL_REVIEW"
    assert gate["manual_review_eligible"] is True
    assert gate["automatic_live_orders_authorized"] is False
    assert any("human" in item.lower() for item in gate["requirements"])


@pytest.mark.parametrize("signal,summary", [
    ({"side": "HOLD"}, summarize_votes(_votes())),
    ({"side": "BUY"}, summarize_votes(_votes(veto=True))),
    ({"side": "BUY"}, summarize_votes(_votes(buy=7))),
])
def test_execution_gate_fails_closed(signal, summary):
    gate = build_execution_gate(signal, summary)
    assert gate["candidate_status"] == "BLOCKED"
    assert gate["manual_review_eligible"] is False
    assert gate["automatic_live_orders_authorized"] is False
