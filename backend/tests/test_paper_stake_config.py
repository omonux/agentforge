"""Safety regression tests for configurable paper stake limits."""
import pytest
from pydantic import ValidationError
from app import main
from app.omonux_stake_sizing import adaptive_paper_quantity


def test_stake_cap_never_exceeds_ten_or_available_risk():
    for confidence in (60, 80, 90, 99):
        qty, info=adaptive_paper_quantity(price=100,stop=99,equity=100,
            available_cash=100,risk_percent=5,max_notional_percent=100,
            confidence=confidence,max_stake=10)
        assert qty*100<=10+1e-9
        assert info["leverage"]==1 and info["mode"]=="paper_only"
    qty,_=adaptive_paper_quantity(price=100,stop=90,equity=100,
        available_cash=100,risk_percent=1,max_notional_percent=100,
        confidence=99,max_stake=10)
    assert qty*100<=10.0+1e-9\n    assert qty*(100-90)<=1.0+1e-9


def test_config_rejects_excessive_stake_or_positions():
    with pytest.raises(ValidationError):
        main.AutoTradeConfig(max_paper_stake_usdt=10.01)
    with pytest.raises(ValidationError):
        main.AutoTradeConfig(max_open_positions=3)
    with pytest.raises(ValidationError):
        main.AutoTradeConfig(max_paper_stake_usdt=0)
    with pytest.raises(ValidationError):
        main.AutoTradeConfig(mode="paper",max_paper_stake_usdt=float("nan"))


def test_config_persists_stake_and_two_position_limit(tmp_path,monkeypatch):
    monkeypatch.setattr(main,"DB",tmp_path/"stake-config.db")
    with main.db() as conn:
        conn.execute("""CREATE TABLE auto_trade_settings(
            id INTEGER PRIMARY KEY,running INTEGER DEFAULT 0,mode TEXT DEFAULT 'paper',
            risk_percent REAL DEFAULT 1,min_confidence INTEGER DEFAULT 75,
            max_open_positions INTEGER DEFAULT 2,max_daily_loss_percent REAL DEFAULT 3,
            cooldown_minutes INTEGER DEFAULT 30,max_trades_per_day INTEGER DEFAULT 5,
            max_notional_percent REAL DEFAULT 20,max_paper_stake_usdt REAL DEFAULT 10,
            updated TEXT)""")
        conn.execute("INSERT INTO auto_trade_settings(id) VALUES(1)")
        conn.execute("CREATE TABLE auto_trade_positions(id TEXT,symbol TEXT,opened TEXT)")
    cfg=main.AutoTradeConfig(max_paper_stake_usdt=7.5,max_open_positions=2)
    result=main.auto_trade_config(cfg)
    assert result["settings"]["max_paper_stake_usdt"]==pytest.approx(7.5)
    assert result["settings"]["max_open_positions"]==2
    assert result["settings"]["mode"]=="paper"
