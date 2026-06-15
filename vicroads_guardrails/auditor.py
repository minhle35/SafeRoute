from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field


class AuditRecord(BaseModel):
    """Compliance schema for one LLM request. Source of truth for callers.

    Built in the route handler and passed to app.database.write_audit().
    No DB dependency here — vicroads_guardrails stays infrastructure-free.
    """

    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    developer_id: str
    model: str
    pii_detected: bool
    redacted_types: list[str]
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: float
