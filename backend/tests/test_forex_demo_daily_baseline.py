import unittest
import sys
import types
from unittest.mock import patch

from fastapi import HTTPException

import app.tickerall_demo_transport as tickerall_demo_transport
import app.omonux_forex as omonux_forex
from app.omonux_forex import record_mt5_demo_daily_baseline


class FakeJournal:
    def __init__(self):
        self.initialized = False
        self.values = None

    def initialize(self):
        self.initialized = True

    def record_daily_equity_baseline(self, account_id, trading_day, equity, currency):
        self.values = (account_id, trading_day, equity, currency)
        return {"trading_day": trading_day.isoformat(), "start_equity": equity,
                "currency": currency, "recorded_at": "test"}


class DailyBaselineRouteTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.journal = FakeJournal()
        journal_module = types.ModuleType("app.forex_neon_journal")
        journal_module.NeonDemoJournal = lambda: self.journal
        journal_module.DurableJournalUnavailable = RuntimeError
        self.journal_module = patch.dict(sys.modules,
                                         {"app.forex_neon_journal": journal_module})
        self.journal_module.start()
        self.request = patch.object(tickerall_demo_transport, "_request",
                             return_value=[{"id": "demo-account", "isDemo": True,
                                            "broker": "mt5", "hot": True,
                                            "status": "online"}])
        self.get_account = patch.object(tickerall_demo_transport, "get_demo_account",
                                 return_value={"id": "demo-account", "isDemo": True,
                                               "broker": "mt5", "status": "online",
                                               "account": {"equity": "10000.25",
                                                           "currency": "USD"}})
        self.account_id = patch.object(omonux_forex, "_account_id",
                                return_value="demo-account")
        self.request.start()
        self.get_account.start()
        self.account_id.start()
        self.addCleanup(self.request.stop)
        self.addCleanup(self.get_account.stop)
        self.addCleanup(self.journal_module.stop)
        self.addCleanup(self.account_id.stop)

    async def test_stores_only_verified_demo_usd_equity(self):
        result = await record_mt5_demo_daily_baseline()
        self.assertTrue(self.journal.initialized)
        self.assertEqual(self.journal.values[0], "demo-account")
        self.assertEqual(self.journal.values[2:], ("10000.25", "USD"))
        self.assertFalse(result["order_submitted"])
        self.assertEqual(result["mode"], "MT5_DEMO_ONLY")

    async def test_cold_session_does_not_write_baseline(self):
        self.request.stop()
        self.request = patch.object(tickerall_demo_transport, "_request",
                             return_value=[{"id": "demo-account", "isDemo": True,
                                            "broker": "mt5", "hot": False,
                                            "status": "online"}])
        self.request.start()
        with self.assertRaises(HTTPException):
            await record_mt5_demo_daily_baseline()
        self.assertFalse(self.journal.initialized)
        self.assertIsNone(self.journal.values)

    async def test_non_usd_account_does_not_write_baseline(self):
        self.get_account.stop()
        self.get_account = patch.object(tickerall_demo_transport, "get_demo_account",
                                 return_value={"id": "demo-account", "isDemo": True,
                                               "broker": "mt5", "status": "online",
                                               "account": {"equity": "10000.25",
                                                           "currency": "EUR"}})
        self.get_account.start()
        with self.assertRaises(HTTPException):
            await record_mt5_demo_daily_baseline()
        self.assertFalse(self.journal.initialized)
        self.assertIsNone(self.journal.values)


if __name__ == "__main__":
    unittest.main()
