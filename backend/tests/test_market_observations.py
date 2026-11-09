"""Research observation persistence is bounded and read-only."""
import sqlite3
from app.main import ensure_market_observations_table


def test_observation_schema_and_index():
    conn=sqlite3.connect(":memory:")
    ensure_market_observations_table(conn)
    conn.execute("""INSERT INTO market_observations
     (id,symbol,checked_at_ms,buy_venue,sell_venue,gross_edge_bps,estimated_net_edge_bps,indicative_notional_usdt,assumed_cost_bps,recorded_at)
     VALUES(?,?,?,?,?,?,?,?,?,?)""",
     ("obs-1","BTCUSDT",1000,"binance","bybit",45,10,200,35,"2026-11-09T00:00:00+00:00"))
    assert conn.execute("SELECT estimated_net_edge_bps FROM market_observations WHERE symbol=?",("BTCUSDT",)).fetchone()[0]==10
    indexes={row[1] for row in conn.execute("PRAGMA index_list(market_observations)")}
    assert "idx_market_observations_symbol_time" in indexes
    conn.close()
