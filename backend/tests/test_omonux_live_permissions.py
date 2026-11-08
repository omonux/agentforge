import asyncio

import pytest
from fastapi import HTTPException

from app.omonux_live_execution import ensure_binance_spot_only
from app import omonux_live_ops


def test_binance_permissions_accept_spot_only_with_withdrawals_disabled():
    ensure_binance_spot_only({"canTrade": True, "canWithdraw": False, "permissions": ["SPOT"]})


@pytest.mark.parametrize("account", [
    {"canTrade": True, "canWithdraw": True, "permissions": ["SPOT"]},
    {"canTrade": False, "canWithdraw": False, "permissions": ["SPOT"]},
    {"canTrade": True, "canWithdraw": False, "permissions": ["SPOT", "MARGIN"]},
    {"canTrade": True, "permissions": ["SPOT"]},
])
def test_binance_permissions_fail_closed(account):
    with pytest.raises(HTTPException):
        ensure_binance_spot_only(account)


def _run_bybit_permissions(monkeypatch, info):
    async def fake_request(method, path, key, secret):
        assert method == "GET"
        assert path == "/v5/user/query-api"
        return info

    monkeypatch.setattr(omonux_live_ops, "bybit_request", fake_request)
    asyncio.run(omonux_live_ops.ensure_bybit_spot_only_permissions("key", "secret"))


def test_bybit_permissions_accept_spot_trade_only_with_ip_allowlist(monkeypatch):
    _run_bybit_permissions(monkeypatch, {
        "readOnly": False,
        "ips": "203.0.113.10",
        "permissions": {"Spot": ["SpotTrade"], "Wallet": [], "ContractTrade": []},
    })


@pytest.mark.parametrize("info", [
    {"readOnly": False, "ips": "203.0.113.10", "permissions": {"Spot": ["SpotTrade"], "Wallet": ["Withdraw"]}},
    {"readOnly": False, "ips": "203.0.113.10", "permissions": {"Spot": ["SpotTrade"], "ContractTrade": ["ContractTrade"]}},
    {"readOnly": False, "ips": "", "permissions": {"Spot": ["SpotTrade"], "Wallet": []}},
    {"readOnly": True, "ips": "203.0.113.10", "permissions": {"Spot": ["SpotTrade"]}},
    {"readOnly": False, "ips": "203.0.113.10"},
])
def test_bybit_permissions_reject_unsafe_or_unverifiable_keys(monkeypatch, info):
    with pytest.raises(HTTPException):
        _run_bybit_permissions(monkeypatch, info)
