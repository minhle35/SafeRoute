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

The hook fires inside `async_pre_call_hook` — a LiteLLM middleware interface that mutates the Python dictionary object in local RAM. Because LiteLLM's HTTPX client reads from this same dictionary when constructing the outbound request, the raw PII value is overwritten before any network packet is assembled. This is a structural guarantee, not a best-effort filter.

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
│                        DEVELOPER ENVIRONMENT                            │
│                                                                         │
│   openai.OpenAI(base_url="http://vicroads-ai-gateway.internal/v1")      │
│   anthropic.Anthropic(base_url="...")                                   │
│                                                                         │
│   ← No code change beyond base_url. All existing SDK calls work.        │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼ Standard OpenAI/Anthropic payload
┌─────────────────────────────────────────────────────────────────────────┐
│                    FASTAPI APPLICATION LAYER                            │
│                                                                         │
│   POST /v1/chat/completions                                             │
│   POST /v1/messages                                                     │
│   GET  /health                                                          │
│   GET  /metrics  (Prometheus scrape endpoint)                           │
│                                                                         │
│   Auth middleware → validates developer API key                         │
│   Rate limiting  → per developer_id token bucket                        │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼ Validated payload enters LiteLLM
┌─────────────────────────────────────────────────────────────────────────┐
│                         LITELLM PROXY ENGINE                            │
│                                                                         │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │              async_pre_call_hook (FIRES FIRST)                  │   │
│   │                                                                 │   │
│   │   vicroads_guardrails.redactor.redact(data["messages"])         │   │
│   │         │                                                       │   │
│   │         ├── RegexRedactor                                       │   │
│   │         │     VIC Driver Licence: \b\d{9}\b and variants        │   │
│   │         │     Standard plates:   [0-9][A-Z]{2}[0-9][A-Z]{2}    │   │
│   │         │     Custom plates:     [A-Z]{2,8}                     │   │
│   │         │                                                       │   │
│   │         └── SpaCyNERRedactor (en_core_web_sm — LOCAL ONLY)      │   │
│   │               PERSON → [REDACTED_PERSON]                        │   │
│   │               GPE    → [REDACTED_LOCATION]                      │   │
│   │               DATE   → [REDACTED_DATE]                          │   │
│   │                                                                 │   │
│   │   data["messages"] mutated IN LOCAL RAM                         │   │
│   │   ← raw PII value no longer exists in Python process            │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                    │                                    │
│                                    ▼                                    │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │              async_log_success_event (FIRES AFTER)              │   │
│   │                                                                 │   │
│   │   vicroads_guardrails.auditor.write_audit_record(               │   │
│   │       developer_id, model, tokens, pii_detected, redacted_types │   │
│   │   )  → FastAPI BackgroundTask (non-blocking)                    │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                    │                                    │
│   Provider routing: Azure OpenAI · Anthropic · AWS Bedrock · Gemini    │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼ CLEAN, redacted payload only
┌─────────────────────────────────────────────────────────────────────────┐
│                      UPSTREAM LLM PROVIDERS                             │
│                                                                         │
│   Azure OpenAI    api.azure.com         ← gpt-4o, gpt-4o-mini          │
│   Anthropic       api.anthropic.com     ← claude-3-5-sonnet             │
│   AWS Bedrock     bedrock.amazonaws.com ← Titan, Claude on Bedrock      │
│                                                                         │
│   ← These services NEVER receive raw Victorian citizen data.            │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       STORAGE & OBSERVABILITY                           │
│                                                                         │
│   SQLite / PostgreSQL                                                   │
│     audit_logs table (schema above)                                     │
│     ← pii_detected, redacted_types — no raw PII ever written           │
│                                                                         │
│   Prometheus /metrics                                                   │
│     token_usage_total{developer_id, model}                              │
│     pii_interceptions_total{redacted_type}                              │
│     request_latency_seconds{p50, p99}                                   │
│                                                                         │
│   Grafana dashboard                                                     │
│     % of requests with PII detected (compliance health)                 │
│     Token usage per team (cost governance)                              │
│     Latency per model (performance monitoring)                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 3.2 The `vicroads_guardrails` Package Structure

```
vicroads_guardrails/
├── __init__.py
├── redactor.py          ← Core interception logic (async_pre_call_hook)
│     RegexRedactor      — Victorian-specific compiled patterns
│     SpaCyNERRedactor   — Local NER, en_core_web_sm
│     Redactor           — Orchestrates both, returns RedactionResult
│
├── auditor.py           ← Compliance audit writer (async_log_success_event)
│     AuditRecord        — Pydantic schema matching audit_logs table
│     AuditWriter        — SQLAlchemy async write via BackgroundTasks
│
├── patterns.py          ← Victorian PII regex definitions (documented)
│     VIC_DRIVER_LICENCE — 9-digit numeric: \b\d{9}\b
│     VIC_PLATE_STANDARD — [0-9][A-Z]{2}[\-]?[0-9][A-Z]{2}
│     VIC_PLATE_CUSTOM   — \b[A-Z]{2,8}\b (with context filtering)
│     PHONE_AU           — Standard Australian mobile/landline
│
├── mcp_server.py        ← MCP tool exposure (one-day addition)
│     search_with_guardrails(query: str) → GuardrailedResponse
│     ← Enables Claude Code and MCP-compatible agents to invoke safely
│
└── tests/
      test_redactor.py       — Unit tests per pattern, per entity type
      test_pii_guarantee.py  — End-to-end compliance guarantee tests
      test_auditor.py        — Audit record assertions
      test_mcp_server.py     — MCP tool invocation tests
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

---

## 5. Key Findings

**Finding 1 — The structural guarantee is stronger than a test guarantee.**  
Because `async_pre_call_hook` mutates the message dictionary in local Python memory before LiteLLM's HTTPX client constructs the outbound request object, it is structurally impossible for a raw PII value to appear in the network packet. This is not "we tested it and it didn't leak" — it is "the architecture prevents the leak at the object level." The test suite proves the hook fires correctly. The architecture proves that if the hook fires, leakage cannot occur.

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

| Component | Layer | Who builds it | Time |
|---|---|---|---|
| FastAPI proxy app | Infrastructure | `app/` | Phase 1 — 3 days |
| `vicroads_guardrails` package | Compliance | `vicroads_guardrails/` | Phase 2 — 5 days |
| Audit schema + async writer | Compliance | `vicroads_guardrails/auditor.py` | Phase 3 — 2 days |
| Prometheus + Grafana | Observability | `docker-compose.yml` | Phase 3 — 1 day |
| Compliance test suite | Quality | `tests/test_pii_guarantee.py` | Phase 4 — 3 days |
| `pii-leak-check` CI gate | Quality | `.github/workflows/compliance.yml` | Phase 4 — 1 day |
| `DEVELOPER_RUNBOOK.md` (RLS-AI-001) | Enablement | Docs | Phase 4 — 2 days |
| MCP server wrapper | Platform | `vicroads_guardrails/mcp_server.py` | Extension — 1 day |

**Total estimated build time:** 18 days part-time.  
**Core compliance features (Phases 1–2):** 8 days.