"""Fail-closed MT5 demo scheduler supervisor.

This worker observes durable safety controls; it does not place broker orders.
The execution adapter is deliberately absent until protected-order acceptance,
read-back, daily risk accounting, and recovery have integration-test evidence.
"""
import asyncio
import os
import re
from datetime import datetime, timezone

ACCOUNT_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,80}$")
STATE = {"running": False, "last_check_at": None, "status": "not_started",
         "blockers": ["Broker execution adapter not verified"], "orders_submitted": 0}

def snapshot():
    return {**STATE, "blockers": list(STATE["blockers"])}

def evaluate(journal, account_id, broker_proof=False):
    """Never authorize submission based solely on a healthy account or a cleared halt."""
    reasons = []
    if not ACCOUNT_PATTERN.fullmatch(account_id or ""):
        reasons.append("MT5 demo account ID missing or invalid")
        return reasons
    state = journal.safety_snapshot(account_id)
    if state["emergency_stop_active"]:
        reasons.append("Persisted emergency stop engaged")
    if state["unresolved_order_count"]:
        reasons.append("Unresolved demo orders require reconciliation")
    if not journal.daily_equity_baseline(account_id, datetime.now(timezone.utc).date()):
        reasons.append("Broker-verified daily equity baseline missing")
    if not broker_proof:
        reasons.append("Protected-order acceptance and broker SL/TP read-back unverified")
    reasons.append("Broker execution adapter and automatic approvals not implemented")
    return reasons

async def check_once():
    STATE["last_check_at"] = datetime.now(timezone.utc).isoformat()
    account_id = os.getenv("TICKERALL_ACCOUNT_ID", "")
    try:
        from .forex_neon_journal import NeonDemoJournal
        journal = NeonDemoJournal()
        STATE["blockers"] = evaluate(journal, account_id)
        STATE["status"] = "blocked"
    except Exception:
        STATE["blockers"] = ["Persistent risk controls unavailable"]
        STATE["status"] = "blocked"

async def demo_scheduler_supervisor():
    """Periodic monitoring only. Never calls TickerAll order endpoints."""
    STATE["running"] = True
    try:
        while True:
            await check_once()
            await asyncio.sleep(max(60, int(os.getenv("MT5_DEMO_SAFETY_CHECK_SECONDS", "300"))))
    finally:
        STATE["running"] = False
