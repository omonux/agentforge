from dataclasses import replace
from decimal import Decimal as D
from app.demo_autotrade_gate import DemoSnapshot, TradeProposal, evaluate

S = DemoSnapshot(True, True, True, D("10000"), D("0"), 0, True, 2, False, False)
T = TradeProposal("EURUSD", "BUY", D("1.10"), D("1.09"), D("1.12"),
                  D("20"), 11, 12, True)

def test_healthy_proposal_only_passes_review():
    assert evaluate(S, T).approved_for_demo_review

def test_no_manual_approval():
    assert not evaluate(S, replace(T, manual_approval=False)).approved_for_demo_review

def test_kill_switch_blocks():
    assert not evaluate(replace(S, kill_switch_engaged=True), T).approved_for_demo_review

def test_unverified_positions_block():
    assert not evaluate(replace(S, positions_verified=False), T).approved_for_demo_review

def test_stale_snapshot_blocks():
    assert not evaluate(replace(S, snapshot_age_seconds=16), T).approved_for_demo_review

def test_daily_loss_blocks():
    assert not evaluate(replace(S, daily_realized_pnl=D("-101")), T).approved_for_demo_review

def test_risk_limit_blocks():
    assert not evaluate(S, replace(T, risk_usd=D("26"))).approved_for_demo_review

def test_pending_order_blocks():
    assert not evaluate(replace(S, pending_order_exists=True), T).approved_for_demo_review

def test_wrong_stop_blocks():
    assert not evaluate(S, replace(T, stop_loss=D("1.11"))).approved_for_demo_review

def test_live_account_blocks():
    assert not evaluate(replace(S, is_demo=False), T).approved_for_demo_review

def test_nan_blocks():
    assert not evaluate(replace(S, account_equity=D("NaN")), T).approved_for_demo_review
