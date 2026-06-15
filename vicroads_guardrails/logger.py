from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from typing import Any

_logger = logging.getLogger("saferoute")
_logger.setLevel(logging.INFO)

if not _logger.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter("%(message)s"))
    _logger.addHandler(_handler)


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def log_request(
    *,
    developer_id: str,
    model: str,
    pii_detected: bool,
    redacted_types: list[str],
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    latency_ms: float,
    extra: dict[str, Any] | None = None,
) -> None:
    record: dict[str, Any] = {
        "timestamp":      _now_iso(),
        "request_id":     str(uuid.uuid4()),
        "developer_id":   developer_id,
        "model":          model,
        "pii_detected":   pii_detected,
        "redacted_types": redacted_types,
        "tokens": {
            "input":  input_tokens,
            "output": output_tokens,
            "total":  input_tokens + output_tokens,
        },
        "cost_usd":    round(cost_usd, 8),
        "latency_ms":  round(latency_ms, 2),
    }
    if extra:
        record.update(extra)
    _logger.info(json.dumps(record))


# Per-token pricing table (USD per 1 000 tokens)
_PRICE_PER_1K: dict[str, tuple[float, float]] = {
    "gpt-3.5-turbo":                        (0.0005,  0.0015),
    "gpt-4o":                               (0.005,   0.015),
    "claude-haiku-4-5-20251001":            (0.001,   0.005),
    "google/gemma-4-27b-it:free":           (0.0,     0.0),
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    key = model.split("/")[-1]  # strip provider prefix
    prices = _PRICE_PER_1K.get(key, (0.001, 0.003))  # sane default
    return (input_tokens * prices[0] + output_tokens * prices[1]) / 1000
