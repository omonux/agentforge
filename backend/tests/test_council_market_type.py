"""Market-aware twelve-agent evidence regression tests (no network)."""
import pytest
from app.omonux_council import _market_evidence, summarize_votes

def candles():
    return [{"time": i * 1800000, "close": 1.1 + i * 0.0001,
             "high": 1.11 + i * 0.0001, "low": 1.09 + i * 0.0001,
             "volume": 0} for i in range(40)]

def test_forex_evidence_never_claims_binance_or_centralized_volume():
    evidence = _market_evidence("EURUSD", "M30", candles(),
                                {"side": "SELL"}, market_type="forex")
    assert evidence["market_type"] == "forex"
    assert "MT5" in evidence["data_source"]
    assert any("not centralized" in x for x in evidence["limitations"])

def test_crypto_evidence_keeps_existing_default():
    evidence = _market_evidence("BTCUSDT", "30m", candles(), {"side": "BUY"})
    assert evidence["market_type"] == "crypto"
    assert evidence["data_source"] == "Binance public OHLCV"

def test_unknown_market_fails_closed():
    with pytest.raises(ValueError, match="Unsupported market"):
        _market_evidence("EURUSD", "M30", candles(), {}, market_type="stocks")

def test_sell_consensus_is_supported_but_veto_blocks():
    votes = [{"id": str(i), "stance": "SELL", "status": "completed",
              "confidence": 90, "veto": False} for i in range(12)]
    assert summarize_votes(votes, "SELL")["approved"] is True
    votes[0]["veto"] = True
    assert summarize_votes(votes, "SELL")["approved"] is False
