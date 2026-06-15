from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String


class _Base(DeclarativeBase):
    pass


class AuditLog(_Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(36), index=True)
    timestamp: Mapped[str] = mapped_column(DateTime(timezone=True))
    developer_id: Mapped[str] = mapped_column(String(256), index=True)
    model: Mapped[str] = mapped_column(String(128))
    pii_detected: Mapped[bool] = mapped_column(Boolean)
    redacted_types: Mapped[list] = mapped_column(JSON)
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)
    cost_usd: Mapped[float] = mapped_column(Float)
    latency_ms: Mapped[float] = mapped_column(Float)
