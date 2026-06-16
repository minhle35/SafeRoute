# VicRoads Secure AI Gateway — Design Decision Document

**Document ID:** RLS-AI-000  
**Status:** Finalised  
**Author:** Ellie Le  
**Last Updated:** June 2026  
**Audience:** AI Enablement Team · Engineering Leads · Compliance Review

---

## 1. The Problem This Project Exists to Solve

VicRoads Registration and Licensing Services is scaling its digital transformation by encouraging software engineering teams to leverage Large Language Models. This creates an immediate and non-negotiable conflict.

Developers writing AI-assisted features reach for the simplest path: calling `api.openai.com` or `api.anthropic.com` directly. In most organisations, this is acceptable. At VicRoads, it is not.

Under the 40-year joint venture partnership between the Victorian State Government, Aware Super, Australian Retirement Trust, and Macquarie Asset Management, **the Victorian Government retains sole ownership, control, and statutory responsibility over citizen regulation, data integrity, and privacy provisions for Registration and Licensing Services.** This is not a policy preference. It is a structural legal obligation.

A developer who copies a licence number into a prompt and calls `api.openai.com` has, in that moment, transferred Victorian citizen data to a third-party server outside government control. The gateway exists to make that structurally impossible — without changing how developers write code.

---

## 2. The Three Highest-Priority Features

Out of all possible features for this system, three are load-bearing. Everything else is additive. If these three work correctly, the project fulfils its purpose. If any one fails, the project fails regardless of what else it does.

---

### Priority 1 — Zero-Trust PII Redaction (The Compliance Guarantee)

**Why this is first:**  
Every other feature — cost tracking, sandbox convenience, developer experience — is valuable but optional. PII redaction is the reason this project exists. Without it, a developer sending `"John Smith's licence is 999123456"` to the gateway is in exactly the same position as calling the public API directly. The redaction must be structurally guaranteed, not just tested.

**What it does:**  
Intercepts every inbound prompt in local server memory before LiteLLM constructs an outbound HTTP request. Applies two detection layers in sequence:

- **Regex sub-engine** — deterministic, compiled patterns for Victorian-specific identifiers: Driver Licence numbers (9-digit numeric and alpha-numeric variants), standard plate formats (`1AA-2BB`, `AAA-111`), and custom plate patterns
- **SpaCy NER sub-engine** — local Named Entity Recognition for `PERSON`, `GPE` (locations), `ORG`, and `DATE` entities using `en_core_web_sm`, which runs entirely within the server process

Redaction runs in the route handler before `litellm.acompletion()` is called, mutating the Python message list in local RAM. Because LiteLLM's HTTPX client reads from this same list when constructing the outbound request, the raw PII value is overwritten before any network packet is assembled. This is a structural guarantee enforced at the route layer, not a best-effort filter.

**The tradeoff accepted:**  
SpaCy `en_core_web_sm` adds approximately 80–150ms of latency per request. A larger model (`en_core_web_lg`) would improve NER accuracy but add 300–500ms and significant memory overhead. The small model is the correct tradeoff for a developer sandbox where compliance certainty matters more than throughput, and latency is acceptable.

---

### Priority 2 — Compliance-First Audit Schema (The Proof of Enforcement)

**Why this is second:**  
The redaction happening is not sufficient for a regulated environment. The redaction must be *provable* to government auditors and joint venture operators. An immutable, queryable record of every request — what was flagged, what model was used, how many tokens were consumed — is the difference between a compliant system and a system that claims to be compliant.

**What it does:**  
Every request writes an asynchronous audit record via FastAPI's `BackgroundTasks` — the write never blocks the proxy cycle. The schema is designed around two principles: proving enforcement without storing evidence of the violation.

