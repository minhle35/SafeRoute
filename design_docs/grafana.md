# Grafana — Observability Dashboard

## Role

Grafana is the visualisation layer over Prometheus. It turns raw PromQL time-series into dashboards that a non-technical stakeholder can read. The SafeRoute dashboard (`saferoute-v1`) surfaces four operational concerns — compliance, performance, governance, and capacity — in a single view.

---

## Dashboard Panels

**File:** `grafana/dashboards/saferoute.json`

| Panel | Type | PromQL | Answers |
|---|---|---|---|
| PII Detection Rate | Time series | `sum(rate(pii_interceptions_total[5m]))` | Are developers leaking PII right now? |
| PII by Entity Type | Pie chart | `sum by(entity_type)(increase(...[1h]))` | Which PII types are most commonly sent? |
| Request Latency P95 | Time series | `histogram_quantile(0.95, ...)` | Are we meeting latency SLOs? |
| Cost per Developer | Bar gauge | `sum by(developer_id)(increase(...[24h]))` | Who is approaching their $5/day budget? |
| Token Burn Rate | Time series | `sum by(direction)(rate(token_usage_total[5m]))` | Are we approaching capacity limits? |

The Cost panel has threshold markers at **$3.50 (yellow)** and **$5.00 (red)** matching the in-app `DAILY_BUDGET_USD` enforcement limit.

---

## Auto-Provisioning (Zero Click Setup)

Grafana loads the dashboard and datasource automatically on first start — no manual import required. This is done via volume-mounted provisioning files:

```
grafana/
├── provisioning/
│   ├── datasources/
│   │   └── prometheus.yml   ← registers Prometheus as default datasource
│   └── dashboards/
│       └── dashboard.yml    ← tells Grafana where to find dashboard JSON
└── dashboards/
    └── saferoute.json       ← the actual dashboard definition
```

`docker-compose.yml` mounts these directories into the Grafana container:

```yaml
volumes:
  - ./grafana/provisioning:/etc/grafana/provisioning
  - ./grafana/dashboards:/var/lib/grafana/dashboards
```

**Datasource config** (`provisioning/datasources/prometheus.yml`):
```yaml
datasources:
  - name: Prometheus
    type: prometheus
    url: http://prometheus:9090
    isDefault: true
```

**Dashboard provider config** (`provisioning/dashboards/dashboard.yml`):
```yaml
providers:
  - name: SafeRoute
    type: file
    updateIntervalSeconds: 30
    options:
      path: /var/lib/grafana/dashboards
```

---

## Accessing the Dashboard

After `docker compose up`:

| URL | Description |
|---|---|
| `http://localhost:3000` | Grafana login (anonymous access enabled) |
| `http://localhost:3000/d/saferoute-v1/` | Direct link to SafeRoute dashboard |
| `http://localhost:9090` | Prometheus UI (raw metrics browser) |

Anonymous access is enabled in `docker-compose.yml` via environment variables:

```yaml
GF_AUTH_ANONYMOUS_ENABLED: "true"
GF_AUTH_ANONYMOUS_ORG_ROLE: "Viewer"
```

This is appropriate for local development. In production, disable anonymous access and configure SSO.

---

## Why Grafana over Splunk for this use case?

| Factor | Grafana + Prometheus | Splunk |
|---|---|---|
| Setup complexity | Docker Compose, zero config | Agent install, index config |
| Time-series queries | PromQL (purpose-built) | SPL (general purpose) |
| Real-time refresh | 15 s (native) | Near-real-time (licensed) |
| Cost | Open source | Enterprise licensed |
| Best for | Numeric metrics, operational dashboards | Log search, SIEM, compliance archiving |

SafeRoute uses Grafana for operational metrics dashboards. Structured JSON logs (stdout) are the feed for any future Splunk integration.
