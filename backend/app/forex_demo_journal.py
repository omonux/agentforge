"""Durable, fail-closed demo order reservation and emergency-stop journal.

SQLite is suitable only on a persistent single-writer volume. Never use an
ephemeral Render Free filesystem as a durable order journal. This module has
no broker transport and never submits an order.
"""
from __future__ import annotations
import sqlite3
import time
import uuid
from pathlib import Path

class JournalRejected(RuntimeError):
    pass

SCHEMA = """
CREATE TABLE IF NOT EXISTS control (
    account_id TEXT PRIMARY KEY,
    halted INTEGER NOT NULL DEFAULT 1 CHECK(halted IN (0,1)),
    updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS orders (
    idempotency_key TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    signal_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN
        ('RESERVED','SUBMITTING','UNKNOWN','ACKNOWLEDGED','REJECTED','RECONCILED')),
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    UNIQUE(account_id, signal_id)
);
CREATE INDEX IF NOT EXISTS orders_by_account ON orders(account_id, status);
"""

class DemoOrderJournal:
    def __init__(self, path: str, *, persistent_storage_verified: bool = False):
        if not persistent_storage_verified or not path or path == ":memory:":
            raise JournalRejected("Verified persistent order storage is required")
        self.path = Path(path)
        if not self.path.is_absolute():
            raise JournalRejected("Absolute persistent storage path required")
        if not self.path.parent.is_dir():
            raise JournalRejected("Journal directory missing")
        with self._connect() as db:
            db.executescript(SCHEMA)

    def _connect(self):
        db = sqlite3.connect(str(self.path), timeout=5, isolation_level=None)
        db.execute("PRAGMA busy_timeout=5000")
        db.execute("PRAGMA synchronous=FULL")
        db.execute("PRAGMA journal_mode=WAL")
        return db

    def set_halted(self, account_id: str, halted: bool) -> None:
        if not account_id:
            raise JournalRejected("Account missing")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""INSERT INTO control(account_id, halted, updated_at)
                          VALUES (?, ?, ?) ON CONFLICT(account_id) DO UPDATE SET
                          halted=excluded.halted, updated_at=excluded.updated_at""",
                       (account_id, int(halted), int(time.time())))
            db.commit()

    def is_halted(self, account_id: str) -> bool:
        with self._connect() as db:
            row = db.execute("SELECT halted FROM control WHERE account_id=?",
                             (account_id,)).fetchone()
            return row is None or row[0] != 0

    def reserve(self, account_id: str, signal_id: str, *, key: str | None = None) -> str:
        """Atomically reserve at most one outstanding submission per account.

        No retry after a timeout: UNKNOWN remains blocked until reconciliation.
        Existing open broker positions must also be checked separately.
        """
        if not account_id or not signal_id or len(signal_id) > 128:
            raise JournalRejected("Invalid reservation identity")
        token = str(uuid.UUID(key)) if key is not None else str(uuid.uuid4())
        now = int(time.time())
        with self._connect() as db:
            try:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute("SELECT halted FROM control WHERE account_id=?",
                                 (account_id,)).fetchone()
                if row is None or row[0] != 0:
                    raise JournalRejected("Emergency stop enabled or uninitialized")
                outstanding = db.execute("""SELECT 1 FROM orders WHERE account_id=?
                    AND status IN ('RESERVED','SUBMITTING','UNKNOWN','ACKNOWLEDGED')
                    LIMIT 1""", (account_id,)).fetchone()
                if outstanding:
                    raise JournalRejected("Outstanding order requires reconciliation")
                db.execute("""INSERT INTO orders(idempotency_key,account_id,signal_id,
                    status,created_at,updated_at) VALUES(?,?,?,'RESERVED',?,?)""",
                    (token, account_id, signal_id, now, now))
                db.commit()
            except sqlite3.IntegrityError:
                raise JournalRejected("Duplicate order or signal") from None
        return token

    def mark_submitting(self, key: str) -> None:
        self._transition(key, "RESERVED", "SUBMITTING")

    def mark_unknown(self, key: str) -> None:
        self._transition(key, "SUBMITTING", "UNKNOWN")

    def mark_acknowledged(self, key: str) -> None:
        self._transition(key, "SUBMITTING", "ACKNOWLEDGED")

    def mark_rejected(self, key: str) -> None:
        self._transition(key, "RESERVED", "REJECTED")

    def _transition(self, key: str, expected: str, target: str) -> None:
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            changed = db.execute("""UPDATE orders SET status=?,updated_at=?
                WHERE idempotency_key=? AND status=?""",
                (target, int(time.time()), key, expected)).rowcount
            if changed != 1:
                raise JournalRejected("Unexpected order state; manual reconciliation required")
            db.commit()

    def get_status(self, key: str) -> str | None:
        with self._connect() as db:
            row = db.execute("SELECT status FROM orders WHERE idempotency_key=?",
                             (key,)).fetchone()
            return row[0] if row else None
