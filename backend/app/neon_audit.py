"""Optional Neon-backed audit store. Never places or authorizes exchange orders.

Only activates when DATABASE_URL is configured. Existing SQLite-backed app
operations remain unchanged until separately migrated and tested.
"""
import os
import uuid
from contextlib import contextmanager

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/trading/audit", tags=["Trading Audit"])


def _dsn():
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        raise HTTPException(503, "PostgreSQL audit storage is not configured.")
    if not url.startswith(("postgresql://", "postgres://")):
        raise HTTPException(503, "DATABASE_URL must be a PostgreSQL connection URL.")
    return url


@contextmanager
def _connection():
    try:
        import psycopg
        with psycopg.connect(_dsn(), connect_timeout=5, autocommit=False) as conn:
            yield conn
    except HTTPException:
        raise
    except Exception as exc:
        # Never include the connection string, credentials, or SQL in errors.
        raise HTTPException(503, "PostgreSQL audit storage is unavailable.") from None


class RiskAuditEvent(BaseModel):
    exchange: str | None = Field(default=None, pattern="^(binance|bybit)$")
    symbol: str | None = Field(default=None, max_length=20, pattern="^[A-Z0-9]+$")
    event_type: str = Field(min_length=3, max_length=80)
    reason: str = Field(min_length=3, max_length=500)


@router.get("/health")
def audit_health():
    """Authenticated read-only connectivity and migration check."""
    with _connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT to_regclass('agentforge.risk_events') IS NOT NULL, "
                "to_regclass('agentforge.order_intents') IS NOT NULL"
            )
            risk_ready, orders_ready = cur.fetchone()
    return {
        "connected": True,
        "schema_ready": bool(risk_ready and orders_ready),
        "storage": "postgresql",
        "live_trading_enabled_by_this_module": False,
    }


@router.post("/risk-events", status_code=201)
def record_risk_event(event: RiskAuditEvent):
    """Persist a manually supplied audit event, not an order or approval."""
    ident = uuid.uuid4()
    with _connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO agentforge.risk_events "
                "(id,exchange,symbol,event_type,reason) "
                "VALUES (%s,%s,%s,%s,%s)",
                (ident, event.exchange, event.symbol, event.event_type, event.reason),
            )
    return {"id": str(ident), "recorded": True, "live_order_placed": False}
