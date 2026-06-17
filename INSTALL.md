# Installation Guide

Full setup from `git clone` to running tests and reading results.

---

## Prerequisites

| Tool | Version | Install |
|---|---|---|
| Python | 3.12+ | [python.org](https://python.org) |
| uv | latest | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Docker + Docker Compose | 24+ | [docker.com](https://docker.com) |
| Git | any | pre-installed on macOS/Linux |

---

## 1. Clone the Repository

```bash
git clone https://github.com/minhle35/lightLLM.git
cd lightLLM
```

---

## 2. Configure Environment Variables

Copy the template and fill in your OpenRouter API key. Every other field has a working default.

```bash
cp .env.template .env
```

Open `.env` and set:

```
OPENROUTER_API_KEY=<your-key-from-openrouter.ai>
```

Get a free key at **https://openrouter.ai/keys** — no credit card required for free-tier models.

---

## 3. Install Python Dependencies

`uv` reads `pyproject.toml` and installs everything including the SpaCy NER model:

```bash
uv sync --all-groups
```

This installs:
- FastAPI, LiteLLM, pydantic-settings (app dependencies)
- SpaCy + `en_core_web_sm` NER model (~12 MB, downloaded from GitHub)
- pytest, pytest-cov, pytest-asyncio, httpx (dev/test dependencies)

---

## 4. Prepare the Test Environment

No additional setup is needed. Tests use an in-memory SQLite database and a mocked LLM — no external services required.

Verify the install by running the test suite:

```bash
uv run pytest tests/ -v
```

Expected output: all tests green, 55 passed.

---

## 5. Run Tests with Coverage

```bash
uv run pytest tests/ --cov=vicroads_guardrails --cov=app --cov-report=term-missing
```

### Reading the coverage report

```
Name                                          Stmts   Miss  Cover   Missing
---------------------------------------------------------------------------
app/api/route_chat_completion_middleware.py      47      1  97.9%   83
vicroads_guardrails/redactor.py                  47      0 100.0%
...
TOTAL                                           292     15  94.9%
```

- **Stmts** — total executable lines
- **Miss** — lines not executed by any test
- **Cover** — percentage covered
- **Missing** — specific line numbers not reached; check these for untested branches

---

## 6. Run the PII Accuracy Benchmark

The benchmark measures precision/recall/F1 across 103 labelled corpus entries. It is separate from the unit tests.

```bash
# Run as pytest (shows pass/fail per entry)
uv run pytest benchmarks/ -v

# Run as script (writes ACCURACY_REPORT.md with F1 table)
uv run python benchmarks/test_pii_accuracy.py
```

### Reading the accuracy report

Open `benchmarks/ACCURACY_REPORT.md`:

```
| Entity         | TP | FP | FN | TN | Precision | Recall |   F1  |
|----------------|----|----|----|----|-----------|--------|-------|
| MEDICARE       | 10 |  0 |  0 |  5 |   1.000   | 1.000  | 1.000 |
| VIC_DL         | 10 |  0 |  1 |  1 |   1.000   | 0.909  | 0.952 |
| VIC_PLATE      |  8 |  3 |  0 |  1 |   0.727   | 1.000  | 0.842 |
```

- **TP** — correctly detected PII (true positive)
- **FP** — non-PII flagged as PII (false positive) — annotated as known gaps in the corpus
- **FN** — PII missed by the redactor (false negative) — highest risk, investigate these
- **F1** — harmonic mean of precision and recall; 1.0 is perfect

Known FP patterns (e.g. VIC_PLATE matching `AI CD`, `NO GO`) are documented in `benchmarks/pii_corpus.py` as `TN` entries with `known-fp` labels.

---

## 7. Start the Full Stack (Docker)

Starts the FastAPI gateway, Prometheus, and Grafana together:

```bash
docker compose up --build
```

| Service | URL | Description |
|---|---|---|
| Gateway API | `http://localhost:8000` | OpenAI-compatible chat endpoint |
| API Docs | `http://localhost:8000/docs` | Interactive Swagger UI |
| Prometheus | `http://localhost:9090` | Raw metrics browser |
| Grafana | `http://localhost:3000` | Pre-built SafeRoute dashboard |

Direct dashboard link: `http://localhost:3000/d/saferoute-v1/`

### Send a test request

```bash
curl -s http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-Developer-Token: dev-test" \
  -d '{
    "model": "openrouter/meta-llama/llama-3.1-8b-instruct:free",
    "messages": [{"role": "user", "content": "Hello, what is 2+2?"}]
  }' | jq .choices[0].message.content
```

### Test PII redaction

```bash
curl -s http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-Developer-Token: dev-test" \
  -d '{
    "model": "openrouter/meta-llama/llama-3.1-8b-instruct:free",
    "messages": [{"role": "user", "content": "My licence is 123456789 and email is test@example.com"}]
  }'
```

Check Docker logs to confirm redaction occurred:

```bash
docker compose logs app | grep pii_detected
```

---

## 8. Stopping the Stack

```bash
docker compose down          # stop containers, keep volumes
docker compose down -v       # stop containers and remove volumes (reset Grafana/Prometheus data)
```

---

## Troubleshooting

**`401 User not found` from OpenRouter**
Your `OPENROUTER_API_KEY` in `.env` is invalid. Get a new key at openrouter.ai/keys and restart: `docker compose down && docker compose up`.

**SpaCy model not found (`E050`)**
Run `uv sync --all-groups` — the model is a Python wheel and must be installed before the app starts.

**Port already in use**
Change `SERVER_PORT` in `.env` and update the port mapping in `docker-compose.yml` to match.

**Grafana dashboard empty**
Navigate directly to `http://localhost:3000/d/saferoute-v1/` — dashboards are not starred by default.
