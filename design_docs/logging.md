# Logging System — Design

## Overview

SafeRoute uses **two complementary logging mechanisms** with different purposes, latencies, and retention characteristics:

```
Each request
     │
     ├─► stdout JSON log (synchronous, immediate)    logger.py
     │
     └─► SQLite audit record (async, non-blocking)   database.py + BackgroundTasks
```

---

## 1. Structured JSON Stdout Log

**File:** `vicroads_guardrails/logger.py`

Every completed request emits a single JSON line to stdout:

```json
{
  "timestamp":      "2025-01-15T09:23:41Z",
  "request_id":     "a3f2c1d0-...",
  "developer_id":   "dev-alice",
  "model":          "meta-llama/llama-3.1-8b-instruct:free",
  "pii_detected":   true,
  "redacted_types": ["REDACTED_VIC_DL", "REDACTED_EMAIL"],
  "tokens":         { "input": 42, "output": 187, "total": 229 },
  "cost_usd":       0.00023,
  "latency_ms":     312.4
}
```

### Design choices

- **One line per request** — trivially `grep`-able and compatible with any log aggregator (Splunk, CloudWatch, Datadog, Loki).
- **Structured keys** — downstream consumers can filter by `pii_detected`, `developer_id`, or `model` without parsing free text.
- **`request_id` (UUID4)** — correlates the log line with the audit DB row for forensic investigation.
- **Emitted synchronously before the response is returned** — the log line is guaranteed even if the DB write fails.

---

## 2. Async Audit Database

**Files:** `app/database.py`, `app/models/audit_log.py`

A full `AuditLog` row is written to SQLite (or PostgreSQL in production) via FastAPI's `BackgroundTasks`:

```python
background_tasks.add_task(write_audit, audit_record)
return response   # response is sent to developer immediately
```

The DB write happens **after** the HTTP response is delivered, so it never adds to perceived latency.

### Schema

| Column | Type | Purpose |
|---|---|---|
| `id` | UUID | Primary key |
| `timestamp` | DateTime | UTC request time |
| `developer_id` | String | Who made the call |
| `model` | String | Which model was used |
| `pii_detected` | Boolean | Quick compliance filter |
| `redacted_types` | JSON | Which PII types were found |
| `input_tokens` | Integer | Billing / capacity |
| `output_tokens` | Integer | Billing / capacity |
| `cost_usd` | Float | Governance |
| `latency_ms` | Float | Performance tracking |

### Why both systems?

| | Stdout JSON | Audit DB |
|---|---|---|
| Latency impact | Zero | Zero (background) |
| Survives app restart | Only if captured by a log driver | Yes |
| Queryable by SQL | No | Yes |
| Forwarded to SIEM | Yes (via Docker log driver) | Needs export job |
| Primary use | Real-time alerting, Splunk ingestion | Compliance reporting, forensics |

---

## Log Levels and Configuration

Controlled via `.env`:

```
LOG_LEVEL=INFO    # DEBUG | INFO | WARNING | ERROR | CRITICAL
LOG_FILE=app.log  # future file sink (currently stdout only)
```

The `saferoute` logger (`logging.getLogger("saferoute")`) is configured once at module import time and shared across all request handlers.
