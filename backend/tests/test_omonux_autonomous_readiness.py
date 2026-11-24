from app.omonux_autonomous_readiness import ReadinessEvidence, evaluate_autonomous_readiness


def test_default_blocks_unattended_live_orders():
    result = evaluate_autonomous_readiness(ReadinessEvidence())
    assert result["blockers"]
    assert result["automatic_live_orders_authorized"] is False


def test_partial_checks_cannot_authorize():
    result = evaluate_autonomous_readiness(
        ReadinessEvidence(persistent_order_ledger=True, testnet_end_to_end_passed=True)
    )
    assert "PORTFOLIO_PROTECTIONS_WIRED" in result["blockers"]
    assert result["automatic_live_orders_authorized"] is False


def test_all_verified_still_requires_separate_authorization():
    evidence = ReadinessEvidence(**{name: True for name in ReadinessEvidence.__dataclass_fields__})
    result = evaluate_autonomous_readiness(evidence)
    assert result["ready_for_operator_review"] is True
    assert result["automatic_live_orders_authorized"] is False
