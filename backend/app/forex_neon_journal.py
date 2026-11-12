"""PostgreSQL-backed MT5 demo order coordination.

No broker requests or autonomous execution. Fail closed when DATABASE_URL is absent.
"""
from __future__ import annotations
import os
import uuid
from contextlib import contextmanager
import psycopg

class DurableJournalUnavailable(RuntimeError):
    pass

SCHEMA = """
CREATE TABLE IF NOT EXISTS mt5_demo_controls (
 account_id text PRIMARY KEY,
 halted boolean NOT NULL DEFAULT true,
 updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS mt5_demo_orders (
 idempotency_key uuid PRIMARY KEY,
 account_id text NOT NULL,
 signal_id text NOT NULL,
 status text NOT NULL CHECK (status IN
  ('RESERVED','SUBMITTING','UNKNOWN','ACKNOWLEDGED','REJECTED','RECONCILED')),
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(account_id,signal_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS mt5_one_unresolved_order
 ON mt5_demo_orders(account_id)
 WHERE status IN ('RESERVED','SUBMITTING','UNKNOWN','ACKNOWLEDGED');
"""

class NeonDemoJournal:
    def __init__(self, dsn: str | None = None):
        self.dsn = dsn or os.getenv("DATABASE_URL")
        if not self.dsn or not self.dsn.startswith(("postgresql://", "postgres://")):
            raise DurableJournalUnavailable("PostgreSQL DATABASE_URL required")
        if "sslmode=disable" in self.dsn.lower():
            raise DurableJournalUnavailable("Database TLS must not be disabled")

    @contextmanager
    def _connection(self):
        try:
            with psycopg.connect(self.dsn, connect_timeout=8) as conn:
                yield conn
        except psycopg.Error as exc:
            raise DurableJournalUnavailable("Persistent MT5 journal unavailable") from exc

    def initialize(self):
        with self._connection() as conn:
            conn.execute(SCHEMA, prepare=False)

    def is_halted(self, account_id: str) -> bool:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT halted FROM mt5_demo_controls WHERE account_id=%s",
                (account_id,)).fetchone()
            return row is None or row[0] is not False

    def set_halted(self, account_id: str, halted: bool) -> None:
        if not account_id:
            raise ValueError("Account required")
        with self._connection() as conn:
            conn.execute("""INSERT INTO mt5_demo_controls(account_id,halted)
              VALUES(%s,%s) ON CONFLICT(account_id) DO UPDATE SET
              halted=EXCLUDED.halted,updated_at=now()""", (account_id, halted))

    def reserve(self, account_id: str, signal_id: str) -> str:
        if not account_id or not signal_id or len(signal_id) > 128:
            raise ValueError("Invalid signal identity")
        key = str(uuid.uuid4())
        with self._connection() as conn:
            # Account-scoped advisory lock prevents concurrent reservations.
            conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                         (account_id,))
            row = conn.execute(
                "SELECT halted FROM mt5_demo_controls WHERE account_id=%s FOR UPDATE",
                (account_id,)).fetchone()
            if row is None or row[0] is not False:
                raise DurableJournalUnavailable("Demo trading halted or uninitialized")
            pending = conn.execute("""SELECT 1 FROM mt5_demo_orders
              WHERE account_id=%s AND status IN
              ('RESERVED','SUBMITTING','UNKNOWN','ACKNOWLEDGED') LIMIT 1""",
              (account_id,)).fetchone()
            if pending:
                raise DurableJournalUnavailable("Unreconciled order exists")
            try:
                conn.execute("""INSERT INTO mt5_demo_orders
                  (idempotency_key,account_id,signal_id,status)
                  VALUES(%s,%s,%s,'RESERVED')""",
                  (key,account_id,signal_id))
            except psycopg.errors.UniqueViolation as exc:
                raise DurableJournalUnavailable("Duplicate signal or order") from exc
        return key

    def transition(self, key: str, expected: str, target: str) -> None:
        allowed = {("RESERVED","SUBMITTING"),("RESERVED","REJECTED"),
                   ("SUBMITTING","UNKNOWN"),("SUBMITTING","ACKNOWLEDGED"),
                   ("UNKNOWN","RECONCILED"),("ACKNOWLEDGED","RECONCILED")}
        if (expected,target) not in allowed:
            raise ValueError("Invalid journal transition")
        with self._connection() as conn:
            result = conn.execute("""UPDATE mt5_demo_orders SET status=%s,updated_at=now()
              WHERE idempotency_key=%s AND status=%s""", (target,key,expected))
            if result.rowcount != 1:
                raise DurableJournalUnavailable("Order state uncertain; reconcile first")
