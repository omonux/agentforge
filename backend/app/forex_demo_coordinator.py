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


async def execute_reserved_demo_once(*, account_id: str, signal_id: str,
                                     evidence: DemoRiskEvidence,
                                     journal: NeonDemoJournal,
                                     symbol: str, side: str, volume: float,
                                     stop_loss: float, take_profit: float,
                                     submit_order=None) -> dict:
    """One-shot protected DEMO order coordinator; not connected to HTTP/scheduler.

    Caller must independently collect fresh broker evidence, confirm a
    one-time human approval, and validate TP direction and broker stops.
    A lost broker response becomes UNKNOWN and is NEVER retried here.
    """
    from .tickerall_demo_transport import submit_demo_market_order, BrokerUnavailable
    from .forex_demo_risk import RiskRejected
    if symbol != evidence.symbol or side != evidence.side:
        raise RiskRejected("Broker symbol or side differs from verified risk evidence")
    from decimal import Decimal, InvalidOperation
    try:
        volume_value = Decimal(str(volume))
        stop_value = Decimal(str(stop_loss))
        target_value = Decimal(str(take_profit))
        entry_value = Decimal(str(evidence.entry_price))
        evidence_volume = Decimal(str(evidence.requested_volume))
        evidence_stop = Decimal(str(evidence.stop_price))
    except (InvalidOperation, TypeError, ValueError):
        raise RiskRejected("Invalid order numeric parameters") from None
    if not all(x.is_finite() for x in
               (volume_value, stop_value, target_value, entry_value, evidence_volume, evidence_stop)):
        raise RiskRejected("Nonfinite order parameters")
    if volume_value != evidence_volume or stop_value != evidence_stop:
        raise RiskRejected("Order volume or stop differs from risk evidence")
    if target_value <= 0 or (side == "BUY" and target_value <= entry_value) or (side == "SELL" and target_value >= entry_value):
        raise RiskRejected("Take profit must be on profitable side of verified entry")
    if submit_order is None:
        submit_order = submit_demo_market_order
    reservation = reserve_approved_demo_signal(
        account_id=account_id, signal_id=signal_id,
        evidence=evidence, journal=journal)
    journal.transition(reservation.reservation_key, "RESERVED", "SUBMITTING")
    try:
        result = await submit_order(
            account_id, symbol=symbol, side=side, volume=volume,
            stop_loss=stop_loss, take_profit=take_profit,
            idempotency_key=reservation.reservation_key)
    except Exception:
        # Even a transport error can mean broker execution succeeded.
        # Preserve UNKNOWN to prevent a second order without reconciliation.
        journal.transition(reservation.reservation_key, "SUBMITTING", "UNKNOWN")
        raise BrokerUnavailable("Demo order outcome uncertain; journal UNKNOWN; inspect broker before retry") from None
    if not isinstance(result, dict) or result.get("confirmed_open") is not True or not result.get("ticket"):
        journal.transition(reservation.reservation_key, "SUBMITTING", "UNKNOWN")
        raise BrokerUnavailable("Demo order not independently confirmed; reconcile before retry")
    journal.transition(reservation.reservation_key, "SUBMITTING", "ACKNOWLEDGED")
    return {"status": "ACKNOWLEDGED", "mode": "DEMO_ONLY",
            "ticket": str(result["ticket"]),
            "idempotency_key": reservation.reservation_key,
            "risk_amount": reservation.risk_amount,
            "broker_stop_loss_confirmed": True,
            "broker_take_profit_confirmed": True,
            "reconciliation_required": True}
