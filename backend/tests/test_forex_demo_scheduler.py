import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from app.forex_demo_scheduler import evaluate, check_once, STATE

class FakeJournal:
    def __init__(self, halted=True, unresolved=0, baseline=None):
        self.halted = halted
        self.unresolved = unresolved
        self.baseline = baseline

    def safety_snapshot(self, account_id):
        return {"emergency_stop_active": self.halted,
                "unresolved_order_count": self.unresolved}

    def daily_equity_baseline(self, account_id, day):
        return self.baseline

class DemoSchedulerSafetyTests(unittest.TestCase):
    def test_missing_account_blocks(self):
        self.assertIn("MT5 demo account ID missing or invalid", evaluate(FakeJournal(), ""))

    def test_emergency_stop_blocks(self):
        self.assertIn("Persisted emergency stop engaged", evaluate(FakeJournal(), "cmwddqr3t18vyo901n2hs3m7f"))

    def test_unresolved_order_blocks(self):
        self.assertIn("Unresolved demo orders require reconciliation",
                      evaluate(FakeJournal(False, 1, {"start_equity": "10000"}), "cmwddqr3t18vyo901n2hs3m7f"))

    def test_missing_baseline_blocks(self):
        self.assertIn("Broker-verified daily equity baseline missing",
                      evaluate(FakeJournal(False, 0, None), "cmwddqr3t18vyo901n2hs3m7f"))

    def test_even_with_proof_scheduler_cannot_submit(self):
        reasons = evaluate(FakeJournal(False, 0, {"start_equity": "10000"}),
                           "cmwddqr3t18vyo901n2hs3m7f", broker_proof=True)
        self.assertIn("Broker execution adapter and automatic approvals not implemented", reasons)

if __name__ == "__main__":
    unittest.main()
