"""Offline one-shot execution tests: no broker credentials or network calls."""
import asyncio
from types import SimpleNamespace
import pytest
from app import forex_demo_coordinator as coordinator
from app.tickerall_demo_transport import BrokerUnavailable
from app.forex_demo_risk import RiskRejected


class Journal:
    def __init__(self):
        self.states = []
    def transition(self, key, before, after):
        self.states.append((key, before, after))


def evidence():
    return SimpleNamespace(symbol="EURUSDm", side="BUY",
                           entry_price="1.1000", requested_volume="0.01",
                           stop_price="1.0980")


def setup(monkeypatch):
    journal = Journal()
    monkeypatch.setattr(coordinator, "reserve_approved_demo_signal",
                        lambda **kwargs: SimpleNamespace(reservation_key="test-uuid",
                                                          risk_amount="2.00"))
    return journal


def call(journal, submit, **changes):
    kwargs = dict(account_id="demo", signal_id="signal-1",
                  evidence=evidence(), journal=journal, symbol="EURUSDm",
                  side="BUY", volume=0.01, stop_loss=1.098,
                  take_profit=1.104, submit_order=submit)
    kwargs.update(changes)
    return asyncio.run(coordinator.execute_reserved_demo_once(**kwargs))


def test_confirmed_order_is_acknowledged(monkeypatch):
    journal = setup(monkeypatch)
    async def submit(*args, **kwargs):
        assert kwargs["idempotency_key"] == "test-uuid"
        return {"confirmed_open": True, "ticket": "123"}
    result = call(journal, submit)
    assert result["status"] == "ACKNOWLEDGED"
    assert [s[2] for s in journal.states] == ["SUBMITTING", "ACKNOWLEDGED"]


def test_timeout_becomes_unknown_and_not_retried(monkeypatch):
    journal = setup(monkeypatch)
    attempts = []
    async def submit(*args, **kwargs):
        attempts.append(1)
        raise TimeoutError("broker response lost")
    with pytest.raises(BrokerUnavailable, match="uncertain"):
        call(journal, submit)
    assert len(attempts) == 1
    assert [s[2] for s in journal.states] == ["SUBMITTING", "UNKNOWN"]


def test_unconfirmed_broker_result_becomes_unknown(monkeypatch):
    journal = setup(monkeypatch)
    async def submit(*args, **kwargs):
        return {"status": "pending"}
    with pytest.raises(BrokerUnavailable):
        call(journal, submit)
    assert journal.states[-1][2] == "UNKNOWN"


@pytest.mark.parametrize("changes", [
    {"symbol": "GBPUSDm"},
    {"side": "SELL"},
    {"volume": 0.02},
    {"stop_loss": 1.09},
    {"take_profit": 1.09},
])
def test_invalid_order_does_not_reserve(monkeypatch, changes):
    journal = setup(monkeypatch)
    async def submit(*args, **kwargs):
        pytest.fail("Order should not be submitted")
    with pytest.raises(RiskRejected):
        call(journal, submit, **changes)
    assert journal.states == []
