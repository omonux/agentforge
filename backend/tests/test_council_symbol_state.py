"""The council must not suppress a new symbol after reviewing another symbol."""
from fastapi.testclient import TestClient
from app import main


def test_council_scan_candle_state_is_per_symbol(tmp_path,monkeypatch):
    monkeypatch.setattr(main,"DB",tmp_path/"symbol-state.db")
    with TestClient(main.app):
        with main.db() as conn:
            conn.execute(
                "INSERT INTO council_symbol_scan_state(symbol,last_candle_time,updated) VALUES(?,?,?)",
                ("BTCUSDT",1234567890,"2026-11-09T00:00:00+00:00"))
            conn.execute(
                "INSERT INTO council_symbol_scan_state(symbol,last_candle_time,updated) VALUES(?,?,?)",
                ("ETHUSDT",1234567000,"2026-11-09T00:00:00+00:00"))
        btc=main.one("SELECT last_candle_time FROM council_symbol_scan_state WHERE symbol=?",("BTCUSDT",))
        eth=main.one("SELECT last_candle_time FROM council_symbol_scan_state WHERE symbol=?",("ETHUSDT",))
        sol=main.one("SELECT last_candle_time FROM council_symbol_scan_state WHERE symbol=?",("SOLUSDT",))
        assert btc["last_candle_time"]==1234567890
        assert eth["last_candle_time"]==1234567000
        assert sol is None
        with main.db() as conn:
            conn.execute(
                "INSERT INTO council_symbol_scan_state(symbol,last_candle_time,updated) VALUES(?,?,?) ON CONFLICT(symbol) DO UPDATE SET last_candle_time=excluded.last_candle_time,updated=excluded.updated",
                ("ETHUSDT",1234568000,"2026-11-09T00:30:00+00:00"))
        assert main.one("SELECT last_candle_time FROM council_symbol_scan_state WHERE symbol=?",("BTCUSDT",))["last_candle_time"]==1234567890
        assert main.one("SELECT last_candle_time FROM council_symbol_scan_state WHERE symbol=?",("ETHUSDT",))["last_candle_time"]==1234568000
