"""PostgreSQL audit module safety tests (no external database required)."""
import os
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.neon_audit import _dsn, RiskAuditEvent


def test_missing_url_fails_closed():
    with patch.dict(os.environ, {"DATABASE_URL": ""}):
        with pytest.raises(HTTPException) as err:
            _dsn()
    assert err.value.status_code == 503


def test_non_postgres_url_fails_closed():
    with patch.dict(os.environ, {"DATABASE_URL": "sqlite:///tmp/a.db"}):
        with pytest.raises(HTTPException) as err:
            _dsn()
    assert err.value.status_code == 503


def test_valid_postgres_url():
    with patch.dict(os.environ, {"DATABASE_URL": "postgresql://example.invalid/db"}):
        assert _dsn().startswith("postgresql://")


def test_risk_event_has_no_order_fields():
    event = RiskAuditEvent(exchange="binance", symbol="BTCUSDT",
                           event_type="COOLDOWN", reason="Cooldown active")
    assert "quantity" not in event.model_dump()
    assert "order_id" not in event.model_dump()
