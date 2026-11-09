"""Profit Intelligence V1: deterministic, no network and no live orders."""
import asyncio
import pytest
from app import main
from app.omonux_profit_intelligence import paper_performance


def test_realized_metrics_drawdown_and_profit_factor():
    events=[
      {"id":"a","event_type":"PAPER_EXIT","created":"2026-01-01","pnl":1.0},
      {"id":"b","event_type":"PAPER_EXIT","created":"2026-01-02","pnl":-2.0},
      {"id":"c","event_type":"PAPER_EXIT","created":"2026-01-03","pnl":3.0},
    ]
    result=paper_performance(events)
    assert result["closed_trades"]==3
    assert result["wins"]==2 and result["losses"]==1
    assert result["win_rate_percent"]==pytest.approx(66.67)
    assert result["realized_pnl"]==pytest.approx(2.0)
    assert result["profit_factor"]==pytest.approx(2.0)
    assert result["max_realized_drawdown_percent"]==pytest.approx(200/101)


def test_no_trades_or_losses_do_not_invent_profit_factor():
    result=paper_performance([])
    assert result["win_rate_percent"] is None
    assert result["profit_factor"] is None
    assert result["max_realized_drawdown_percent"]==0
    assert paper_performance([{"event_type":"PAPER_EXIT","created":"a","pnl":1}])["profit_factor"] is None


def test_portfolio_uses_quotes_and_fails_closed(tmp_path,monkeypatch):
    monkeypatch.setattr(main,"DB",tmp_path/"analytics.db")
    with main.db() as conn:
        conn.execute("CREATE TABLE auto_trade_positions(id TEXT PRIMARY KEY,symbol TEXT,side TEXT,quantity REAL,entry_price REAL,stop_price REAL,target_price REAL,opened TEXT)")
        conn.execute("CREATE TABLE auto_trade_events(id TEXT PRIMARY KEY,event_type TEXT,symbol TEXT,details TEXT,pnl REAL,created TEXT)")
        conn.execute("CREATE TABLE auto_trade_settings(id INTEGER PRIMARY KEY,running INTEGER)")
        conn.execute("INSERT INTO auto_trade_settings VALUES(1,0)")
        conn.execute("INSERT INTO auto_trade_positions VALUES('p1','BTCUSDT','BUY',0.1,100,98,110,'2026-01-01')")
    monkeypatch.setattr(main,"auto_settings",lambda:{"running":0})
    async def fresh(symbols):
        assert symbols==["BTCUSDT"]
        return {"BTCUSDT":105.0}
    monkeypatch.setattr(main,"fetch_fresh_prices",fresh)
    result=asyncio.run(main.auto_paper_portfolio())
    assert result["equity"]==pytest.approx(100.5)
    assert result["estimated_net_equity"]==pytest.approx(100.4795)
    assert result["price_source"]=="public_binance_ticker_price"
    async def unavailable(symbols):
        return {}
    monkeypatch.setattr(main,"fetch_fresh_prices",unavailable)
    result=asyncio.run(main.auto_paper_portfolio())
    assert result["equity"] is None
    assert result["mark_to_market_complete"] is False
    assert result["positions"][0]["mark_price"] is None
