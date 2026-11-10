"""Offline integration tests for durable demo order journal; no broker I/O."""
import sqlite3
import pytest
from app.forex_demo_journal import DemoOrderJournal, JournalRejected

def journal(tmp_path):
    return DemoOrderJournal(str(tmp_path / "orders.db"), persistent_storage_verified=True)

def test_rejects_ephemeral_or_unverified_storage(tmp_path):
    with pytest.raises(JournalRejected):
        DemoOrderJournal(":memory:", persistent_storage_verified=True)
    with pytest.raises(JournalRejected):
        DemoOrderJournal(str(tmp_path / "orders.db"))

def test_kill_switch_defaults_on_and_survives_restart(tmp_path):
    j = journal(tmp_path)
    assert j.is_halted("demo")
    with pytest.raises(JournalRejected, match="Emergency stop"):
        j.reserve("demo", "signal-1")
    j.set_halted("demo", False)
    assert not journal(tmp_path).is_halted("demo")
    j.set_halted("demo", True)
    assert journal(tmp_path).is_halted("demo")

def test_duplicate_and_outstanding_order_blocked(tmp_path):
    j = journal(tmp_path)
    j.set_halted("demo", False)
    key = j.reserve("demo", "signal-1")
    assert j.get_status(key) == "RESERVED"
    with pytest.raises(JournalRejected, match="Outstanding"):
        j.reserve("demo", "signal-2")
    j.mark_submitting(key)
    j.mark_unknown(key)
    with pytest.raises(JournalRejected, match="Outstanding"):
        journal(tmp_path).reserve("demo", "signal-2")
    with pytest.raises(JournalRejected, match="Unexpected"):
        j.mark_submitting(key)

def test_acknowledged_blocks_further_orders(tmp_path):
    j = journal(tmp_path)
    j.set_halted("demo", False)
    key = j.reserve("demo", "signal-1")
    j.mark_submitting(key)
    j.mark_acknowledged(key)
    with pytest.raises(JournalRejected, match="Outstanding"):
        j.reserve("demo", "signal-2")

def test_rejected_reservation_can_be_replaced_but_not_reused(tmp_path):
    j = journal(tmp_path)
    j.set_halted("demo", False)
    key = j.reserve("demo", "signal-1")
    j.mark_rejected(key)
    with pytest.raises(JournalRejected, match="Duplicate"):
        j.reserve("demo", "signal-1")
    assert j.reserve("demo", "signal-2") != key

def test_atomic_single_reservation_across_connections(tmp_path):
    j1 = journal(tmp_path)
    j2 = journal(tmp_path)
    j1.set_halted("demo", False)
    j1.reserve("demo", "one")
    with pytest.raises(JournalRejected):
        j2.reserve("demo", "two")
