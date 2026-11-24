"""Fail-closed readiness gate for unattended live trading.

This module is intentionally independent of exchange execution. It never
enables trading, handles credentials, or submits an order.
"""
from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class ReadinessEvidence:
    persistent_order_ledger: bool = False
    atomic_order_claims: bool = False
    restart_reconciliation: bool = False
    verified_spot_permissions: bool = False
    withdrawal_permission_disabled: bool = False
    account_balance_fresh: bool = False
    exchange_rules_fresh: bool = False
    portfolio_protections_wired: bool = False
    emergency_stop_verified: bool = False
    idempotent_exchange_submission: bool = False
    testnet_end_to_end_passed: bool = False
    operator_opt_in: bool = False


def evaluate_autonomous_readiness(evidence: ReadinessEvidence) -> dict:
    """Return blockers, not an execution permit.

    Evidence is an explicit record of verified integration tests, never
    inferred from presence of environment variables or a successful AI vote.
    """
    blockers = [name.upper() for name, verified in vars(evidence).items() if verified is not True]
    return {
        "ready_for_operator_review": not blockers,
        "blockers": blockers,
        "automatic_live_orders_authorized": False,
        "notice": "A passing checklist does not authorize exchange orders.",
    }
