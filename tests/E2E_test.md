# End-to-End PII Guarantee Test Design

**File:** `tests/test_pii_guarantee.py`  
**Status:** Implemented — 15 tests, all passing  
**Last updated:** June 2026

---

## 1. The Testing Problem

The compliance guarantee this project makes is precise:

> Raw citizen PII must never appear in the arguments passed to `litellm.acompletion()`.

This is not "the response looks clean" — it is "the data was already gone before the HTTP packet was built." These are structurally different claims and require different test strategies.

`test_redactor.py` proves the detector works in isolation:
```python
assert "[REDACTED_VIC_DL]" in _redact_text("licence 123456789").text
```

That is necessary but not sufficient. It does not prove:

- The route handler actually calls `redact_messages()` before `acompletion()`
- The cleaned messages — not the raw ones — are what gets forwarded
- The pipeline is wired correctly end to end: auth → budget → redact → forward → audit

`test_pii_guarantee.py` proves all of the above by intercepting the call at the LLM boundary and inspecting what arrived there.

---

## 2. Testing Strategy — Three Layers

```
test_redactor.py          Unit layer
  └── Does this pattern detect this input?
  └── No HTTP, no DB, no LiteLLM
  └── 27 tests, fast (~1s)

test_auditor.py           Integration layer
  └── Does the DB write succeed with the right data?
  └── No HTTP, no LiteLLM, in-memory SQLite
  └── 13 tests, fast (~1s)

test_pii_guarantee.py     E2E compliance layer      ← this document
  └── Does the full pipeline: auth → redact → forward → audit?
  └── Full FastAPI app, mocked LiteLLM, in-memory SQLite
  └── 15 tests, moderate speed (~4s)

benchmarks/test_pii_accuracy.py   Accuracy layer    ← planned
  └── What fraction of real-world inputs are detected correctly?
  └── Precision / Recall / F1 per entity type
```

Each layer proves something the layer below it cannot.

---

## 3. Key Decisions

### Decision 1 — ASGI Transport, not a running server

**Options considered:**

| Approach | What it does | Verdict |
|---|---|---|
| `uvicorn` subprocess + `httpx.AsyncClient` | Starts a real server on a port | ❌ Slow startup, port conflicts, CI flaky |
| `TestClient` (Starlette sync) | Wraps the ASGI app synchronously | ❌ Cannot test async background tasks properly |
| `AsyncClient` + `ASGITransport` | Drives the ASGI app in-process, same event loop | ✅ Chosen |

```python
async with AsyncClient(
    transport=ASGITransport(app=app), base_url="http://test"
) as client:
    response = await client.post("/v1/chat/completions", ...)
```

**Why this works:** `ASGITransport` calls the FastAPI ASGI callable directly, bypassing TCP entirely. The entire request/response cycle — including Starlette middleware, dependency injection, background tasks — runs in the same Python process and event loop as the test. This makes it deterministic and fast.

**The non-obvious consequence:** `ASGITransport` does **not** send a `lifespan.startup` event to the app. FastAPI's `lifespan` context manager (which calls `init_db`) never fires. See Decision 4.

---

### Decision 2 — Mock `litellm.acompletion`, not the HTTP layer

**The assertion we need to make:**
```
PII does not appear in the messages argument passed to acompletion()
```

To make this assertion, we need to intercept the call at the Python function boundary — not at the HTTP level. Mocking the outbound HTTP to OpenRouter would prove nothing about what LiteLLM received.

```python
# What we patch
patch("litellm.acompletion", new=_make_fake_llm(captured))

# What the fake captures
async def _fake(**kwargs):
    captured.append([m["content"] for m in kwargs.get("messages", [])])
    ...
```

`captured[0]` after a request is the list of message content strings that the route handler actually forwarded. If `"123456789"` is not in that list, PII did not reach the LLM boundary.

**Why patch `litellm.acompletion` directly (not via the route module):**

The route does `import litellm` then calls `litellm.acompletion(...)`. Patching `litellm.acompletion` modifies the attribute on the litellm module object. Since the route holds a reference to the module (not the function), it will see the patched version. Patching `app.api.route_chat_completion_middleware.litellm.acompletion` would also work but is more fragile to refactoring.

