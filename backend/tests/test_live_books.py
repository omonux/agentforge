import pytest
from app.omonux_live_books import evaluate_quotes,scan_live_books


def quote(bid,ask):
    return {"bid":bid,"ask":ask,"bid_size":2,"ask_size":3}


def test_bid_ask_costs_and_route():
    r=evaluate_quotes("BTCUSDT",quote(100,101),quote(102,103))
    assert r["best_route"]["buy_venue"]=="binance"
    assert r["best_route"]["sell_venue"]=="bybit"
    assert r["best_route"]["gross_edge_bps"]>0
    assert r["best_route"]["estimated_net_edge_bps"]<r["best_route"]["gross_edge_bps"]
    assert not r["executable"]


def test_crossed_or_empty_books_fail_closed():
    with pytest.raises(ValueError):
        evaluate_quotes("BTCUSDT",quote(102,101),quote(100,101))
    with pytest.raises(ValueError):
        evaluate_quotes("BTCUSDT",quote(0,101),quote(100,101))


@pytest.mark.asyncio
async def test_invalid_symbols_do_not_fetch():
    with pytest.raises(ValueError):
        await scan_live_books(["NOTLISTED"])
    with pytest.raises(ValueError):
        await scan_live_books(["BTCUSDT","BTCUSDT"])
