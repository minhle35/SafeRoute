# vicroads_guardrails — Package Design

## Purpose

`vicroads_guardrails` is an internal Python package that enforces PII redaction before any prompt reaches a Large Language Model. It is the primary compliance control in the SafeRoute gateway: no citizen data ever leaves the local process.

It is deliberately a **standalone package**, not embedded in the FastAPI app, so it can be:
- Imported and tested in complete isolation from the web layer
- Audited independently (a compliance team reviews one package, not an entire server)
- Reused by other VicRoads tooling without pulling in FastAPI dependencies

---

## Two-Pass Redaction Pipeline

Every message passes through two sequential layers before being forwarded.

```
raw message content
       │
       ▼
┌─────────────────────────────────────┐
│  Pass 1 — Deterministic Regex       │  patterns.py
│                                     │
│  VIC_DL  → [REDACTED_VIC_DL]       │
│  MEDICARE → [REDACTED_MEDICARE]     │
│  AU_PHONE → [REDACTED_PHONE]        │
│  EMAIL    → [REDACTED_EMAIL]        │
│  ADDRESS  → [REDACTED_ADDRESS]      │
│  VIC_PLATE → [REDACTED_PLATE]       │
└────────────────┬────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────┐
│  Pass 2 — SpaCy NER                 │  redactor.py
│  (en_core_web_sm, loaded once)      │
│                                     │
│  PERSON  → [REDACTED_NAME]          │
│  GPE/LOC → [REDACTED_LOCATION]      │
│  ORG     → [REDACTED_ORG]           │
│  DATE    → [REDACTED_DATE]          │
└────────────────┬────────────────────┘
                 │
                 ▼
          redacted message
```

### Why two passes?

| Layer | Catches | Miss rate | Speed |
|---|---|---|---|
| Regex only | Structured tokens (DL, Medicare, phone, email) | High for freeform names/places | ~0.1 ms |
| NER only | Names, locations, organisations | High for structured tokens (no training data) | 80–150 ms |
| Both (sequential) | Structured + freeform | Lowest achievable | 80–150 ms total |

Regex runs **first**: it produces zero false positives for the patterns it covers, eliminates those tokens before NER even sees them, and prevents NER from mis-classifying a redacted placeholder.

### Pass 1 — Pattern ordering

Patterns in `PATTERNS` are ordered most-specific first to prevent shorter patterns from consuming part of a longer token:

```
VIC_DL → MEDICARE → AU_PHONE → EMAIL → ADDRESS → VIC_PLATE
```

VIC_DL (9 digits) must precede MEDICARE (10 digits starting 2–6) because a 10-digit Medicare number's last 9 digits would otherwise match VIC_DL first.

### Pass 2 — SpaCy optimisations

- Model loaded once with `@lru_cache(maxsize=1)` — the 12 MB model is not reloaded per request.
- `parser` and `lemmatizer` disabled at load time — they are not needed for NER and add latency.
- Entities iterated in **reverse character order** so substitutions don't shift offsets for earlier entities.
- Bare-digit DATE entities are skipped: SpaCy labels standalone numbers (e.g. `2024`) as `DATE`, but those are reference IDs, not dates. Real dates contain letters, slashes, or hyphens.

---

## Public API

```python
from vicroads_guardrails.redactor import redact_messages, _redact_text

# Batch redaction — used by the gateway
clean_messages, redacted_types = redact_messages(messages_dicts)

# Single-string redaction — used by benchmarks
result = _redact_text("My licence is 123456789 and email is a@b.com")
result.text           # "[REDACTED_VIC_DL] and email is [REDACTED_EMAIL]"
result.redacted_types # ["REDACTED_VIC_DL", "REDACTED_EMAIL"]
result.pii_detected   # True
```

`redact_messages` mutates message dicts in-place and returns the list alongside a deduplicated list of all tags found. This is the only function the FastAPI layer calls.

---

## Why a Separate Package (not middleware)?

LiteLLM's `async_pre_call_hook` only fires in **Proxy mode** (the LiteLLM CLI server). SafeRoute uses the **LiteLLM SDK** (`litellm.acompletion()`), where hooks never fire. Embedding redaction in FastAPI middleware would run it on all routes including `/health` and `/metrics`. The package-function pattern is explicit, testable, and fires at exactly the right point in the request lifecycle.

```python
# route_chat_completion_middleware.py — step 3
clean_messages, redacted_types = redact_messages(messages_dicts)

# step 4 — LiteLLM never sees raw PII
response = await litellm.acompletion(model=..., messages=clean_messages, ...)
```
