"""PostgreSQL-backed MT5 demo order coordination.

No broker requests or autonomous execution. Fail closed when DATABASE_URL is absent.
"""
from __future__ import annotations
import os
import uuid
from decimal import Decimal, InvalidOperation
from datetime import date
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
CREATE TABLE IF NOT EXISTS mt5_demo_daily_equity (
 account_id text NOT NULL, trading_day date NOT NULL,
 start_equity numeric NOT NULL CHECK (start_equity > 0),
 currency text NOT NULL, recorded_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY (account_id, trading_day)
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

    def safety_snapshot(self, account_id: str) -> dict:
        """Read-only, account-scoped controls and unresolved-order counts."""
        if not account_id:
            raise ValueError("Account required")
        with self._connection() as conn:
            row = conn.execute(
                "SELECT halted,updated_at FROM mt5_demo_controls WHERE account_id=%s",
                (account_id,)).fetchone()
            pending = conn.execute("""SELECT count(*) FROM mt5_demo_orders
              WHERE account_id=%s AND status IN
              ('RESERVED','SUBMITTING','UNKNOWN','ACKNOWLEDGED')""",
              (account_id,)).fetchone()
        return {
            "emergency_stop_active": row is None or row[0] is not False,
            "emergency_stop_record_exists": row is not None,
            "emergency_stop_updated_at": row[1].isoformat() if row else None,
            "unresolved_order_count": int(pending[0]) if pending else 0,
        }

    def record_daily_equity_baseline(self, account_id: str, trading_day: date,
                                     equity: str, currency: str) -> dict:
        """Immutable first snapshot for UTC trading day; never overwrite baseline.

        Caller MUST independently verify equity/currency against fresh DEMO
        broker account data. This method does not fetch or infer broker data.
        """
        if not account_id or not isinstance(trading_day, date) or isinstance(trading_day, __import__("datetime").datetime):
            raise ValueError("Valid account and date required")
        if not isinstance(currency, str) or not currency.isalpha() or len(currency) != 3:
            raise ValueError("Valid account currency required")
        try:
            value = Decimal(str(equity))
        except (InvalidOperation, ValueError):
            raise ValueError("Invalid equity") from None
        if not value.is_finite() or value <= 0:
            raise ValueError("Positive finite equity required")
        with self._connection() as conn:
            conn.execute("""INSERT INTO mt5_demo_daily_equity
                (account_id,trading_day,start_equity,currency)
                VALUES (%s,%s,%s,%s)
                ON CONFLICT (account_id,trading_day) DO NOTHING""",
                (account_id,trading_day,value,currency.upper()))
            row = conn.execute("""SELECT start_equity,currency,recorded_at
                FROM mt5_demo_daily_equity
                WHERE account_id=%s AND trading_day=%s""",
                (account_id,trading_day)).fetchone()
        if row[1] != currency.upper():
            raise DurableJournalUnavailable("Account currency changed; risk baseline blocked")
        return {"trading_day":trading_day.isoformat(),"start_equity":str(row[0]),
                "currency":row[1],"recorded_at":row[2].isoformat()}

    def daily_equity_baseline(self, account_id: str, trading_day: date) -> dict | None:
        if not account_id or not isinstance(trading_day,date):
            raise ValueError("Valid account and date required")
        with self._connection() as conn:
            row = conn.execute("""SELECT start_equity,currency,recorded_at
                FROM mt5_demo_daily_equity
                WHERE account_id=%s AND trading_day=%s""",
                (account_id,trading_day)).fetchone()
        if row is None:
            return None
        return {"trading_day":trading_day.isoformat(),"start_equity":str(row[0]),
                "currency":row[1],"recorded_at":row[2].isoformat()}

    def unresolved_orders(self, account_id: str) -> list[dict]:
        """Read-only pending journal records; never resolve from an empty snapshot."""
        if not account_id:
            raise ValueError("Account required")
        with self._connection() as conn:
            rows = conn.execute("""SELECT idempotency_key,signal_id,status,created_at,updated_at
                FROM mt5_demo_orders WHERE account_id=%s
                AND status IN ('RESERVED','SUBMITTING','UNKNOWN','ACKNOWLEDGED')
                ORDER BY created_at LIMIT 100""", (account_id,)).fetchall()
        return [{"idempotency_key":str(r[0]),"signal_id":r[1],
                 "status":r[2],"created_at":r[3].isoformat(),
                 "updated_at":r[4].isoformat()} for r in rows]
