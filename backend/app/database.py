"""Database connection helpers for the SQLite development and Neon production stores.

The production adapter intentionally covers the small SQLite SQL surface used by
AgentForge. It keeps older feature modules working while they move to explicit
PostgreSQL queries. DATABASE_URL is only read by the backend process.
"""
from __future__ import annotations

import os
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any


class HybridRow:
    """A result row addressable by either column name or SQLite-style index."""

    def __init__(self, names: tuple[str, ...], values: tuple[Any, ...]):
        self._names = names
        self._values = values
        self._mapping = dict(zip(names, values))

    def __getitem__(self, key):
        return self._values[key] if isinstance(key, int) else self._mapping[key]

    def __iter__(self):
        return iter(self._values)

    def __len__(self):
        return len(self._values)

    def keys(self):
        return self._mapping.keys()


def _row_factory(cursor):
    names = tuple(col.name for col in cursor.description)
    return lambda values: HybridRow(names, values)


class PostgresConnection:
    def __init__(self, connection):
        self._connection = connection

    @property
    def closed(self):
        return self._connection.closed

    def execute(self, sql: str, params=()):
        sql = _translate_sql(sql)
        return self._connection.execute(sql, tuple(params or ()))

    def executemany(self, sql: str, seq_of_params):
        return self._connection.executemany(_translate_sql(sql), seq_of_params)

    def commit(self):
        self._connection.commit()

    def rollback(self):
        self._connection.rollback()

    def close(self):
        self._connection.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type is None:
                self.commit()
            else:
                self.rollback()
        finally:
            self.close()


def _translate_sql(sql: str) -> str:
    """Translate the handful of SQLite-only statements used in app modules."""
    statement = sql.strip()
    lowered = statement.lower()
    if lowered.startswith("pragma table_info(") and statement.endswith(")"):
        table = statement[statement.find("(") + 1:-1].strip().strip('"`[]')
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table):
            raise ValueError("Unsupported table metadata query")
        return ("SELECT ordinal_position - 1 AS cid, column_name AS name, data_type AS type, "
                "(is_nullable = 'NO') AS notnull, column_default AS dflt_value, "
                "ordinal_position AS pk FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name = %s "
                "ORDER BY ordinal_position").replace("%s", "'" + table + "'", 1)
    if "sqlite_master" in lowered:
        return ("SELECT table_name AS name FROM information_schema.tables "
                "WHERE table_schema = current_schema() AND table_type = 'BASE TABLE'")
    statement = re.sub(r"\bBEGIN\s+IMMEDIATE\b", "BEGIN", statement, flags=re.I)
    statement = re.sub(r"\bINSERT\s+OR\s+IGNORE\s+INTO\b", "INSERT INTO", statement, flags=re.I)
    if lowered.startswith("insert or ignore into") and "on conflict" not in lowered:
        statement = statement.rstrip(";") + " ON CONFLICT DO NOTHING"
    if re.match(r"(?is)^\s*INSERT\s+OR\s+REPLACE\s+INTO\s+yt_settings\s*\(", statement):
        statement = re.sub(r"(?i)^\s*INSERT\s+OR\s+REPLACE\s+INTO", "INSERT INTO", statement)
        statement = statement.rstrip(";") + (
            " ON CONFLICT (id) DO UPDATE SET access_token=EXCLUDED.access_token, "
            "refresh_token=EXCLUDED.refresh_token, expires_at=EXCLUDED.expires_at, "
            "channel_title=EXCLUDED.channel_title, channel_id=EXCLUDED.channel_id"
        )
    statement = re.sub(r"\bMIN\(([^(),]+),\s*([^()]+)\)", r"LEAST(\1, \2)", statement, flags=re.I)
    statement = re.sub(r"\bLIMIT\s+-1\s+OFFSET\s+", "OFFSET ", statement, flags=re.I)
    statement = statement.replace("?", "%s")
    statement = re.sub(r"\bBLOB\b", "BYTEA", statement, flags=re.I)
    return statement


def _postgres_dsn() -> str:
    dsn = os.getenv("DATABASE_URL", "").strip()
    if not dsn:
        if os.getenv("RENDER", "").lower() == "true" and os.getenv("DATABASE_REQUIRED", "true").lower() == "true":
            raise RuntimeError("DATABASE_URL is required for the deployed AgentForge workspace.")
        return ""
    if not dsn.startswith(("postgres://", "postgresql://")) or "sslmode=disable" in dsn.lower():
        raise RuntimeError("DATABASE_URL must be a TLS-protected PostgreSQL URL.")
    return dsn


@contextmanager
def connect(database_path: Path):
    dsn = _postgres_dsn()
    if dsn:
        import psycopg
        with psycopg.connect(dsn, connect_timeout=8, row_factory=_row_factory) as raw:
            yield PostgresConnection(raw)
        return
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database_path, timeout=15) as raw:
        raw.row_factory = sqlite3.Row
        yield raw


def is_postgres() -> bool:
    return bool(os.getenv("DATABASE_URL", "").strip())


def integrity_error_types():
    if is_postgres():
        import psycopg
        return (psycopg.IntegrityError,)
    return (sqlite3.IntegrityError,)