```
audit_logs
├── id                UUID PRIMARY KEY
├── developer_id      VARCHAR(50)     — which team or engineer
├── model_requested   VARCHAR(100)    — gpt-4o, claude-3-5-sonnet, etc.
├── input_tokens      INTEGER         — token count of the REDACTED prompt
├── output_tokens     INTEGER         — token count of the response
├── pii_detected      BOOLEAN         — was any PII intercepted?
├── redacted_types    VARCHAR(255)    — e.g. "VIC_DL,PERSON,ADDRESS"
└── timestamp         DATETIME        — ISO 8601
```

**The critical design decision — what is NOT stored:**  
The raw prompt is never written to the database. Storing it would create a secondary log of citizen data, which would itself violate the privacy provisions the gateway is designed to enforce. `redacted_types` stores *what kind* of data was found, not the data itself. This provides auditors with proof of enforcement — "PII was detected and redacted on this request at this time" — without creating a compliance liability in the audit store.

**Strategic alignment:**  
`pii_detected` and `redacted_types` together enable a Grafana dashboard showing: what percentage of LLM traffic contains citizen data attempts, which PII types appear most frequently, and which teams or developer IDs are most likely to send raw sensitive data. This gives VicRoads' compliance function an active monitoring capability, not just a historical log.

---

### Priority 3 — Drop-In SDK Compatibility (The Adoption Guarantee)

**Why this is third:**  
A compliant gateway that developers route around is not a solution. The single biggest risk to any internal security tool is that developers find it inconvenient and bypass it. Drop-in compatibility eliminates that risk by making the secure path identical in effort to the insecure path.

**What it does:**  
The gateway exposes `POST /v1/chat/completions` with a request and response schema that is byte-for-byte compatible with the OpenAI API specification. A developer using the `openai` Python SDK changes exactly one line:

```python
# Before — direct public API call
client = openai.OpenAI(api_key="sk-...")

# After — routed through the secure gateway
client = openai.OpenAI(
    api_key="dev-internal-token",
    base_url="http://vicroads-ai-gateway.internal/v1"
)
```

The Anthropic SDK is similarly supported via LiteLLM's protocol translation layer. No other change is required. Streaming, function calling, and multi-turn conversations all work identically.

**The tradeoff accepted:**  
Maintaining OpenAI API schema compatibility means the gateway is coupled to OpenAI's API versioning. If OpenAI releases breaking changes to `/v1/chat/completions`, the gateway must be updated. This is an acceptable ongoing maintenance cost given that LiteLLM abstracts most of this complexity and updates its compatibility layer independently.

---

## 3. System Architecture

### 3.1 Component Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        DEVELOPER WORKFLOW                               │
│                                                                         │
│   git commit  →  pre-commit hooks  →  ruff · mypy · pytest             │
│   git push    →  GitHub Actions CI →  lint · unit · integration · cov  │
│   PR merged   →  CD pipeline       →  Docker build · staging deploy    │
│                                                                         │
│   openai.OpenAI(base_url="http://vicroads-ai-gateway.internal/v1")      │
│   ← one-line change — all existing SDK calls work unchanged             │
└──────────────────────────────────┬──────────────────────────────────────┘
                                   │  HTTP POST /v1/chat/completions
                                   │  X-Developer-Token: dev-xxxx
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    FASTAPI GUARDRAIL PROXY  (app/)                      │
│                                                                         │
│   POST /v1/chat/completions   POST /v1/messages   GET /health           │
│   GET  /metrics  ← Prometheus scrape                                    │
│                                                                         │
│   ① Auth          validate X-Developer-Token prefix                    │
│   ② Preflight     token count vs llm_max_tokens                        │
│   ③ Budget        daily spend check per developer_id                   │
│   ④ PII Redact    vicroads_guardrails.redactor  (in local RAM)         │
│   ⑤ LLM Forward  litellm.acompletion  (timeout + fallback chain)      │
│   ⑥ Cost Ledger   estimate_cost → update daily spend                  │
│   ⑦ Audit         log_request (stdout) + enqueue write_audit (arq)    │
└──────────┬───────────────────────────────────┬──────────────────────────┘
           │                                   │
           │ ④ redact_messages()               │ ⑦ arq.enqueue(write_audit)
           ▼                                   ▼
