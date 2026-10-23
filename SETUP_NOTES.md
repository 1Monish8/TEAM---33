# Verified environment (23 Oct)

## Start the demo
NEVER `make start` -- its --force-recreate flag breaks the startup.

alias dc='docker compose --env-file .env --env-file .env.override -f compose.yaml -f compose.full.yaml -f compose.observability.yaml -f compose.extras.yaml'
dc up -d --remove-orphans

## Jaeger  http://localhost:8080/jaeger/ui/api/v3
- /services
- /traces?query.service_name=X&query.start_time_min=<RFC3339>&query.start_time_max=<RFC3339>&query.num_traces=N
- /traces/<trace_id>

Gotchas:
- snake_case params ONLY. camelCase is silently ignored and returns the WRONG service.
- The old /api/traces path is gone (404). Jaeger 2.x uses /api/v3.
- Response is OTLP: resourceSpans[].scopeSpans[].spans[]
- Timestamps are NANOseconds. Divide by 1_000_000 for ms.
- status.code == 2 means error. status.message holds the cause text.
- Attribute values are typed wrappers: {"stringValue": ...}, {"intValue": "200"} (a STRING).
- The Jaeger UI's red bars are unreliable. status.code is not.

## Prometheus  http://localhost:9090
- traces_span_metrics_calls_total{service_name, span_name, span_kind, status_code}
- status_code values: STATUS_CODE_ERROR / STATUS_CODE_OK / STATUS_CODE_UNSET
- traces_span_metrics_duration_milliseconds_bucket
- container_uptime_seconds, container_memory_percent_ratio, container_cpu_utilization_ratio
- Scrape interval is 60s. Wait 2 minutes after injecting a fault.

## OpenSearch
Port is ephemeral, changes every restart:
  export OS_PORT=$(dc port opensearch 9200 | cut -d: -f2)
- index: otel-logs-YYYY-MM-DD
- fields: body / resource.service.name / @timestamp / severity.text

## KEY FINDING
With paymentFailure on, FIVE services report errors:
frontend-proxy, frontend, load-generator, checkout, payment.
Only payment is broken.
checkout even has a span named oteldemo.PaymentService/Charge carrying the same
error message -- that is its client-side span, not the fault.

The root cause is the DEEPEST failing span whose own children did not fail.
Metrics alone cannot tell these apart: all five showed an identical 0.0999 error rate.
