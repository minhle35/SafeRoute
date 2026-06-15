from __future__ import annotations


from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.models import AuditLog, _Base

from vicroads_guardrails.auditor import AuditRecord

# ── Module-level engine — set by init_db() at app startup ─────────────────────
_engine: AsyncEngine | None = None
_AsyncSessionLocal: async_sessionmaker[AsyncSession] | None = None


async def init_db(database_url: str) -> None:
    """Create engine, session factory, and DDL. Call once on app startup."""
    global _engine, _AsyncSessionLocal
    _engine = create_async_engine(database_url, echo=False)
    _AsyncSessionLocal = async_sessionmaker(_engine, expire_on_commit=False)
    async with _engine.begin() as conn:
        await conn.run_sync(_Base.metadata.create_all)


async def write_audit(record: AuditRecord) -> None:
    """Persist one audit record. Designed to be called via BackgroundTasks."""
    if _AsyncSessionLocal is None:
        raise RuntimeError("Database not initialised — call init_db() at startup")
    async with _AsyncSessionLocal() as session:
        session.add(
            AuditLog(
                request_id=record.request_id,
                timestamp=record.timestamp,
                developer_id=record.developer_id,
                model=record.model,
                pii_detected=record.pii_detected,
                redacted_types=record.redacted_types,
                input_tokens=record.input_tokens,
                output_tokens=record.output_tokens,
                cost_usd=record.cost_usd,
                latency_ms=record.latency_ms,
            )
        )
        await session.commit()
