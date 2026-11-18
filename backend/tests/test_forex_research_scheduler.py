import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

import app.forex_research_scheduler as scheduler


class ForexResearchSchedulerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        scheduler.STATUS.update({"running": False, "last_cycle_at": None,
                                 "last_results": {}, "last_error": None,
                                 "last_started_at": None})

    async def test_controlled_failure_is_explained_without_execution(self):
        failure = HTTPException(503, "AI provider not configured; no council decision")
        with patch("app.omonux_forex.forex_research",
                   new=AsyncMock(side_effect=failure)):
            await scheduler.run_cycle()

        result = scheduler.STATUS["last_results"]["EURUSD"]
        self.assertEqual(result["result"], "research_unavailable")
        self.assertEqual(result["reason"], "AI provider not configured; no council decision")
        self.assertEqual(result["execution"], "no_order_placed")

    async def test_uncontrolled_failure_does_not_leak_exception_text(self):
        failure = RuntimeError("Bearer secret=do-not-show")
        with patch("app.omonux_forex.forex_research",
                   new=AsyncMock(side_effect=failure)):
            await scheduler.run_cycle()

        result = scheduler.STATUS["last_results"]["EURUSD"]
        self.assertNotIn("do-not-show", result["reason"])
        self.assertEqual(result["execution"], "no_order_placed")


if __name__ == "__main__":
    unittest.main()
