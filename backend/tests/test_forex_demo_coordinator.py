from dataclasses import replace
import pytest
from app.forex_demo_coordinator import reserve_approved_demo_signal
from app.forex_demo_risk import DemoRiskEvidence, RiskRejected
from app.forex_neon_journal import NeonDemoJournal, DurableJournalUnavailable

def evidence():
    return DemoRiskEvidence(
        verified_demo=True,session_ready=True,trading_permitted=True,
        broker_state_fresh=True,prices_fresh=True,symbol_tradeable=True,
        spread_acceptable=True,stop_supported=True,durable_journal_ready=True,
        reconciliation_ready=True,manual_approval_verified=True,kill_switch_off=True,
        account_equity="10000",start_of_day_equity="10000",current_equity="10000",
        open_positions=0,requested_volume="0.01",min_volume="0.01",
        max_volume="100",volume_step="0.01",entry_price="1.10",
        stop_price="1.09",loss_per_price_unit_per_lot="100000",
        available_margin="9000",required_margin="100",
        symbol="EURUSD",side="BUY")

class Journal:
    halted = True
    reserved = False
    def is_halted(self, account_id): return self.halted
    def reserve(self, account_id, signal_id):
        self.reserved = True
        return "test-key"

def test_halted_cannot_reserve():
    j=Journal()
    with pytest.raises(DurableJournalUnavailable):
        reserve_approved_demo_signal(account_id="demo",signal_id="a",evidence=evidence(),journal=j)
    assert not j.reserved

def test_missing_approval_cannot_reserve():
    j=Journal();j.halted=False
    with pytest.raises(RiskRejected):
        reserve_approved_demo_signal(account_id="demo",signal_id="a",
           evidence=replace(evidence(),manual_approval_verified=False),journal=j)
    assert not j.reserved

def test_valid_proposal_only_reserves_never_submits():
    j=Journal();j.halted=False
    result=reserve_approved_demo_signal(account_id="demo",signal_id="a",
         evidence=evidence(),journal=j)
    assert result.status=="RESERVED_NOT_SUBMITTED"
    assert j.reserved

def test_missing_database_fails_closed(monkeypatch):
    monkeypatch.delenv("DATABASE_URL",raising=False)
    with pytest.raises(DurableJournalUnavailable):
        NeonDemoJournal()