┌──────────────────────────┐       ┌───────────────────────────────────────┐
│  vicroads_guardrails/    │       │   TASK QUEUE                          │
│                          │       │                                       │
│  patterns.py             │       │   Redis  ← crash-safe task store     │
│    VIC_DL  \d{9}     │       │   arq worker process                 │
│    VIC_DL  [A-Z]\d{8}    │       │     → write_audit(AuditRecord)       │
│    AU_PHONE  04xx...      │       │     → retry on DB failure            │
│    MEDICARE  [2-6]\d{9}  │       └───────────────────┬───────────────────┘
│    EMAIL · ADDRESS        │                           │
│                          │                           │ persists to
│  redactor.py             │                           ▼
│    Pass 1 — Regex        │       ┌───────────────────────────────────────┐
│    Pass 2 — SpaCy NER    │       │   STORAGE LAYER                       │
│      PERSON → [NAME]     │       │                                       │
│      GPE    → [LOCATION] │       │   PostgreSQL  audit_logs table        │
│      ORG    → [ORG]      │       │     request_id · developer_id · model │
│      DATE * → [DATE]     │       │     pii_detected · redacted_types     │
│      * skip bare digits  │       │     tokens · cost_usd · latency_ms   │
│                          │       │     ← no raw PII ever written         │
│  auditor.py              │       │                                       │
│    AuditRecord (Pydantic)│       │   Redis  daily spend per developer    │
│    write_audit (async)   │       └───────────────────┬───────────────────┘
│                          │                           │
│  logger.py               │                           │ queried by
│    JSON → stdout         │                           ▼
│    JSON → Splunk HEC     │       ┌───────────────────────────────────────┐
└──────────────────────────┘       │   OBSERVABILITY LAYER                 │
           │                       │                                       │
           │ clean redacted        │   Prometheus  scrapes /metrics        │
           │ payload only          │     pii_interceptions_total           │
           ▼                       │     request_latency_seconds{p50,p99}  │
┌──────────────────────────┐       │     token_usage_total{model}          │
│  UPSTREAM LLM PROVIDERS  │       │                                       │
│                          │       │   Grafana  dashboards                 │
│  OpenRouter / OpenAI     │       │     PII detection rate (compliance)   │
│  Anthropic               │       │     Cost per developer (governance)   │
│  AWS Bedrock             │       │     Latency per model (performance)   │
│                          │       │     sources: PostgreSQL + Prometheus  │
│  ← never see raw PII     │       │                                       │
└──────────────────────────┘       │   Splunk  indexes JSON audit logs     │
                                   │     search PII attempts by developer  │
                                   │     cost spike alerting               │
                                   └───────────────────────────────────────┘
```

> `DATE` entities that are bare digit strings (e.g. `12345678`) are skipped —
> SpaCy false-positives on numeric IDs. Real dates contain letters or separators
> (`Jan 2024`, `15/01/2024`).

### 3.2 The `vicroads_guardrails` Package Structure

```
vicroads_guardrails/
├── __init__.py
├── redactor.py          ← Core interception logic (called before acompletion)
│     RegexRedactor      — Victorian-specific compiled patterns
│     SpaCyNERRedactor   — Local NER, en_core_web_sm
│     Redactor           — Orchestrates both, returns RedactionResult
│
├── auditor.py           ← Compliance schema (AuditRecord Pydantic model)
│     AuditRecord        — Pydantic schema matching audit_logs table
│     AuditWriter        — SQLAlchemy async write via BackgroundTasks
│
├── patterns.py          ← Victorian PII regex definitions (documented)
│     VIC_DRIVER_LICENCE — 9-digit numeric: \b\d{9}\b
│     VIC_PLATE_STANDARD — [0-9][A-Z]{2}[\-]?[0-9][A-Z]{2}
│     VIC_PLATE_CUSTOM   — \b[A-Z]{2,8}\b (with context filtering)
│     PHONE_AU           — Standard Australian mobile/landline
│
└── tests/
      test_redactor.py       — 27 unit tests per pattern, per entity type (pass/fail)
      test_pii_guarantee.py  — 15 E2E compliance guarantee tests (PII never reaches LLM)
      test_auditor.py        — 13 audit record persistence tests

