"""Connect the existing MT5 risk engine to durable reservation, without order submission."""
from __future__ import annotations
from dataclasses import dataclass
from .forex_demo_risk import DemoRiskEvidence, evaluate_demo_order
from .forex_neon_journal import NeonDemoJournal, DurableJournalUnavailable

@dataclass(frozen=True)
class ReviewResult:
    signal_id: str
    reservation_key: str
    risk_amount: str
    status: str

def reserve_approved_demo_signal(*, account_id: str, signal_id: str,
                                 evidence: DemoRiskEvidence,
                                 journal: NeonDemoJournal) -> ReviewResult:
    """Server-side approved evidence only. Never accepts client-supplied permission flags."""
    if not account_id or not signal_id:
        raise ValueError("Account and signal required")
    if journal.is_halted(account_id):
        raise DurableJournalUnavailable("Demo emergency stop active")
    decision = evaluate_demo_order(evidence)
    # The atomic reservation blocks duplicate/pending orders across workers.
    key = journal.reserve(account_id, signal_id)
    return ReviewResult(signal_id, key, decision["risk_amount"],
                        "RESERVED_NOT_SUBMITTED")
