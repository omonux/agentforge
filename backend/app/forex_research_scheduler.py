"""Opt-in, research-only Forex scheduler. Never submits broker orders.

The scheduler is deliberately separate from MT5 execution permissions. It
requires FOREX_RESEARCH_SCHEDULER_ENABLED=true, runs one cycle at a time,
and records only non-sensitive operational status in process memory.
"""
import asyncio
import os
from datetime import datetime, timezone

PAIRS = ("EURUSD", "GBPUSD", "USDJPY")
STATUS = {"enabled": False, "running": False, "last_cycle_at": None,
          "last_results": {}, "last_error": None, "execution": "research_only_no_orders"}

def snapshot():
    return {**STATUS, "last_results": dict(STATUS["last_results"])}

async def run_cycle():
    from .omonux_forex import forex_research
    if STATUS["running"]:
        return
    STATUS["running"] = True
    try:
        for pair in PAIRS:
            try:
                result = await forex_research(pair, timeframe="M30", hours=168)
                STATUS["last_results"][pair] = {
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                    "result": "research_completed",
                    "execution": "no_order_placed",
                    "signal": str(result.get("signal", {}).get("side", "UNVERIFIED"))
                        if isinstance(result.get("signal"), dict) else "UNVERIFIED",
                }
            except asyncio.CancelledError:
                raise
            except Exception:
                STATUS["last_results"][pair] = {
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                    "result": "research_unavailable",
                    "execution": "no_order_placed",
                }
        STATUS["last_cycle_at"] = datetime.now(timezone.utc).isoformat()
        STATUS["last_error"] = None
    finally:
        STATUS["running"] = False

async def research_scheduler():
    STATUS["enabled"] = os.getenv("FOREX_RESEARCH_SCHEDULER_ENABLED", "").lower() == "true"
    if not STATUS["enabled"]:
        return
    await asyncio.sleep(30)
    while True:
        try:
            await run_cycle()
        except asyncio.CancelledError:
            raise
        except Exception:
            STATUS["last_error"] = "Research scheduler cycle failed"
        await asyncio.sleep(max(300, int(os.getenv("FOREX_RESEARCH_INTERVAL_SECONDS", "1800"))))
