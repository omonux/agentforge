"""Regression tests for long/short paper-trading direction and council gating."""
from app.omonux_council import summarize_votes
from app.omonux_engine import build_signal

def votes(direction, n=9, opposite=1, veto=False):
    other = "SELL" if direction == "BUY" else "BUY"
    result = []
    for i in range(12):
        stance = direction if i < n else other if i < n + opposite else "HOLD"
        result.append({"id":str(i),"stance":stance,"confidence":75,"status":"completed","veto":veto and i==0})
    return result

def test_sell_consensus_approves_only_short():
    packet = summarize_votes(votes("SELL"), "SELL")
    assert packet["approved"] is True
    assert packet["approved_direction"] == "SELL"
    assert summarize_votes(votes("SELL"), "BUY")["approved"] is False

def test_buy_consensus_remains_supported():
    assert summarize_votes(votes("BUY"), "BUY")["approved"] is True

def test_veto_and_incomplete_votes_block_short():
    assert summarize_votes(votes("SELL", veto=True), "SELL")["approved"] is False
    partial = votes("SELL")
    partial[0]["status"] = "failed"
    assert summarize_votes(partial, "SELL")["approved"] is False

def test_hold_never_approves():
    assert summarize_votes(votes("SELL"), "HOLD")["approved"] is False

def test_directional_confidence_and_stop_geometry():
    def candles(falling):
        out = []
        for i in range(100):
            p = 200 - i * 1.5 if falling else 50 + i * 1.5
            out.append({"time":i*1800000,"open":p,"high":p+1,"low":p-1,"close":p,"volume":1000})
        return out
    sell = build_signal("BTCUSDT", candles(True))
    buy = build_signal("BTCUSDT", candles(False))
    assert sell["side"] == "SELL"
    assert sell["directional_confidence"] == 100-sell["confidence"]
    assert sell["risk_levels"]["target_reference"] < sell["price"] < sell["risk_levels"]["stop_reference"]
    assert buy["side"] == "BUY"
    assert buy["directional_confidence"] == buy["confidence"]
    assert buy["risk_levels"]["stop_reference"] < buy["price"] < buy["risk_levels"]["target_reference"]
