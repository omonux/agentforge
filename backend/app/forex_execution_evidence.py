"""Fail-closed parsing of read-only broker execution evidence."""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

def numeric(value, allow_zero=False):
    if isinstance(value, bool) or value is None:
        return None
    try:
        v = Decimal(str(value))
        return str(v) if v.is_finite() and (v >= 0 if allow_zero else v > 0) else None
    except (InvalidOperation, ValueError, TypeError):
        return None

def symbol_evidence(payload, symbol):
    if isinstance(payload, dict) and isinstance(payload.get("spec"), dict):
        payload = [payload["spec"]]
    rows = payload if isinstance(payload, list) else payload.get("symbols", []) if isinstance(payload, dict) else []
    if isinstance(rows, dict):
        rows = list(rows.values())
    if not isinstance(rows, list):
        return {}
    row = next((r for r in rows if isinstance(r, dict) and r.get("symbol", r.get("name")) == symbol), None)
    if row is None:
        return {}
    fields = {"min_volume": ("volumeMin", "minVolume", "minLot"),
              "max_volume": ("volumeMax", "maxVolume", "maxLot"),
              "volume_step": ("volumeStep", "lotStep"),
              "contract_size": ("contractSize",),
              "tick_size": ("tickSize",), "tick_value": ("tickValueAccount",),
              "stops_level": ("stopLevel", "stopsLevel")}
    out = {}
    for name, aliases in fields.items():
        value = next((row[k] for k in aliases if k in row), None)
        out[name] = numeric(value, name == "stops_level")
    out["spec_source"] = row.get("specSource")
    out["trade_mode"] = row.get("tradeMode")
    return out

def quote_evidence(payload, symbol):
    quote = payload.get("quote", payload) if isinstance(payload, dict) else {}
    if not isinstance(quote, dict) or quote.get("symbol") != symbol:
        return {}
    bid, ask = numeric(quote.get("bid")), numeric(quote.get("ask"))
    timestamp = quote.get("timestamp", quote.get("time"))
    if not bid or not ask or not timestamp:
        return {}
    try:
        ts = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            return {}
        age = (datetime.now(timezone.utc) - ts.astimezone(timezone.utc)).total_seconds()
        if not 0 <= age <= 30 or Decimal(ask) <= Decimal(bid):
            return {}
    except (ValueError, TypeError, OverflowError):
        return {}
    return {"bid": bid, "ask": ask, "timestamp": ts.isoformat(), "age_seconds": round(age, 2)}
