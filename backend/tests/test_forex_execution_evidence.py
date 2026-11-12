from datetime import datetime, timedelta, timezone
from app.forex_execution_evidence import numeric, symbol_evidence, quote_evidence

def test_numeric_rejects_invalid():
    assert numeric(True) is None
    assert numeric("NaN") is None
    assert numeric("-1") is None
    assert numeric("0", allow_zero=True) == "0"

def test_specifications_require_actual_broker_fields():
    row = {"symbol": "EURUSDm", "volumeMin": 0.01, "volumeMax": 100,
           "volumeStep": 0.01, "contractSize": 100000,
           "tickSize": 0.00001, "tickValue": 1, "stopsLevel": 0}
    data = symbol_evidence({"symbols": [row]}, "EURUSDm")
    assert data["min_volume"] == "0.01"
    assert data["stops_level"] == "0"
    assert symbol_evidence({"symbols": [row]}, "GBPUSDm") == {}
    assert symbol_evidence({}, "EURUSDm") == {}

def test_quote_must_be_fresh_and_timestamped():
    now = datetime.now(timezone.utc)
    quote = {"symbol": "EURUSDm", "bid": 1.1, "ask": 1.1002,
             "timestamp": now.isoformat()}
    assert quote_evidence(quote, "EURUSDm")["bid"] == "1.1"
    quote["timestamp"] = (now - timedelta(minutes=2)).isoformat()
    assert quote_evidence(quote, "EURUSDm") == {}
    quote["timestamp"] = now.isoformat()
    quote["ask"] = 1.0
    assert quote_evidence(quote, "EURUSDm") == {}
