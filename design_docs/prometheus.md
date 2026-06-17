# Prometheus — Metrics Design

## Role

Prometheus scrapes numeric time-series from the gateway's `/metrics` endpoint every 15 seconds. These metrics answer operational questions that structured logs cannot: rate-of-change, percentile latency, and cumulative cost — all queryable without parsing JSON.

---

## Metrics Defined

**File:** `app/api/route_metrics.py`

### `pii_interceptions_total` — Counter

```
Labels: entity_type (e.g. "REDACTED_VIC_DL", "REDACTED_EMAIL")
```

Incremented once per redacted PII type per request. Use for:
- `rate(pii_interceptions_total[5m])` — real-time compliance rate
- `sum by(entity_type)(increase(...[1h]))` — which PII types developers most commonly leak

### `request_latency_seconds` — Histogram

```
Labels: model
Buckets: 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0 seconds
```

End-to-end wall-clock time from request receipt to response sent. Use for:
- `histogram_quantile(0.95, ...)` — P95 latency SLO tracking
- Baseline includes SpaCy's 80–150 ms redaction pass — factor this into model comparisons

### `token_usage_total` — Counter

```
Labels: model, direction ("input" | "output")
```

Cumulative token consumption. Use for:
- `rate(token_usage_total[5m])` — token burn rate (capacity planning)
- Comparing input vs output ratio by model

### `request_cost_usd_total` — Counter

```
Labels: developer_id
```

Cumulative USD spend per developer. Use for:
- `increase(request_cost_usd_total[24h])` — daily spend per developer (governance)
- Visualised in Grafana with $3.50 warning / $5.00 critical threshold markers

---

## Scrape Configuration

**File:** `prometheus.yml`

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: saferoute
    static_configs:
      - targets: ["app:8000"]   # Docker service name
    metrics_path: /metrics
```

The `/metrics` endpoint is served by `prometheus-client` via FastAPI:

```python
@app.get("/metrics", include_in_schema=False)
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
```

`include_in_schema=False` hides it from the OpenAPI docs — it is an ops endpoint, not part of the developer-facing API.

---

## Why Prometheus over logging for metrics?

Structured JSON logs contain the same raw numbers, but to answer "what is the P95 latency for Llama over the past hour?" you would need to:
1. Export logs to an aggregation system
2. Parse each JSON line
3. Compute the histogram manually

Prometheus makes this a single PromQL query:
```
histogram_quantile(0.95, sum by(le, model)(rate(request_latency_seconds_bucket[1h])))
```

Prometheus is the right tool for time-series numeric data; structured logs are the right tool for event records. Both run concurrently in SafeRoute.
