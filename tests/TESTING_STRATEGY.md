# Testing Strategy

## Overview

SafeRoute has two testable units with different risk profiles:

- **`vicroads_guardrails` package** — pure Python, no I/O, deterministic. Risk: missed PII reaching the LLM.
- **FastAPI app** — async HTTP handler, depends on database, LLM network calls. Risk: auth bypass, incorrect request lifecycle.

Each unit uses a different testing strategy chosen to match its failure modes.

---

## Strategies Considered

| Strategy | Description | Pros | Cons |
|---|---|---|---|
| **Unit tests (pure)** | Test functions in isolation, no I/O | Fast, deterministic, catches logic bugs | Can't verify integration between components |
| **Integration tests (real DB)** | Run against real SQLite in-memory | Catches schema mismatches, real query behaviour | Slower, needs DB setup |
| **Contract / snapshot tests** | Assert exact output text | Pinpoints regressions to the character | Brittle — any refactor breaks them |
| **Parametric corpus tests** | Labelled dataset of TP/TN/FP/FN, run all | Measures F1, honest about false positives | Separate from pytest run, needs curation |
| **End-to-end tests (real LLM)** | Hit the real OpenRouter API | Proves full stack works | Non-deterministic, costs money, needs live key |
| **ASGI transport tests** | Full FastAPI app over `httpx.ASGITransport`, mock LLM | Tests auth, middleware, DB together; no network | Slightly more complex fixture setup |

---

## Strategies Selected

### `vicroads_guardrails` — Unit + Parametric Corpus

**Files:** `tests/test_redactor.py`, `tests/test_auditor.py`, `benchmarks/test_pii_accuracy.py`

**Chosen strategy: Unit tests with adversarial inputs + parametric accuracy corpus**

The redaction pipeline is pure Python with no side effects. Unit tests verify each entity type and edge case directly against `_redact_text()` and `redact_messages()`.

A separate parametric corpus (`benchmarks/`) runs 103 labelled entries and computes precision/recall/F1 per entity type. This is **not** part of the default `pytest` run (`testpaths = ["tests"]`) — it is run explicitly and its results are committed as `benchmarks/ACCURACY_REPORT.md`. This separation is intentional: unit tests enforce regressions; the corpus measures true accuracy including known gaps.

**Why not snapshot tests?** The redacted output text is deterministic today but the exact placeholder strings could change. F1 against TP/TN labels is more meaningful than exact-string matching.

**Why not end-to-end?** The guardrails package has no network dependency. Testing it end-to-end would add noise (LLM non-determinism) to a deterministic function.

---

### FastAPI app — ASGI Transport + Mocked LLM

**Files:** `tests/test_pii_guarantee.py`

**Chosen strategy: Full ASGI integration with mocked LLM and in-memory SQLite**

```python
# transport exercises all FastAPI layers: routing, auth, middleware, DB
transport=ASGITransport(app=app)

# mocked LLM: no network, captures what was actually forwarded
patch("litellm.acompletion", new=_make_fake_llm(captured))

# in-memory SQLite: real schema, real queries, no file system
await init_db("sqlite+aiosqlite:///:memory:")
```

This tests the entire request lifecycle — auth, token budget, PII redaction, background audit write, response — without making any network calls. The mock LLM captures the exact messages forwarded to `acompletion()`, allowing assertions that PII was removed **before the HTTP packet was built**, not just in the response.

**Why mock the LLM but not the DB?** LLM responses are non-deterministic and cost money. The DB is deterministic and must be tested with its real schema to catch migration issues. This is the opposite of a typical mock-everything unit test.

**Why not real LLM integration tests?** Covered by manual end-to-end testing documented in `tests/E2E_test.md`. Automated tests with real LLM calls are non-deterministic and would make CI flaky.

---

## Coverage Targets

Run: `uv run pytest tests/ --cov=vicroads_guardrails --cov=app --cov-report=term-missing`

| Package | Current | Target |
|---|---|---|
| `vicroads_guardrails` | ~99% | ≥ 95% |
| `app` | ~92% | ≥ 90% |
| **Combined** | **94.9%** | **≥ 90%** |

The three uncovered lines in `app` are the lifespan startup/shutdown handlers and the `/metrics` endpoint — all exercised by Docker integration, not unit tests. This gap is acceptable.

---

## Running Tests

```bash
# Unit + integration tests (CI default)
uv run pytest tests/ -v

# With coverage
uv run pytest tests/ --cov=vicroads_guardrails --cov=app --cov-report=term-missing

# PII accuracy corpus (benchmark suite — not in CI)
uv run pytest benchmarks/ -v

# Generate accuracy report to ACCURACY_REPORT.md
uv run python benchmarks/test_pii_accuracy.py
```