**We also patch `litellm.token_counter`:**
```python
patch("litellm.token_counter", return_value=20)
```
Without this, `token_counter` makes a real call and may return a count above `llm_max_tokens`, causing 422 before the redaction step runs.

---

### Decision 3 — The fake LiteLLM response must be a real `ModelResponse`

The route contains:
```python
assert isinstance(response, ModelResponse), "expected non-streaming response"
```

A plain `MagicMock()` fails `isinstance`. The fake must return an actual `ModelResponse` (or subclass), otherwise the test fails at the assertion before reaching the audit step.

```python
from litellm import ModelResponse
from litellm.utils import Usage

async def _fake(**kwargs):
    captured.append([m["content"] for m in kwargs.get("messages", [])])
    r = ModelResponse(id="chatcmpl-test", choices=[], model="gpt-3.5-turbo")
    r.usage = Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    return r
```

`ModelResponse` inherits from `OpenAIObject` which inherits from `dict`. FastAPI can serialise it as JSON without additional configuration. `Usage` is constructed explicitly because `response.usage.prompt_tokens` is accessed in the route — `None` would cause a Pydantic validation error on `AuditRecord(input_tokens=None)`.

---

### Decision 4 — Initialise the database directly, not via lifespan

**The problem:** `ASGITransport` does not fire the ASGI lifespan. The `lifespan` context in `app/main.py` calls `init_db(settings.database_url)`. Without lifespan, `_db._engine` and `_db._AsyncSessionLocal` remain `None`.

The background task `write_audit()` checks:
```python
if _AsyncSessionLocal is None:
    raise RuntimeError("Database not initialised")
```

In test mode, this exception propagates back through the ASGI stack into `await client.post(...)`, causing the test to fail with a RuntimeError even though the PII assertion would have passed.

**The fix: initialise directly in the fixture.**

```python
@pytest.fixture
async def client():
    _db._engine = None
    _db._AsyncSessionLocal = None
    await _db.init_db("sqlite+aiosqlite:///:memory:")   # ← in-memory, per test

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c

    if _db._engine:
        await _db._engine.dispose()
    _db._engine = None
    _db._AsyncSessionLocal = None
```

**Why in-memory SQLite (`////:memory:`):** Each test gets a completely empty database. No state leaks between tests. No file cleanup needed. The `aiosqlite` driver supports in-memory databases with `sqlite+aiosqlite:///:memory:`.

**Why dispose the engine after the test:** SQLite in-memory databases are destroyed when the last connection closes. Calling `engine.dispose()` closes the connection pool cleanly, preventing "database is locked" warnings in subsequent tests.

---

### Decision 5 — Fixture scoping: per-test, not per-session

**`client` fixture scope:** function (default). Each test gets a fresh database and a fresh `AsyncClient`. This costs ~250ms per test but eliminates all inter-test state.

**`captured` fixture scope:** function. A new `[]` list per test. Without this, message captures from test N would appear in test N+1's assertions.

**`mock_llm` fixture depends on `captured`:** pytest resolves shared fixture instances within the same test. Both `mock_llm` and the test method receive the same `captured` list instance, so the fake LLM writes into the same list the test reads from.

```python
@pytest.fixture
def captured() -> list[list[str]]:
    return []

@pytest.fixture
def mock_llm(captured):          # receives the same captured as the test
    with patch("litellm.acompletion", new=_make_fake_llm(captured)):
        yield
```

---

### Decision 6 — Assert absence of PII, not presence of redaction token

The primary assertion in every PII test is:

```python
assert all("123456789" not in c for c in captured[0])
```

Not:
```python
assert any("[REDACTED_VIC_DL]" in c for c in captured[0])
```

Both assertions are present in the tests — but they prove different things:

| Assertion | What it proves | What it misses |
|---|---|---|
| PII string absent from forwarded messages | The raw value never reached the LLM boundary | Does not confirm replacement happened (could be deletion) |
| Redaction token present in forwarded messages | The replacement is correct | Does not confirm the original was removed |

