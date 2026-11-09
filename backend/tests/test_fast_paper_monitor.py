"""Fast monitoring closes paper positions without invoking the AI council."""
import asyncio
import pytest
from app import main
from app.omonux_fast_monitor import paper_exit_reason


def test_buy_sell_stop_target():
    assert paper_exit_reason("BUY",99,99,110)=="STOP_LOSS"
    assert paper_exit_reason("BUY",110,99,110)=="TAKE_PROFIT"
    assert paper_exit_reason("SELL",101,101,90)=="STOP_LOSS"
    assert paper_exit_reason("SELL",90,101,90)=="TAKE_PROFIT"
    assert paper_exit_reason("BUY",100,99,110) is None
    with pytest.raises(ValueError):
        paper_exit_reason("BUY",float("nan"),99,110)


def test_fast_monitor_exit_without_ai(tmp_path,monkeypatch):
    monkeypatch.setattr(main,"DB",tmp_path/"paper-monitor.db")
    with main.db() as conn:
        conn.execute("CREATE TABLE auto_trade_positions(id TEXT PRIMARY KEY,symbol TEXT,side TEXT,quantity REAL,entry_price REAL,stop_price REAL,target_price REAL,opened TEXT)")
        conn.execute("CREATE TABLE auto_trade_events(id TEXT PRIMARY KEY,event_type TEXT,symbol TEXT,details TEXT,pnl REAL,created TEXT)")
        conn.execute("INSERT INTO auto_trade_positions VALUES(?,?,?,?,?,?,?,?)",
                     ("p1","BTCUSDT","BUY",.1,100,98,104,"2026-01-01"))
    async def quotes(symbols):
        assert symbols==["BTCUSDT"]
        return {"BTCUSDT":105.0}
    monkeypatch.setattr(main,"fetch_fresh_prices",quotes)
    result=asyncio.run(main.monitor_paper_positions())
    assert result["closed"]==1
    assert main.rows("SELECT * FROM auto_trade_positions")==[]
    event=main.one("SELECT * FROM auto_trade_events WHERE event_type='PAPER_EXIT'")
    assert event["pnl"]==pytest.approx(.4795)
    assert "fast_quote_monitor" in event["details"]


def test_missing_quote_fails_closed(tmp_path,monkeypatch):
    monkeypatch.setattr(main,"DB",tmp_path/"missing-quote.db")
    with main.db() as conn:
        conn.execute("CREATE TABLE auto_trade_positions(id TEXT PRIMARY KEY,symbol TEXT,side TEXT,quantity REAL,entry_price REAL,stop_price REAL,target_price REAL,opened TEXT)")
        conn.execute("CREATE TABLE auto_trade_events(id TEXT PRIMARY KEY,event_type TEXT,symbol TEXT,details TEXT,pnl REAL,created TEXT)")
        conn.execute("INSERT INTO auto_trade_positions VALUES(?,?,?,?,?,?,?,?)",
                     ("p1","ETHUSDT","SELL",1,100,102,95,"2026-01-01"))
    async def no_quotes(symbols):
        return {}
    monkeypatch.setattr(main,"fetch_fresh_prices",no_quotes)
    result=asyncio.run(main.monitor_paper_positions())
    assert result["closed"]==0
    assert result["errors"]==["ETHUSDT"]
    assert len(main.rows("SELECT * FROM auto_trade_positions"))==1
