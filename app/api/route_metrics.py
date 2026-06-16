"""
Prometheus metric singletons for the SafeRoute gateway.

Module-level objects — import and call directly, no instantiation needed.
Scraped by Prometheus at GET /metrics (see app/main.py).

Four metrics cover the four Grafana panels described in README §3.1:
  pii_interceptions_total   → PII detection rate / type breakdown (compliance)
  request_latency_seconds   → P95 latency per model (performance)
  token_usage_total         → Token burn rate (capacity)
  request_cost_usd_total    → Cost per developer (governance)
"""

from prometheus_client import Counter, Histogram

pii_interceptions_total = Counter(
    "pii_interceptions_total",
    "PII entity types intercepted before LLM call",
    ["entity_type"],
)

request_latency_seconds = Histogram(
    "request_latency_seconds",
    "End-to-end request latency including SpaCy redaction",
    ["model"],
    buckets=[0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0],
)

token_usage_total = Counter(
    "token_usage_total",
    "Tokens consumed by direction",
    ["model", "direction"],  # direction = "input" | "output"
)
request_cost_usd_total = Counter(
    "request_cost_usd_total",
    "Estimated cost in USD per developer",
    ["developer_id"],
)
