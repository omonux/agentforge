"""Pure risk policy tests: never call broker or submit orders."""
from dataclasses import replace
import pytest
from app.forex_demo_risk import (DemoRiskEvidence, RiskRejected,
    build_demo_order_plan, build_existing_position_protection, evaluate_demo_order)

def valid():
    return DemoRiskEvidence(
        verified_demo=True, session_ready=True, trading_permitted=True,
        broker_state_fresh=True, prices_fresh=True, symbol_tradeable=True,
        spread_acceptable=True, stop_supported=True, durable_journal_ready=True,
        reconciliation_ready=True, manual_approval_verified=True,
        kill_switch_off=True, account_equity="10000",
        start_of_day_equity="10000", current_equity="10000",
        open_positions=0, requested_volume="0.01",
        min_volume="0.01", max_volume="1", volume_step="0.01",
        entry_price="1.1000", stop_price="1.0990",
        loss_per_price_unit_per_lot="100000", available_margin="1000",
        required_margin="100", symbol="EURUSD", side="BUY",
    )

def test_valid_evidence_only_passes_risk_gate():
    result = evaluate_demo_order(valid())
    assert result["decision"] == "RISK_CHECK_PASSED_MANUAL_APPROVAL_ONLY"
    assert result["order_submitted"] == "false"

@pytest.mark.parametrize("field,value", [
    ("verified_demo", False), ("session_ready", False),
    ("trading_permitted", False), ("broker_state_fresh", False),
    ("prices_fresh", False), ("symbol_tradeable", False),
    ("spread_acceptable", False), ("stop_supported", False),
    ("durable_journal_ready", False), ("reconciliation_ready", False),
    ("manual_approval_verified", False), ("kill_switch_off", False),
    ("open_positions", 1), ("open_positions", None),
    ("account_equity", "NaN"), ("start_of_day_equity", "0"),
    ("requested_volume", "0.015"), ("requested_volume", "2"),
    ("available_margin", "50"), ("stop_price", "1.1010"),
    ("loss_per_price_unit_per_lot", None), ("side", "HOLD"),
])
def test_missing_or_unsafe_evidence_rejected(field, value):
    with pytest.raises(RiskRejected):
        evaluate_demo_order(replace(valid(), **{field: value}))

def test_per_trade_risk_limit():
    with pytest.raises(RiskRejected, match=r"\$4"):
        evaluate_demo_order(replace(valid(), requested_volume="0.05"))

def test_daily_loss_limit():
    with pytest.raises(RiskRejected, match="Daily loss"):
        evaluate_demo_order(replace(valid(), current_equity="9900"))

def test_projected_loss_cannot_cross_daily_limit():
    with pytest.raises(RiskRejected, match="daily 1%"):
        evaluate_demo_order(replace(valid(), current_equity="9900.5"))

def test_sell_requires_stop_above_entry():
    with pytest.raises(RiskRejected, match="SELL stop"):
        evaluate_demo_order(replace(valid(), side="SELL"))

def test_exact_trade_risk_limit_accepted():
    result = evaluate_demo_order(replace(valid(), requested_volume="0.04"))
    assert result["risk_amount"] == "4.000000"
    assert result["risk_limit"] == "4.00"


def test_ai_trade_plan_sizes_to_four_dollars_and_sets_two_to_one_target():
    result = build_demo_order_plan(
        side="BUY", entry_price="1.10000", stop_reference="1.09900",
        tick_size="0.00001", tick_value_account_per_lot="1",
        min_volume="0.01", max_volume="1", volume_step="0.01",
        account_equity="10000", start_of_day_equity="10000",
        current_equity="10000", account_currency="USD",
    )
    assert result["volume_lots"] == "0.04"
    assert result["risk_amount_usd"] == "4.00"
    assert result["take_profit_reference"] == "1.10200"
    assert result["order_submitted"] == "false"


def test_ai_trade_plan_rejects_broker_minimum_lot_above_four_dollars():
    with pytest.raises(RiskRejected, match="minimum volume"):
        build_demo_order_plan(
            side="BUY", entry_price="1.10000", stop_reference="1.09900",
            tick_size="0.00001", tick_value_account_per_lot="1",
            min_volume="0.05", max_volume="1", volume_step="0.01",
            account_equity="10000", start_of_day_equity="10000",
            current_equity="10000", account_currency="USD",
        )


@pytest.mark.parametrize("side,expected_stop,expected_target", [
    ("BUY", "1.09980", "1.10100"),
    ("SELL", "1.10070", "1.09950"),
])
def test_existing_position_protection_calculates_broker_aligned_levels(side, expected_stop, expected_target):
    result = build_existing_position_protection(
        side=side, reference_price="1.10020" if side == "BUY" else "1.10030", volume="0.10",
        tick_size="0.00001", tick_value_account_per_lot="1",
        account_equity="10000", account_currency="USD",
        bid="1.10020", ask="1.10030", point="0.00001",
        stop_level_points="0",
    )
    assert result["stop_loss"] == expected_stop
    assert result["take_profit"] == expected_target
    assert float(result["risk_amount_usd"]) == 4.0
    assert result["risk_cap_usd"] == "4.00"
    assert result["mode"] == "DEMO_ONLY"


def test_existing_position_protection_rejects_when_broker_minimum_exceeds_cap():
    with pytest.raises(RiskRejected, match="minimum distance"):
        build_existing_position_protection(
            side="BUY", reference_price="1.10000", volume="0.10",
            tick_size="0.00001", tick_value_account_per_lot="1",
            account_equity="10000", account_currency="USD",
            bid="1.10000", ask="1.10010", point="0.00001",
            stop_level_points="5000",
        )


def test_existing_position_protection_requires_usd_account_for_dollar_cap():
    with pytest.raises(RiskRejected, match="USD account"):
        build_existing_position_protection(
            side="BUY", reference_price="1.10020", volume="0.10",
            tick_size="0.00001", tick_value_account_per_lot="1",
            account_equity="10000", account_currency="EUR",
            bid="1.10020", ask="1.10030", point="0.00001",
            stop_level_points="0",
        )
