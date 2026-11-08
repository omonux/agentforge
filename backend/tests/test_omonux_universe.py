import unittest
from unittest.mock import AsyncMock, patch

from app.omonux_universe import UNIVERSE_SYMBOLS, scan_market_universe


class UniverseTests(unittest.IsolatedAsyncioTestCase):
    def test_universe_has_fifty_unique_symbols(self):
        self.assertEqual(len(UNIVERSE_SYMBOLS), 50)
        self.assertEqual(len(set(UNIVERSE_SYMBOLS)), 50)

    async def test_scan_is_bounded_and_returns_fail_closed_metadata(self):
        with patch("app.omonux_universe.fetch_both_market_candles", new=AsyncMock(side_effect=RuntimeError("offline"))):
            result = await scan_market_universe(max_symbols=4)
        self.assertEqual(result["markets_checked"], 4)
        self.assertEqual(result["markets_unavailable"], 4)
        self.assertEqual(result["top_candidates"], [])
        self.assertEqual(result["execution"], "research_and_paper_candidate_only")


if __name__ == "__main__":
    unittest.main()