Both together prove: the PII was replaced, not deleted, and the replacement is syntactically correct. Running only the second assertion would pass even if the redactor had a bug that left both the original value and the token in the output.

---

## 4. Test Class Breakdown

### `TestPIIGuarantee` — 10 tests

Each test sends one request containing a known PII value and asserts it is absent from `captured[0]` (the messages forwarded to the mocked LLM).

| Test | PII type | Detection layer | Key edge case |
|---|---|---|---|
| `test_vic_dl_numeric_never_reaches_llm` | `VIC_DL` | Regex | 9-digit numeric |
| `test_vic_dl_alpha_never_reaches_llm` | `VIC_DL` | Regex | Alpha prefix `A12345678` |
| `test_email_never_reaches_llm` | `EMAIL` | Regex | Standard address |
| `test_au_phone_never_reaches_llm` | `AU_PHONE` | Regex | Mobile `04xx xxx xxx` |
| `test_medicare_never_reaches_llm` | `MEDICARE` | Regex | Leading digit `2–6` constraint |
| `test_street_address_never_reaches_llm` | `ADDRESS` | Regex | Number + street type |
| `test_person_name_never_reaches_llm` | `PERSON` | SpaCy NER | `en_core_web_sm` |
| `test_pii_in_system_role_also_redacted` | `EMAIL` | Regex | System message, not just user |
| `test_multiple_pii_types_all_redacted` | Mixed | Regex | 4 PII types in one message |
| `test_clean_message_passes_through_unchanged` | None | — | Exact string equality |

The system-role test is deliberately included because a naïve implementation might only redact `user` messages. `redact_messages()` iterates all roles.

The clean message test uses `assert captured[0][0] == text` — exact equality, not substring. If the redactor modifies clean text (over-redaction), this test fails.

### `TestGatewayGuards` — 5 tests

These test the HTTP-layer enforcement that fires before any redaction or LLM call.

| Test | Expected code | What it proves |
|---|---|---|
| `test_missing_auth_header_returns_401` | 401 | `APIKeyHeader` returns 401 (not 403) for absent header |
| `test_invalid_token_prefix_returns_403` | 403 | `validate_developer_token` rejects non-`dev-` prefix |
| `test_prompt_too_long_returns_422` | 422 | Token preflight fires before redaction |
| `test_budget_exceeded_returns_402` | 402 | Daily spend check fires before redaction |
| `test_health_endpoint_always_available` | 200 | `/health` has no auth requirement |

**Non-obvious finding:** FastAPI's `APIKeyHeader` returns **401** when the header is absent, not 403. It returns 403 only when the header is present but rejected by the dependency. The distinction matters for client error handling.

---

## 5. Background Task Behaviour in ASGI Tests

FastAPI's `BackgroundTasks` run **after** the response is sent. In production, this means the audit DB write is non-blocking. In ASGI test mode, `ASGITransport` runs the complete ASGI lifecycle — including background tasks — before returning from `await client.post(...)`.

This means:
- The response is received
- All background tasks (including `write_audit`) complete
- Control returns to the test

DB assertions can be made immediately after `await client.post(...)` without any `asyncio.sleep` or polling. This is a useful property of in-process ASGI testing that does not hold for tests against a real running server.

---

## 6. What This Suite Cannot Prove

These are the known limitations, each addressed by a separate testing layer:

| Claim | Where tested | Status |
|---|---|---|
| VIC DL regex has zero false-positives on 9-digit non-DL strings | `benchmarks/test_pii_accuracy.py` | 🔲 Not yet built |
| SpaCy NER recall rate for person names across varied inputs | `benchmarks/test_pii_accuracy.py` | 🔲 Not yet built |
| PII embedded in JSON or code blocks is detected | Not tested anywhere | Gap |
| Concurrent requests do not leak PII between sessions | Load test (Locust) | 🔲 Not yet built |
| Gateway latency overhead at P95 | Benchmark (Locust + mock) | 🔲 Not yet built |

The E2E compliance tests prove the pipeline is wired correctly on specific known inputs. The accuracy benchmark (§4.6 in `README.md`) proves the detection rates across a representative corpus including adversarial negatives.