benchmarks/
├── pii_corpus.py            ← Labelled dataset — true positives + true negatives per entity
│     VIC_DL corpus          — valid DL numbers + 9-digit non-DL strings (refs, ABNs)
│     MEDICARE corpus        — valid AU Medicare + structurally similar non-Medicare digits
│     AU_PHONE corpus        — valid AU mobile/landline + digit strings that must not match
│     EMAIL, ADDRESS, PERSON — positive + negative examples per type
│
├── test_pii_accuracy.py     ← Precision / Recall / F1 benchmark runner
│     runs corpus through _redact_text(), counts TP/FP/FN per entity type
│     outputs: ACCURACY_REPORT.md
│
└── ACCURACY_REPORT.md       ← Generated report committed to repo
      | Entity   | Precision | Recall | F1   |
      | VIC_DL   | 1.000     | 1.000  | 1.00 |  ← target
      | MEDICARE | —         | —      | —    |
      | ...
```

---

## 4. Research: Tradeoffs Evaluated

### 4.1 Build from scratch vs. extend LiteLLM

| Dimension | Build from scratch | Extend LiteLLM |
|---|---|---|
| Provider routing | Must implement per provider | Free — 100+ providers |
| Streaming support | Complex, weeks of work | Free |
| Token counting | Must implement per model | Built-in callbacks |
| Retry / fallback logic | Must implement | Built-in |
| Victorian PII redaction | Must implement | Must implement |
| Audit schema | Must implement | Must implement |
| Maintenance burden | High — own every layer | Low — own compliance layer only |
| Differentiation | Indistinguishable from existing proxies | Clear — custom compliance package |

**Decision: Extend LiteLLM.** The custom layer (`vicroads_guardrails`) is where the genuine value and differentiation lives. Rebuilding what LiteLLM already does correctly adds risk and maintenance burden without adding compliance value.

### 4.2 Local NER vs. cloud NER

| Dimension | SpaCy local (`en_core_web_sm`) | Cloud NER (AWS Comprehend, Azure Text Analytics) |
|---|---|---|
| Data leaves network? | Never | Yes — violates the core requirement |
| Latency | 80–150ms | 200–400ms + network |
| Accuracy (PERSON, GPE) | Good | Excellent |
| Cost | Free | Per-request pricing |
| Compliance risk | None | Sends text to third party |

**Decision: SpaCy local, unconditionally.** Sending text to a cloud NER service to detect PII before sending it to an LLM defeats the purpose. The compliance requirement is that citizen data does not leave the local network. Cloud NER violates that requirement.

### 4.3 `en_core_web_sm` vs. `en_core_web_lg`

| Dimension | `en_core_web_sm` (12MB) | `en_core_web_lg` (560MB) |
|---|---|---|
| Latency per request | 80–150ms | 300–500ms |
| NER accuracy | Good — sufficient for names, locations | Excellent |
| Memory footprint | Minimal | Significant for a proxy service |
| False negative risk | Low for structured PII; moderate for ambiguous names | Lower |

**Decision: `en_core_web_sm`.** The regex engine catches structured Victorian identifiers (licences, plates) with 100% determinism. SpaCy handles unstructured entities (names, addresses). The small model's accuracy is sufficient for the unstructured layer, and the latency cost of the large model is unacceptable for a developer sandbox.

### 4.4 SQLite vs. PostgreSQL for audit logs

| Dimension | SQLite | PostgreSQL |
|---|---|---|
| Local dev setup | Zero-config | Requires Docker or install |
| Production readiness | Limited concurrency | Production-grade |
| Compliance auditability | Sufficient for MVP | Required for production |

**Decision: SQLite for local development, PostgreSQL for production.** The schema is identical — SQLAlchemy abstracts the difference. Developers can run the gateway locally with no infrastructure dependencies. Production deployment uses PostgreSQL via RDS.

### 4.5 LiteLLM Presidio integration vs. purpose-built `vicroads_guardrails` package

LiteLLM ships a first-party [Microsoft Presidio](https://microsoft.github.io/presidio/) integration that can automatically mask PII in requests. Understanding why we did not use it is important context for anyone maintaining this codebase.

**The Presidio integration is Proxy-only — it does not apply to this architecture**

The LiteLLM Presidio hooks (`mode: "pre_call"`) only fire when running LiteLLM as a standalone Proxy Server process:

```bash
litellm --config config.yaml --port 4000   # separate process, separate container
```

These hooks — `async_pre_call_hook`, `async_post_call_success_hook` — are documented as **Proxy-only**. They do **not** fire when calling `litellm.acompletion()` directly from Python, which is how this gateway is built. Our FastAPI app IS the gateway; it calls the LiteLLM SDK directly. Adopting the Presidio integration would require restructuring from:

```
User → FastAPI gateway  →  litellm.acompletion()  →  LLM provider
```

to:

```
User → FastAPI gateway  →  LiteLLM Proxy  →  Presidio containers  →  LLM provider
```

That adds two extra network hops and three new Docker services (`litellm-proxy`, `presidio-analyzer`, `presidio-anonymizer`) for a redaction capability we already own in-process.

**Even with Presidio deployed, VIC-specific PII requires custom recognizers**

Presidio ships global recognizers tuned to international and US data formats — not Australian jurisdiction-specific identifiers:

| PII Type | Presidio built-in | `vicroads_guardrails` |
|---|---|---|
| Victorian Driver Licence | ❌ No `AU_DRIVER_LICENSE`. `US_DRIVER_LICENSE` exists but targets US formats and **false-positives** on 9-digit VIC DL strings (Presidio's own docs warn of this for short alphanumeric strings) | ✅ `r"\b(?:\d{9}|[A-Z]\d{8}|\d{8}[A-Z])\b"` — deterministic, zero false-positives |
| Australian Medicare | ❌ No `AU_MEDICARE` entity type | ✅ `r"\b[2-6]\d{9}\b"` with leading-digit constraint |
| Australian phone numbers | Partial — generic `PHONE_NUMBER` does not reliably match `04xx xxx xxx` mobile or `(0x) xxxx xxxx` landline with AU dialling conventions | ✅ AU-specific multi-pattern with negative lookbehind |
| VIC number plates | ❌ No recognizer | ✅ Standard + custom plate formats |
| Person names | ✅ ML-based, good recall | ✅ SpaCy `en_core_web_sm` — comparable quality, fully in-process |
| Email addresses | ✅ `EMAIL_ADDRESS` | ✅ Regex |

Even if Presidio were running, every VIC-specific pattern would still need to be supplied as a `presidio_ad_hoc_recognizers.json` custom recognizer file — which is exactly what `patterns.py` already is. Presidio provides the container infrastructure; we still write the rules.

The LiteLLM Presidio tutorial acknowledges this gap directly under *"Custom Entity Recognition"*: domain-specific identifiers (employee IDs, internal codes, government identifiers) must be written as custom patterns. Victorian government identifiers fall precisely into this category.

**Why SpaCy in-process rather than Presidio for name detection**

Presidio's analyzer does use a more capable NLP model for person names than `en_core_web_sm`. However, running Presidio as a sidecar means:

- An HTTP call to the `presidio-analyzer` container on every request — adding 50–200ms inside the redaction path
- Text leaving the Python process boundary, even to a localhost sidecar — the data custody requirement (§4.2) requires text to remain within the server process
- An additional infrastructure dependency that must be healthy for every request

SpaCy runs entirely in-process. The latency cost (~80–150ms) is accepted as a tradeoff in §4.3. Replacing SpaCy with Presidio is a valid upgrade path if name-detection accuracy gaps emerge in production; it is not the right first choice.

**Decision: purpose-built `vicroads_guardrails` package, direct SDK.**  
`redact_messages()` called before `litellm.acompletion()` is not a workaround — it is the correct architecture for an embedded gateway that must enforce jurisdiction-specific compliance rules without external dependencies. The Presidio path would add infrastructure overhead without removing the need to write a single pattern in `patterns.py`.

### 4.6 PII Detection Accuracy — Benchmark Design

`test_redactor.py` proves that specific hand-crafted inputs are redacted correctly. It does not measure detection rates across a representative population of real-world inputs. The claims in §4.5 and §5 Finding 4 require empirical evidence:

- §4.5 states VIC DL detection is "deterministic, zero false-positives" — this is currently an assertion, not a measurement
- §5 Finding 4 states generic proxies cannot handle Victorian identifiers — this needs a side-by-side recall comparison to be citable

**What a unit test proves vs. what a benchmark proves:**

| | `test_redactor.py` | `benchmarks/test_pii_accuracy.py` |
|---|---|---|
| Purpose | Does this exact input get redacted? | What fraction of real inputs are handled correctly? |
| Failures caught | Broken regex, wrong replacement token | False negatives (PII missed), false positives (non-PII flagged) |
| Corpus | Hand-picked to pass | Adversarial negatives designed to probe false-positive rate |
| Output | Pass / fail | Precision / Recall / F1 per entity type |

**Corpus design — the critical piece is the negative set:**

Each entity type needs two sides of the corpus:

| Entity | True positive examples | True negative examples (must NOT be redacted) |
|---|---|---|
| `VIC_DL` | `123456789`, `A12345678`, `12345678Z` | 9-digit ABN fragments, postcodes (`3000`), reference IDs (`REF-123456789`) |
| `MEDICARE` | `2123456701`, `6987654321` | 10-digit phone numbers starting with `0`, BSB + account combos |
| `AU_PHONE` | `0412 345 678`, `(03) 9000 1234` | Fax numbers in text, international numbers `+44 7700...` |
| `EMAIL` | `jane@example.com` | Malformed addresses `user@`, partial domains |
| `ADDRESS` | `42 Collins Street` | Business names containing street words `"Road Safety Inc"` |
| `PERSON` (SpaCy) | `"John Smith submitted"` | Single common words `"Victoria"`, organisation names |

**Expected output table** (`benchmarks/ACCURACY_REPORT.md`):

| Entity type | TP | FP | FN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|
| VIC_DL | — | — | — | target: 1.00 | target: 1.00 | target: 1.00 |
| MEDICARE | — | — | — | — | — | — |
| AU_PHONE | — | — | — | — | — | — |
| EMAIL | — | — | — | — | — | — |
| ADDRESS | — | — | — | — | — | — |
| PERSON (SpaCy NER) | — | — | — | expected lower | expected lower | — |

SpaCy NER for `PERSON` is expected to have lower recall than the regex patterns — the benchmark quantifies the gap and determines whether it is acceptable or whether a larger model is warranted.

**What the benchmark validates beyond the existing test suite:**

1. The "zero false-positives" claim for `VIC_DL` becomes `Precision(VIC_DL) = 1.0` — verifiable and auditable
2. `Recall(PERSON)` quantifies what §6 acknowledges: "SpaCy NER engine will miss edge cases"
3. Provides evidence for §5 Finding 4: comparing recall on VIC DL corpus between our regex and Presidio's `US_DRIVER_LICENSE` recogniser (which would score near 0 on VIC format)

---

## 5. Key Findings

**Finding 1 — The structural guarantee is stronger than a test guarantee.**  
Because `redact_messages()` mutates the Python message list in local RAM before `litellm.acompletion()` is called, it is structurally impossible for a raw PII value to appear in the outbound network packet — LiteLLM's HTTPX client reads from this same list when constructing the request. This is not "we tested it and it didn't leak" — it is "the architecture prevents the leak at the object level." The compliance test suite (`test_pii_guarantee.py`) proves this by capturing the exact `messages` argument passed to the mocked `acompletion()` and asserting no raw PII appears in it.

**Finding 2 — The audit schema must not store what it is protecting against.**  
Storing the raw prompt in the audit log would create a secondary repository of citizen data, which would itself require the same data custody controls as the primary systems. `redacted_types` provides auditors with proof of enforcement without this liability. This is the correct design for a regulated environment.

**Finding 3 — Developer adoption is a compliance requirement, not a UX preference.**  
A gateway that developers bypass provides zero compliance value. Drop-in SDK compatibility removes the friction cost of adoption to near zero. In a regulated environment, making the compliant path the path of least resistance is not a feature — it is a prerequisite for the system to function as intended.

**Finding 4 — Open-source proxies (LiteLLM, Portkey, Kong AI Gateway) do not solve this problem.**  
Generic proxies provide PII detection as an optional plugin using generic patterns (credit cards, US SSNs, email addresses). They do not know what a Victorian Driver Licence number looks like. They do not know VicRoads plate formats. They cannot be configured to satisfy the specific data custody obligations of the VicRoads joint venture agreement. They are the right foundation. They are not the solution.

---

## 6. What This Project Is Not

This document should be explicit about scope boundaries.

This gateway is **not** a production security system. It is an AI enablement sandbox — a controlled environment where developers can experiment with LLMs safely. It does not replace VicRoads' existing data governance frameworks, security controls, or privacy impact assessments. It is a developer tool that enforces the compliance baseline so that developers do not have to think about it on every request.

It is also **not** a claim that all PII will be detected. The regex engine is deterministic for known Victorian formats. The SpaCy NER engine will miss edge cases — unusual name formats, novel address structures, PII embedded in code or structured data. The runbook is explicit about this: the gateway is a guardrail, not a guarantee that all sensitive content is removed. Developers remain responsible for not including citizen data in prompts unnecessarily.

---

## 7. What Gets Built — Summary

| Component | Status | Layer | Location |
|---|---|---|---|
| FastAPI proxy app — auth, budget, PII, audit | ✅ Done | Infrastructure | `app/` |
| `vicroads_guardrails` package — patterns, redactor, auditor | ✅ Done | Compliance | `vicroads_guardrails/` |
| Audit schema + async DB writer | ✅ Done | Compliance | `app/database.py`, `app/models/` |
| Compliance test suite — 55 tests (unit + E2E) | ✅ Done | Quality | `tests/` |
| CI pipeline — lint, type-check, pytest on push | ✅ Done | Quality | `.github/workflows/compliance.yml` |
| OpenRouter integration — API key propagation, `OR_SITE_URL` | ✅ Done | Infrastructure | `app/main.py`, `app/settings.py` |
| PII detection accuracy benchmark — corpus + precision/recall/F1 | 🔲 Next | Quality | `benchmarks/` |
| Prometheus metrics endpoint — `GET /metrics` | 🔲 Planned | Observability | `app/api/route_metrics.py` |
| Grafana dashboard — PII rate, cost, latency | 🔲 Planned | Observability | `docker-compose.yml` |
| `DEVELOPER_RUNBOOK.md` (RLS-AI-001) | 🔲 Planned | Enablement | `DEVELOPER_RUNBOOK.md` |
| MCP server wrapper | 🔲 Planned | Platform | `vicroads_guardrails/mcp_server.py` |