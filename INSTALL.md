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
git clone https://github.com/minhle35/SafeRoute.git
cd SafeRoute
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

Starts the FastAPI gateway, Prometheus, and Grafana together. If ports 8000, 9090, or 3000 are already taken by something else on your machine (common when running multiple projects), use the `make up` target instead of `docker compose up` directly — it auto-finds free ports first:

```bash
make up
```

This runs [`scripts/find_ports.sh`](scripts/find_ports.sh), which scans a 50-port window above each default (8000, 9090, 3000), writes the first free port for each into `.env` as `APP_PORT` / `PROMETHEUS_PORT` / `GRAFANA_PORT`, then builds and starts the stack. `docker-compose.yml` reads these via `${APP_PORT:-8000}` substitution, so nothing breaks if you skip this and run `docker compose up --build` directly on a machine with no conflicts.

Check `.env` after `make up` to see which ports were actually assigned:

```bash
grep PORT .env
```

| Service | Default URL | Description |
|---|---|---|
| Gateway API | `http://localhost:8000` | OpenAI-compatible chat endpoint |
| API Docs | `http://localhost:8000/docs` | Interactive Swagger UI |
| Prometheus | `http://localhost:9090` | Raw metrics browser |
| Grafana | `http://localhost:3000` | Pre-built SafeRoute dashboard |

(Substitute the actual assigned ports from `.env` if `make up` picked different ones.)

Direct dashboard link: `http://localhost:<GRAFANA_PORT>/d/saferoute-v1/`

Other Makefile targets:

```bash
make ports     # only resolve free ports and write .env, don't start anything
make down      # stop the stack
make restart   # re-resolve ports and rebuild — use after editing .env or code
make logs      # follow logs for all services
```

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
make down                    # stop containers, keep volumes
docker compose down -v       # stop containers and remove volumes (reset Grafana/Prometheus data)
```

---

## Troubleshooting

**`401 User not found` from OpenRouter**
Your `OPENROUTER_API_KEY` in `.env` is invalid, or you rotated it without restarting. `docker-compose.yml` uses `env_file: .env`, which is only read when a container is *created* — editing `.env` does not propagate to an already-running container. Recreate it: `make restart` (or `docker compose up -d --force-recreate app`).

**SpaCy model not found (`E050`)**
Run `uv sync --all-groups` — the model is a Python wheel and must be installed before the app starts.

**Port already in use**
Run `make up` instead of `docker compose up` directly — it runs [`scripts/find_ports.sh`](scripts/find_ports.sh) first, which finds a free port within 50 of each default and writes it to `.env`. Run `make ports` alone if you just want to see which ports would be assigned without starting anything.

**Grafana dashboard empty**
Navigate directly to `http://localhost:3000/d/saferoute-v1/` — dashboards are not starred by default.
