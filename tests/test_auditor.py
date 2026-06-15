"""
Tests for the audit layer — AuditRecord schema (vicroads_guardrails)
and DB persistence (app.database).
Run: uv run pytest tests/test_auditor.py -v
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select

import app.database as _db
from app.database import init_db, write_audit
from app.models import AuditLog
from vicroads_guardrails.auditor import AuditRecord

_IN_MEMORY = "sqlite+aiosqlite:///:memory:"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_engine():
    """Reset module-level DB globals before and after every test."""
    _db._engine = None
    _db._AsyncSessionLocal = None
    yield
    _db._engine = None
    _db._AsyncSessionLocal = None


def _record(**overrides) -> AuditRecord:
    defaults = dict(
        developer_id="dev-test-001",
        model="gpt-3.5-turbo",
        pii_detected=True,
        redacted_types=["REDACTED_VIC_DL", "REDACTED_EMAIL"],
        input_tokens=25,
        output_tokens=40,
        cost_usd=0.000085,
        latency_ms=812.5,
    )
    return AuditRecord(**(defaults | overrides))


# ---------------------------------------------------------------------------
# AuditRecord — Pydantic schema (vicroads_guardrails.auditor)
# ---------------------------------------------------------------------------


class TestAuditRecord:
    def test_auto_generates_request_id(self):
        r = _record()
        assert r.request_id
        uuid.UUID(r.request_id)  # raises ValueError if not a valid UUID

    def test_two_records_have_different_request_ids(self):
        assert _record().request_id != _record().request_id

    def test_auto_generates_utc_timestamp(self):
        before = datetime.now(timezone.utc)
        r = _record()
        after = datetime.now(timezone.utc)
        assert before <= r.timestamp <= after

    def test_explicit_request_id_preserved(self):
        rid = str(uuid.uuid4())
        assert _record(request_id=rid).request_id == rid

    def test_no_pii_record(self):
        r = _record(pii_detected=False, redacted_types=[])
        assert not r.pii_detected
        assert r.redacted_types == []


# ---------------------------------------------------------------------------
# init_db — startup lifecycle (app.database)
# ---------------------------------------------------------------------------


class TestInitDb:
    @pytest.mark.anyio
    async def test_sets_engine_and_session_factory(self):
        await init_db(_IN_MEMORY)
        assert _db._engine is not None
        assert _db._AsyncSessionLocal is not None

    @pytest.mark.anyio
    async def test_idempotent(self):
        """create_all is safe to call twice — must not raise."""
        await init_db(_IN_MEMORY)
        await init_db(_IN_MEMORY)

    @pytest.mark.anyio
    async def test_creates_audit_logs_table(self):
        await init_db(_IN_MEMORY)
        async with _db._AsyncSessionLocal() as session:
            count = (
                await session.execute(select(func.count()).select_from(AuditLog))
            ).scalar()
        assert count == 0


# ---------------------------------------------------------------------------
# write_audit — persistence (app.database)
# ---------------------------------------------------------------------------


class TestWriteAudit:
    @pytest.mark.anyio
    async def test_persists_all_fields(self):
        await init_db(_IN_MEMORY)
        rec = _record()
        await write_audit(rec)

        async with _db._AsyncSessionLocal() as session:
            row = (await session.execute(select(AuditLog))).scalar_one()

        assert row.request_id == rec.request_id
        assert row.developer_id == "dev-test-001"
        assert row.model == "gpt-3.5-turbo"
        assert row.pii_detected is True
        assert row.redacted_types == ["REDACTED_VIC_DL", "REDACTED_EMAIL"]
        assert row.input_tokens == 25
        assert row.output_tokens == 40
        assert abs(row.cost_usd - 0.000085) < 1e-9
        assert abs(row.latency_ms - 812.5) < 0.01

    @pytest.mark.anyio
    async def test_multiple_records_stored_independently(self):
        await init_db(_IN_MEMORY)
        await write_audit(_record(developer_id="dev-a"))
        await write_audit(_record(developer_id="dev-b"))
        await write_audit(_record(developer_id="dev-a"))

        async with _db._AsyncSessionLocal() as session:
            count = (
                await session.execute(select(func.count()).select_from(AuditLog))
            ).scalar()
        assert count == 3

    @pytest.mark.anyio
    async def test_no_pii_record_stored_correctly(self):
        await init_db(_IN_MEMORY)
        await write_audit(_record(pii_detected=False, redacted_types=[]))

        async with _db._AsyncSessionLocal() as session:
            row = (await session.execute(select(AuditLog))).scalar_one()

        assert row.pii_detected is False
        assert row.redacted_types == []

    @pytest.mark.anyio
    async def test_each_record_gets_unique_request_id(self):
        await init_db(_IN_MEMORY)
        await write_audit(_record())
        await write_audit(_record())

        async with _db._AsyncSessionLocal() as session:
            rows = (await session.execute(select(AuditLog))).scalars().all()

        assert rows[0].request_id != rows[1].request_id

    @pytest.mark.anyio
    async def test_raises_if_not_initialised(self):
        with pytest.raises(RuntimeError, match="Database not initialised"):
            await write_audit(_record())
